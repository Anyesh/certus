from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from certus.sidecar.hashing import (
    compute_body_hash,
    compute_signature_hash,
    extract_function_info,
)
from certus.sidecar.models import SidecarCertificate, SidecarFileEntry
from certus.sidecar.store import SidecarStore


@pytest.fixture
def certus_project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()

    source_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    (src / "math_utils.py").write_text(source_code)

    store = SidecarStore(tmp_path)
    store.init()

    funcs = extract_function_info(source_code)
    add_info = funcs[0]

    store.save_certificate(
        "src/math_utils.py",
        "add",
        SidecarFileEntry(
            signature_hash=compute_signature_hash(add_info),
            body_hash=compute_body_hash(add_info),
            generated_by="test",
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            certificate=SidecarCertificate(
                preconditions=["isinstance(a, int)", "isinstance(b, int)"],
                postconditions=[{"when": "always", "guarantees": ["result == a + b"]}],
            ),
        ),
    )

    return tmp_path


def test_plugin_collects_certus_items(certus_project):
    from certus.pytest_plugin import collect_certus_items

    items = collect_certus_items(certus_project)
    assert len(items) == 1
    assert items[0]["function"] == "add"
    assert items[0]["source_file"] == "src/math_utils.py"


def test_plugin_runs_via_pytester(pytester):
    src = pytester.path / "src"
    src.mkdir()
    (src / "utils.py").write_text("def double(x: int) -> int:\n    return x * 2\n")

    store = SidecarStore(pytester.path)
    store.init()

    funcs = extract_function_info((src / "utils.py").read_text())
    info = funcs[0]

    store.save_certificate(
        "src/utils.py",
        "double",
        SidecarFileEntry(
            signature_hash=compute_signature_hash(info),
            body_hash=compute_body_hash(info),
            generated_by="test",
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            certificate=SidecarCertificate(
                preconditions=["isinstance(x, int)"],
                postconditions=[{"when": "always", "guarantees": ["result == x * 2"]}],
            ),
        ),
    )

    pytester.makepyfile(test_basic="def test_one():\n    assert True\n")

    result = pytester.runpytest("-v", "--certus-runs=30")
    result.stdout.fnmatch_lines(["*certus::*double*PASSED*"])


def test_plugin_skip_flag(pytester):
    pytester.makepyfile(test_basic="def test_one():\n    assert True\n")

    result = pytester.runpytest("-v", "--certus-skip")
    result.stdout.no_fnmatch_line("*certus::*")
