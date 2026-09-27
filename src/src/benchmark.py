"""Compare branch predictors on a CSV trace."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from predictors import (
    Branch,
    OneBit,
    StaticNotTaken,
    TwoBit,
    evaluate,
)


def load_trace(path: Path) -> list[Branch]:
    with path.open(newline="") as file:
        reader = csv.DictReader(file)

        if not {"pc", "taken"}.issubset(
            reader.fieldnames or []
        ):
            raise ValueError("Trace needs pc,taken columns")

        branches = []

        for line_number, row in enumerate(
            reader,
            start=2,
        ):
            if row["taken"] not in ("0", "1"):
                raise ValueError(
                    f"line {line_number}: "
                    "taken must be 0 or 1"
                )

            pc = int(row["pc"], 0)

            if pc < 0 or pc % 4:
                raise ValueError(
                    f"line {line_number}: PC must be "
                    "nonnegative and 4-byte aligned"
                )

            branches.append(
                Branch(
                    pc,
                    row["taken"] == "1",
                )
            )

    return branches


def run(
    trace_path: Path,
    output_dir: Path,
    entries: int,
    penalty: int,
) -> list[dict]:
    branches = load_trace(trace_path)

    predictors = [
        StaticNotTaken(),
        OneBit(entries),
        TwoBit(entries),
    ]

    results = [
        evaluate(p, branches, penalty)
        for p in predictors
    ]

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with (output_dir / "summary.csv").open(
        "w",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(results[0]),
        )

        writer.writeheader()
        writer.writerows(results)

    lines = [
        "# Branch predictor benchmark",
        "",
        (
            f"Synthetic trace: `{trace_path}` "
            f"({len(branches)} branch events)"
        ),
        (
            f"Direct-mapped table entries: {entries}; "
            f"illustrative penalty: {penalty} "
            "cycles/misprediction."
        ),
        "",
        (
            "| Predictor | Correct (%) | "
            "Mispredictions | Penalty cycles only |"
        ),
        "| --- | ---: | ---: | ---: |",
    ]

    for row in results:
        lines.append(
            f"| {row['predictor']} "
            f"| {100 * row['accuracy']:.2f} "
            f"| {row['mispredictions']} "
            f"| {row['penalty_cycles_only']} |"
        )

    lines += [
        "",
        (
            "These are synthetic-trace results, "
            "not measured BOOM performance "
            "or full-program runtime."
        ),
        "",
    ]

    (output_dir / "report.md").write_text(
        "\n".join(lines)
    )

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

    except ImportError:
        print(
            "matplotlib not installed; "
            "skipping accuracy.png"
        )

    else:
        fig, ax = plt.subplots(figsize=(7, 4))

        ax.bar(
            [r["predictor"] for r in results],
            [100 * r["accuracy"] for r in results],
        )

        ax.set(
            ylabel="Prediction accuracy (%)",
            ylim=(0, 100),
            title="Synthetic branch trace",
        )

        ax.grid(axis="y", alpha=0.3)

        fig.tight_layout()
        fig.savefig(
            output_dir / "accuracy.png",
            dpi=160,
        )
        plt.close(fig)

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--trace",
        type=Path,
        default=Path("data/example_trace.csv"),
    )

    parser.add_argument(
        "--entries",
        type=int,
        default=16,
    )

    parser.add_argument(
        "--penalty",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--out",
        type=Path,
        default=Path("results"),
    )

    args = parser.parse_args()

    for result in run(
        args.trace,
        args.out,
        args.entries,
        args.penalty,
    ):
        print(
            f"{result['predictor']}: "
            f"{result['accuracy']:.2%} accuracy, "
            f"{result['mispredictions']} misses"
        )
