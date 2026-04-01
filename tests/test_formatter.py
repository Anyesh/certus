import pytest
from certus.pipeline.formatter import (
    format_task_a, format_task_b, format_validated_results, TrainingExample,
)
from certus.pipeline.validator import ValidationResult
from certus.pipeline.augmenter import AugmentationResult
from certus.pipeline.collector import CodeSample


def _make_validated():
    sample = CodeSample(
        source="test", task_id="1",
        description="Add two numbers",
        code="def add(a, b):\n    return a + b",
    )
    aug = AugmentationResult(
        sample=sample,
        certificate_kwargs={
            "preconditions": ["isinstance(a, int)", "isinstance(b, int)"],
            "postconditions": [{"when": "always", "guarantees": ["result == a + b"]}],
        },
        raw_response="@certus(...)",
    )
    return ValidationResult(augmentation=aug, passed=True)


def test_format_task_a():
    vr = _make_validated()
    example = format_task_a(vr)
    assert isinstance(example, TrainingExample)
    assert "Add two numbers" in example.prompt
    assert "@certus(" in example.completion
    assert "def add(a, b)" in example.completion


def test_format_task_b():
    vr = _make_validated()
    example = format_task_b(vr)
    assert isinstance(example, TrainingExample)
    assert "def add(a, b)" in example.prompt
    assert "@certus(" in example.completion
    assert "def add" not in example.completion


def test_format_validated_results():
    vr = _make_validated()
    examples = format_validated_results([vr])
    assert len(examples) >= 1
    task_types = {e.task_type for e in examples}
    assert "task_a" in task_types or "task_b" in task_types


def test_training_example_to_chat_format():
    example = TrainingExample(
        task_type="task_a",
        prompt="Write a function",
        completion="@certus(...)\ndef f(): pass",
        source="test",
        task_id="1",
    )
    chat = example.to_chat_format()
    assert len(chat) == 2
    assert chat[0]["role"] == "user"
    assert chat[1]["role"] == "assistant"
