"""Pass 0: Structural validation of Certus certificates against source AST."""

from __future__ import annotations

import ast

from certus.spec.schema import Certificate
from certus.spec.safe_subset import validate_expression, UnsafeExpressionError

VALID_STEP_TYPES = frozenset({"establish", "invoke", "derive", "branch", "conclude"})


def validate_certificate(cert: Certificate, source: str) -> list[str]:
    """Validate a certificate against source code. Returns list of error strings."""
    errors: list[str] = []

    for expr in cert.signature.preconditions:
        _check_expr(expr, "precondition", errors)

    for post in cert.postconditions:
        if post.when != "always":
            _check_expr(post.when, "postcondition when", errors)
        for g in post.guarantees:
            _check_expr(g, "postcondition guarantee", errors)

    if cert.object_invariants:
        for inv in cert.object_invariants:
            _check_expr(inv, "object invariant", errors)

    if cert.invariants:
        for inv in cert.invariants:
            for m in inv.maintains:
                _check_expr(m, "loop invariant", errors)
            if inv.termination:
                _check_expr(inv.termination, "termination expression", errors)

    if cert.raises:
        for r in cert.raises:
            if r.when:
                _check_expr(r.when, "raises when", errors)
            for g in r.guarantees:
                _check_expr(g, "raises guarantee", errors)

    if cert.depends_on:
        for dep in cert.depends_on:
            for u in dep.uses:
                _check_expr(u, f"depends_on({dep.function}) uses", errors)

    if cert.proof:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            errors.append("Failed to parse source code")
            return errors
        for step in cert.proof:
            _validate_proof_step(step, tree, errors)

    return errors


def _check_expr(expr: str, context: str, errors: list[str]) -> None:
    try:
        validate_expression(expr)
    except UnsafeExpressionError as e:
        errors.append(f"{context}: {e}")


def _validate_proof_step(step, tree: ast.AST, errors: list[str]) -> None:
    if step.step not in VALID_STEP_TYPES:
        errors.append(f"Invalid proof step type: {step.step}")
        return

    if step.check:
        _check_expr(step.check, f"proof step ({step.step}) check", errors)

    if step.true_path and "check" in step.true_path:
        _check_expr(step.true_path["check"], f"proof step ({step.step}) true_path check", errors)

    if step.false_path and "check" in step.false_path:
        _check_expr(step.false_path["check"], f"proof step ({step.step}) false_path check", errors)

    if step.step == "branch" and step.anchor.startswith("branch:"):
        condition_str = step.anchor[len("branch:"):]
        if not _find_branch_in_ast(tree, condition_str):
            errors.append(f"Proof step anchor not found in source: {step.anchor}")

    if step.step == "invoke" and step.anchor.startswith("call:"):
        func_name = step.anchor[len("call:"):]
        if not _find_call_in_ast(tree, func_name):
            errors.append(f"Proof step anchor not found in source: {step.anchor}")


def _find_branch_in_ast(tree: ast.AST, condition: str) -> bool:
    try:
        target = ast.dump(ast.parse(condition, mode="eval").body)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            if ast.dump(node.test) == target:
                return True
    return False


def _find_call_in_ast(tree: ast.AST, func_name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _extract_call_name(node.func)
            if name and func_name in name:
                return True
    return False


def _extract_call_name(node: ast.AST) -> str | None:
    match node:
        case ast.Name(id=name):
            return name
        case ast.Attribute(value=value, attr=attr):
            parent = _extract_call_name(value)
            return f"{parent}.{attr}" if parent else attr
        case _:
            return None
