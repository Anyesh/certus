from __future__ import annotations

import json
from pathlib import Path

from certus.sidecar.hashing import (
    FunctionInfo,
    compute_body_hash,
    compute_signature_hash,
    extract_function_info,
)
from certus.sidecar.models import SidecarFile, SidecarFileEntry


class SidecarStore:
    def __init__(self, project_root: str | Path):
        self.root = Path(project_root)
        self.certus_dir = self.root / ".certus"
        self.cache_dir = self.certus_dir / ".cache"

    def init(self) -> None:
        self.certus_dir.mkdir(exist_ok=True)
        self.cache_dir.mkdir(exist_ok=True)
        gitignore = self.cache_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("*\n")

    def _sidecar_path(self, source_file: str) -> Path:
        p = Path(source_file)
        return self.certus_dir / p.parent / f"{p.stem}.certus.json"

    def load_file(self, source_file: str) -> SidecarFile | None:
        path = self._sidecar_path(source_file)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return SidecarFile.model_validate(data)

    def save_certificate(
        self, source_file: str, function_name: str, entry: SidecarFileEntry
    ) -> None:
        existing = self.load_file(source_file)
        if existing is None:
            existing = SidecarFile(version="1.0", source_file=source_file, functions={})

        existing.functions[function_name] = entry

        path = self._sidecar_path(source_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(existing.model_dump_json(indent=2) + "\n")

    def remove_certificate(self, source_file: str, function_name: str) -> None:
        existing = self.load_file(source_file)
        if existing is None:
            return
        existing.functions.pop(function_name, None)
        path = self._sidecar_path(source_file)
        path.write_text(existing.model_dump_json(indent=2) + "\n")

    def list_certified_files(self) -> list[SidecarFile]:
        results = []
        for path in self.certus_dir.rglob("*.certus.json"):
            data = json.loads(path.read_text())
            results.append(SidecarFile.model_validate(data))
        return results

    def get_uncertified_functions(self, source_file: str) -> list[FunctionInfo]:
        source_path = self.root / source_file
        if not source_path.exists():
            return []

        source = source_path.read_text()
        all_funcs = extract_function_info(source)
        existing = self.load_file(source_file)
        certified_names = set(existing.functions.keys()) if existing else set()

        return [f for f in all_funcs if f.qualname not in certified_names]

    def get_stale_certificates(self, source_file: str) -> list[tuple[str, str]]:
        existing = self.load_file(source_file)
        if existing is None:
            return []

        source_path = self.root / source_file
        if not source_path.exists():
            return [(name, "source_deleted") for name in existing.functions]

        source = source_path.read_text()
        funcs = extract_function_info(source)
        func_map = {f.qualname: f for f in funcs}

        stale = []
        for name, entry in existing.functions.items():
            if name not in func_map:
                stale.append((name, "orphaned"))
                continue
            info = func_map[name]
            if compute_signature_hash(info) != entry.signature_hash:
                stale.append((name, "signature"))
            elif compute_body_hash(info) != entry.body_hash:
                stale.append((name, "body"))

        return stale
