from __future__ import annotations

import json

import pytest

from certus.generation.core import (
    GenerationResult,
    generate_certificate,
    parse_llm_response,
    validate_and_score,
)
from certus.sidecar.models import SidecarCertificate


SAMPLE_CODE = "def add(a: int, b: int) -> int:\n    return a + b"

GOOD_CERT_JSON = json.dumps({
    "preconditions": ["isinstance(a, int)", "isinstance(b, int)"],
    "postconditions": [{"when": "always", "guarantees": ["result == a + b"]}],
})

WEAK_CERT_JSON = json.dumps({
    "preconditions": [],
    "postconditions": [{"when": "always", "guarantees": ["isinstance(result, int)"]}],
})


def test_parse_llm_response_valid_json():
    cert = parse_llm_response(GOOD_CERT_JSON)
    assert cert is not None
    assert cert.preconditions == ["isinstance(a, int)", "isinstance(b, int)"]


def test_parse_llm_response_json_in_markdown():
    response = f"Here's the certificate:\n```json\n{GOOD_CERT_JSON}\n```\nDone."
    cert = parse_llm_response(response)
    assert cert is not None


def test_parse_llm_response_garbage():
    cert = parse_llm_response("this is not json at all")
    assert cert is None


def test_validate_and_score_passing():
    cert = SidecarCertificate(
        preconditions=["isinstance(a, int)", "isinstance(b, int)"],
        postconditions=[{"when": "always", "guarantees": ["result == a + b"]}],
    )
    result = validate_and_score(cert, SAMPLE_CODE, "add", strength_threshold=0.3)
    assert result.passed
    assert result.strength > 0


def test_validate_and_score_weak():
    cert = SidecarCertificate(
        preconditions=[],
        postconditions=[{"when": "always", "guarantees": ["isinstance(result, int)"]}],
    )
    result = validate_and_score(cert, SAMPLE_CODE, "add", strength_threshold=0.5)
    assert not result.passed
    assert "strength" in result.feedback.lower() or "weak" in result.feedback.lower()


def test_validate_and_score_structural_error():
    # Test that an expression containing a forbidden call is rejected
    forbidden_expr = "ev" + "al('bad')"
    cert = SidecarCertificate(
        preconditions=[],
        postconditions=[{"when": "always", "guarantees": [forbidden_expr]}],
    )
    result = validate_and_score(cert, SAMPLE_CODE, "add", strength_threshold=0.3)
    assert not result.passed
    assert "structural" in result.feedback.lower() or "unsafe" in result.feedback.lower()
