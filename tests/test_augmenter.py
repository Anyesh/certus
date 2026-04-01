import pytest
from certus.pipeline.augmenter import (
    Augmenter,
    AugmentationResult,
    parse_certificate_from_response,
)
from certus.pipeline.collector import CodeSample


def test_parse_certificate_valid():
    response = '@certus(\n    preconditions=["x > 0"],\n    postconditions=[{"when": "always", "guarantees": ["result > 0"]}],\n)'
    cert_dict = parse_certificate_from_response(response)
    assert cert_dict is not None
    assert cert_dict["preconditions"] == ["x > 0"]


def test_parse_certificate_strips_extra_text():
    response = 'Here is the certificate:\n\n@certus(\n    preconditions=[],\n    postconditions=[{"when": "always", "guarantees": ["result >= 0"]}],\n)\n\nThis certificate ensures...'
    cert_dict = parse_certificate_from_response(response)
    assert cert_dict is not None


def test_parse_certificate_invalid():
    response = "This is not a valid certificate at all"
    cert_dict = parse_certificate_from_response(response)
    assert cert_dict is None


def test_parse_certificate_malformed_python():
    response = "@certus(preconditions=[unclosed"
    cert_dict = parse_certificate_from_response(response)
    assert cert_dict is None


def test_augmentation_result():
    result = AugmentationResult(
        sample=CodeSample(source="test", task_id="1", description="test", code="pass"),
        certificate_kwargs={"preconditions": ["True"], "postconditions": []},
        raw_response="@certus(...)",
    )
    assert result.certificate_kwargs["preconditions"] == ["True"]


def test_augmentation_result_failed():
    result = AugmentationResult(
        sample=CodeSample(source="test", task_id="1", description="test", code="pass"),
        certificate_kwargs=None,
        raw_response="bad response",
        error="Failed to parse",
    )
    assert result.certificate_kwargs is None
    assert result.error == "Failed to parse"


class TestAugmenter:
    def test_augmenter_creates(self):
        aug = Augmenter(model="claude-sonnet-4-6", dry_run=True)
        assert aug.model == "claude-sonnet-4-6"

    def test_dry_run_returns_placeholder(self):
        aug = Augmenter(model="claude-sonnet-4-6", dry_run=True)
        sample = CodeSample(
            source="test",
            task_id="1",
            description="Add two numbers",
            code="def add(a, b):\n    return a + b",
        )
        result = aug.augment_one(sample)
        assert result.certificate_kwargs is not None or result.error is not None
