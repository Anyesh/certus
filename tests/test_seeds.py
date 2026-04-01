"""End-to-end: run the checker on all seed certificates."""

import inspect
from certus.checker.runner import run_checker


def _get_source(func):
    """Get source code of the wrapped function."""
    try:
        return inspect.getsource(func.__wrapped__)
    except (AttributeError, OSError):
        return inspect.getsource(func)


class TestPureFunctionSeeds:
    def test_merge_sorted(self):
        from seeds.pure_functions.merge_sorted import merge_sorted
        cert = merge_sorted.__certus__
        source = _get_source(merge_sorted)
        report = run_checker(merge_sorted, cert, source, mode="fast", num_runs=500)
        assert report.summary.violated == 0, _violations(report)

    def test_kth_smallest(self):
        from seeds.pure_functions.kth_smallest import kth_smallest
        cert = kth_smallest.__certus__
        source = _get_source(kth_smallest)
        report = run_checker(kth_smallest, cert, source, mode="fast", num_runs=500)
        assert report.summary.violated == 0, _violations(report)

    def test_fibonacci(self):
        from seeds.pure_functions.fibonacci import fibonacci
        cert = fibonacci.__certus__
        source = _get_source(fibonacci)
        report = run_checker(fibonacci, cert, source, mode="fast", num_runs=500)
        assert report.summary.violated == 0, _violations(report)


class TestErrorHandlingSeeds:
    def test_safe_divide(self):
        from seeds.error_handling.safe_divide import safe_divide
        cert = safe_divide.__certus__
        source = _get_source(safe_divide)
        report = run_checker(safe_divide, cert, source, mode="fast", num_runs=500)
        assert report.summary.violated == 0, _violations(report)

    def test_try_parse_int(self):
        from seeds.error_handling.parse_int import try_parse_int
        cert = try_parse_int.__certus__
        source = _get_source(try_parse_int)
        report = run_checker(try_parse_int, cert, source, mode="fast", num_runs=500)
        assert report.summary.violated == 0, _violations(report)


class TestBrokenSeeds:
    def test_bad_postcondition_fails(self):
        from seeds.broken.bad_postcondition import absolute_value
        cert = absolute_value.__certus__
        source = _get_source(absolute_value)
        report = run_checker(absolute_value, cert, source, mode="fast", num_runs=500)
        assert report.summary.violated > 0

    def test_bad_expression_fails_validation(self):
        from seeds.broken.bad_expression import identity
        cert = identity.__certus__
        source = _get_source(identity)
        report = run_checker(identity, cert, source, mode="fast")
        assert report.summary.unverified > 0


def _violations(report):
    return [c for c in report.claims if c.status == "violated"]
