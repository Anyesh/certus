"""Seed certificate: division with error handling."""

from certus.decorator import certus


@certus(
    preconditions=[],
    postconditions=[
        {"when": "result is not None", "guarantees": ["result == a / b"]},
    ],
    raises=[{"exception": "ValueError", "when": "b == 0", "guarantees": []}],
)
def safe_divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("division by zero")
    return a / b
