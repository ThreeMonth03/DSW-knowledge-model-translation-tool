"""Validate an append-only DSW Knowledge Model release repository."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml

from .dsw_models_adapter import DswModelsBundleAdapter
from .translation_repository_config import normalize_version


class KmReleaseValidationError(ValueError):
    """Raised when a KM release or repository configuration is invalid."""


@dataclass(frozen=True)
class KmSourceRepositoryConfig:
    """Stable identity and paths for a KM source repository."""

    organization_id: str
    km_id: str
    name: str
    initial_parent_package_id: str
    bundle_path: Path
    manifest_path: Path
    tag_prefix: str


@dataclass(frozen=True)
class KmReleaseManifest:
    """Metadata that binds one DSW package release to one Git tag."""

    package_id: str
    version: str
    previous_package_id: str | None
    forked_from: str
    bundle_sha256: str


@dataclass(frozen=True)
class KmReleaseValidationResult:
    """Summary of a successful release validation."""

    released: bool
    package_id: str | None
    version: str | None
    package_count: int
    event_count: int
    bundle_sha256: str | None


@dataclass(frozen=True)
class KmReleasePreparationResult:
    """Manifest fields generated from one exported KM bundle."""

    manifest_path: Path
    package_id: str
    version: str
    previous_package_id: str | None
    bundle_sha256: str


def prepare_km_release_manifest(
    *,
    repo_root: Path,
    config_path: Path = Path("km-repository.yml"),
    overwrite: bool = False,
) -> KmReleasePreparationResult:
    """Generate and validate release-manifest.yml from an exported KM bundle."""

    root = repo_root.resolve()
    resolved_config = config_path if config_path.is_absolute() else root / config_path
    config = load_km_source_repository_config(resolved_config)
    bundle_path = root / config.bundle_path
    manifest_path = root / config.manifest_path
    if not bundle_path.is_file():
        raise KmReleaseValidationError(f"KM bundle does not exist: {bundle_path}")
    if manifest_path.exists() and not overwrite:
        raise KmReleaseValidationError(
            f"Release manifest already exists: {manifest_path}; pass --overwrite to replace it"
        )

    try:
        DswModelsBundleAdapter.load_bundle_events(str(bundle_path))
    except (OSError, RuntimeError, ValueError) as error:
        raise KmReleaseValidationError(
            f"KM bundle does not match the official DSW schema: {error}"
        ) from error
    bundle = _load_bundle(bundle_path)
    version = normalize_version(str(bundle.get("version") or ""))
    package_id = str(bundle.get("id") or "")
    target_packages = [
        package
        for package in bundle.get("packages", ())
        if isinstance(package, dict)
        and package.get("organizationId") == config.organization_id
        and package.get("kmId") == config.km_id
    ]
    if not target_packages:
        raise KmReleaseValidationError(
            f"bundle contains no packages for {config.organization_id}:{config.km_id}"
        )
    previous_package_id = target_packages[-1].get("previousPackageId")
    if previous_package_id is not None and not isinstance(previous_package_id, str):
        raise KmReleaseValidationError("latest previousPackageId must be null or a string")
    bundle_sha256 = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    manifest_payload = {
        "schema_version": 1,
        "package_id": package_id,
        "version": version,
        "previous_package_id": previous_package_id,
        "forked_from": config.initial_parent_package_id,
        "bundle_sha256": bundle_sha256,
    }

    previous_manifest = manifest_path.read_bytes() if manifest_path.is_file() else None
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        yaml.safe_dump(manifest_payload, sort_keys=False),
        encoding="utf-8",
    )
    try:
        validate_km_release_repository(
            repo_root=root,
            config_path=resolved_config,
        )
    except KmReleaseValidationError:
        if previous_manifest is None:
            manifest_path.unlink(missing_ok=True)
        else:
            manifest_path.write_bytes(previous_manifest)
        raise

    return KmReleasePreparationResult(
        manifest_path=manifest_path,
        package_id=package_id,
        version=version,
        previous_package_id=previous_package_id,
        bundle_sha256=bundle_sha256,
    )


def validate_km_release_repository(
    *,
    repo_root: Path,
    config_path: Path = Path("km-repository.yml"),
    tag: str | None = None,
    previous_bundle_path: Path | None = None,
    allow_unreleased: bool = False,
) -> KmReleaseValidationResult:
    """Validate repository state and, when present, the current KM release."""

    root = repo_root.resolve()
    resolved_config = config_path if config_path.is_absolute() else root / config_path
    config = load_km_source_repository_config(resolved_config)
    bundle_path = root / config.bundle_path
    manifest_path = root / config.manifest_path
    has_bundle = bundle_path.is_file()
    has_manifest = manifest_path.is_file()

    if not has_bundle and not has_manifest and allow_unreleased:
        return KmReleaseValidationResult(
            released=False,
            package_id=None,
            version=None,
            package_count=0,
            event_count=0,
            bundle_sha256=None,
        )
    if has_bundle != has_manifest:
        missing = manifest_path if has_bundle else bundle_path
        raise KmReleaseValidationError(
            f"Partially released repository: missing {missing.relative_to(root)}"
        )
    if not has_bundle:
        raise KmReleaseValidationError(
            "No KM release is present; add both the bundle and release manifest"
        )

    manifest = load_km_release_manifest(manifest_path)
    bundle = _load_bundle(bundle_path)
    try:
        DswModelsBundleAdapter.load_bundle_events(str(bundle_path))
    except (OSError, RuntimeError, ValueError) as error:
        raise KmReleaseValidationError(
            f"KM bundle does not match the official DSW schema: {error}"
        ) from error
    actual_sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    errors: list[str] = []
    _validate_release_identity(
        errors=errors,
        bundle=bundle,
        manifest=manifest,
        config=config,
        actual_sha=actual_sha,
        tag=tag,
    )
    packages, event_count = _validate_package_chain(
        errors=errors,
        bundle=bundle,
        manifest=manifest,
        config=config,
    )

    if previous_bundle_path is not None:
        _validate_immutable_history(
            errors=errors,
            current_bundle=bundle,
            previous_bundle=_load_bundle(previous_bundle_path),
            manifest=manifest,
            config=config,
        )

    if errors:
        raise KmReleaseValidationError("\n".join(f"- {error}" for error in errors))
    return KmReleaseValidationResult(
        released=True,
        package_id=manifest.package_id,
        version=manifest.version,
        package_count=len(packages),
        event_count=event_count,
        bundle_sha256=actual_sha,
    )


def load_km_source_repository_config(path: Path) -> KmSourceRepositoryConfig:
    payload = _load_yaml_mapping(path, "KM repository config")
    if payload.get("schema_version", 1) != 1:
        raise KmReleaseValidationError("Unsupported km-repository.yml schema_version")
    km = _mapping(payload, "knowledge_model")
    release = _mapping(payload, "release")
    return KmSourceRepositoryConfig(
        organization_id=_string(km, "organization_id"),
        km_id=_string(km, "km_id"),
        name=_string(km, "name"),
        initial_parent_package_id=_string(km, "initial_parent_package_id"),
        bundle_path=Path(_string(km, "bundle_path")),
        manifest_path=Path(_string(release, "manifest_path")),
        tag_prefix=_string(release, "tag_prefix"),
    )


def load_km_release_manifest(path: Path) -> KmReleaseManifest:
    payload = _load_yaml_mapping(path, "KM release manifest")
    if payload.get("schema_version", 1) != 1:
        raise KmReleaseValidationError("Unsupported release-manifest.yml schema_version")
    previous = payload.get("previous_package_id")
    if previous is not None and (not isinstance(previous, str) or not previous.strip()):
        raise KmReleaseValidationError("previous_package_id must be null or a non-empty string")
    sha = _string(payload, "bundle_sha256").lower()
    if len(sha) != 64 or any(character not in "0123456789abcdef" for character in sha):
        raise KmReleaseValidationError("bundle_sha256 must be a lowercase SHA-256 hex digest")
    return KmReleaseManifest(
        package_id=_string(payload, "package_id"),
        version=normalize_version(_string(payload, "version")),
        previous_package_id=previous.strip() if isinstance(previous, str) else None,
        forked_from=_string(payload, "forked_from"),
        bundle_sha256=sha,
    )


def _validate_release_identity(
    *,
    errors: list[str],
    bundle: dict[str, Any],
    manifest: KmReleaseManifest,
    config: KmSourceRepositoryConfig,
    actual_sha: str,
    tag: str | None,
) -> None:
    expected_id = f"{config.organization_id}:{config.km_id}:{manifest.version}"
    _expect_equal(errors, "manifest package_id", manifest.package_id, expected_id)
    _expect_equal(errors, "bundle id", bundle.get("id"), manifest.package_id)
    _expect_equal(
        errors,
        "bundle organizationId",
        bundle.get("organizationId"),
        config.organization_id,
    )
    _expect_equal(errors, "bundle kmId", bundle.get("kmId"), config.km_id)
    _expect_equal(errors, "bundle version", str(bundle.get("version") or ""), manifest.version)
    _expect_equal(errors, "bundle SHA-256", actual_sha, manifest.bundle_sha256)
    _expect_equal(
        errors,
        "manifest forked_from",
        manifest.forked_from,
        config.initial_parent_package_id,
    )
    if tag is not None:
        _expect_equal(errors, "Git tag", tag, f"{config.tag_prefix}{manifest.version}")


def _validate_package_chain(
    *,
    errors: list[str],
    bundle: dict[str, Any],
    manifest: KmReleaseManifest,
    config: KmSourceRepositoryConfig,
) -> tuple[list[dict[str, Any]], int]:
    raw_packages = bundle.get("packages")
    if not isinstance(raw_packages, list) or not raw_packages:
        errors.append("bundle packages must be a non-empty list")
        return [], 0

    packages = [package for package in raw_packages if isinstance(package, dict)]
    _check_unique(
        errors,
        "package IDs",
        [str(package.get("id") or "") for package in packages],
    )
    event_count = 0
    for package in packages:
        package_events = [event for event in package.get("events", ()) if isinstance(event, dict)]
        event_count += len(package_events)
        _check_unique(
            errors,
            f"event UUIDs in {package.get('id')}",
            [str(event.get("uuid") or "") for event in package_events],
        )

    target_packages = [
        package
        for package in packages
        if package.get("organizationId") == config.organization_id
        and package.get("kmId") == config.km_id
    ]
    if not target_packages:
        errors.append(f"bundle contains no packages for {config.organization_id}:{config.km_id}")
        return packages, event_count

    first = target_packages[0]
    latest = target_packages[-1]
    _expect_equal(
        errors,
        "first target forkOfPackageId",
        first.get("forkOfPackageId"),
        config.initial_parent_package_id,
    )
    _expect_equal(errors, "latest target package ID", latest.get("id"), manifest.package_id)
    _expect_equal(
        errors,
        "latest previousPackageId",
        latest.get("previousPackageId"),
        manifest.previous_package_id,
    )
    for previous, current in pairwise(target_packages):
        _expect_equal(
            errors,
            f"{current.get('id')} previousPackageId",
            current.get("previousPackageId"),
            previous.get("id"),
        )
    return packages, event_count


def _validate_immutable_history(
    *,
    errors: list[str],
    current_bundle: dict[str, Any],
    previous_bundle: dict[str, Any],
    manifest: KmReleaseManifest,
    config: KmSourceRepositoryConfig,
) -> None:
    if manifest.previous_package_id is None:
        errors.append("a previous bundle was supplied for an initial release")
        return
    _expect_equal(
        errors,
        "previous bundle id",
        previous_bundle.get("id"),
        manifest.previous_package_id,
    )
    current_packages = {
        package.get("id"): package
        for package in current_bundle.get("packages", ())
        if isinstance(package, dict)
    }
    for previous_package in previous_bundle.get("packages", ()):
        if not isinstance(previous_package, dict):
            continue
        if (
            previous_package.get("organizationId") != config.organization_id
            or previous_package.get("kmId") != config.km_id
        ):
            continue
        package_id = previous_package.get("id")
        current_package = current_packages.get(package_id)
        if current_package is None:
            errors.append(f"historical package disappeared: {package_id}")
        elif _canonical_json(current_package) != _canonical_json(previous_package):
            errors.append(f"historical package was rewritten: {package_id}")


def _load_bundle(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise KmReleaseValidationError(f"Unable to read KM bundle {path}: {error}") from error
    if not isinstance(payload, dict):
        raise KmReleaseValidationError(f"KM bundle must contain a JSON object: {path}")
    return payload


def _load_yaml_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise KmReleaseValidationError(f"Unable to read {label} {path}: {error}") from error
    if not isinstance(payload, dict):
        raise KmReleaseValidationError(f"{label} must contain a mapping")
    return payload


def _mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise KmReleaseValidationError(f"Expected mapping at `{key}`")
    return value


def _string(parent: dict[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise KmReleaseValidationError(f"Expected non-empty string at `{key}`")
    return value.strip()


def _expect_equal(errors: list[str], label: str, actual: object, expected: object) -> None:
    if actual != expected:
        errors.append(f"{label}: expected {expected!r}, got {actual!r}")


def _check_unique(errors: list[str], label: str, values: list[str]) -> None:
    non_empty = [value for value in values if value]
    if len(non_empty) != len(values):
        errors.append(f"{label} contain an empty value")
    duplicates = sorted(value for value, count in Counter(non_empty).items() if count > 1)
    if duplicates:
        errors.append(f"{label} are duplicated: {', '.join(duplicates[:10])}")


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
