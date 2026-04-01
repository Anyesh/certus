from certus.spec.schema import Certificate, Signature, Postcondition
from certus.checker.dynamic import run_dynamic_checks


def _make_cert(**overrides):
    defaults = {
        "certus": "0.1",
        "function": "f",
        "signature": Signature(
            params={"x": "int"}, returns="int", preconditions=["isinstance(x, int)"]
        ),
        "postconditions": [Postcondition(when="always", guarantees=["result >= 0"])],
    }
    defaults.update(overrides)
    return Certificate(**defaults)


def test_passing_postcondition():
    def f(x: int) -> int:
        return abs(x)

    cert = _make_cert()
    results = run_dynamic_checks(f, cert, num_runs=100)
    assert all(r.status == "held" for r in results)
    assert all(r.runs == 100 for r in results)


def test_failing_postcondition():
    def f(x: int) -> int:
        return x

    cert = _make_cert()
    results = run_dynamic_checks(f, cert, num_runs=1000)
    violated = [r for r in results if r.status == "violated"]
    assert len(violated) > 0
    assert violated[0].counterexample is not None


def test_precondition_filters_inputs():
    def f(x: int) -> int:
        assert x > 0
        return x

    cert = _make_cert(
        signature=Signature(
            params={"x": "int"},
            returns="int",
            preconditions=["isinstance(x, int)", "x > 0"],
        ),
        postconditions=[Postcondition(when="always", guarantees=["result > 0"])],
    )
    results = run_dynamic_checks(f, cert, num_runs=100)
    assert all(r.status == "held" for r in results)


def test_multiple_guarantees():
    def f(x: int) -> int:
        return abs(x) + 1

    cert = _make_cert(
        postconditions=[
            Postcondition(when="always", guarantees=["result >= 0", "result >= 1"]),
        ]
    )
    results = run_dynamic_checks(f, cert, num_runs=100)
    assert len(results) == 2
    assert all(r.status == "held" for r in results)


def test_branched_postconditions():
    def f(x: int) -> int:
        if x > 0:
            return x
        return -x

    cert = _make_cert(
        postconditions=[
            Postcondition(when="result > 0", guarantees=["result == abs(x)"]),
            Postcondition(when="result == 0", guarantees=["x == 0"]),
        ]
    )
    results = run_dynamic_checks(f, cert, num_runs=200)
    held = [r for r in results if r.status == "held"]
    assert len(held) >= 1
