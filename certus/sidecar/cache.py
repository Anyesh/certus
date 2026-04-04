from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CheckResult:
    status: str  # "passed", "failed", "stale", "weak"
    body_hash: str
    strength: float
    num_guarantees: int
    proved: int
    held: int
    violated: int
    unverified: int


class CheckCache:
    """File-backed verification result cache stored in .certus/.cache/.

    Results are keyed by (source_file, function_name). A cache hit requires
    that the stored body_hash matches the caller-supplied hash, enabling
    incremental checking: unchanged functions skip re-verification.
    """

    FILENAME = "check_results.json"

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self._path = self.cache_dir / self.FILENAME
        self._data: dict[str, dict[str, dict]] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text())
            except (json.JSONDecodeError, KeyError):
                self._data = {}

    def get(
        self, source_file: str, function_name: str, current_body_hash: str
    ) -> CheckResult | None:
        file_data = self._data.get(source_file, {})
        func_data = file_data.get(function_name)
        if func_data is None:
            return None
        if func_data.get("body_hash") != current_body_hash:
            return None
        return CheckResult(**func_data)

    def put(self, source_file: str, function_name: str, result: CheckResult) -> None:
        if source_file not in self._data:
            self._data[source_file] = {}
        self._data[source_file][function_name] = asdict(result)

    def flush(self) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2) + "\n")

    def clear(self) -> None:
        self._data = {}
        if self._path.exists():
            self._path.unlink()
