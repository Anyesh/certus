import pytest
from certus.spec.schema import Certificate, Signature, Postcondition, ProofStep, Dependency
from certus.checker.validation import validate_certificate

# These strings intentionally contain forbidden names to test that the validator
# correctly rejects them. They are never executed.
_FORBIDDEN_EVAL = "eval('True')"
_FORBIDDEN_IMPORT = "__import__('os')"
_FORBIDDEN_OPEN = "open('/etc/passwd')"
_FORBIDDEN_EXEC_CHECK = "exec('x')"
_FORBIDDEN_EXEC_DEP = "exec('bad')"


def _make_cert(**kwargs):
    defaults = {
        "certus": "0.1",
        "function": "test_module.f",
        "signature": Signature(params={"x": "int"}, returns="int", preconditions=[]),
        "postconditions": [Postcondition(when="always", guarantees=["result >= 0"])],
    }
    defaults.update(kwargs)
    return Certificate(**defaults)


SOURCE = """\
def f(x: int) -> int:
    if x > 0:
        return x
    return -x
"""


def test_valid_minimal_certificate():
    errors = validate_certificate(_make_cert(), SOURCE)
    assert errors == []


def test_invalid_expression_in_precondition():
    cert = _make_cert(
        signature=Signature(params={"x": "int"}, returns="int", preconditions=[_FORBIDDEN_EVAL]),
    )
    errors = validate_certificate(cert, SOURCE)
    assert any("eval" in e for e in errors)


def test_invalid_expression_in_postcondition():
    cert = _make_cert(
        postconditions=[Postcondition(when="always", guarantees=[_FORBIDDEN_IMPORT])],
    )
    errors = validate_certificate(cert, SOURCE)
    assert any("__import__" in e for e in errors)


def test_invalid_expression_in_when():
    cert = _make_cert(
        postconditions=[Postcondition(when=_FORBIDDEN_OPEN, guarantees=["result >= 0"])],
    )
    errors = validate_certificate(cert, SOURCE)
    assert any("open" in e for e in errors)


def test_proof_step_anchor_establish():
    cert = _make_cert(proof=[
        ProofStep(step="establish", anchor="entry", claim="x is int", check="isinstance(x, int)"),
        ProofStep(step="conclude", anchor="exit", claim="done", check="result >= 0"),
    ])
    errors = validate_certificate(cert, SOURCE)
    assert errors == []


def test_proof_step_invalid_check_expression():
    cert = _make_cert(proof=[
        ProofStep(step="establish", anchor="entry", claim="x", check=_FORBIDDEN_EXEC_CHECK),
    ])
    errors = validate_certificate(cert, SOURCE)
    assert any("exec" in e for e in errors)


def test_proof_step_branch_anchor_resolves():
    cert = _make_cert(proof=[
        ProofStep(
            step="branch", anchor="branch:x > 0", condition="x > 0",
            true_path={"claim": "pos", "check": "x > 0"},
            false_path={"claim": "neg", "check": "x <= 0"},
        ),
    ])
    errors = validate_certificate(cert, SOURCE)
    assert errors == []


def test_proof_step_branch_anchor_not_found():
    cert = _make_cert(proof=[
        ProofStep(
            step="branch", anchor="branch:y > 100", condition="y > 100",
            true_path={"claim": "a", "check": "True"},
            false_path={"claim": "b", "check": "True"},
        ),
    ])
    errors = validate_certificate(cert, SOURCE)
    assert any("anchor" in e.lower() for e in errors)


def test_invalid_step_type():
    cert = _make_cert(proof=[
        ProofStep(step="unknown_step", anchor="entry", claim="x", check="True"),
    ])
    errors = validate_certificate(cert, SOURCE)
    assert any("step type" in e.lower() for e in errors)


def test_depends_on_uses_validated():
    cert = _make_cert(depends_on=[
        Dependency(function="helper", certified=True, uses=[_FORBIDDEN_EXEC_DEP]),
    ])
    errors = validate_certificate(cert, SOURCE)
    assert any("exec" in e for e in errors)
