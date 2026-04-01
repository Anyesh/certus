"""BROKEN seed: contains forbidden expression (uses eval)."""

from certus.decorator import certus


@certus(
    preconditions=["eval('True')"],
    postconditions=[{"when": "always", "guarantees": ["result >= 0"]}],
)
def identity(x: int) -> int:
    return x
