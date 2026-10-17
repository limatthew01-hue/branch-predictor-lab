"""Benchmark a CSV trace, or sweep five seeded synthetic workloads."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

# Support both documented direct-script use and python -m src.benchmark.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.predictors import StaticNotTaken, OneBit, TwoBit, GShare, evaluate
from src.traces import PATTERNS, generate_workload, load_trace


def predictors(entries: int):
    if entries < 2 or entries & (entries - 1):
        raise ValueError("entries must be a power of two, at least 2")
    return [StaticNotTaken(), OneBit(entries), TwoBit(entries), GShare(entries)]


def trace_digest(branches) -> str:
    payload = "".join(f"{b.pc},{int(b.taken)}\n" for b in branches)
    return hashlib.sha256(payload.encode()).hexdigest()


def compare(branches, entries: int, penalty: int = 5, warmup: int = 0):
    return [dict(entries=entries, **evaluate(p, branches, penalty, warmup))
            for p in predictors(entries)]


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def save_plot(rows: list[dict], output: Path, suite: bool):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"svg.fonttype": "none", "font.size": 10})
    if suite:
        sizes = sorted({r["entries"] for r in rows})
        focus = 64 if 64 in sizes else sizes[-1]
        names = [p.name for p in predictors(64)]
        grid = [[100 * next(r["accuracy"] for r in rows
                            if r["workload"] == pattern and r["entries"] == focus
                            and r["predictor"] == name) for name in names]
                for pattern in PATTERNS]
        fig, ax = plt.subplots(figsize=(8.8, 5.2))
        ax.imshow(grid, cmap="Greens", vmin=0, vmax=100, aspect="auto")
        ax.set_xticks(range(4), ["Static NT", "One bit", "Two bit", "Gshare"])
        ax.set_yticks(range(5), [p.title() for p in PATTERNS])
        ax.tick_params(length=0, pad=10)
        for i, line in enumerate(grid):
            for j, value in enumerate(line):
                ax.text(j, i, f"{value:.1f}%", ha="center", va="center",
                        color="white" if value > 65 else "#333333", fontsize=12)
        ax.set_title("Direction prediction on synthetic traces", loc="left", pad=20)
        row = next(r for r in rows if r["entries"] == focus)
        ax.set_xlabel(f'{focus} entries · {row["warmup_branches"]:,} warm-up branches · '
                      f'{row["branches"]:,} measured branches', labelpad=15)
        fig.tight_layout()
        fig.savefig(output / "accuracy.svg", metadata={"Date": None})
        plt.close(fig)
        fig, ax = plt.subplots(figsize=(8.8, 4.8))
        for name, color in zip(names, ["#9b9b9b", "#78a99a", "#26785e", "#25424a"]):
            subset = [r for r in rows if r["workload"] == "aliasing" and r["predictor"] == name]
            ax.plot([r["entries"] for r in subset], [100*r["accuracy"] for r in subset],
                    "o-", label=name, color=color)
        ax.set(xscale="log", ylim=(-3, 103), xlabel="Table entries (log scale)",
               ylabel="Prediction accuracy (%)", title="Aliasing: branches at 0x1000 and 0x1040")
        ax.grid(alpha=.2); ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False); fig.tight_layout()
        fig.savefig(output / "aliasing.svg", metadata={"Date": None})
        plt.close(fig)
    else:
        fig, ax = plt.subplots(figsize=(8.8, 4.8))
        bars = ax.bar([r["predictor"] for r in rows], [100*r["accuracy"] for r in rows],
                      color=["#aaaaaa", "#9ec3b6", "#26785e", "#25424a"])
        ax.bar_label(bars, fmt="%.2f%%", padding=5)
        ax.set(ylabel="Prediction accuracy (%)", ylim=(0, 110), title="Direction prediction · CSV trace")
        ax.spines[["top", "right"]].set_visible(False); ax.grid(axis="y", alpha=.2)
        ax.set_axisbelow(True); fig.tight_layout()
        fig.savefig(output / "accuracy.svg", metadata={"Date": None})
        plt.close(fig)


def run(trace_path: Path, output_dir: Path, entries: int = 16,
        penalty: int = 5, warmup: int = 0) -> list[dict]:
    branches = load_trace(trace_path)
    rows = compare(branches, entries, penalty, warmup)
    output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(output_dir / "summary.csv", rows)
    metadata = {"input": trace_path.name, "trace_sha256": trace_digest(branches),
                "total_branch_events": len(branches), "entries": entries,
                "penalty_cycles_per_miss": penalty, "warmup_branches": warmup,
                "alignment_bytes": 4, "update": "immediate actual outcome"}
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    lines = ["# CSV trace benchmark", "", f"Input: `{trace_path.name}`; {len(branches):,} events; {entries} entries; {warmup} warm-up events.", "",
             "| Predictor | Accuracy | Misses | State bits | Penalty cycles only |",
             "| --- | ---: | ---: | ---: | ---: |"]
    lines += [f'| {r["predictor"]} | {100*r["accuracy"]:.2f}% | {r["mispredictions"]} | {r["state_bits"]} | {r["penalty_cycles_only"]} |' for r in rows]
    lines += ["", f"Penalty is an illustrative {penalty} cycles per miss, not a measured runtime or CPI.",
              "Equal table entries do not mean equal storage: one-bit uses N bits, two-bit uses 2N, and gshare uses 2N + log2(N).",
              "These results come from the supplied branch trace. No BOOM core, pipeline, cache, or FPGA was measured.", ""]
    (output_dir / "report.md").write_text("\n".join(lines))
    save_plot(rows, output_dir, False)
    return rows


def run_suite(output: Path, events: int = 4096, seed: int = 7,
              warmup: int = 256, sizes=(4, 16, 64, 256), penalty: int = 5):
    if not sizes:
        raise ValueError("provide at least one table size")
    focus = 64 if 64 in sizes else max(sizes)
    rows, digests = [], {}
    for pattern in PATTERNS:
        branches = generate_workload(pattern, events, seed)
        digests[pattern] = trace_digest(branches)
        for size in sizes:
            rows.extend(dict(workload=pattern, **r) for r in compare(branches, size, penalty, warmup))
    output.mkdir(parents=True, exist_ok=True)
    write_csv(output / "summary.csv", rows)
    metadata = {"synthetic": True, "seed": seed, "events_per_workload": events,
                "warmup_branches": warmup, "sizes": list(sizes),
                "history_bits": "log2(entries)", "penalty_cycles_per_miss": penalty,
                "trace_sha256": digests, "update": "predict, then immediate actual-outcome update"}
    (output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    lines = ["# Synthetic workload sweep", "",
             f"Seed {seed}; {events:,} events per workload, first {warmup:,} used only for warm-up.",
             f"Table sizes: {', '.join(map(str, sizes))}. Fresh predictor state for every case.", "",
             f"## Results at {focus} entries", "",
             "| Workload | Static NT | One bit | Two bit | Gshare |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for pattern in PATTERNS:
        selected = [r for r in rows if r["workload"] == pattern and r["entries"] == focus]
        lines.append("| " + pattern + " | " + " | ".join(f'{100*r["accuracy"]:.2f}%' for r in selected) + " |")
    lines += ["", "## What the cases isolate", "",
              "- Loop: 31 taken outcomes followed by one exit; hysteresis avoids relearning after each exit.",
              "- Alternating: one PC alternates N/T; history can distinguish outcomes that a last-outcome bit cannot.",
              "- Correlated: random branch A followed by branch B with the same outcome; A remains unpredictable, while B has useful history.",
              "- Aliasing: PCs 0x1000 and 0x1040 have opposite fixed outcomes. They collide at 4/16 entries and separate at 64/256.",
              "- Random: independent fair outcomes provide a control with no intended learnable pattern.", "",
              "Initial state: one-bit N, two-bit/gshare weakly N, global history zero. History width equals log2(entries).",
              "The predictors have equal entry counts, not equal bit budgets. State excludes tags, targets, control, and SRAM overhead.",
              "These handcrafted cases demonstrate behavior; they are not representative application traces or evidence of BOOM/FPGA speedup.", ""]
    (output / "report.md").write_text("\n".join(lines))
    save_plot(rows, output, True)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--trace", type=Path)
    inputs.add_argument("--suite", action="store_true")
    parser.add_argument("--entries", type=int, default=16)
    parser.add_argument("--penalty", type=int, default=5)
    parser.add_argument("--warmup", type=int)
    parser.add_argument("--events", type=int, default=4096)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--sizes", default="4,16,64,256")
    parser.add_argument("--out", type=Path, default=Path("results"))
    args = parser.parse_args()
    try:
        if args.suite:
            sizes = tuple(sorted(set(int(s) for s in args.sizes.split(","))))
            rows = run_suite(args.out, args.events, args.seed,
                             256 if args.warmup is None else args.warmup, sizes, args.penalty)
            print(f"Wrote {len(rows)} synthetic experiment rows to {args.out}")
        else:
            rows = run(args.trace or Path("data/example_trace.csv"), args.out,
                       args.entries, args.penalty, args.warmup or 0)
            for row in rows:
                print(f'{row["predictor"]}: {100*row["accuracy"]:.2f}% accuracy, {row["mispredictions"]} misses')
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
