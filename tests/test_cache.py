from certus.checker.cache import VerificationCache
from certus.checker.report import VerificationReport, ClaimResult, StrengthScore


def _make_report():
    return VerificationReport(
        function="f",
        certificate_depth="minimal",
        claims=[ClaimResult(claim="result > 0", status="proved", method="z3")],
        dependencies=[],
        strength=StrengthScore(rejection_rate=0.5),
    )


def test_cache_miss():
    assert VerificationCache().get("src", "cert", "f") is None


def test_cache_hit():
    cache = VerificationCache()
    cache.put("src", "cert", "f", _make_report())
    assert cache.get("src", "cert", "f") is not None


def test_invalidation_on_source_change():
    cache = VerificationCache()
    cache.put("src_v1", "cert", "f", _make_report())
    assert cache.get("src_v2", "cert", "f") is None


def test_invalidation_on_cert_change():
    cache = VerificationCache()
    cache.put("src", "cert_v1", "f", _make_report())
    assert cache.get("src", "cert_v2", "f") is None


def test_clear():
    cache = VerificationCache()
    cache.put("src", "cert", "f", _make_report())
    cache.clear()
    assert cache.get("src", "cert", "f") is None
