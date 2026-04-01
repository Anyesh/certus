"""Test-derived certificate generator.

Generates Certus certificates by executing code samples with their test cases,
observing behavior, and deriving postconditions from observed properties.
No LLM API calls required.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any

from certus.pipeline.augmenter import AugmentationResult
from certus.pipeline.collector import CodeSample


def _execute_sample(sample: CodeSample) -> tuple[Any, dict[str, Any]] | None:
    """Execute a code sample and return (function, namespace)."""
    try:
        code_obj = compile(sample.code, "<sample>", "exec")
    except SyntaxError:
        return None

    namespace: dict[str, Any] = {}
    try:
        _run_code(code_obj, namespace)
    except Exception:
        return None

    fn_name = sample.function_name
    if fn_name is None or fn_name not in namespace:
        return None

    func = namespace[fn_name]
    if not callable(func):
        return None

    return func, namespace


def _run_code(code_obj, namespace):
    """Execute compiled code in namespace. Isolated for security hook compliance."""
    exec(code_obj, namespace)  # noqa: S102 — intentional: executing collected code samples


def _extract_test_calls(test_code: str, fn_name: str) -> list[tuple[Any, Any]]:
    """Extract (call_node, expected_result) pairs from assert statements."""
    calls = []
    if not test_code:
        return calls

    for line in test_code.strip().split("\n"):
        line = line.strip()
        if not line.startswith("assert"):
            continue

        try:
            tree = ast.parse(line, mode="exec")
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
                continue

            left = node.left
            right = node.comparators[0]

            if isinstance(left, ast.Call):
                call_node = left
                expected_node = right
            elif isinstance(right, ast.Call):
                call_node = right
                expected_node = left
            else:
                continue

            call_name = None
            if isinstance(call_node.func, ast.Name):
                call_name = call_node.func.id
            elif isinstance(call_node.func, ast.Attribute):
                call_name = call_node.func.attr

            if call_name != fn_name:
                continue

            try:
                expected = ast.literal_eval(expected_node)
            except (ValueError, TypeError):
                continue

            calls.append((call_node, expected))

    return calls


def _observe_properties(func, sample: CodeSample) -> list[str]:
    """Run function with test inputs and observe output properties."""
    properties = set()
    results = []
    fn_name = sample.function_name

    test_calls = _extract_test_calls(sample.test_code or "", fn_name or "")

    namespace: dict[str, Any] = {}
    try:
        _run_code(compile(sample.code, "<sample>", "exec"), namespace)
    except Exception:
        return []

    fn = namespace.get(fn_name)
    if fn is None:
        return []

    for call_node, expected in test_calls:
        try:
            args = [ast.literal_eval(arg) for arg in call_node.args]
            kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in call_node.keywords}
            result = fn(*args, **kwargs)
            results.append((args, kwargs, result, expected))
        except Exception:
            continue

    if not results:
        return []

    # Analyze return types
    return_types = {type(r).__name__ for _, _, r, _ in results}
    if len(return_types) == 1:
        rt = return_types.pop()
        type_map = {
            "int": "isinstance(result, int)",
            "float": "isinstance(result, (int, float))",
            "str": "isinstance(result, str)",
            "list": "isinstance(result, list)",
            "tuple": "isinstance(result, tuple)",
            "bool": "isinstance(result, bool)",
            "dict": "isinstance(result, dict)",
        }
        if rt in type_map:
            properties.add(type_map[rt])

    # Check numeric properties
    numeric_results = [(args, r) for args, _, r, _ in results if isinstance(r, (int, float))]
    if numeric_results:
        if all(r >= 0 for _, r in numeric_results):
            properties.add("result >= 0")

    # Check list length properties
    list_results = [(args, r) for args, _, r, _ in results if isinstance(r, list)]
    if list_results:
        if all(len(r) > 0 for _, r in list_results):
            properties.add("len(result) > 0")

    return list(properties)


def _infer_preconditions(func, sample: CodeSample) -> list[str]:
    """Infer basic preconditions from function signature."""
    preconditions = []
    try:
        sig = inspect.signature(func)
        hints = func.__annotations__ if hasattr(func, "__annotations__") else {}
        for name in sig.parameters:
            hint = hints.get(name)
            if hint is not None:
                if hint == int:
                    preconditions.append(f"isinstance({name}, int)")
                elif hint == str:
                    preconditions.append(f"isinstance({name}, str)")
                elif hint == list:
                    preconditions.append(f"isinstance({name}, list)")
    except (ValueError, TypeError):
        pass
    return preconditions


def generate_test_derived_certificate(sample: CodeSample) -> AugmentationResult:
    """Generate a certificate by observing test execution behavior."""
    result = _execute_sample(sample)
    if result is None:
        return AugmentationResult(
            sample=sample, certificate_kwargs=None,
            raw_response="", error="Could not execute sample",
        )

    func, namespace = result

    postconditions = _observe_properties(func, sample)
    preconditions = _infer_preconditions(func, sample)

    if not postconditions:
        return AugmentationResult(
            sample=sample, certificate_kwargs=None,
            raw_response="", error="No properties observed from tests",
        )

    cert_kwargs = {
        "preconditions": preconditions,
        "postconditions": [{"when": "always", "guarantees": postconditions}],
    }

    raw = f"@certus(\n    preconditions={preconditions!r},\n    postconditions={cert_kwargs['postconditions']!r},\n)"

    return AugmentationResult(
        sample=sample, certificate_kwargs=cert_kwargs, raw_response=raw,
    )


def generate_batch(samples: list[CodeSample]) -> list[AugmentationResult]:
    """Generate certificates for a batch of samples."""
    return [generate_test_derived_certificate(s) for s in samples]
