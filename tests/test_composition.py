from certus.spec.schema import Certificate, Signature, Postcondition, Dependency
from certus.checker.composition import check_composition


def _make_cert(name, deps=None, guarantees=None):
    return Certificate(
        certus="0.1",
        function=name,
        signature=Signature(params={}, returns="None", preconditions=[]),
        postconditions=[
            Postcondition(when="always", guarantees=guarantees or ["True"])
        ],
        depends_on=deps,
    )


def test_no_dependencies():
    assert check_composition(_make_cert("f"), {}) == []


def test_certified_dependency_found():
    dep_cert = _make_cert("helper", guarantees=["result > 0"])
    cert = _make_cert(
        "f",
        deps=[
            Dependency(function="helper", certified=True, uses=["result > 0"]),
        ],
    )
    results = check_composition(cert, {"helper": dep_cert})
    assert len(results) == 1
    assert results[0].status == "verified"
    assert results[0].uses_valid is True


def test_certified_dependency_not_found():
    cert = _make_cert(
        "f",
        deps=[
            Dependency(function="helper", certified=True, uses=["result > 0"]),
        ],
    )
    results = check_composition(cert, {})
    assert results[0].status == "not_found"


def test_certified_dependency_uses_mismatch():
    dep_cert = _make_cert("helper", guarantees=["result >= 0"])
    cert = _make_cert(
        "f",
        deps=[
            Dependency(function="helper", certified=True, uses=["result > 100"]),
        ],
    )
    results = check_composition(cert, {"helper": dep_cert})
    assert results[0].uses_valid is False


def test_uncertified_dependency():
    cert = _make_cert(
        "f",
        deps=[
            Dependency(
                function="sorted", certified=False, uses=["result == sorted(result)"]
            ),
        ],
    )
    results = check_composition(cert, {})
    assert results[0].status == "assumed"


def test_circular_dependency():
    cert_a = _make_cert(
        "a", deps=[Dependency(function="b", certified=True, uses=["True"])]
    )
    cert_b = _make_cert(
        "b", deps=[Dependency(function="a", certified=True, uses=["True"])]
    )
    results = check_composition(cert_a, {"a": cert_a, "b": cert_b})
    circular = [r for r in results if "circular" in r.status]
    assert len(circular) > 0
