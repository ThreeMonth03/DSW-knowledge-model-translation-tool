"""Shared legal-review file and checksum helpers."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


class LegalReviewError(ValueError):
    """Raised when legal-review rules or mappings are invalid."""


def load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    """Load a required top-level YAML mapping."""

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise LegalReviewError(f"Unable to read {label} {path}: {error}") from error
    if not isinstance(payload, dict):
        raise LegalReviewError(f"{label} must be a YAML mapping")
    return payload


def sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file."""

    return hashlib.sha256(path.read_bytes()).hexdigest()
