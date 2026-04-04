from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from certus.checker.runner import check_from_sidecar
from certus.sidecar.cache import CheckCache, CheckResult
from certus.sidecar.hashing import compute_body_hash, extract_function_info
from certus.sidecar.store import SidecarStore


class CertusViolationError(Exception):
    pass


class CertusStructuralError(Exception):
    pass


class CertusStaleError(Exception):
    pass


def _find_project_root(start: Path) -> Path | None:
    current = start.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".certus").is_dir():
            return candidate
    return None


def collect_certus_items(project_root: Path) -> list[dict[str, Any]]:
    store = SidecarStore(project_root)
    results = []
    for sidecar_file in store.list_certified_files():
        for func_name, entry in sidecar_file.functions.items():
            results.append(
                {
                    "function": func_name,
                    "source_file": sidecar_file.source_file,
                    "entry": entry,
                }
            )
    return results


class CertusItem(pytest.Item):
    def __init__(
        self,
        name: str,
        parent: pytest.Collector,
        source_file: str,
        function_name: str,
        entry: Any,
        project_root: Path,
        num_runs: int,
        force_full: bool,
        strict: bool,
        **kwargs: Any,
    ):
        super().__init__(name, parent, **kwargs)
        self._source_file = source_file
        self._function_name = function_name
        self._entry = entry
        self._project_root = project_root
        self._num_runs = num_runs
        self._force_full = force_full
        self._strict = strict

    @classmethod
    def from_parent(
        cls,
        parent,
        *,
        name,
        source_file,
        function_name,
        entry,
        project_root,
        num_runs,
        force_full,
        strict,
    ):  # type: ignore[override]
        return super().from_parent(
            parent,
            name=name,
            source_file=source_file,
            function_name=function_name,
            entry=entry,
            project_root=project_root,
            num_runs=num_runs,
            force_full=force_full,
            strict=strict,
        )

    def reportinfo(self):
        return self.fspath, None, f"certus::{self._source_file}::{self._function_name}"

    def runtest(self):
        source_path = self._project_root / self._source_file
        if not source_path.exists():
            raise CertusStructuralError(f"Source file not found: {source_path}")

        source = source_path.read_text()

        funcs = extract_function_info(source)
        func_map = {f.qualname: f for f in funcs}
        func_info = func_map.get(self._function_name)

        if func_info is None:
            raise CertusStructuralError(
                f"Function '{self._function_name}' not found in {self._source_file}"
            )

        current_body_hash = compute_body_hash(func_info)

        cache: CheckCache | None = None
        if not self._force_full:
            cache_dir = self._project_root / ".certus" / ".cache"
            if cache_dir.is_dir():
                cache = CheckCache(cache_dir)
                cached = cache.get(
                    self._source_file, self._function_name, current_body_hash
                )
                if cached is not None:
                    if cached.status == "failed":
                        raise CertusViolationError(
                            f"Cached failure for '{self._function_name}': "
                            f"{cached.violated} violation(s) in previous run"
                        )
                    if cached.status == "stale" and self._strict:
                        raise CertusStaleError(
                            f"Certificate for '{self._function_name}' is stale"
                        )
                    return

        stale = SidecarStore(self._project_root).get_stale_certificates(
            self._source_file
        )
        stale_names = {name for name, _ in stale}
        if self._function_name in stale_names:
            if self._strict:
                raise CertusStaleError(
                    f"Certificate for '{self._function_name}' is stale (signature or body changed)"
                )
            pytest.skip(
                f"Certificate for '{self._function_name}' is stale; re-generate to update"
            )

        report = check_from_sidecar(
            self._function_name,
            self._entry,
            source,
            mode="fast",
            num_runs=self._num_runs,
        )

        s = report.summary
        num_guarantees = len(report.claims)
        status = "passed" if s.violated == 0 and s.unverified == 0 else "failed"

        result = CheckResult(
            status=status,
            body_hash=current_body_hash,
            strength=report.strength.rejection_rate,
            num_guarantees=num_guarantees,
            proved=s.proved,
            held=s.held,
            violated=s.violated,
            unverified=s.unverified,
        )

        if cache is not None:
            cache.put(self._source_file, self._function_name, result)
            cache.flush()

        if s.violated > 0:
            violations = [c for c in report.claims if c.status == "violated"]
            details = "; ".join(
                f"{c.claim} (counterexample: {c.counterexample})"
                if c.counterexample
                else c.claim
                for c in violations
            )
            raise CertusViolationError(
                f"'{self._function_name}' violated {s.violated} guarantee(s): {details}"
            )

        if s.unverified > 0:
            unverified = [c.claim for c in report.claims if c.status == "unverified"]
            raise CertusStructuralError(
                f"'{self._function_name}' has {s.unverified} unverifiable guarantee(s): "
                + "; ".join(unverified)
            )

    def repr_failure(self, excinfo):
        exc = excinfo.value
        if isinstance(exc, CertusViolationError):
            return f"CERTUS VIOLATION: {exc}"
        if isinstance(exc, CertusStructuralError):
            return f"CERTUS STRUCTURAL ERROR: {exc}"
        if isinstance(exc, CertusStaleError):
            return f"CERTUS STALE: {exc}"
        return super().repr_failure(excinfo)


class CertusCollector(pytest.Collector):
    def __init__(
        self, name: str, parent: pytest.Session, project_root: Path, **kwargs: Any
    ):
        super().__init__(name, parent, **kwargs)
        self._project_root = project_root

    @classmethod
    def from_parent(cls, parent, *, name, project_root, **kwargs):  # type: ignore[override]
        return super().from_parent(
            parent, name=name, project_root=project_root, **kwargs
        )

    def collect(self):
        config = self.config
        num_runs = config.getoption("--certus-runs", default=30)
        force_full = config.getoption("--certus-full", default=False)
        strict = config.getoption("--certus-strict", default=False)

        for item_data in collect_certus_items(self._project_root):
            func = item_data["function"]
            src = item_data["source_file"]
            entry = item_data["entry"]
            item_name = f"{src}::{func}"
            yield CertusItem.from_parent(
                self,
                name=item_name,
                source_file=src,
                function_name=func,
                entry=entry,
                project_root=self._project_root,
                num_runs=num_runs,
                force_full=force_full,
                strict=strict,
            )


def pytest_addoption(parser):
    group = parser.getgroup("certus", "Certus certificate verification")
    group.addoption(
        "--certus-skip",
        action="store_true",
        default=False,
        help="Skip all Certus certificate checks",
    )
    group.addoption(
        "--certus-only",
        action="store_true",
        default=False,
        help="Run only Certus certificate checks (skip regular tests)",
    )
    group.addoption(
        "--certus-full",
        action="store_true",
        default=False,
        help="Force full re-verification (ignore cache)",
    )
    group.addoption(
        "--certus-strict",
        action="store_true",
        default=False,
        help="Treat stale or weak certificates as errors",
    )
    group.addoption(
        "--certus-runs",
        type=int,
        default=30,
        help="Number of Hypothesis runs per certificate (default: 30)",
    )


def pytest_collection_finish(session: pytest.Session):
    if session.config.getoption("--certus-skip", default=False):
        return

    project_root = _find_project_root(Path(session.config.rootdir))
    if project_root is None:
        return

    collector = CertusCollector.from_parent(
        session,
        name="certus",
        project_root=project_root,
    )
    try:
        new_items = list(collector.collect())
    except Exception:
        return

    session.items.extend(new_items)
    session.testscollected += len(new_items)


def pytest_collection_modifyitems(session: pytest.Session, config, items):
    if not config.getoption("--certus-only", default=False):
        return

    certus_items = [item for item in items if isinstance(item, CertusItem)]
    items[:] = certus_items
