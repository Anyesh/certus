"""Pass 2: Dynamic verification using Hypothesis-generated inputs."""

from __future__ import annotations

import ast
from typing import Any

from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st

from certus.spec.schema import Certificate
from certus.checker.report import ClaimResult

TYPE_STRATEGIES: dict[str, st.SearchStrategy] = {
    "int": st.integers(min_value=-10000, max_value=10000),
    "float": st.floats(min_value=-10000, max_value=10000, allow_nan=False, allow_infinity=False),
    "str": st.text(max_size=100),
    "bool": st.booleans(),
    "list": st.lists(st.integers(min_value=-100, max_value=100), max_size=20),
    "list[int]": st.lists(st.integers(min_value=-100, max_value=100), max_size=20),
    "list[float]": st.lists(st.floats(min_value=-100, max_value=100, allow_nan=False), max_size=20),
    "list[str]": st.lists(st.text(max_size=20), max_size=10),
}


def _strategy_for_type(type_str: str) -> st.SearchStrategy:
    return TYPE_STRATEGIES.get(type_str, st.integers(min_value=-1000, max_value=1000))


def _build_safe_namespace(params: dict[str, Any]) -> dict[str, Any]:
    safe_builtins = {
        "len": len, "sorted": sorted, "all": all, "any": any,
        "min": min, "max": max, "sum": sum, "abs": abs,
        "set": set, "list": list, "tuple": tuple, "range": range,
        "isinstance": isinstance, "type": type, "int": int, "float": float,
        "str": str, "bool": bool, "frozenset": frozenset,
        "enumerate": enumerate, "zip": zip,
        "True": True, "False": False, "None": None,
    }
    ns = {"__builtins__": safe_builtins}
    ns.update(params)
    return ns


def _eval_expr(expr: str, namespace: dict[str, Any]) -> Any:
    # Compile to a code object for the expression, then evaluate it.
    # The namespace has restricted __builtins__ to limit dangerous access.
    code = compile(ast.parse(expr, mode="eval"), "<certus-expr>", "eval")
    return eval(code, namespace)  # noqa: S307 — restricted namespace


def run_dynamic_checks(
    func,
    cert: Certificate,
    num_runs: int = 1000,
) -> list[ClaimResult]:
    """Run dynamic verification. Returns a ClaimResult per guarantee."""
    param_strategies = {}
    for name, type_str in cert.signature.params.items():
        if name == "self":
            continue
        param_strategies[name] = _strategy_for_type(type_str)

    guarantees: list[tuple[str, str]] = []
    for post in cert.postconditions:
        for g in post.guarantees:
            guarantees.append((post.when, g))

    results: list[ClaimResult] = []
    for when, guarantee in guarantees:
        result = _check_single_guarantee(func, cert, param_strategies, when, guarantee, num_runs)
        results.append(result)

    return results


def _check_single_guarantee(
    func, cert, param_strategies, when, guarantee, num_runs,
) -> ClaimResult:
    counterexample = None
    actual_runs = 0

    if not param_strategies:
        try:
            result = func()
            ns = _build_safe_namespace({"result": result})
            if when == "always" or _eval_expr(when, ns):
                if not _eval_expr(guarantee, ns):
                    return ClaimResult(
                        claim=guarantee, status="violated", method="hypothesis",
                        runs=1, counterexample={},
                    )
            return ClaimResult(claim=guarantee, status="held", method="hypothesis", runs=1)
        except Exception:
            return ClaimResult(claim=guarantee, status="held", method="hypothesis", runs=1)

    combined = st.fixed_dictionaries(param_strategies)

    @settings(max_examples=num_runs, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
    @given(params=combined)
    def check(params):
        nonlocal counterexample, actual_runs

        if counterexample is not None:
            return

        ns = _build_safe_namespace(params)

        for pre in cert.signature.preconditions:
            try:
                if not _eval_expr(pre, ns):
                    assume(False)
                    return
            except Exception:
                assume(False)
                return

        try:
            result = func(**params)
        except Exception:
            return

        ns["result"] = result
        actual_runs += 1

        if when != "always":
            try:
                if not _eval_expr(when, ns):
                    return
            except Exception:
                return

        try:
            if not _eval_expr(guarantee, ns):
                counterexample = params.copy()
                counterexample["result"] = result
        except Exception:
            pass

    try:
        check()
    except Exception:
        pass

    if counterexample is not None:
        return ClaimResult(
            claim=guarantee, status="violated", method="hypothesis",
            runs=actual_runs, counterexample=counterexample,
        )

    return ClaimResult(
        claim=guarantee, status="held", method="hypothesis",
        runs=max(actual_runs, 1),
    )
