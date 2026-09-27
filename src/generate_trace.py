"""Generate a deterministic, synthetic trace for a first experiment."""

import argparse
import csv
from pathlib import Path


def generate() -> list[tuple[str, int]]:
    trace = []

    for loop in range(12):
        for iteration in range(8):
            # A loop branch: taken seven times, then not taken.
            trace.append(
                ("0x100", int(iteration < 7))
            )

            # A second branch with a changing outcome pattern.
            if iteration % 2 == 0:
                trace.append(
                    (
                        "0x120",
                        int(
                            (loop + iteration // 2) % 2 == 0
                        ),
                    )
                )

    return trace


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--out",
        type=Path,
        default=Path("data/example_trace.csv"),
    )

    args = parser.parse_args()

    args.out.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with args.out.open("w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow(["pc", "taken"])
        writer.writerows(generate())

    print(
        f"Wrote {len(generate())} synthetic branch events "
        f"to {args.out}"
    )
