"""Certificate generator: calls inference backend, parses result, runs checker."""

from __future__ import annotations

import ast
import inspect
import json
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Any

from certus.checker.runner import run_checker
from certus.checker.report import VerificationReport
from certus.pipeline.augmenter import (
    parse_certificate_from_response,
    AugmentationResult,
)
from certus.pipeline.collector import CodeSample
from certus.pipeline.validator import validate_augmentation, ValidationResult
from certus.spec.schema import Certificate, Signature, Postcondition


@dataclass
class GenerateResult:
    function_name: str
    raw_certificate: str | None
    parsed: bool
    certificate_kwargs: dict[str, Any] | None
    validation: ValidationResult | None
    error: str | None = None


def extract_functions(source: str) -> list[tuple[str, str]]:
    """Extract (name, source) pairs for all top-level functions in source code."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    functions = []
    lines = source.splitlines(keepends=True)
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            start = node.lineno - 1
            end = node.end_lineno if node.end_lineno else start + 1
            func_source = "".join(lines[start:end])
            functions.append((node.name, func_source))
    return functions


def call_inference_server(code: str, server_url: str) -> str | None:
    """Call the inference server and return the raw certificate string."""
    payload = json.dumps({"code": code}).encode()
    req = urllib.request.Request(
        f"{server_url}/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read())
            if result.get("error"):
                return None
            return result.get("certificate")
    except (urllib.error.URLError, TimeoutError):
        return None


def generate_for_function(
    func_name: str,
    func_source: str,
    full_source: str,
    server_url: str,
    checker_mode: str = "fast",
    num_runs: int = 30,
) -> GenerateResult:
    """Generate and verify a certificate for a single function."""
    # Step 1: Call inference server
    raw = call_inference_server(func_source, server_url)
    if raw is None:
        return GenerateResult(
            function_name=func_name,
            raw_certificate=None,
            parsed=False,
            certificate_kwargs=None,
            validation=None,
            error="Inference server returned no result",
        )

    # Step 2: Parse the certificate
    cert_kwargs = parse_certificate_from_response(raw)
    if cert_kwargs is None:
        return GenerateResult(
            function_name=func_name,
            raw_certificate=raw,
            parsed=False,
            certificate_kwargs=None,
            validation=None,
            error="Could not parse @certus(...) from model output",
        )

    # Step 3: Validate through the checker
    sample = CodeSample(
        source="generate",
        task_id=func_name,
        description="",
        code=full_source,
    )
    aug = AugmentationResult(
        sample=sample,
        certificate_kwargs=cert_kwargs,
        raw_response=raw,
    )
    vr = validate_augmentation(aug, num_runs=num_runs, checker_mode=checker_mode)

    return GenerateResult(
        function_name=func_name,
        raw_certificate=raw,
        parsed=True,
        certificate_kwargs=cert_kwargs,
        validation=vr,
    )


def generate_for_file(
    filepath: str,
    server_url: str,
    function_name: str | None = None,
    checker_mode: str = "fast",
    num_runs: int = 30,
) -> list[GenerateResult]:
    """Generate certificates for functions in a Python file."""
    with open(filepath) as f:
        source = f.read()

    functions = extract_functions(source)
    if not functions:
        return [
            GenerateResult(
                function_name="(none)",
                raw_certificate=None,
                parsed=False,
                certificate_kwargs=None,
                validation=None,
                error="No functions found in file",
            )
        ]

    if function_name:
        functions = [(n, s) for n, s in functions if n == function_name]
        if not functions:
            return [
                GenerateResult(
                    function_name=function_name,
                    raw_certificate=None,
                    parsed=False,
                    certificate_kwargs=None,
                    validation=None,
                    error=f"Function '{function_name}' not found",
                )
            ]

    results = []
    for name, func_src in functions:
        result = generate_for_function(
            name,
            func_src,
            source,
            server_url,
            checker_mode,
            num_runs,
        )
        results.append(result)
    return results
