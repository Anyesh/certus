"""Augmenter: generates Certus certificates via Claude API."""

from __future__ import annotations

import ast
import re
import time
from dataclasses import dataclass
from typing import Any

from certus.pipeline.collector import CodeSample
from certus.pipeline.prompts import SYSTEM_PROMPT, build_augmentation_messages


@dataclass
class AugmentationResult:
    sample: CodeSample
    certificate_kwargs: dict[str, Any] | None
    raw_response: str
    error: str | None = None


def _ast_node_to_value(node: ast.expr) -> Any:
    """Convert an AST literal node to a Python value without using eval."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.List):
        return [_ast_node_to_value(elt) for elt in node.elts]
    if isinstance(node, ast.Dict):
        return {
            _ast_node_to_value(k): _ast_node_to_value(v)
            for k, v in zip(node.keys, node.values)
            if k is not None
        }
    if isinstance(node, ast.Tuple):
        return tuple(_ast_node_to_value(elt) for elt in node.elts)
    if isinstance(node, ast.Set):
        return {_ast_node_to_value(elt) for elt in node.elts}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        val = _ast_node_to_value(node.operand)
        if isinstance(val, (int, float)):
            return -val
    raise ValueError(
        f"Unsupported AST node type for literal extraction: {type(node).__name__}"
    )


def parse_certificate_from_response(response: str) -> dict[str, Any] | None:
    """Extract @certus(...) kwargs from a model response string."""
    match = re.search(r"@certus\(", response)
    if not match:
        return None

    start = match.start()
    text = response[start:]

    depth = 0
    end = None
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end is None:
        return None

    decorator_call = text[:end]
    call_args = decorator_call[len("@certus") :]

    try:
        fake_code = f"_certus_call{call_args}"
        tree = ast.parse(fake_code, mode="eval")
    except SyntaxError:
        return None

    if not isinstance(tree.body, ast.Call):
        return None

    kwargs = {}
    for kw in tree.body.keywords:
        try:
            kwargs[kw.arg] = _ast_node_to_value(kw.value)
        except (ValueError, TypeError):
            continue

    if not kwargs:
        return None

    return kwargs


class Augmenter:
    """Generates Certus certificates using Claude API."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 2048,
        dry_run: bool = False,
        delay_between_calls: float = 0.5,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.dry_run = dry_run
        self.delay_between_calls = delay_between_calls
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def augment_one(self, sample: CodeSample) -> AugmentationResult:
        """Generate a certificate for a single code sample."""
        if self.dry_run:
            return self._dry_run_augment(sample)

        messages = build_augmentation_messages(sample.code, sample.description)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=SYSTEM_PROMPT,
                messages=messages,
            )
            raw = response.content[0].text if response.content else ""
        except Exception as e:
            return AugmentationResult(
                sample=sample,
                certificate_kwargs=None,
                raw_response="",
                error=str(e),
            )

        cert_kwargs = parse_certificate_from_response(raw)
        if cert_kwargs is None:
            return AugmentationResult(
                sample=sample,
                certificate_kwargs=None,
                raw_response=raw,
                error="Failed to parse certificate from response",
            )

        return AugmentationResult(
            sample=sample,
            certificate_kwargs=cert_kwargs,
            raw_response=raw,
        )

    def augment_batch(self, samples: list[CodeSample]) -> list[AugmentationResult]:
        """Augment a batch of code samples with rate limiting."""
        results = []
        for i, sample in enumerate(samples):
            result = self.augment_one(sample)
            results.append(result)
            if not self.dry_run and i < len(samples) - 1:
                time.sleep(self.delay_between_calls)
        return results

    def _dry_run_augment(self, sample: CodeSample) -> AugmentationResult:
        """Return a synthetic certificate for testing without API calls."""
        raw = (
            "@certus(\n"
            "    preconditions=[],\n"
            '    postconditions=[{"when": "always", "guarantees": ["isinstance(result, object)"]}],\n'
            ")"
        )
        cert_kwargs = parse_certificate_from_response(raw)
        return AugmentationResult(
            sample=sample,
            certificate_kwargs=cert_kwargs,
            raw_response=raw,
        )
