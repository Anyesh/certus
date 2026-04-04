from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from certus.sidecar.models import SidecarCertificate, SidecarFile, SidecarFileEntry
from certus.sidecar.store import SidecarStore


@pytest.fixture
def project_dir(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "utils.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n\n"
        "def sub(a: int, b: int) -> int:\n    return a - b\n"
    )
    return tmp_path


@pytest.fixture
def store(project_dir):
    return SidecarStore(project_dir)


def _make_entry(**overrides):
    defaults = dict(
        signature_hash="sig123",
        body_hash="body456",
        generated_by="test",
        generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        certificate=SidecarCertificate(
            preconditions=["a > 0"],
            postconditions=[{"when": "always", "guarantees": ["result > 0"]}],
        ),
    )
    defaults.update(overrides)
    return SidecarFileEntry(**defaults)


def test_init_creates_certus_dir(store, project_dir):
    store.init()
    assert (project_dir / ".certus").is_dir()
    assert (project_dir / ".certus" / ".cache").is_dir()
    gitignore = (project_dir / ".certus" / ".cache" / ".gitignore").read_text()
    assert "*" in gitignore


def test_save_and_load_certificate(store, project_dir):
    store.init()
    entry = _make_entry()
    store.save_certificate("src/utils.py", "add", entry)

    loaded = store.load_file("src/utils.py")
    assert loaded is not None
    assert "add" in loaded.functions
    assert loaded.functions["add"].signature_hash == "sig123"


def test_load_nonexistent_returns_none(store):
    store.init()
    assert store.load_file("nonexistent.py") is None


def test_save_multiple_functions(store):
    store.init()
    store.save_certificate("src/utils.py", "add", _make_entry(signature_hash="aaa"))
    store.save_certificate("src/utils.py", "sub", _make_entry(signature_hash="bbb"))

    loaded = store.load_file("src/utils.py")
    assert len(loaded.functions) == 2
    assert loaded.functions["add"].signature_hash == "aaa"
    assert loaded.functions["sub"].signature_hash == "bbb"


def test_save_overwrites_existing_function(store):
    store.init()
    store.save_certificate("src/utils.py", "add", _make_entry(signature_hash="old"))
    store.save_certificate("src/utils.py", "add", _make_entry(signature_hash="new"))

    loaded = store.load_file("src/utils.py")
    assert loaded.functions["add"].signature_hash == "new"


def test_sidecar_path_mirrors_source(store, project_dir):
    store.init()
    store.save_certificate("src/utils.py", "add", _make_entry())

    expected_path = project_dir / ".certus" / "src" / "utils.certus.json"
    assert expected_path.exists()


def test_list_certified_files(store):
    store.init()
    store.save_certificate("src/utils.py", "add", _make_entry())
    store.save_certificate("src/auth.py", "login", _make_entry())

    files = store.list_certified_files()
    source_files = {f.source_file for f in files}
    assert "src/utils.py" in source_files
    assert "src/auth.py" in source_files


def test_remove_certificate(store):
    store.init()
    store.save_certificate("src/utils.py", "add", _make_entry())
    store.save_certificate("src/utils.py", "sub", _make_entry())

    store.remove_certificate("src/utils.py", "add")
    loaded = store.load_file("src/utils.py")
    assert "add" not in loaded.functions
    assert "sub" in loaded.functions


def test_get_uncertified_functions(store, project_dir):
    store.init()
    store.save_certificate("src/utils.py", "add", _make_entry())

    uncertified = store.get_uncertified_functions("src/utils.py")
    names = [f.qualname for f in uncertified]
    assert "sub" in names
    assert "add" not in names


def test_get_stale_certificates(store, project_dir):
    store.init()
    store.save_certificate(
        "src/utils.py", "add", _make_entry(signature_hash="wrong_hash")
    )

    stale = store.get_stale_certificates("src/utils.py")
    assert any(s[0] == "add" and s[1] == "signature" for s in stale)
