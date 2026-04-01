"""Certus certificate schema v0.1 as Pydantic models."""

from __future__ import annotations

from pydantic import BaseModel


class Signature(BaseModel):
    params: dict[str, str]
    returns: str
    preconditions: list[str]


class Postcondition(BaseModel):
    when: str
    guarantees: list[str]


class Effect(BaseModel):
    reads: list[str] = []
    mutates: list[str] = []


class LoopInvariant(BaseModel):
    loop: str
    maintains: list[str]
    termination: str | None = None


class ExceptionalPostcondition(BaseModel):
    exception: str
    when: str
    guarantees: list[str]


class Dependency(BaseModel):
    function: str
    certified: bool
    uses: list[str]


class ProofStep(BaseModel):
    step: str  # establish, invoke, derive, branch, conclude
    anchor: str
    claim: str | None = None
    check: str | None = None
    # For invoke steps
    function: str | None = None
    uses: list[str] | None = None
    # For branch steps
    condition: str | None = None
    true_path: dict[str, str] | None = None
    false_path: dict[str, str] | None = None


class Certificate(BaseModel):
    certus: str
    function: str

    # Required (minimal depth)
    signature: Signature
    postconditions: list[Postcondition]

    # Optional (standard depth)
    effects: Effect | None = None
    object_invariants: list[str] | None = None
    invariants: list[LoopInvariant] | None = None
    raises: list[ExceptionalPostcondition] | None = None
    depends_on: list[Dependency] | None = None
    assumptions: list[str] | None = None

    # Optional (full depth)
    proof: list[ProofStep] | None = None
