"""The @certus decorator for embedding certificates in Python code."""

from __future__ import annotations

import functools
import inspect
import os
from typing import Any

from certus.spec.schema import (
    Certificate,
    Dependency,
    Effect,
    ExceptionalPostcondition,
    LoopInvariant,
    Postcondition,
    ProofStep,
    Signature,
)


def certus(
    preconditions: list[str] | None = None,
    postconditions: list[dict[str, Any]] | None = None,
    effects: dict[str, list[str]] | None = None,
    object_invariants: list[str] | None = None,
    invariants: list[dict[str, Any]] | None = None,
    raises: list[dict[str, Any]] | None = None,
    depends_on: list[dict[str, Any]] | None = None,
    assumptions: list[str] | None = None,
    proof: list[dict[str, Any]] | None = None,
):
    """Decorator that attaches a Certus certificate to a function."""

    def decorator(func):
        sig = inspect.signature(func)
        hints = func.__annotations__ if hasattr(func, "__annotations__") else {}
        params = {}
        for name in sig.parameters:
            hint = hints.get(name)
            if hint is None:
                params[name] = "Any"
            elif isinstance(hint, type):
                params[name] = hint.__name__
            else:
                params[name] = str(hint)
        return_hint = hints.get("return")
        if return_hint is None:
            return_str = "Any"
        elif isinstance(return_hint, type):
            return_str = return_hint.__name__
        else:
            return_str = str(return_hint)

        cert = Certificate(
            certus="0.1",
            function=func.__qualname__,
            signature=Signature(
                params=params,
                returns=return_str,
                preconditions=preconditions or [],
            ),
            postconditions=[Postcondition(**p) for p in (postconditions or [])],
            effects=Effect(**effects) if effects else None,
            object_invariants=object_invariants,
            invariants=[LoopInvariant(**i) for i in invariants] if invariants else None,
            raises=[ExceptionalPostcondition(**r) for r in raises] if raises else None,
            depends_on=[Dependency(**d) for d in depends_on] if depends_on else None,
            assumptions=assumptions,
            proof=[ProofStep(**p) for p in proof] if proof else None,
        )

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            mode = os.environ.get("CERTUS_MODE", "disabled")

            if mode == "disabled":
                return func(*args, **kwargs)

            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            namespace = dict(bound.arguments)

            if mode in ("assert", "audit"):
                for pre in cert.signature.preconditions:
                    # eval is intentional: evaluates certificate expression strings
                    if not eval(pre, {"__builtins__": {}}, namespace):  # noqa: S307
                        msg = f"Precondition failed: {pre}"
                        if mode == "assert":
                            raise AssertionError(msg)

            result = func(*args, **kwargs)
            namespace["result"] = result

            if mode in ("assert", "audit"):
                for post in cert.postconditions:
                    when_holds = (
                        post.when == "always"
                        or eval(post.when, {"__builtins__": {}}, namespace)  # noqa: S307
                    )
                    if when_holds:
                        for g in post.guarantees:
                            if not eval(g, {"__builtins__": {}}, namespace):  # noqa: S307
                                msg = f"Postcondition failed: {g}"
                                if mode == "assert":
                                    raise AssertionError(msg)

            return result

        wrapper.__certus__ = cert
        return wrapper

    return decorator
