from __future__ import annotations

from datetime import datetime, timezone

import pytest

from certus.checker.runner import check_from_sidecar
from certus.sidecar.models import SidecarCertificate, SidecarFileEntry


VALID_SOURCE = """
def add(a: int, b: int) -> int:
    return a + b
"""

FAILING_SOURCE = """
def bad_add(a: int, b: int) -> int:
    return a - b
"""


def _make_entry(preconditions, postconditions):
    return SidecarFileEntry(
        signature_hash="test",
        body_hash="test",
        generated_by="test",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        certificate=SidecarCertificate(
            preconditions=preconditions,
            postconditions=postconditions,
        ),
    )


def test_check_from_sidecar_passing():
    entry = _make_entry(
        preconditions=["isinstance(a, int)", "isinstance(b, int)"],
        postconditions=[{"when": "always", "guarantees": ["result == a + b"]}],
    )
    report = check_from_sidecar("add", entry, VALID_SOURCE, num_runs=30)
    assert report.summary.violated == 0


def test_check_from_sidecar_violated():
    entry = _make_entry(
        preconditions=["isinstance(a, int)", "isinstance(b, int)"],
        postconditions=[{"when": "always", "guarantees": ["result == a + b"]}],
    )
    report = check_from_sidecar("bad_add", entry, FAILING_SOURCE, num_runs=30)
    assert report.summary.violated > 0


def test_check_from_sidecar_structural_failure():
    entry = _make_entry(
        preconditions=[],
        postconditions=[{"when": "always", "guarantees": ["eval('bad')"]}],
    )
    report = check_from_sidecar("add", entry, VALID_SOURCE, num_runs=30)
    assert report.summary.unverified > 0


def test_check_from_sidecar_strength():
    entry = _make_entry(
        preconditions=["isinstance(a, int)", "isinstance(b, int)"],
        postconditions=[{"when": "always", "guarantees": ["result == a + b"]}],
    )
    report = check_from_sidecar("add", entry, VALID_SOURCE, num_runs=30)
    assert report.strength.rejection_rate > 0
