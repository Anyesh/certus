"""Batch validator: runs checker in fast mode to filter augmented certificates."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

from certus.checker.report import VerificationReport
from certus.checker.runner import run_checker
from certus.pipeline.augmenter import AugmentationResult
from certus.spec.schema import Certificate, Signature, Postcondition


STRENGTH_THRESHOLD = 0.1


@dataclass
class ValidationResult:
    augmentation: AugmentationResult
    passed: bool
    report: VerificationReport | None = None
    reason: str | None = None


def validate_augmentation(
    aug_result: AugmentationResult,
    num_runs: int = 200,
    checker_mode: str = "fast",
) -> ValidationResult:
    """Validate a single augmentation result using the checker."""
    if aug_result.certificate_kwargs is None:
        return ValidationResult(
            augmentation=aug_result,
            passed=False,
            reason=f"No certificate: {aug_result.error}",
        )

    sample = aug_result.sample
    kwargs = aug_result.certificate_kwargs

    try:
        code_obj = compile(sample.code, "<augmented>", "exec")
    except SyntaxError as e:
        return ValidationResult(
            augmentation=aug_result,
            passed=False,
            reason=f"Code syntax error: {e}",
        )

    namespace: dict[str, Any] = {}
    try:
        exec(code_obj, namespace)
    except Exception as e:
        return ValidationResult(
            augmentation=aug_result,
            passed=False,
            reason=f"Code runtime error: {e}",
        )

    fn_name = sample.function_name
    if fn_name is None or fn_name not in namespace:
        return ValidationResult(
            augmentation=aug_result,
            passed=False,
            reason=f"Function '{fn_name}' not found after executing code",
        )

    func = namespace[fn_name]
    if not callable(func):
        return ValidationResult(
            augmentation=aug_result,
            passed=False,
            reason=f"'{fn_name}' is not callable",
        )

    sig = inspect.signature(func)
    hints = func.__annotations__ if hasattr(func, "__annotations__") else {}
    params = {}
    for name in sig.parameters:
        hint = hints.get(name)
        if hint is None:
            params[name] = "int"
        elif isinstance(hint, type):
            params[name] = hint.__name__
        else:
            params[name] = str(hint)
    return_hint = hints.get("return")
    if return_hint is None:
        return_str = "Any"
    elif isinstance(return_hint, type):
        return_str = return_hint.__name__
    else:
        return_str = str(return_hint)

    postconditions = [Postcondition(**p) for p in kwargs.get("postconditions", [])]

    cert = Certificate(
        certus="0.1",
        function=fn_name,
        signature=Signature(
            params=params,
            returns=return_str,
            preconditions=kwargs.get("preconditions", []),
        ),
        postconditions=postconditions,
    )

    try:
        report = run_checker(
            func, cert, sample.code, mode=checker_mode, num_runs=num_runs
        )
    except Exception as e:
        return ValidationResult(
            augmentation=aug_result,
            passed=False,
            reason=f"Checker error: {e}",
        )

    if report.summary.violated > 0:
        return ValidationResult(
            augmentation=aug_result,
            passed=False,
            report=report,
            reason="Postcondition violated",
        )

    if report.summary.unverified > 0:
        return ValidationResult(
            augmentation=aug_result,
            passed=False,
            report=report,
            reason="Validation errors (unsafe expressions or malformed certificate)",
        )

    if report.strength.rejection_rate < STRENGTH_THRESHOLD:
        return ValidationResult(
            augmentation=aug_result,
            passed=False,
            report=report,
            reason=f"Tautological: strength {report.strength.rejection_rate} below threshold {STRENGTH_THRESHOLD}",
        )

    return ValidationResult(
        augmentation=aug_result,
        passed=True,
        report=report,
    )
