from __future__ import annotations

from certus.spec.safe_subset import ALLOWED_BUILTINS, ALLOWED_METHODS


def get_format_spec() -> str:
    return """\
Certificate JSON format:
{
  "preconditions": ["<expr>", ...],
  "postconditions": [
    {"when": "always" | "<condition expr>", "guarantees": ["<expr>", ...]}
  ]
}

Fields:
- preconditions: list of boolean Python expressions that must hold on the inputs.
- postconditions: list of outcome branches. Each branch has:
  - "when": either the literal string "always" or a boolean condition expression.
  - "guarantees": list of boolean Python expressions about the result.
- In guarantee expressions, "result" refers to the function's return value.
- "old(expr)" captures the value of expr at function entry (before any mutation)."""


def get_safe_expression_context() -> str:
    # Exclude "old" from the displayed builtins — it is a Certus special form,
    # not a real builtin, and showing it as one confuses models.
    display_builtins = sorted(ALLOWED_BUILTINS - {"old"})
    display_methods = sorted(ALLOWED_METHODS)

    return (
        "Safe expression rules:\n"
        "- Only the following builtins are allowed: "
        + ", ".join(display_builtins)
        + "\n"
        "- Method calls allowed on str/list/dict/set/tuple: "
        + ", ".join(display_methods)
        + "\n"
        "- No lambdas, f-strings, walrus operator, or dunder access.\n"
        "- Forbidden: running arbitrary code, file I/O, or any unsafe names.\n"
        "- Special form: old(expr) captures the pre-call value of expr."
    )


def build_generation_prompt(
    function_code: str,
    function_name: str,
    examples: list[str] | None = None,
) -> str:
    parts: list[str] = []

    parts.append(
        "You are a formal verification assistant. Your task is to generate a "
        "Certus certificate for the Python function below.\n\n"
        "A strong certificate captures precise, falsifiable properties: it should "
        "reject wrong implementations, not merely describe the type of the result."
    )

    parts.append(get_format_spec())
    parts.append(get_safe_expression_context())

    if examples:
        parts.append("Example certificates for similar functions:")
        for i, ex in enumerate(examples, 1):
            parts.append(f"Example {i}:\n{ex}")

    parts.append(f"Function to certify ({function_name}):\n\n{function_code}")

    parts.append(
        "Generate a certificate as a JSON object. Requirements:\n"
        "1. Preconditions must capture all meaningful input constraints.\n"
        "2. Postconditions must be falsifiable — avoid tautological guarantees "
        "like isinstance(result, int) when a stronger property holds.\n"
        "3. Use 'result' for the return value. Use 'old(expr)' for pre-call values.\n"
        "4. Respond with ONLY the JSON object, no explanation."
    )

    return "\n\n".join(parts)


def build_feedback_prompt(
    function_code: str,
    function_name: str,
    previous_certificate: str,
    feedback: str,
) -> str:
    parts: list[str] = []

    parts.append(
        "You are a formal verification assistant. A previous certificate you generated "
        "was rejected. Your task is to produce an improved certificate."
    )

    parts.append(get_format_spec())
    parts.append(get_safe_expression_context())

    parts.append(f"Function ({function_name}):\n\n{function_code}")

    parts.append(f"Rejected certificate:\n{previous_certificate}")

    parts.append(f"Rejection reason:\n{feedback}")

    parts.append(
        "Generate an improved certificate that addresses the rejection reason. "
        "The new certificate must be stronger and more precise than the rejected one.\n"
        "Respond with ONLY the JSON object, no explanation."
    )

    return "\n\n".join(parts)
