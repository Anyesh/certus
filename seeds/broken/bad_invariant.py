"""BROKEN seed: invariant does not hold (claims sum is always negative)."""

from certus.decorator import certus


@certus(
    preconditions=["len(arr) > 0", "all(x > 0 for x in arr)"],
    postconditions=[{"when": "always", "guarantees": ["result == sum(arr)"]}],
    invariants=[{"loop": "for x in arr", "maintains": ["total < 0"]}],
)
def sum_positive(arr: list) -> int:
    total = 0
    for x in arr:
        total += x
    return total
