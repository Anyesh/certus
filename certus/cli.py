"""Certus CLI."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import click

from certus.checker.runner import run_checker
from certus.sidecar.store import SidecarStore


@click.group()
def main():
    """Certus: Certificate-augmented generation for verifiable AI code."""
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--mode", type=click.Choice(["fast", "full", "strict"]), default="fast")
@click.option("--runs", type=int, default=1000, help="Number of dynamic test runs")
def check(path: str, mode: str, runs: int):
    """Verify Certus certificates in a Python file."""
    filepath = Path(path)
    source = filepath.read_text()

    spec = importlib.util.spec_from_file_location("_certus_target", filepath)
    if spec is None or spec.loader is None:
        click.echo(f"Error: could not load {path}", err=True)
        sys.exit(1)

    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as e:
        click.echo(f"Error importing {path}: {e}", err=True)
        sys.exit(1)

    certified = []
    for name, obj in inspect.getmembers(module):
        if callable(obj) and hasattr(obj, "__certus__"):
            certified.append((name, obj))
    for name, cls in inspect.getmembers(module, inspect.isclass):
        for mname, method in inspect.getmembers(cls):
            if callable(method) and hasattr(method, "__certus__"):
                certified.append((f"{name}.{mname}", method))

    if not certified:
        click.echo(f"No Certus certificates found in {path}")
        return

    any_failed = False
    for name, func in certified:
        cert = func.__certus__
        report = run_checker(func, cert, source, mode=mode, num_runs=runs)

        s = report.summary
        icon = "PASS" if s.violated == 0 and s.unverified == 0 else "FAIL"
        click.echo(f"\n{icon} {name}")
        click.echo(f"  depth: {report.certificate_depth}")
        click.echo(
            f"  proved: {s.proved}  held: {s.held}  violated: {s.violated}  unverified: {s.unverified}"
        )
        click.echo(f"  confidence: {s.confidence}")
        click.echo(f"  strength: {report.strength.rejection_rate}")

        if s.violated > 0:
            any_failed = True
            for c in report.claims:
                if c.status == "violated":
                    click.echo(f"  VIOLATED: {c.claim}")
                    if c.counterexample:
                        click.echo(f"    counterexample: {c.counterexample}")

        if s.unverified > 0:
            any_failed = True
            for c in report.claims:
                if c.status == "unverified":
                    click.echo(f"  UNVERIFIED: {c.claim}")

    if any_failed:
        sys.exit(1)


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--function", "-f", default=None, help="Specific function name (default: all)"
)
@click.option("--server", default="http://localhost:8234", help="Inference server URL")
@click.option(
    "--mode",
    type=click.Choice(["fast", "structural"]),
    default="fast",
    help="Checker mode",
)
@click.option("--runs", type=int, default=30, help="Hypothesis test runs per guarantee")
def generate(path: str, function: str | None, server: str, mode: str, runs: int):
    """Generate and verify Certus certificates for functions in a Python file."""
    from certus.generator import generate_for_file

    results = generate_for_file(
        path, server, function_name=function, checker_mode=mode, num_runs=runs
    )

    any_failed = False
    for r in results:
        if r.error:
            click.echo(f"\nERROR {r.function_name}: {r.error}")
            if r.raw_certificate:
                click.echo(f"  raw output: {r.raw_certificate[:200]}")
            any_failed = True
            continue

        vr = r.validation
        passed = vr.passed if vr else False
        icon = "PASS" if passed else "FAIL"

        click.echo(f"\n{icon} {r.function_name}")
        click.echo(f"  certificate:")
        for line in (r.raw_certificate or "").strip().splitlines():
            click.echo(f"    {line}")

        if vr and vr.report:
            s = vr.report.summary
            click.echo(f"  verification:")
            click.echo(
                f"    proved: {s.proved}  held: {s.held}  violated: {s.violated}  unverified: {s.unverified}"
            )
            click.echo(f"    confidence: {s.confidence}")
            click.echo(f"    strength: {vr.report.strength.rejection_rate}")

            if s.violated > 0:
                for c in vr.report.claims:
                    if c.status == "violated":
                        click.echo(f"    VIOLATED: {c.claim}")
                        if c.counterexample:
                            click.echo(f"      counterexample: {c.counterexample}")
        elif vr and not vr.passed:
            click.echo(f"  reason: {vr.reason}")

        if not passed:
            any_failed = True

    if any_failed:
        sys.exit(1)


@main.command()
@click.option("--sources", default="mbpp", help="Comma-separated data sources")
@click.option("--max-samples", type=int, default=500)
@click.option("--model", default="claude-sonnet-4-6", help="Model for augmentation")
@click.option(
    "--dry-run", is_flag=True, help="Use synthetic certificates (no API calls)"
)
@click.option("--checker-runs", type=int, default=200)
@click.option("--output", default="data/training", help="Output directory")
def pipeline(
    sources: str,
    max_samples: int,
    model: str,
    dry_run: bool,
    checker_runs: int,
    output: str,
):
    """Run the training data pipeline."""
    from certus.pipeline.runner import PipelineRunner, PipelineConfig

    config = PipelineConfig(
        sources=sources.split(","),
        max_samples=max_samples,
        augmenter_model=model,
        dry_run=dry_run,
        checker_runs=checker_runs,
        output_dir=output,
    )

    click.echo(f"Running pipeline: {config.sources}, max_samples={config.max_samples}")
    click.echo(f"Model: {config.augmenter_model}, dry_run={config.dry_run}")

    runner = PipelineRunner(config)
    report = runner.run()

    click.echo(f"\nPipeline complete:")
    click.echo(f"  Collected: {report.collected}")
    click.echo(f"  Augmented: {report.augmented}")
    click.echo(f"  Passed:    {report.passed}")
    click.echo(f"  Formatted: {report.formatted}")
    click.echo(f"  Pass rate: {report.pass_rate:.1%}")
    click.echo(f"\nOutput: {config.output_dir}")


@main.command()
@click.option(
    "--project-root",
    type=click.Path(exists=True),
    default=".",
    help="Project root directory",
)
def init(project_root: str):
    store = SidecarStore(project_root)
    store.init()
    click.echo(f"Initialized .certus/ in {Path(project_root).resolve()}")


@main.command()
@click.option(
    "--project-root",
    type=click.Path(exists=True),
    default=".",
    help="Project root directory",
)
def status(project_root: str):
    store = SidecarStore(project_root)
    files = store.list_certified_files()
    if not files:
        click.echo("No certificates found. Run 'certus init' to get started.")
        return
    total_certified = 0
    total_stale = 0
    for sf in files:
        certified = len(sf.functions)
        total_certified += certified
        stale_entries = store.get_stale_certificates(sf.source_file)
        stale = len(stale_entries)
        total_stale += stale
        uncertified_funcs = store.get_uncertified_functions(sf.source_file)
        uncertified = len(uncertified_funcs)
        click.echo(
            f"  {sf.source_file}: {certified} certified, {uncertified} uncertified, {stale} stale"
        )
    click.echo(f"\nTotal: {total_certified} certified, {total_stale} stale")


@main.command()
@click.option(
    "--project-root",
    type=click.Path(exists=True),
    default=".",
    help="Project root directory",
)
def clean(project_root: str):
    store = SidecarStore(project_root)
    files = store.list_certified_files()
    removed = 0
    for sf in files:
        stale = store.get_stale_certificates(sf.source_file)
        for name, reason in stale:
            if reason == "orphaned":
                store.remove_certificate(sf.source_file, name)
                click.echo(f"  Removed orphaned certificate: {sf.source_file}::{name}")
                removed += 1
    if removed == 0:
        click.echo("No orphaned certificates found.")
    else:
        click.echo(f"\nRemoved {removed} orphaned certificate(s).")
