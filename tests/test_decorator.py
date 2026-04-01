import os
import pytest
from unittest.mock import patch
from certus.decorator import certus
from certus.spec.schema import Certificate


def test_decorator_stores_metadata():
    @certus(
        preconditions=["x > 0"],
        postconditions=[{"when": "always", "guarantees": ["result > 0"]}],
    )
    def square(x: int) -> int:
        return x * x

    assert hasattr(square, "__certus__")
    cert = square.__certus__
    assert isinstance(cert, Certificate)
    assert cert.signature.preconditions == ["x > 0"]


def test_decorator_disabled_mode_is_noop():
    @certus(
        preconditions=["x > 0"],
        postconditions=[{"when": "always", "guarantees": ["result > 0"]}],
    )
    def square(x: int) -> int:
        return x * x

    assert square(-3) == 9


def test_decorator_assert_mode_passes():
    with patch.dict(os.environ, {"CERTUS_MODE": "assert"}):

        @certus(
            preconditions=["x > 0"],
            postconditions=[{"when": "always", "guarantees": ["result > 0"]}],
        )
        def square(x: int) -> int:
            return x * x

        assert square(3) == 9


def test_decorator_assert_mode_fails_postcondition():
    with patch.dict(os.environ, {"CERTUS_MODE": "assert"}):

        @certus(
            preconditions=[],
            postconditions=[{"when": "always", "guarantees": ["result > 100"]}],
        )
        def small(x: int) -> int:
            return x

        with pytest.raises(AssertionError, match="Postcondition failed"):
            small(5)


def test_decorator_assert_mode_fails_precondition():
    with patch.dict(os.environ, {"CERTUS_MODE": "assert"}):

        @certus(
            preconditions=["x > 0"],
            postconditions=[{"when": "always", "guarantees": ["result > 0"]}],
        )
        def square(x: int) -> int:
            return x * x

        with pytest.raises(AssertionError, match="Precondition failed"):
            square(-1)


def test_decorator_preserves_function_name():
    @certus(preconditions=[], postconditions=[])
    def my_func():
        pass

    assert my_func.__name__ == "my_func"


def test_decorator_with_effects():
    @certus(
        preconditions=[],
        postconditions=[{"when": "always", "guarantees": ["result is None"]}],
        effects={"reads": ["self.x"], "mutates": ["self.y"]},
    )
    def method(self):
        return None

    assert method.__certus__.effects.reads == ["self.x"]


def test_decorator_to_certificate():
    @certus(
        preconditions=["a > 0"],
        postconditions=[{"when": "always", "guarantees": ["result == a + b"]}],
        assumptions=["no overflow"],
    )
    def add(a: int, b: int) -> int:
        return a + b

    cert = add.__certus__
    assert cert.certus == "0.1"
    assert cert.assumptions == ["no overflow"]
