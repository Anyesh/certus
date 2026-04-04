from __future__ import annotations

import pytest

from certus.sidecar.hashing import (
    compute_signature_hash,
    compute_body_hash,
    extract_function_info,
)


SAMPLE_SOURCE = """
def add(a: int, b: int) -> int:
    return a + b

def greet(name: str) -> str:
    return f"hello {name}"

class Calculator:
    def multiply(self, x: float, y: float) -> float:
        return x * y
"""


def test_extract_function_info_finds_top_level():
    funcs = extract_function_info(SAMPLE_SOURCE)
    names = [f.qualname for f in funcs]
    assert "add" in names
    assert "greet" in names


def test_extract_function_info_finds_methods():
    funcs = extract_function_info(SAMPLE_SOURCE)
    names = [f.qualname for f in funcs]
    assert "Calculator.multiply" in names


def test_signature_hash_stable():
    funcs = extract_function_info(SAMPLE_SOURCE)
    add_info = next(f for f in funcs if f.qualname == "add")
    h1 = compute_signature_hash(add_info)
    h2 = compute_signature_hash(add_info)
    assert h1 == h2


def test_signature_hash_changes_on_param_rename():
    source_v1 = "def foo(x: int) -> int:\n    return x"
    source_v2 = "def foo(y: int) -> int:\n    return y"
    f1 = extract_function_info(source_v1)[0]
    f2 = extract_function_info(source_v2)[0]
    assert compute_signature_hash(f1) != compute_signature_hash(f2)


def test_signature_hash_changes_on_type_change():
    source_v1 = "def foo(x: int) -> int:\n    return x"
    source_v2 = "def foo(x: float) -> int:\n    return x"
    f1 = extract_function_info(source_v1)[0]
    f2 = extract_function_info(source_v2)[0]
    assert compute_signature_hash(f1) != compute_signature_hash(f2)


def test_body_hash_stable():
    funcs = extract_function_info(SAMPLE_SOURCE)
    add_info = next(f for f in funcs if f.qualname == "add")
    h1 = compute_body_hash(add_info)
    h2 = compute_body_hash(add_info)
    assert h1 == h2


def test_body_hash_changes_on_implementation_change():
    source_v1 = "def foo(x: int) -> int:\n    return x + 1"
    source_v2 = "def foo(x: int) -> int:\n    return x + 2"
    f1 = extract_function_info(source_v1)[0]
    f2 = extract_function_info(source_v2)[0]
    assert compute_body_hash(f1) != compute_body_hash(f2)


def test_body_hash_ignores_whitespace_only_changes():
    source_v1 = "def foo(x: int) -> int:\n    return x + 1"
    source_v2 = "def foo(x: int) -> int:\n    return x  +  1"
    f1 = extract_function_info(source_v1)[0]
    f2 = extract_function_info(source_v2)[0]
    # AST-based hashing normalizes whitespace away
    assert compute_body_hash(f1) == compute_body_hash(f2)


def test_extract_function_info_returns_source():
    funcs = extract_function_info(SAMPLE_SOURCE)
    add_info = next(f for f in funcs if f.qualname == "add")
    assert "return a + b" in add_info.source
