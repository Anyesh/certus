"""Pipeline runner: orchestrates collection, augmentation, validation, formatting."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from certus.pipeline.collector import MBPPCollector, CodeSample
from certus.pipeline.augmenter import Augmenter
from certus.pipeline.validator import validate_augmentation
from certus.pipeline.formatter import format_validated_results


@dataclass
class PipelineConfig:
    sources: list[str]
    max_samples: int = 500
    augmenter_model: str = "claude-sonnet-4-6"
    dry_run: bool = False
    checker_runs: int = 200
    output_dir: str = "data/training"


@dataclass
class PipelineReport:
    collected: int
    augmented: int
    passed: int
    formatted: int

    @property
    def pass_rate(self) -> float:
        if self.augmented == 0:
            return 0.0
        return self.passed / self.augmented


class PipelineRunner:
    """Orchestrates the full data pipeline."""

    def __init__(self, config: PipelineConfig):
        self.config = config

    def run(self) -> PipelineReport:
        samples = self._collect()

        augmenter = Augmenter(
            model=self.config.augmenter_model,
            dry_run=self.config.dry_run,
        )
        aug_results = augmenter.augment_batch(samples)

        validated = []
        for aug in aug_results:
            vr = validate_augmentation(aug, num_runs=self.config.checker_runs)
            validated.append(vr)

        passed = [v for v in validated if v.passed]
        examples = format_validated_results(passed)

        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if examples:
            output_file = output_dir / "training_data.jsonl"
            with open(output_file, "w") as f:
                for ex in examples:
                    f.write(json.dumps(ex.to_dict()) + "\n")

        report = PipelineReport(
            collected=len(samples),
            augmented=len(aug_results),
            passed=len(passed),
            formatted=len(examples),
        )

        report_file = output_dir / "report.json"
        with open(report_file, "w") as f:
            json.dump(
                {
                    "collected": report.collected,
                    "augmented": report.augmented,
                    "passed": report.passed,
                    "formatted": report.formatted,
                    "pass_rate": report.pass_rate,
                },
                f,
                indent=2,
            )

        return report

    def _collect(self) -> list[CodeSample]:
        samples = []
        for source in self.config.sources:
            if source == "mbpp":
                collector = MBPPCollector(max_samples=self.config.max_samples)
                samples.extend(collector.collect())
        return samples
