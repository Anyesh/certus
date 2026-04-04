"""Checker runner: orchestrates verification passes and produces reports."""

from __future__ import annotations

import random

from certus.spec.schema import Certificate
from certus.checker.validation import validate_certificate
from certus.checker.dynamic import run_dynamic_checks, _build_safe_namespace, _eval_expr
from certus.checker.composition import check_composition
from certus.checker.report import (
    ClaimResult,
    StrengthScore,
    VerificationReport,
)

# Alias so the module surface matches what callers expect
_eval_safe = _eval_expr


def _detect_depth(cert: Certificate) -> str:
    if cert.proof:
        return "full"
    if cert.invariants or cert.effects or cert.depends_on:
        return "standard"
    return "minimal"


def _measure_strength(cert: Certificate, num_samples: int = 200) -> StrengthScore:
    all_guarantees = []
    for post in cert.postconditions:
        if post.when == "always":
            all_guarantees.extend(post.guarantees)

    if not all_guarantees:
        return StrengthScore(rejection_rate=0.0)

    rejected = 0
    tested = 0

    for _ in range(num_samples):
        fake_result = random.randint(-10000, 10000)
        ns = _build_safe_namespace({"result": fake_result})
        for name in cert.signature.params:
            if name == "self":
                continue
            ns[name] = random.randint(-100, 100)

        tested += 1
        for g in all_guarantees:
            try:
                if not _eval_safe(g, ns):
                    rejected += 1
                    break
            except Exception:
                rejected += 1
                break

    return StrengthScore(rejection_rate=round(rejected / max(tested, 1), 4))


def run_checker(
    func,
    cert: Certificate,
    source: str,
    mode: str = "fast",
    registry: dict[str, Certificate] | None = None,
    num_runs: int = 1000,
) -> VerificationReport:
    depth = _detect_depth(cert)
    claims: list[ClaimResult] = []
    dep_results = []

    # Pass 0: Validation
    validation_errors = validate_certificate(cert, source)
    if validation_errors:
        for err in validation_errors:
            claims.append(ClaimResult(claim=err, status="unverified"))
        return VerificationReport(
            function=cert.function,
            certificate_depth=depth,
            claims=claims,
            dependencies=dep_results,
            strength=StrengthScore(rejection_rate=0.0),
        )

    # Pass 2: Dynamic (skipped in structural mode)
    if mode != "structural":
        dynamic_results = run_dynamic_checks(func, cert, num_runs=num_runs)
        claims.extend(dynamic_results)

    # Pass 3: Composition
    if cert.depends_on and registry is not None:
        dep_results = check_composition(cert, registry)

    strength = _measure_strength(cert)

    return VerificationReport(
        function=cert.function,
        certificate_depth=depth,
        claims=claims,
        dependencies=dep_results,
        strength=strength,
    )


def check_from_sidecar(
    function_name: str,
    entry: "SidecarFileEntry",
    source: str,
    mode: str = "fast",
    num_runs: int = 1000,
) -> VerificationReport:
    import ast  # noqa

    from certus.sidecar.models import SidecarFileEntry  # noqa
    from certus.spec.schema import Postcondition, Signature  # noqa

    sc = entry.certificate

    tree = ast.parse(source)
    func_node = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == function_name or function_name.endswith(f".{node.name}"):
                func_node = node
                break

    params = {}
    returns = "Any"
    if func_node:
        for arg in func_node.args.args:
            ann = arg.annotation
            params[arg.arg] = ast.unparse(ann) if ann else "Any"
        if func_node.returns:
            returns = ast.unparse(func_node.returns)

    cert = Certificate(
        certus="0.1",
        function=function_name,
        signature=Signature(
            params=params,
            returns=returns,
            preconditions=sc.preconditions,
        ),
        postconditions=[Postcondition(**p) for p in sc.postconditions],
    )

    namespace: dict = {}
    compiled = compile(source, "<sidecar>", "exec")
    exec(compiled, namespace)  # noqa: S102

    func = namespace.get(function_name.split(".")[-1])
    if func is None:
        return VerificationReport(
            function=function_name,
            certificate_depth="minimal",
            claims=[
                ClaimResult(
                    claim=f"Function '{function_name}' not found in source",
                    status="unverified",
                )
            ],
            dependencies=[],
            strength=StrengthScore(rejection_rate=0.0),
        )

    return run_checker(func, cert, source, mode=mode, num_runs=num_runs)
