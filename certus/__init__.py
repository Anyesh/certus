"""Certus: Certificate-augmented generation for verifiable AI code."""

__version__ = "0.1.0"

from certus.decorator import certus
from certus.checker.runner import run_checker, check_from_sidecar
from certus.spec.schema import Certificate
from certus.spec.serializers import certificate_from_yaml, certificate_to_yaml
from certus.sidecar.store import SidecarStore
from certus.sidecar.models import SidecarFile, SidecarFileEntry, SidecarCertificate

__all__ = [
    "certus",
    "run_checker",
    "check_from_sidecar",
    "Certificate",
    "certificate_from_yaml",
    "certificate_to_yaml",
    "SidecarStore",
    "SidecarFile",
    "SidecarFileEntry",
    "SidecarCertificate",
]
