import pytest
from certus.pipeline.validator import validate_augmentation, ValidationResult
from certus.pipeline.augmenter import AugmentationResult
from certus.pipeline.collector import CodeSample


def _make_sample(code="def add(a, b):\n    return a + b"):
    return CodeSample(source="test", task_id="1", description="Add", code=code)


def test_valid_certificate():
    result = AugmentationResult(
        sample=_make_sample(),
        certificate_kwargs={
            "preconditions": [],
            "postconditions": [{"when": "always", "guarantees": ["result == a + b"]}],
        },
        raw_response="@certus(...)",
    )
    vr = validate_augmentation(result, num_runs=50)
    assert vr.passed is True
    assert vr.report is not None


def test_invalid_certificate_fails():
    result = AugmentationResult(
        sample=_make_sample(),
        certificate_kwargs={
            "preconditions": [],
            "postconditions": [{"when": "always", "guarantees": ["result < 0"]}],
        },
        raw_response="@certus(...)",
    )
    vr = validate_augmentation(result, num_runs=100)
    assert vr.passed is False


def test_none_certificate_fails():
    result = AugmentationResult(
        sample=_make_sample(),
        certificate_kwargs=None,
        raw_response="bad",
        error="parse failed",
    )
    vr = validate_augmentation(result, num_runs=50)
    assert vr.passed is False


def test_code_that_doesnt_parse():
    result = AugmentationResult(
        sample=_make_sample(code="def broken(:\n    pass"),
        certificate_kwargs={
            "preconditions": [],
            "postconditions": [{"when": "always", "guarantees": ["True"]}],
        },
        raw_response="@certus(...)",
    )
    vr = validate_augmentation(result, num_runs=50)
    assert vr.passed is False
