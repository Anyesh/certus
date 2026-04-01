"""Seed certificate: compute nth fibonacci number."""

from certus.decorator import certus


@certus(
    preconditions=["n >= 0"],
    postconditions=[
        {"when": "n == 0", "guarantees": ["result == 0"]},
        {"when": "n == 1", "guarantees": ["result == 1"]},
        {"when": "n >= 2", "guarantees": ["result >= 1"]},
        {"when": "always", "guarantees": ["result >= 0"]},
    ],
)
def fibonacci(n: int) -> int:
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
