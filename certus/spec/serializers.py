"""YAML/JSON serializers for Certus certificates."""

from __future__ import annotations

import yaml

from certus.spec.schema import Certificate


def certificate_to_yaml(cert: Certificate) -> str:
    """Serialize a Certificate to a YAML string."""
    data = cert.model_dump(exclude_none=True)
    return yaml.dump(data, sort_keys=False, allow_unicode=True)


def certificate_from_yaml(text: str) -> Certificate:
    """Deserialize a Certificate from a YAML string."""
    data = yaml.safe_load(text)
    return Certificate(**data)
