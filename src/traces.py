"""Strict CSV input plus seeded synthetic workloads with known structure."""

from pathlib import Path
import csv
import random

from .predictors import Branch

PATTERNS = ("loop", "alternating", "correlated", "aliasing", "random")


def load_trace(path: Path) -> list[Branch]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        if not {"pc", "taken"}.issubset(reader.fieldnames or []):
            raise ValueError("trace needs pc,taken columns")
        branches = []
        for line, row in enumerate(reader, 2):
            if row["taken"] not in ("0", "1"):
                raise ValueError(f"line {line}: taken must be 0 or 1")
            try:
                value = row["pc"].strip()
                pc = int(value, 16 if value.lower().startswith("0x") else 10)
                branches.append(Branch(pc, row["taken"] == "1"))
            except (ValueError, AttributeError) as error:
                raise ValueError(f"line {line}: invalid PC ({error})") from error
    if not branches:
        raise ValueError("trace must contain at least one branch")
    return branches


def generate_workload(pattern: str, events: int = 4096, seed: int = 7) -> list[Branch]:
    if pattern not in PATTERNS:
        raise ValueError(f"unknown workload: {pattern}")
    if events <= 0:
        raise ValueError("events must be positive")
    rng = random.Random(seed)
    result = []
    previous = False
    for event in range(events):
        pc = 0x1000
        if pattern == "loop":
            taken = event % 32 != 31
        elif pattern == "alternating":
            taken = event % 2 == 1
        elif pattern == "correlated":
            if event % 2 == 0:
                previous = bool(rng.getrandbits(1))
            pc += (event % 2) * 4
            taken = previous
        elif pattern == "aliasing":
            # These PCs collide at 4 and 16 entries, separate at 64 and 256.
            pc += (event % 2) * 0x40
            taken = event % 2 == 0
        else:
            taken = bool(rng.getrandbits(1))
        result.append(Branch(pc, taken))
    return result


def write_trace(path: Path, branches: list[Branch]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["pc", "taken"])
        writer.writerows((hex(b.pc), int(b.taken)) for b in branches)
