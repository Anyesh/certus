from certus.checker.report import (
    ClaimResult,
    DependencyResult,
    StrengthScore,
    VerificationReport,
)


def test_claim_result_proved():
    c = ClaimResult(claim="result > 0", status="proved", method="z3")
    assert c.confidence == 1.0


def test_claim_result_held():
    c = ClaimResult(claim="result > 0", status="held", method="hypothesis", runs=10000)
    assert 0 < c.confidence < 1.0


def test_claim_result_violated():
    c = ClaimResult(
        claim="result > 0",
        status="violated",
        method="hypothesis",
        counterexample={"x": -1},
    )
    assert c.confidence == 0.0


def test_claim_result_unverified():
    c = ClaimResult(claim="result > 0", status="unverified")
    assert c.confidence == 0.0


def test_report_summary():
    report = VerificationReport(
        function="test.f",
        certificate_depth="minimal",
        claims=[
            ClaimResult(claim="result > 0", status="proved", method="z3"),
            ClaimResult(
                claim="result < 100", status="held", method="hypothesis", runs=10000
            ),
            ClaimResult(claim="result != 50", status="proved", method="z3"),
        ],
        dependencies=[],
        strength=StrengthScore(rejection_rate=0.85),
    )
    assert report.summary.proved == 2
    assert report.summary.held == 1
    assert report.summary.violated == 0
    assert report.summary.confidence > 0.9


def test_report_with_violation():
    report = VerificationReport(
        function="test.f",
        certificate_depth="minimal",
        claims=[
            ClaimResult(
                claim="result > 0",
                status="violated",
                method="hypothesis",
                counterexample={"x": -1},
            ),
        ],
        dependencies=[],
        strength=StrengthScore(rejection_rate=0.5),
    )
    assert report.summary.violated == 1
    assert report.summary.confidence == 0.0
