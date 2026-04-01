"""Seed certificate: safe integer parsing."""

from certus.decorator import certus


@certus(
    preconditions=[],
    postconditions=[
        {"when": "result is not None", "guarantees": ["result == int(s)"]},
        {"when": "result is None", "guarantees": []},
    ],
)
def try_parse_int(s: str):
    try:
        return int(s)
    except ValueError:
        return None
