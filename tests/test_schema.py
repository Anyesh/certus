import pytest
from certus.spec.schema import (
    Certificate,
    Signature,
    Postcondition,
    Effect,
    LoopInvariant,
    ExceptionalPostcondition,
    Dependency,
    ProofStep,
)


def test_minimal_certificate():
    """A minimal certificate has only signature and postconditions."""
    cert = Certificate(
        certus="0.1",
        function="math_utils.add",
        signature=Signature(
            params={"a": "int", "b": "int"},
            returns="int",
            preconditions=[],
        ),
        postconditions=[
            Postcondition(
                when="always",
                guarantees=["result == a + b"],
            )
        ],
    )
    assert cert.certus == "0.1"
    assert cert.function == "math_utils.add"
    assert len(cert.postconditions) == 1
    assert cert.postconditions[0].guarantees == ["result == a + b"]


def test_minimal_certificate_optional_fields_default_none():
    """Optional fields default to None or empty."""
    cert = Certificate(
        certus="0.1",
        function="f",
        signature=Signature(params={}, returns="None", preconditions=[]),
        postconditions=[],
    )
    assert cert.effects is None
    assert cert.object_invariants is None
    assert cert.invariants is None
    assert cert.raises is None
    assert cert.depends_on is None
    assert cert.assumptions is None
    assert cert.proof is None


def test_standard_depth_certificate():
    """Standard depth adds effects, invariants, depends_on."""
    cert = Certificate(
        certus="0.1",
        function="TokenBucket.consume",
        signature=Signature(
            params={"self": "TokenBucket", "n": "int"},
            returns="bool",
            preconditions=["n >= 1"],
        ),
        postconditions=[
            Postcondition(when="result is True", guarantees=["self.tokens >= 0"]),
            Postcondition(when="result is False", guarantees=["self.tokens < n"]),
        ],
        effects=Effect(
            reads=["self.rate", "self.capacity"],
            mutates=["self.tokens", "self.last_refill"],
        ),
        object_invariants=["0 <= self.tokens <= self.capacity"],
        depends_on=[
            Dependency(
                function="TokenBucket._refill",
                certified=True,
                uses=["0 <= self.tokens <= self.capacity"],
            )
        ],
    )
    assert cert.effects.mutates == ["self.tokens", "self.last_refill"]
    assert cert.depends_on[0].certified is True


def test_full_depth_certificate_with_proof():
    """Full depth adds proof sketch."""
    cert = Certificate(
        certus="0.1",
        function="f",
        signature=Signature(params={"x": "int"}, returns="int", preconditions=[]),
        postconditions=[Postcondition(when="always", guarantees=["result >= 0"])],
        proof=[
            ProofStep(
                step="establish",
                anchor="entry",
                claim="x is an integer",
                check="isinstance(x, int)",
            ),
            ProofStep(
                step="conclude",
                anchor="exit",
                claim="result is non-negative",
                check="result >= 0",
            ),
        ],
    )
    assert len(cert.proof) == 2
    assert cert.proof[0].step == "establish"


def test_dependency_certified_defaults_true():
    dep = Dependency(function="foo", certified=True, uses=["result > 0"])
    assert dep.certified is True


def test_dependency_uncertified():
    dep = Dependency(
        function="sorted", certified=False, uses=["result == sorted(result)"]
    )
    assert dep.certified is False


def test_loop_invariant():
    inv = LoopInvariant(
        loop="while i < len(a)",
        maintains=["result[:i] == sorted(result[:i])"],
        termination="len(a) - i",
    )
    assert inv.termination == "len(a) - i"


def test_exceptional_postcondition():
    exc = ExceptionalPostcondition(
        exception="ValueError",
        when="x < 0",
        guarantees=["str(x) in str(error)"],
    )
    assert exc.exception == "ValueError"


def test_proof_step_derive():
    step = ProofStep(
        step="derive",
        anchor="none",
        claim="elapsed is non-negative",
        check="elapsed >= 0",
    )
    assert step.step == "derive"
    assert step.anchor == "none"


def test_proof_step_branch():
    step = ProofStep(
        step="branch",
        anchor="branch:self.tokens >= n",
        condition="self.tokens >= n",
        true_path={"claim": "tokens sufficient", "check": "self.tokens - n >= 0"},
        false_path={"claim": "tokens insufficient", "check": "self.tokens < n"},
    )
    assert step.condition == "self.tokens >= n"
    assert step.true_path["check"] == "self.tokens - n >= 0"


def test_proof_step_invoke():
    step = ProofStep(
        step="invoke",
        anchor="call:_refill",
        function="TokenBucket._refill",
        claim="refill restores tokens",
        uses=["0 <= self.tokens <= self.capacity"],
    )
    assert step.function == "TokenBucket._refill"
    assert step.uses == ["0 <= self.tokens <= self.capacity"]


def test_certificate_requires_certus_version():
    with pytest.raises(Exception):
        Certificate(
            function="f",
            signature=Signature(params={}, returns="None", preconditions=[]),
            postconditions=[],
        )
