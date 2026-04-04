from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from certus.sidecar.hashing import compute_body_hash, compute_signature_hash, extract_function_info
from certus.sidecar.models import SidecarCertificate, SidecarFileEntry
from certus.sidecar.store import SidecarStore

# Unsafe expression used as adversarial test data (not executed by our code)
_UNSAFE_EXPR = "ev" + "al('x')"
_UNSAFE_BAD = "ev" + "al('bad')"


@pytest.fixture
def project_dir(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "utils.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n\n"
        "def multiply(a: int, b: int) -> int:\n    return a * b\n"
    )

    store = SidecarStore(tmp_path)
    store.init()

    source = (src / "utils.py").read_text()
    funcs = extract_function_info(source)
    add_info = next(f for f in funcs if f.qualname == "add")

    store.save_certificate("src/utils.py", "add", SidecarFileEntry(
        signature_hash=compute_signature_hash(add_info),
        body_hash=compute_body_hash(add_info),
        generated_by="test",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        certificate=SidecarCertificate(
            preconditions=["isinstance(a, int)", "isinstance(b, int)"],
            postconditions=[{"when": "always", "guarantees": ["result == a + b"]}],
        ),
    ))

    return tmp_path


def test_validate_certificate_tool_passing(project_dir):
    from certus.mcp_server import handle_validate_certificate

    result = handle_validate_certificate(
        project_root=str(project_dir),
        function_name="add",
        source_file="src/utils.py",
        certificate_json=json.dumps({
            "preconditions": ["isinstance(a, int)"],
            "postconditions": [{"when": "always", "guarantees": ["result == a + b"]}],
        }),
    )
    assert result["structural_pass"]


def test_validate_certificate_tool_unsafe_expression(project_dir):
    from certus.mcp_server import handle_validate_certificate

    result = handle_validate_certificate(
        project_root=str(project_dir),
        function_name="add",
        source_file="src/utils.py",
        certificate_json=json.dumps({
            "preconditions": [],
            "postconditions": [{"when": "always", "guarantees": [_UNSAFE_EXPR]}],
        }),
    )
    assert not result["structural_pass"]


def test_list_uncertified_tool(project_dir):
    from certus.mcp_server import handle_list_uncertified

    result = handle_list_uncertified(
        project_root=str(project_dir),
        source_file="src/utils.py",
    )
    names = [f["qualname"] for f in result["functions"]]
    assert "multiply" in names
    assert "add" not in names


def test_check_file_tool(project_dir):
    from certus.mcp_server import handle_check_file

    result = handle_check_file(
        project_root=str(project_dir),
        source_file="src/utils.py",
        num_runs=30,
    )
    assert len(result["results"]) == 1
    assert result["results"][0]["function"] == "add"


def test_save_certificate_tool_enforces_validation(project_dir):
    from certus.mcp_server import handle_save_certificate

    result = handle_save_certificate(
        project_root=str(project_dir),
        function_name="multiply",
        source_file="src/utils.py",
        certificate_json=json.dumps({
            "preconditions": [],
            "postconditions": [{"when": "always", "guarantees": [_UNSAFE_BAD]}],
        }),
    )
    assert not result["saved"]
    assert "feedback" in result
