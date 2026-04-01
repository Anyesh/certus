"""Seed certificate: find kth smallest element."""

from certus.decorator import certus


@certus(
    preconditions=["len(arr) > 0", "1 <= k <= len(arr)"],
    postconditions=[
        {
            "when": "always",
            "guarantees": [
                "result in arr",
                "sum(1 for x in arr if x < result) < k",
                "sum(1 for x in arr if x <= result) >= k",
            ],
        }
    ],
    depends_on=[
        {"function": "sorted", "certified": False, "uses": ["result == sorted(result)"]},
    ],
)
def kth_smallest(arr: list, k: int) -> int:
    return sorted(arr)[k - 1]
