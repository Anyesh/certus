"""Content-hash based verification result cache."""

from __future__ import annotations

import hashlib

from certus.checker.report import VerificationReport

CHECKER_VERSION = "0.1.0"


class VerificationCache:
    def __init__(self):
        self._store: dict[str, VerificationReport] = {}

    def _make_key(self, source: str, cert_yaml: str, function: str) -> str:
        content = f"{source}|{cert_yaml}|{function}|{CHECKER_VERSION}"
        return hashlib.sha256(content.encode()).hexdigest()

    def get(
        self, source: str, cert_yaml: str, function: str
    ) -> VerificationReport | None:
        return self._store.get(self._make_key(source, cert_yaml, function))

    def put(
        self, source: str, cert_yaml: str, function: str, report: VerificationReport
    ) -> None:
        self._store[self._make_key(source, cert_yaml, function)] = report

    def clear(self) -> None:
        self._store.clear()
