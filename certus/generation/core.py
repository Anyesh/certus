from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from certus.checker.runner import check_from_sidecar
from certus.generation.prompts import build_feedback_prompt, build_generation_prompt
from certus.sidecar.models import SidecarCertificate, SidecarFileEntry


@dataclass
class ValidationFeedback:
    passed: bool
    strength: float
    feedback: str
    structural_errors: list[str] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)


@dataclass
class GenerationResult:
    function_name: str
    certificate: SidecarCertificate | None
    passed: bool
    strength: float
    feedback: str
    attempts: int


def _make_dummy_entry(cert: SidecarCertificate) -> SidecarFileEntry:
    return SidecarFileEntry(
        signature_hash="gen",
        body_hash="gen",
        generated_by="certus.generation",
        generated_at=datetime.now(tz=timezone.utc),
        certificate=cert,
    )


def parse_llm_response(response: str) -> SidecarCertificate | None:
    # Strategy 1: try the entire response as raw JSON.
    try:
        data = json.loads(response.strip())
        return SidecarCertificate(**data)
    except Exception:
        pass

    # Strategy 2: extract from a markdown code block (```json ... ``` or ``` ... ```).
    md_match = re.search(r"```(?:json)?\s*\n(.*?)```", response, re.DOTALL)
    if md_match:
        try:
            data = json.loads(md_match.group(1).strip())
            return SidecarCertificate(**data)
        except Exception:
            pass

    # Strategy 3: regex search for the outermost JSON object in the response.
    brace_match = re.search(r"\{.*\}", response, re.DOTALL)
    if brace_match:
        try:
            data = json.loads(brace_match.group(0))
            return SidecarCertificate(**data)
        except Exception:
            pass

    return None


def validate_and_score(
    cert: SidecarCertificate,
    source_code: str,
    function_name: str,
    strength_threshold: float = 0.5,
    num_runs: int = 30,
) -> ValidationFeedback:
    entry = _make_dummy_entry(cert)
    report = check_from_sidecar(function_name, entry, source_code, num_runs=num_runs)

    strength = report.strength.rejection_rate
    summary = report.summary

    structural_errors = [c.claim for c in report.claims if c.status == "unverified"]
    violations = [c.claim for c in report.claims if c.status == "violated"]

    if structural_errors:
        feedback_parts = ["Structural/unsafe expression errors:"]
        feedback_parts.extend(f"  - {e}" for e in structural_errors)
        return ValidationFeedback(
            passed=False,
            strength=strength,
            feedback="\n".join(feedback_parts),
            structural_errors=structural_errors,
            violations=violations,
        )

    if violations:
        feedback_parts = [
            f"Dynamic check violations ({len(violations)} claim(s) failed):"
        ]
        feedback_parts.extend(f"  - {v}" for v in violations)
        return ValidationFeedback(
            passed=False,
            strength=strength,
            feedback="\n".join(feedback_parts),
            structural_errors=structural_errors,
            violations=violations,
        )

    if strength < strength_threshold:
        feedback = (
            f"Strength {strength:.3f} is below threshold {strength_threshold:.3f}: "
            "certificate is too weak or tautological. "
            "Add stronger, falsifiable postconditions that constrain the result value."
        )
        return ValidationFeedback(
            passed=False,
            strength=strength,
            feedback=feedback,
            structural_errors=[],
            violations=[],
        )

    return ValidationFeedback(
        passed=True,
        strength=strength,
        feedback="Certificate passed all checks.",
        structural_errors=[],
        violations=[],
    )


def generate_certificate(
    function_code: str,
    function_name: str,
    llm_call,
    strength_threshold: float = 0.5,
    max_attempts: int = 3,
    num_runs: int = 30,
    examples: list[str] | None = None,
) -> GenerationResult:
    best_cert: SidecarCertificate | None = None
    best_strength: float = -1.0
    best_feedback: str = "No valid certificate could be generated."

    prompt = build_generation_prompt(
        function_code=function_code,
        function_name=function_name,
        examples=examples,
    )

    for attempt in range(1, max_attempts + 1):
        response = llm_call(prompt)
        cert = parse_llm_response(response)

        if cert is None:
            best_feedback = (
                "Could not parse a valid certificate JSON from the model response."
            )
            prompt = build_feedback_prompt(
                function_code=function_code,
                function_name=function_name,
                previous_certificate=response[:500],
                feedback="The response was not valid JSON. Return only a JSON object.",
            )
            continue

        result = validate_and_score(
            cert,
            function_code,
            function_name,
            strength_threshold=strength_threshold,
            num_runs=num_runs,
        )

        if result.strength > best_strength:
            best_strength = result.strength
            best_cert = cert
            best_feedback = result.feedback

        if result.passed:
            return GenerationResult(
                function_name=function_name,
                certificate=cert,
                passed=True,
                strength=result.strength,
                feedback=result.feedback,
                attempts=attempt,
            )

        prompt = build_feedback_prompt(
            function_code=function_code,
            function_name=function_name,
            previous_certificate=json.dumps(cert.model_dump(exclude_none=True)),
            feedback=result.feedback,
        )

    return GenerationResult(
        function_name=function_name,
        certificate=best_cert,
        passed=False,
        strength=best_strength if best_strength >= 0 else 0.0,
        feedback=best_feedback,
        attempts=max_attempts,
    )
