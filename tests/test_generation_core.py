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

GOOD_CERT_JSON = json.dumps(
    {
        "preconditions": ["isinstance(a, int)", "isinstance(b, int)"],
        "postconditions": [{"when": "always", "guarantees": ["result == a + b"]}],
    }
)

WEAK_CERT_JSON = json.dumps(
    {
        "preconditions": [],
        "postconditions": [
            {"when": "always", "guarantees": ["isinstance(result, int)"]}
        ],
    }
)


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
    assert (
        "structural" in result.feedback.lower() or "unsafe" in result.feedback.lower()
    )


# ---------------------------------------------------------------------------
# Integration tests for generate_certificate() end-to-end loop
# ---------------------------------------------------------------------------


def test_generate_certificate_succeeds_first_try():
    result = generate_certificate(
        function_code=SAMPLE_CODE,
        function_name="add",
        llm_call=lambda prompt: GOOD_CERT_JSON,
        strength_threshold=0.3,
        max_attempts=3,
        num_runs=30,
    )

    assert result.passed is True
    assert result.attempts == 1
    assert result.certificate is not None


def test_generate_certificate_retries_on_weak():
    responses = iter([WEAK_CERT_JSON, GOOD_CERT_JSON])

    result = generate_certificate(
        function_code=SAMPLE_CODE,
        function_name="add",
        llm_call=lambda prompt: next(responses),
        strength_threshold=0.3,
        max_attempts=3,
        num_runs=30,
    )

    assert result.passed is True
    assert result.attempts == 2


def test_generate_certificate_gives_up_after_max_attempts():
    result = generate_certificate(
        function_code=SAMPLE_CODE,
        function_name="add",
        llm_call=lambda prompt: "this is not json at all",
        strength_threshold=0.3,
        max_attempts=3,
        num_runs=30,
    )

    assert result.passed is False
    assert result.certificate is None
    assert result.attempts == 3


def test_generate_certificate_uncertifiable_weak():
    result = generate_certificate(
        function_code=SAMPLE_CODE,
        function_name="add",
        llm_call=lambda prompt: WEAK_CERT_JSON,
        strength_threshold=0.5,
        max_attempts=2,
        num_runs=30,
    )

    assert result.passed is False


def test_generate_certificate_feedback_loop_improves_quality():
    tautological = json.dumps(
        {
            "preconditions": ["isinstance(a, int)", "isinstance(b, int)"],
            "postconditions": [{"when": "always", "guarantees": ["result == result"]}],
        }
    )
    strong = GOOD_CERT_JSON

    attempts = []
    responses = [tautological, strong]

    def llm_call(prompt):
        idx = len(attempts)
        attempts.append(prompt)
        return responses[min(idx, len(responses) - 1)]

    result = generate_certificate(
        function_code=SAMPLE_CODE,
        function_name="add",
        llm_call=llm_call,
        strength_threshold=0.5,
        max_attempts=3,
        num_runs=30,
    )

    assert result.passed is True
    assert result.attempts == 2
    assert len(attempts) == 2
    # Retry prompt should contain feedback about the tautological certificate
    retry_prompt = attempts[1].lower()
    assert (
        "strength" in retry_prompt
        or "weak" in retry_prompt
        or "result == result" in attempts[1]
    )
