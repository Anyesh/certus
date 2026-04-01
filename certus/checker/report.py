"""Verification report data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULT_VIOLATION_FRACTION = 0.001


@dataclass
class ClaimResult:
    claim: str
    status: str  # proved, held, violated, unverified
    method: str | None = None
    runs: int | None = None
    counterexample: dict[str, Any] | None = None

    @property
    def confidence(self) -> float:
        if self.status == "proved":
            return 1.0
        if self.status == "held" and self.runs:
            return 1.0 - (1.0 - DEFAULT_VIOLATION_FRACTION) ** self.runs
        return 0.0


@dataclass
class DependencyResult:
    function: str
    status: str  # verified, unverified, not_found, assumed, circular
    uses_valid: bool


@dataclass
class StrengthScore:
    rejection_rate: float


@dataclass
class ReportSummary:
    proved: int
    held: int
    violated: int
    unverified: int
    confidence: float


@dataclass
class VerificationReport:
    function: str
    certificate_depth: str
    claims: list[ClaimResult]
    dependencies: list[DependencyResult]
    strength: StrengthScore

    @property
    def summary(self) -> ReportSummary:
        proved = sum(1 for c in self.claims if c.status == "proved")
        held = sum(1 for c in self.claims if c.status == "held")
        violated = sum(1 for c in self.claims if c.status == "violated")
        unverified = sum(1 for c in self.claims if c.status == "unverified")

        if violated > 0 or not self.claims:
            confidence = 0.0
        else:
            confidence = 1.0
            for c in self.claims:
                confidence *= c.confidence

        return ReportSummary(
            proved=proved,
            held=held,
            violated=violated,
            unverified=unverified,
            confidence=round(confidence, 4),
        )
