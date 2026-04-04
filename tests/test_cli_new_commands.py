from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from click.testing import CliRunner

from certus.cli import main
from certus.sidecar.models import SidecarCertificate, SidecarFileEntry
from certus.sidecar.store import SidecarStore


@pytest.fixture
def project(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "utils.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n\n"
        "def sub(a: int, b: int) -> int:\n    return a - b\n"
    )
    return tmp_path


@pytest.fixture
def runner():
    return CliRunner()


def _make_entry(**overrides):
    defaults = dict(
        signature_hash="sig",
        body_hash="body",
        generated_by="test",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        certificate=SidecarCertificate(
            preconditions=[],
            postconditions=[{"when": "always", "guarantees": ["result >= 0"]}],
        ),
    )
    defaults.update(overrides)
    return SidecarFileEntry(**defaults)


def test_init_creates_directory(runner, project):
    result = runner.invoke(main, ["init", "--project-root", str(project)])
    assert result.exit_code == 0
    assert (project / ".certus").is_dir()
    assert (project / ".certus" / ".cache").is_dir()


def test_init_idempotent(runner, project):
    runner.invoke(main, ["init", "--project-root", str(project)])
    result = runner.invoke(main, ["init", "--project-root", str(project)])
    assert result.exit_code == 0


def test_status_no_certificates(runner, project):
    store = SidecarStore(project)
    store.init()
    result = runner.invoke(main, ["status", "--project-root", str(project)])
    assert result.exit_code == 0
    assert "No certificates found" in result.output


def test_status_with_certificates(runner, project):
    store = SidecarStore(project)
    store.init()
    store.save_certificate("src/utils.py", "add", _make_entry())

    result = runner.invoke(main, ["status", "--project-root", str(project)])
    assert result.exit_code == 0
    assert "src/utils.py" in result.output
    assert "1 certified" in result.output


def test_clean_removes_orphaned(runner, project):
    store = SidecarStore(project)
    store.init()
    store.save_certificate("src/utils.py", "nonexistent_func", _make_entry())

    result = runner.invoke(main, ["clean", "--project-root", str(project)])
    assert result.exit_code == 0
    assert "nonexistent_func" in result.output

    loaded = store.load_file("src/utils.py")
    assert "nonexistent_func" not in loaded.functions
