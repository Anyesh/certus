from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from certus.sidecar.models import (
    SidecarCertificate,
    SidecarFileEntry,
    SidecarFile,
)


def test_sidecar_certificate_minimal():
    cert = SidecarCertificate(
        preconditions=["len(arr) > 0"],
        postconditions=[{"when": "always", "guarantees": ["result >= 0"]}],
    )
    assert cert.preconditions == ["len(arr) > 0"]
    assert cert.postconditions[0]["when"] == "always"


def test_sidecar_file_entry_roundtrip():
    entry = SidecarFileEntry(
        signature_hash="abc123",
        body_hash="def456",
        generated_by="claude-sonnet-4-20250514",
        generated_at=datetime(2026, 4, 4, tzinfo=timezone.utc),
        certificate=SidecarCertificate(
            preconditions=["x > 0"],
            postconditions=[{"when": "always", "guarantees": ["result > 0"]}],
        ),
    )
    data = entry.model_dump(mode="json")
    restored = SidecarFileEntry.model_validate(data)
    assert restored.signature_hash == "abc123"
    assert restored.body_hash == "def456"
    assert restored.generated_by == "claude-sonnet-4-20250514"


def test_sidecar_file_structure():
    sf = SidecarFile(
        version="1.0",
        source_file="src/utils.py",
        functions={},
    )
    assert sf.version == "1.0"
    assert sf.functions == {}


def test_sidecar_file_json_roundtrip():
    entry = SidecarFileEntry(
        signature_hash="aaa",
        body_hash="bbb",
        generated_by="test",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        certificate=SidecarCertificate(
            preconditions=[],
            postconditions=[{"when": "always", "guarantees": ["result == 0"]}],
        ),
    )
    sf = SidecarFile(
        version="1.0",
        source_file="src/math.py",
        functions={"add": entry},
    )
    json_str = sf.model_dump_json(indent=2)
    restored = SidecarFile.model_validate_json(json_str)
    assert "add" in restored.functions
    assert restored.functions["add"].signature_hash == "aaa"


def test_sidecar_certificate_with_conditional_postconditions():
    cert = SidecarCertificate(
        preconditions=["isinstance(arr, list)"],
        postconditions=[
            {"when": "len(arr) == 0", "guarantees": ["result == []"]},
            {"when": "always", "guarantees": ["isinstance(result, list)"]},
        ],
    )
    assert len(cert.postconditions) == 2
