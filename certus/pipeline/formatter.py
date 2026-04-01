"""Formatter: converts validated results to training-ready format."""

from __future__ import annotations

from dataclasses import dataclass

from certus.pipeline.validator import ValidationResult


@dataclass
class TrainingExample:
    task_type: str  # "task_a" or "task_b"
    prompt: str
    completion: str
    source: str
    task_id: str

    def to_chat_format(self) -> list[dict[str, str]]:
        return [
            {"role": "user", "content": self.prompt},
            {"role": "assistant", "content": self.completion},
        ]

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type,
            "prompt": self.prompt,
            "completion": self.completion,
            "source": self.source,
            "task_id": self.task_id,
            "messages": self.to_chat_format(),
        }


def _build_decorator_string(kwargs: dict) -> str:
    """Build @certus(...) string from kwargs dict."""
    parts = []
    for key in ("preconditions", "postconditions", "effects", "object_invariants",
                "invariants", "raises", "depends_on", "assumptions"):
        if key in kwargs:
            parts.append(f"    {key}={kwargs[key]!r}")

    body = ",\n".join(parts)
    return f"@certus(\n{body},\n)"


def format_task_a(vr: ValidationResult) -> TrainingExample:
    """Format as Task A: generate code + certificate from description."""
    sample = vr.augmentation.sample
    kwargs = vr.augmentation.certificate_kwargs

    decorator = _build_decorator_string(kwargs)
    completion = f"{decorator}\n{sample.code}"

    return TrainingExample(
        task_type="task_a",
        prompt=sample.description,
        completion=completion,
        source=sample.source,
        task_id=sample.task_id,
    )


def format_task_b(vr: ValidationResult) -> TrainingExample:
    """Format as Task B: generate certificate for existing code."""
    sample = vr.augmentation.sample
    kwargs = vr.augmentation.certificate_kwargs

    decorator = _build_decorator_string(kwargs)
    prompt = f"Generate a Certus certificate for this function:\n\n{sample.code}"

    return TrainingExample(
        task_type="task_b",
        prompt=prompt,
        completion=decorator,
        source=sample.source,
        task_id=sample.task_id,
    )


def format_validated_results(
    results: list[ValidationResult],
) -> list[TrainingExample]:
    """Format all passed validation results into training examples.

    Produces both Task A and Task B examples from each result.
    """
    examples = []
    for vr in results:
        if not vr.passed or vr.augmentation.certificate_kwargs is None:
            continue
        examples.append(format_task_a(vr))
        examples.append(format_task_b(vr))

    return examples
