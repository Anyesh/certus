"""Prompt templates for the augmenter."""

from __future__ import annotations

SYSTEM_PROMPT = (
    "You are a Certus certificate generator. Given a Python function, you produce a "
    "Certus certificate as a @certus decorator.\n\n"
    "A Certus certificate declares what properties a function guarantees:\n"
    "- preconditions: what must be true of inputs (Python expressions)\n"
    "- postconditions: what is guaranteed about the result, branched by outcome\n"
    "- Each postcondition has a 'when' condition and 'guarantees' list\n\n"
    "All expressions must be valid Python using only safe builtins: len, sorted, all, "
    "any, min, max, sum, abs, set, list, tuple, range, isinstance, type.\n\n"
    "Special variables: `result` (the return value), `old(expr)` (value at function entry).\n\n"
    "Output ONLY the @certus(...) decorator call, nothing else. No explanation, no code, "
    "just the decorator."
)

FEW_SHOT_EXAMPLES = [
    {
        "code": (
            "def kth_smallest(arr: list, k: int) -> int:\n    return sorted(arr)[k - 1]"
        ),
        "certificate": (
            "@certus(\n"
            '    preconditions=["len(arr) > 0", "1 <= k <= len(arr)"],\n'
            "    postconditions=[\n"
            '        {"when": "always",\n'
            '         "guarantees": ["result in arr",\n'
            '                        "sum(1 for x in arr if x < result) < k",\n'
            '                        "sum(1 for x in arr if x <= result) >= k"]}\n'
            "    ],\n"
            ")"
        ),
    },
    {
        "code": (
            "def fibonacci(n: int) -> int:\n"
            "    if n <= 0:\n"
            "        return 0\n"
            "    if n == 1:\n"
            "        return 1\n"
            "    a, b = 0, 1\n"
            "    for _ in range(2, n + 1):\n"
            "        a, b = b, a + b\n"
            "    return b"
        ),
        "certificate": (
            "@certus(\n"
            '    preconditions=["n >= 0"],\n'
            "    postconditions=[\n"
            '        {"when": "n == 0", "guarantees": ["result == 0"]},\n'
            '        {"when": "n == 1", "guarantees": ["result == 1"]},\n'
            '        {"when": "n >= 2", "guarantees": ["result >= 1"]},\n'
            '        {"when": "always", "guarantees": ["result >= 0"]}\n'
            "    ],\n"
            ")"
        ),
    },
    {
        "code": (
            "def safe_divide(a: float, b: float) -> float:\n"
            "    if b == 0:\n"
            '        raise ValueError("division by zero")\n'
            "    return a / b"
        ),
        "certificate": (
            "@certus(\n"
            "    preconditions=[],\n"
            "    postconditions=[\n"
            '        {"when": "result is not None", "guarantees": ["result == a / b"]}\n'
            "    ],\n"
            '    raises=[{"exception": "ValueError", "when": "b == 0", "guarantees": []}],\n'
            ")"
        ),
    },
]


def build_augmentation_messages(code: str, description: str) -> list[dict]:
    """Build the messages list for a Claude API call."""
    messages = []

    for example in FEW_SHOT_EXAMPLES:
        messages.append(
            {
                "role": "user",
                "content": f"Generate a Certus certificate for this function:\n\n{example['code']}",
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": example["certificate"],
            }
        )

    messages.append(
        {
            "role": "user",
            "content": f"Generate a Certus certificate for this function:\n\n{code}",
        }
    )

    return messages
