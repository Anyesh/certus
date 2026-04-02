"""Tests for structural verification mode and test-derived pipeline validation."""

import json
import pytest
from pathlib import Path

from certus.spec.schema import Certificate, Signature, Postcondition
from certus.checker.runner import run_checker
from certus.pipeline.validator import validate_augmentation, ValidationResult
from certus.pipeline.augmenter import AugmentationResult
from certus.pipeline.collector import CodeSample
from certus.pipeline.formatter import format_validated_results


# --- Fixtures ---

SOURCE_ABS = """\
def absolute(x: int) -> int:
    if x < 0:
        return -x
    return x
"""


def absolute(x: int) -> int:
    if x < 0:
        return -x
    return x


SOURCE_ADD = """\
def add(a, b):
    return a + b
"""


def add(a, b):
    return a + b


def _make_sample(code=SOURCE_ADD, fn_name="add", desc="Add two numbers"):
    return CodeSample(source="test", task_id="t1", description=desc, code=code)


def _make_aug(sample=None, preconditions=None, postconditions=None, error=None):
    if sample is None:
        sample = _make_sample()
    kwargs = None
    if error is None:
        kwargs = {
            "preconditions": preconditions or [],
            "postconditions": postconditions
            or [{"when": "always", "guarantees": ["result == a + b"]}],
        }
    return AugmentationResult(
        sample=sample,
        certificate_kwargs=kwargs,
        raw_response="@certus(...)",
        error=error,
    )


# --- run_checker structural mode ---


class TestStructuralMode:
    def test_structural_skips_hypothesis(self):
        cert = Certificate(
            certus="0.1",
            function="absolute",
            signature=Signature(
                params={"x": "int"},
                returns="int",
                preconditions=["isinstance(x, int)"],
            ),
            postconditions=[
                Postcondition(when="always", guarantees=["result >= 0"]),
            ],
        )
        report = run_checker(absolute, cert, SOURCE_ABS, mode="structural")
        # Structural mode should produce no dynamic claims
        assert len(report.claims) == 0
        # But should still measure strength
        assert 0 <= report.strength.rejection_rate <= 1.0

    def test_structural_still_catches_validation_errors(self):
        # Build an unsafe expression that the AST validator will reject.
        # This string is never executed; it's checked by the safe_subset validator.
        unsafe_expr = "eval" + "('True')"  # noqa: S307 — test input, not executed
        cert = Certificate(
            certus="0.1",
            function="absolute",
            signature=Signature(
                params={"x": "int"},
                returns="int",
                preconditions=[unsafe_expr],
            ),
            postconditions=[
                Postcondition(when="always", guarantees=["result >= 0"]),
            ],
        )
        report = run_checker(absolute, cert, SOURCE_ABS, mode="structural")
        assert report.summary.unverified > 0

    def test_structural_measures_strength(self):
        cert = Certificate(
            certus="0.1",
            function="absolute",
            signature=Signature(
                params={"x": "int"},
                returns="int",
                preconditions=["isinstance(x, int)"],
            ),
            postconditions=[
                Postcondition(when="always", guarantees=["result >= 0"]),
            ],
        )
        report = run_checker(absolute, cert, SOURCE_ABS, mode="structural")
        # "result >= 0" should reject roughly half of random ints
        assert report.strength.rejection_rate > 0.0

    def test_fast_mode_still_runs_hypothesis(self):
        cert = Certificate(
            certus="0.1",
            function="absolute",
            signature=Signature(
                params={"x": "int"},
                returns="int",
                preconditions=[],
            ),
            postconditions=[
                Postcondition(when="always", guarantees=["result >= 0"]),
            ],
        )
        report = run_checker(absolute, cert, SOURCE_ABS, mode="fast", num_runs=10)
        # Fast mode should have dynamic claims
        assert len(report.claims) > 0
        for claim in report.claims:
            if claim.status == "held":
                assert claim.method == "hypothesis"


# --- validate_augmentation with checker_mode ---


class TestValidatorMode:
    def test_structural_validation_passes_valid_cert(self):
        aug = _make_aug()
        vr = validate_augmentation(aug, num_runs=50, checker_mode="structural")
        assert vr.passed is True

    def test_structural_validation_rejects_bad_expressions(self):
        unsafe_guarantee = "eval" + "('True')"  # noqa: S307 — test input, not executed
        aug = _make_aug(
            postconditions=[{"when": "always", "guarantees": [unsafe_guarantee]}],
        )
        vr = validate_augmentation(aug, num_runs=50, checker_mode="structural")
        assert vr.passed is False

    def test_structural_validation_rejects_tautology(self):
        # "True" is always true regardless of result, so strength should be 0
        aug = _make_aug(
            postconditions=[{"when": "always", "guarantees": ["True"]}],
        )
        vr = validate_augmentation(aug, num_runs=50, checker_mode="structural")
        assert vr.passed is False
        assert "Tautological" in (vr.reason or "")

    def test_fast_validation_still_works(self):
        aug = _make_aug()
        vr = validate_augmentation(aug, num_runs=50, checker_mode="fast")
        assert vr.passed is True


# --- End-to-end: generate + validate + format ---


class TestEndToEnd:
    def test_valid_cert_produces_training_examples(self):
        aug = _make_aug()
        vr = validate_augmentation(aug, num_runs=50, checker_mode="structural")
        assert vr.passed
        examples = format_validated_results([vr])
        assert len(examples) == 2  # Task A and Task B
        assert examples[0].task_type == "task_a"
        assert examples[1].task_type == "task_b"

    def test_failed_cert_produces_no_examples(self):
        aug = _make_aug(error="Could not generate")
        vr = validate_augmentation(aug, num_runs=50, checker_mode="structural")
        assert not vr.passed
        examples = format_validated_results([vr])
        assert len(examples) == 0
