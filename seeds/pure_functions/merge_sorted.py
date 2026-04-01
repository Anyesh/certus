"""Seed certificate: merge two sorted lists."""

from certus.decorator import certus


@certus(
    preconditions=[
        "all(isinstance(x, int) for x in a)",
        "all(isinstance(x, int) for x in b)",
        "all(a[i] <= a[i+1] for i in range(len(a)-1))",
        "all(b[i] <= b[i+1] for i in range(len(b)-1))",
    ],
    postconditions=[
        {
            "when": "always",
            "guarantees": [
                "len(result) == len(a) + len(b)",
                "all(result[i] <= result[i+1] for i in range(len(result)-1))",
                "all(x in result for x in a)",
                "all(x in result for x in b)",
            ],
        }
    ],
    invariants=[
        {
            "loop": "while i < len(a) and j < len(b)",
            "maintains": ["all(result[k] <= result[k+1] for k in range(len(result)-1))"],
            "termination": "len(a) - i + len(b) - j",
        }
    ],
    depends_on=[
        {"function": "list.append", "certified": False, "uses": ["len(self) increases by 1"]},
    ],
    assumptions=["input lists fit in memory"],
)
def merge_sorted(a: list, b: list) -> list:
    result = []
    i, j = 0, 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            result.append(a[i])
            i += 1
        else:
            result.append(b[j])
            j += 1
    result.extend(a[i:])
    result.extend(b[j:])
    return result
