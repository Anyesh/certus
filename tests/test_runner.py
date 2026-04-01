from certus.spec.schema import Certificate, Signature, Postcondition
from certus.checker.runner import run_checker


SOURCE_ABS = """\
def absolute(x: int) -> int:
    if x < 0:
        return -x
    return x
"""


def absolute(x: int) -> int:
    if x < 0:
        return -x
    return x


def bad(x: int) -> int:
    return x


SOURCE_BAD = """\
def bad(x: int) -> int:
    return x
"""


def test_fast_mode_valid():
    cert = Certificate(
        certus="0.1", function="absolute",
        signature=Signature(params={"x": "int"}, returns="int", preconditions=["isinstance(x, int)"]),
        postconditions=[Postcondition(when="always", guarantees=["result >= 0"])],
    )
    report = run_checker(absolute, cert, SOURCE_ABS, mode="fast")
    assert report.summary.violated == 0
    assert report.summary.confidence > 0


def test_fast_mode_violation():
    cert = Certificate(
        certus="0.1", function="bad",
        signature=Signature(params={"x": "int"}, returns="int", preconditions=["isinstance(x, int)"]),
        postconditions=[Postcondition(when="always", guarantees=["result >= 0"])],
    )
    report = run_checker(bad, cert, SOURCE_BAD, mode="fast")
    assert report.summary.violated > 0


def test_fast_mode_uses_hypothesis():
    cert = Certificate(
        certus="0.1", function="absolute",
        signature=Signature(params={"x": "int"}, returns="int", preconditions=[]),
        postconditions=[Postcondition(when="always", guarantees=["result >= 0"])],
    )
    report = run_checker(absolute, cert, SOURCE_ABS, mode="fast")
    for claim in report.claims:
        if claim.status == "held":
            assert claim.method == "hypothesis"


def test_validation_errors_produce_unverified():
    UNSAFE_EXPR = "eval" + "('True')"
    cert = Certificate(
        certus="0.1", function="absolute",
        signature=Signature(params={"x": "int"}, returns="int", preconditions=[UNSAFE_EXPR]),
        postconditions=[Postcondition(when="always", guarantees=["result >= 0"])],
    )
    report = run_checker(absolute, cert, SOURCE_ABS, mode="fast")
    assert report.summary.unverified > 0


def test_report_includes_strength():
    cert = Certificate(
        certus="0.1", function="absolute",
        signature=Signature(params={"x": "int"}, returns="int", preconditions=["isinstance(x, int)"]),
        postconditions=[Postcondition(when="always", guarantees=["result >= 0"])],
    )
    report = run_checker(absolute, cert, SOURCE_ABS, mode="fast")
    assert 0 <= report.strength.rejection_rate <= 1.0


def test_certificate_depth_detection():
    cert = Certificate(
        certus="0.1", function="absolute",
        signature=Signature(params={"x": "int"}, returns="int", preconditions=[]),
        postconditions=[Postcondition(when="always", guarantees=["result >= 0"])],
    )
    report = run_checker(absolute, cert, SOURCE_ABS, mode="fast")
    assert report.certificate_depth == "minimal"
