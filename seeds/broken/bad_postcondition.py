"""BROKEN seed: postcondition is wrong (claims abs returns negative)."""

from certus.decorator import certus


@certus(
    preconditions=[],
    postconditions=[{"when": "always", "guarantees": ["result < 0"]}],
)
def absolute_value(x: int) -> int:
    return abs(x)
