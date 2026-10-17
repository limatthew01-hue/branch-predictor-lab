"""Trace-driven direction predictors. Predictions precede immediate updates."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Branch:
    pc: int
    taken: bool

    def __post_init__(self):
        if self.pc < 0 or self.pc % 4:
            raise ValueError("PC must be nonnegative and 4-byte aligned")
        if not isinstance(self.taken, bool):
            raise ValueError("taken must be a boolean")


class StaticNotTaken:
    name = "Static not taken"
    state_bits = 0

    def predict(self, pc: int) -> bool:
        return False

    def update(self, pc: int, taken: bool) -> None:
        pass


class OneBit:
    name = "One-bit BHT"

    def __init__(self, entries: int):
        if entries <= 0:
            raise ValueError("entries must be positive")

        self.entries = [False] * entries
        self.state_bits = entries

    def index(self, pc: int) -> int:
        if pc < 0 or pc % 4:
            raise ValueError(
                "PC must be a nonnegative, 4-byte-aligned address"
            )

        return (pc >> 2) % len(self.entries)

    def predict(self, pc: int) -> bool:
        return self.entries[self.index(pc)]

    def update(self, pc: int, taken: bool) -> None:
        self.entries[self.index(pc)] = taken


class TwoBit:
    name = "Two-bit BHT"

    def __init__(self, entries: int):
        if entries <= 0:
            raise ValueError("entries must be positive")

        # 0 = strongly not taken
        # 1 = weakly not taken
        # 2 = weakly taken
        # 3 = strongly taken
        self.entries = [1] * entries
        self.state_bits = 2 * entries

    def index(self, pc: int) -> int:
        if pc < 0 or pc % 4:
            raise ValueError(
                "PC must be a nonnegative, 4-byte-aligned address"
            )

        return (pc >> 2) % len(self.entries)

    def predict(self, pc: int) -> bool:
        return self.entries[self.index(pc)] >= 2

    def update(self, pc: int, taken: bool) -> None:
        idx = self.index(pc)

        if taken:
            self.entries[idx] = min(
                3,
                self.entries[idx] + 1,
            )
        else:
            self.entries[idx] = max(
                0,
                self.entries[idx] - 1,
            )


class GShare(TwoBit):
    """XOR the word PC with the global history before updating either state."""

    name = "Gshare"

    def __init__(self, entries: int, history_bits: int | None = None):
        if entries < 2 or entries & (entries - 1):
            raise ValueError("gshare entries must be a power of two, at least 2")
        index_bits = entries.bit_length() - 1
        self.history_bits = index_bits if history_bits is None else history_bits
        if not 1 <= self.history_bits <= index_bits:
            raise ValueError("history bits must be between 1 and log2(entries)")
        super().__init__(entries)
        self.history = 0
        self.history_mask = (1 << self.history_bits) - 1
        self.state_bits += self.history_bits

    def index(self, pc: int) -> int:
        # super validates the same four-byte address convention as the BHTs.
        word_index = super().index(pc)
        return (word_index ^ self.history) & (len(self.entries) - 1)

    def update(self, pc: int, taken: bool) -> None:
        super().update(pc, taken)  # Counter index uses the pre-update history.
        self.history = ((self.history << 1) | int(taken)) & self.history_mask


def evaluate(
    predictor,
    branches: list[Branch],
    penalty_cycles: int,
    warmup: int = 0,
) -> dict:
    if penalty_cycles < 0:
        raise ValueError("penalty_cycles must be nonnegative")

    if not branches:
        raise ValueError(
            "trace must contain at least one branch"
        )

    if not 0 <= warmup < len(branches):
        raise ValueError("warmup must leave at least one measured branch")

    misses = 0

    for event, branch in enumerate(branches):
        prediction = predictor.predict(branch.pc)
        if event >= warmup:
            misses += prediction != branch.taken

        predictor.update(
            branch.pc,
            branch.taken,
        )

    return {
        "predictor": predictor.name,
        "branches": len(branches) - warmup,
        "warmup_branches": warmup,
        "state_bits": predictor.state_bits,
        "mispredictions": misses,
        "accuracy": (
            len(branches) - warmup - misses
        ) / (len(branches) - warmup),
        "penalty_cycles_only": misses * penalty_cycles,
    }
