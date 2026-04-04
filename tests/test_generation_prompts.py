from __future__ import annotations

import pytest

from certus.generation.prompts import (
    build_generation_prompt,
    build_feedback_prompt,
    get_safe_expression_context,
    get_format_spec,
)


def test_get_format_spec_contains_schema():
    spec = get_format_spec()
    assert "preconditions" in spec
    assert "postconditions" in spec
    assert "guarantees" in spec


def test_get_safe_expression_context_contains_builtins():
    ctx = get_safe_expression_context()
    assert "len" in ctx
    assert "sorted" in ctx
    assert "isinstance" in ctx
    assert "eval" not in ctx
    assert "exec" not in ctx


def test_build_generation_prompt_includes_code():
    prompt = build_generation_prompt(
        function_code="def add(a: int, b: int) -> int:\n    return a + b",
        function_name="add",
    )
    assert "def add" in prompt
    assert "preconditions" in prompt
    assert "postconditions" in prompt


def test_build_generation_prompt_with_examples():
    prompt = build_generation_prompt(
        function_code="def double(x: int) -> int:\n    return x * 2",
        function_name="double",
        examples=[
            '{"preconditions": ["isinstance(x, int)"], "postconditions": [{"when": "always", "guarantees": ["result == x + x"]}]}'
        ],
    )
    assert "result == x + x" in prompt


def test_build_feedback_prompt():
    prompt = build_feedback_prompt(
        function_code="def add(a: int, b: int) -> int:\n    return a + b",
        function_name="add",
        previous_certificate='{"preconditions": [], "postconditions": [{"when": "always", "guarantees": ["isinstance(result, int)"]}]}',
        feedback="Strength 0.1: postcondition is tautological. Add properties about the result value.",
    )
    assert "isinstance(result, int)" in prompt
    assert "tautological" in prompt
