from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass


@dataclass
class FunctionInfo:
    qualname: str
    params: dict[str, str]  # param_name -> type annotation string
    returns: str
    source: str
    body_ast: ast.AST


def _annotation_to_str(node: ast.expr | None) -> str:
    if node is None:
        return "Any"
    return ast.unparse(node)


def _extract_from_class(
    class_node: ast.ClassDef, lines: list[str]
) -> list[FunctionInfo]:
    results = []
    for node in ast.iter_child_nodes(class_node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            qualname = f"{class_node.name}.{node.name}"
            results.append(_build_function_info(node, qualname, lines))
    return results


def _build_function_info(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    qualname: str,
    lines: list[str],
) -> FunctionInfo:
    params = {}
    for arg in node.args.args:
        params[arg.arg] = _annotation_to_str(arg.annotation)

    returns = _annotation_to_str(node.returns)

    start = node.lineno - 1
    end = node.end_lineno if node.end_lineno else start + 1
    source = "".join(lines[start:end])

    return FunctionInfo(
        qualname=qualname,
        params=params,
        returns=returns,
        source=source,
        body_ast=node,
    )


def extract_function_info(source: str) -> list[FunctionInfo]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    lines = source.splitlines(keepends=True)
    results = []

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            results.append(_build_function_info(node, node.name, lines))
        elif isinstance(node, ast.ClassDef):
            results.extend(_extract_from_class(node, lines))

    return results


def compute_signature_hash(info: FunctionInfo) -> str:
    parts = [info.qualname]
    for name, type_str in sorted(info.params.items()):
        parts.append(f"{name}:{type_str}")
    parts.append(f"return:{info.returns}")
    content = "|".join(parts)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


def compute_body_hash(info: FunctionInfo) -> str:
    body_dump = ast.dump(info.body_ast)
    return hashlib.sha256(body_dump.encode()).hexdigest()[:16]
