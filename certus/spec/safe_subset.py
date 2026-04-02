"""Validates that certificate expressions conform to the Certus safe subset."""

from __future__ import annotations

import ast

ALLOWED_BUILTINS = frozenset(
    {
        "len",
        "sorted",
        "all",
        "any",
        "min",
        "max",
        "sum",
        "abs",
        "set",
        "list",
        "tuple",
        "range",
        "isinstance",
        "type",
        "frozenset",
        "enumerate",
        "zip",
        "int",
        "float",
        "str",
        "bool",
        "old",  # Certus special: value at function entry
    }
)

FORBIDDEN_NAMES = frozenset(
    {
        "eval",
        "exec",
        "__import__",
        "open",
        "print",
        "input",
        "getattr",
        "setattr",
        "delattr",
        "globals",
        "locals",
        "compile",
        "breakpoint",
        "exit",
        "quit",
        "help",
        "dir",
        "vars",
        "classmethod",
        "staticmethod",
        "property",
        "super",
    }
)

# Method calls allowed on safe types (str, list, dict, set, tuple).
# These cannot perform I/O, execute code, or escape the sandbox.
ALLOWED_METHODS = frozenset(
    {
        # str
        "split",
        "rsplit",
        "join",
        "replace",
        "lower",
        "upper",
        "strip",
        "lstrip",
        "rstrip",
        "startswith",
        "endswith",
        "count",
        "find",
        "rfind",
        "index",
        "rindex",
        "isdigit",
        "isalpha",
        "isalnum",
        "isupper",
        "islower",
        "isspace",
        "title",
        "capitalize",
        "swapcase",
        "zfill",
        "center",
        "ljust",
        "rjust",
        # list / tuple
        "copy",
        "sort",
        "reverse",
        # dict
        "keys",
        "values",
        "items",
        "get",
        # set / frozenset
        "add",
        "union",
        "intersection",
        "difference",
        "symmetric_difference",
        "issubset",
        "issuperset",
        "isdisjoint",
        # general
        "append",
        "extend",
        "pop",
        "remove",
        "insert",
        "clear",
        "update",
        "bit_length",
    }
)


class UnsafeExpressionError(Exception):
    """Raised when an expression violates the Certus safe subset."""

    def __init__(self, expression: str, reason: str):
        self.expression = expression
        self.reason = reason
        super().__init__(f"Unsafe expression: {reason} in `{expression}`")


def validate_expression(expression: str) -> None:
    if not expression or not expression.strip():
        raise UnsafeExpressionError(expression, "empty expression")

    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise UnsafeExpressionError(expression, f"syntax error: {e}") from e

    _walk(tree, expression)


def _walk(node: ast.AST, expression: str) -> None:
    match node:
        case ast.Expression(body=body):
            _walk(body, expression)
        case ast.Constant():
            pass
        case ast.Name(id=name):
            if name in FORBIDDEN_NAMES:
                raise UnsafeExpressionError(expression, f"forbidden name: {name}")
            if name.startswith("__") and name.endswith("__"):
                raise UnsafeExpressionError(expression, f"dunder access: {name}")
        case ast.BoolOp(values=values):
            for v in values:
                _walk(v, expression)
        case ast.BinOp(left=left, right=right):
            _walk(left, expression)
            _walk(right, expression)
        case ast.UnaryOp(operand=operand):
            _walk(operand, expression)
        case ast.Compare(left=left, comparators=comps):
            _walk(left, expression)
            for c in comps:
                _walk(c, expression)
        case ast.Subscript(value=value, slice=sl):
            _walk(value, expression)
            _walk(sl, expression)
        case ast.Slice(lower=lower, upper=upper, step=step):
            if lower:
                _walk(lower, expression)
            if upper:
                _walk(upper, expression)
            if step:
                _walk(step, expression)
        case ast.Attribute(value=value, attr=attr):
            if attr.startswith("__") and attr.endswith("__"):
                raise UnsafeExpressionError(expression, f"dunder attribute: {attr}")
            _walk(value, expression)
        case ast.Call(func=func, args=args, keywords=keywords):
            _validate_call(func, expression)
            for a in args:
                _walk(a, expression)
            for kw in keywords:
                _walk(kw.value, expression)
        case ast.ListComp(elt=elt, generators=gens):
            _walk(elt, expression)
            for g in gens:
                _walk_comprehension(g, expression)
        case ast.SetComp(elt=elt, generators=gens):
            _walk(elt, expression)
            for g in gens:
                _walk_comprehension(g, expression)
        case ast.DictComp(key=key, value=value, generators=gens):
            _walk(key, expression)
            _walk(value, expression)
            for g in gens:
                _walk_comprehension(g, expression)
        case ast.GeneratorExp(elt=elt, generators=gens):
            _walk(elt, expression)
            for g in gens:
                _walk_comprehension(g, expression)
        case ast.IfExp(test=test, body=body, orelse=orelse):
            _walk(test, expression)
            _walk(body, expression)
            _walk(orelse, expression)
        case ast.Tuple(elts=elts) | ast.List(elts=elts) | ast.Set(elts=elts):
            for e in elts:
                _walk(e, expression)
        case ast.Dict(keys=keys, values=values):
            for k in keys:
                if k:
                    _walk(k, expression)
            for v in values:
                _walk(v, expression)
        case ast.Starred(value=value):
            _walk(value, expression)
        case ast.NamedExpr():
            raise UnsafeExpressionError(expression, "walrus operator (:=) not allowed")
        case ast.Lambda():
            raise UnsafeExpressionError(expression, "lambda not allowed")
        case ast.JoinedStr():
            raise UnsafeExpressionError(expression, "f-strings not allowed")
        case ast.FormattedValue():
            raise UnsafeExpressionError(expression, "f-strings not allowed")
        case _:
            raise UnsafeExpressionError(
                expression, f"unsupported AST node: {type(node).__name__}"
            )


def _walk_comprehension(comp: ast.comprehension, expression: str) -> None:
    _walk(comp.target, expression)
    _walk(comp.iter, expression)
    for if_clause in comp.ifs:
        _walk(if_clause, expression)


def _validate_call(func: ast.AST, expression: str) -> None:
    """Validate that a call target is either an allowed builtin or an allowed method."""
    match func:
        case ast.Name(id=name):
            if name not in ALLOWED_BUILTINS:
                raise UnsafeExpressionError(
                    expression, f"forbidden function call: {name}"
                )
        case ast.Attribute(value=value, attr=method_name):
            if method_name.startswith("__") and method_name.endswith("__"):
                raise UnsafeExpressionError(
                    expression, f"dunder method call: {method_name}"
                )
            if method_name not in ALLOWED_METHODS:
                raise UnsafeExpressionError(
                    expression, f"forbidden method call: {method_name}"
                )
            _walk(value, expression)
        case _:
            raise UnsafeExpressionError(expression, "forbidden function call: unknown")
