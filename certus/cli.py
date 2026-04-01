"""Certus CLI."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from pathlib import Path

import click

from certus.checker.runner import run_checker


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
        click.echo(f"  proved: {s.proved}  held: {s.held}  violated: {s.violated}  unverified: {s.unverified}")
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
