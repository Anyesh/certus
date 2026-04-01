"""Data collectors for raw code samples."""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass
class CodeSample:
    source: str
    task_id: str
    description: str
    code: str
    test_code: str | None = None

    @property
    def function_name(self) -> str | None:
        try:
            tree = ast.parse(self.code)
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    return node.name
        except SyntaxError:
            pass
        return None


class MBPPCollector:
    """Collects code samples from the MBPP dataset."""

    def __init__(self, max_samples: int = 500, split: str = "train"):
        self.max_samples = max_samples
        self.split = split

    def collect(self) -> list[CodeSample]:
        from datasets import load_dataset

        ds = load_dataset("mbpp", "full", split=self.split)

        samples = []
        for i, row in enumerate(ds):
            if i >= self.max_samples:
                break

            code = row.get("code", "")
            description = row.get("text", "")
            task_id = str(row.get("task_id", i))
            test_list = row.get("test_list", [])
            test_code = "\n".join(test_list) if test_list else None

            if not code.strip() or not description.strip():
                continue

            samples.append(
                CodeSample(
                    source="mbpp",
                    task_id=task_id,
                    description=description,
                    code=code,
                    test_code=test_code,
                )
            )

        return samples
