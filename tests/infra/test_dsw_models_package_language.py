"""Compatibility tests for Registry KM package metadata."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from dsw_km_translation_tool.dsw_models_adapter import DswModelsBundleAdapter


def test_adapter_accepts_registry_package_language(model_path: Path) -> None:
    """Accept the package-level language metadata now emitted by Registry."""

    root = json.loads(model_path.read_text(encoding="utf-8"))
    for package in root["packages"]:
        package["language"] = "en"

    DswModelsBundleAdapter.validate_bundle_root(root)


def test_adapter_keeps_other_unknown_package_fields_strict(model_path: Path) -> None:
    """Do not turn compatibility normalization into broad extra-field ignoring."""

    root = json.loads(model_path.read_text(encoding="utf-8"))
    root = copy.deepcopy(root)
    root["packages"][0]["language"] = "en"
    root["packages"][0]["unexpectedField"] = "must still fail"

    with pytest.raises(ValidationError, match="unexpectedField"):
        DswModelsBundleAdapter.validate_bundle_root(root)


@pytest.mark.parametrize("root", [[], "not an object"])
def test_adapter_delegates_non_object_roots_to_schema_validation(root: object) -> None:
    """Reject non-object JSON roots with the official schema validation error."""

    with pytest.raises(ValidationError):
        DswModelsBundleAdapter.validate_bundle_root(root)
