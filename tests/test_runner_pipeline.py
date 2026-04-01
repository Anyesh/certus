import pytest
from pathlib import Path
from certus.pipeline.runner import PipelineRunner, PipelineConfig, PipelineReport


def test_pipeline_config():
    config = PipelineConfig(
        sources=["mbpp"],
        max_samples=5,
        augmenter_model="claude-sonnet-4-6",
        dry_run=True,
        checker_runs=50,
        output_dir="/tmp/certus_test",
    )
    assert config.dry_run is True
    assert config.max_samples == 5


def test_pipeline_runner_dry_run(tmp_path):
    config = PipelineConfig(
        sources=["mbpp"],
        max_samples=3,
        augmenter_model="claude-sonnet-4-6",
        dry_run=True,
        checker_runs=50,
        output_dir=str(tmp_path / "output"),
    )
    runner = PipelineRunner(config)
    report = runner.run()

    assert isinstance(report, PipelineReport)
    assert report.collected > 0
    assert report.augmented >= 0


def test_pipeline_saves_output(tmp_path):
    config = PipelineConfig(
        sources=["mbpp"],
        max_samples=3,
        augmenter_model="claude-sonnet-4-6",
        dry_run=True,
        checker_runs=50,
        output_dir=str(tmp_path / "output"),
    )
    runner = PipelineRunner(config)
    runner.run()

    output_dir = Path(config.output_dir)
    assert output_dir.exists()


def test_pipeline_report_pass_rate():
    report = PipelineReport(
        collected=100,
        augmented=80,
        passed=40,
        formatted=80,
    )
    assert report.pass_rate == 0.5
