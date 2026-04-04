from __future__ import annotations

import json
from pathlib import Path

import pytest

from certus.sidecar.cache import CheckCache, CheckResult


@pytest.fixture
def cache_dir(tmp_path):
    cache = tmp_path / ".certus" / ".cache"
    cache.mkdir(parents=True)
    return cache


@pytest.fixture
def cache(cache_dir):
    return CheckCache(cache_dir)


def test_get_miss_returns_none(cache):
    assert cache.get("src/utils.py", "add", "body_hash_123") is None


def test_put_and_get(cache):
    result = CheckResult(
        status="passed",
        body_hash="body_hash_123",
        strength=0.85,
        num_guarantees=3,
        proved=0,
        held=3,
        violated=0,
        unverified=0,
    )
    cache.put("src/utils.py", "add", result)
    loaded = cache.get("src/utils.py", "add", "body_hash_123")
    assert loaded is not None
    assert loaded.status == "passed"
    assert loaded.strength == 0.85


def test_cache_miss_on_different_body_hash(cache):
    result = CheckResult(
        status="passed",
        body_hash="old_hash",
        strength=0.85,
        num_guarantees=2,
        proved=0,
        held=2,
        violated=0,
        unverified=0,
    )
    cache.put("src/utils.py", "add", result)
    assert cache.get("src/utils.py", "add", "new_hash") is None


def test_cache_persists_to_disk(cache_dir):
    cache1 = CheckCache(cache_dir)
    result = CheckResult(
        status="passed",
        body_hash="abc",
        strength=0.5,
        num_guarantees=1,
        proved=0,
        held=1,
        violated=0,
        unverified=0,
    )
    cache1.put("src/utils.py", "add", result)
    cache1.flush()

    cache2 = CheckCache(cache_dir)
    loaded = cache2.get("src/utils.py", "add", "abc")
    assert loaded is not None
    assert loaded.status == "passed"


def test_clear(cache):
    result = CheckResult(
        status="passed",
        body_hash="abc",
        strength=0.5,
        num_guarantees=1,
        proved=0,
        held=1,
        violated=0,
        unverified=0,
    )
    cache.put("src/utils.py", "add", result)
    cache.clear()
    assert cache.get("src/utils.py", "add", "abc") is None
