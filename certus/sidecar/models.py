from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SidecarCertificate(BaseModel):
    preconditions: list[str]
    postconditions: list[dict[str, Any]]
    effects: dict[str, list[str]] | None = None
    object_invariants: list[str] | None = None
    invariants: list[dict[str, Any]] | None = None
    raises: list[dict[str, Any]] | None = None
    depends_on: list[dict[str, Any]] | None = None
    assumptions: list[str] | None = None
    proof: list[dict[str, Any]] | None = None


class SidecarFileEntry(BaseModel):
    signature_hash: str
    body_hash: str
    generated_by: str
    generated_at: datetime
    certificate: SidecarCertificate


class SidecarFile(BaseModel):
    version: str = "1.0"
    source_file: str
    functions: dict[str, SidecarFileEntry]
