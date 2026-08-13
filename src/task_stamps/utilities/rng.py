"""Contained random-selection utility.

Production uses an unseeded generator. Tests inject a seeded provider so
assignment and placement randomness is reproducible.
"""

from __future__ import annotations

import random
from typing import Protocol, Sequence, TypeVar

T = TypeVar("T")


class RandomProvider(Protocol):
    def choice(self, items: Sequence[T]) -> T: ...

    def uniform(self, low: float, high: float) -> float: ...


class SystemRandomProvider:
    def __init__(self) -> None:
        self._rng = random.Random()

    def choice(self, items: Sequence[T]) -> T:
        return self._rng.choice(items)

    def uniform(self, low: float, high: float) -> float:
        return self._rng.uniform(low, high)


class SeededRandomProvider(SystemRandomProvider):
    def __init__(self, seed: int) -> None:
        super().__init__()
        self._rng = random.Random(seed)
