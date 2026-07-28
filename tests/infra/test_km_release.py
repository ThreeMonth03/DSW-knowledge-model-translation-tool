"""Tests for append-only source KM repository validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from dsw_km_translation_tool.km_release import (
    KmReleaseValidationError,
    prepare_km_release_manifest,
    validate_km_release_repository,
)
from dsw_km_translation_tool.km_source_repository_scaffold import (
    scaffold_km_source_repository,
)


def write_tw_bundle(target: Path, model_path: Path) -> dict[str, object]:
    """Write a schema-valid fixture with the configured Taiwan KM identity."""

    bundle = json.loads(model_path.read_text(encoding="utf-8"))
    id_map = {package["id"]: f"tw:root-tw:{package['version']}" for package in bundle["packages"]}
    bundle["organizationId"] = "tw"
    bundle["kmId"] = "root-tw"
    bundle["name"] = "Taiwan DSW Knowledge Model"
    bundle["id"] = id_map[bundle["id"]]
    for index, package in enumerate(bundle["packages"]):
        original_id = package["id"]
        package["organizationId"] = "tw"
        package["kmId"] = "root-tw"
        package["name"] = "Taiwan DSW Knowledge Model"
        package["id"] = id_map[original_id]
        package["previousPackageId"] = (
            id_map.get(package.get("previousPackageId")) if index else None
        )
        package["forkOfPackageId"] = "dsw:root:2.7.0" if index == 0 else None
    bundle_path = target / "km" / "root-tw.km"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return bundle


def test_source_repository_scaffold_is_valid_while_unreleased(
    repo_root: Path,
    workspace: Path,
) -> None:
    target = workspace / "source-repo"
    result = scaffold_km_source_repository(
        repo_root=target,
        tooling_repo=repo_root,
        organization_id="tw",
        km_id="root-tw",
        name="Taiwan DSW Knowledge Model",
        initial_parent_package_id="dsw:root:2.7.0",
        tooling_repository="ThreeMonth03/dsw-km-translation-tool",
        tooling_ref="abc123",
    )

    assert result.written_files
    assert (target / ".github" / "workflows" / "release.yml").exists()
    validation = validate_km_release_repository(
        repo_root=target,
        allow_unreleased=True,
    )
    assert validation.released is False


def test_prepare_release_manifest_derives_bundle_metadata(
    repo_root: Path,
    workspace: Path,
    model_path: Path,
) -> None:
    target = workspace / "source-repo"
    scaffold_km_source_repository(
        repo_root=target,
        tooling_repo=repo_root,
        organization_id="tw",
        km_id="root-tw",
        name="Taiwan DSW Knowledge Model",
        initial_parent_package_id="dsw:root:2.7.0",
        tooling_repository="ThreeMonth03/dsw-km-translation-tool",
        tooling_ref="abc123",
    )
    bundle = write_tw_bundle(target, model_path)

    result = prepare_km_release_manifest(repo_root=target)

    assert result.package_id == bundle["id"]
    assert result.version == bundle["version"]
    assert (
        result.bundle_sha256
        == hashlib.sha256((target / "km" / "root-tw.km").read_bytes()).hexdigest()
    )
    manifest = yaml.safe_load(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["package_id"] == bundle["id"]
    assert manifest["forked_from"] == "dsw:root:2.7.0"
    assert validate_km_release_repository(repo_root=target).released is True


def test_release_validator_checks_identity_chain_tag_and_checksum(
    repo_root: Path,
    workspace: Path,
    model_path: Path,
) -> None:
    target = workspace / "source-repo"
    scaffold_km_source_repository(
        repo_root=target,
        tooling_repo=repo_root,
        organization_id="tw",
        km_id="root-tw",
        name="Taiwan DSW Knowledge Model",
        initial_parent_package_id="dsw:root:2.7.0",
        tooling_repository="ThreeMonth03/dsw-km-translation-tool",
        tooling_ref="abc123",
    )
    bundle = json.loads(model_path.read_text(encoding="utf-8"))
    id_map = {package["id"]: f"tw:root-tw:{package['version']}" for package in bundle["packages"]}
    bundle["organizationId"] = "tw"
    bundle["kmId"] = "root-tw"
    bundle["name"] = "Taiwan DSW Knowledge Model"
    bundle["id"] = id_map[bundle["id"]]
    for index, package in enumerate(bundle["packages"]):
        original_id = package["id"]
        package["organizationId"] = "tw"
        package["kmId"] = "root-tw"
        package["name"] = "Taiwan DSW Knowledge Model"
        package["id"] = id_map[original_id]
        package["previousPackageId"] = (
            id_map.get(package.get("previousPackageId")) if index else None
        )
        package["forkOfPackageId"] = "dsw:root:2.7.0" if index == 0 else None
    bundle_path = target / "km" / "root-tw.km"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    latest = bundle["packages"][-1]
    manifest = {
        "schema_version": 1,
        "package_id": bundle["id"],
        "version": bundle["version"],
        "previous_package_id": latest["previousPackageId"],
        "forked_from": "dsw:root:2.7.0",
        "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
    }
    (target / "release-manifest.yml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )

    result = validate_km_release_repository(
        repo_root=target,
        tag="v2.7.0",
    )

    assert result.released is True
    assert result.package_id == "tw:root-tw:2.7.0"
    assert result.package_count == len(bundle["packages"])


def test_release_validator_rejects_moved_tag(
    repo_root: Path,
    workspace: Path,
) -> None:
    target = workspace / "source-repo"
    scaffold_km_source_repository(
        repo_root=target,
        tooling_repo=repo_root,
        organization_id="tw",
        km_id="root-tw",
        name="Taiwan DSW Knowledge Model",
        initial_parent_package_id="dsw:root:2.7.0",
        tooling_repository="ThreeMonth03/dsw-km-translation-tool",
        tooling_ref="abc123",
    )
    try:
        validate_km_release_repository(repo_root=target, tag="v0.1.0")
    except KmReleaseValidationError as error:
        assert "No KM release is present" in str(error)
    else:
        raise AssertionError("Expected an unreleased source repository to fail strict validation")


def test_release_validator_rejects_disconnected_questionnaire_lineage(
    repo_root: Path,
    workspace: Path,
    model_path: Path,
) -> None:
    target = workspace / "source-repo"
    scaffold_km_source_repository(
        repo_root=target,
        tooling_repo=repo_root,
        organization_id="tw",
        km_id="root-tw",
        name="Taiwan DSW Knowledge Model",
        initial_parent_package_id="dsw:root:2.7.0",
        tooling_repository="ThreeMonth03/dsw-km-translation-tool",
        tooling_ref="abc123",
    )
    bundle = write_tw_bundle(target, model_path)
    latest = bundle["packages"][-1]
    latest["previousPackageId"] = None
    bundle_path = target / "km" / "root-tw.km"
    bundle_path.write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "package_id": bundle["id"],
        "version": bundle["version"],
        "previous_package_id": None,
        "forked_from": "dsw:root:2.7.0",
        "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
    }
    (target / "release-manifest.yml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(KmReleaseValidationError, match="empty questionnaire"):
        validate_km_release_repository(repo_root=target)


def test_release_validator_rejects_rewritten_historical_package(
    repo_root: Path,
    workspace: Path,
    model_path: Path,
) -> None:
    target = workspace / "source-repo"
    scaffold_km_source_repository(
        repo_root=target,
        tooling_repo=repo_root,
        organization_id="tw",
        km_id="root-tw",
        name="Taiwan DSW Knowledge Model",
        initial_parent_package_id="dsw:root:2.7.0",
        tooling_repository="ThreeMonth03/dsw-km-translation-tool",
        tooling_ref="abc123",
    )
    current = write_tw_bundle(target, model_path)
    prepared = prepare_km_release_manifest(repo_root=target)
    assert prepared.previous_package_id is not None

    previous = json.loads(json.dumps(current))
    while previous["packages"][-1]["id"] != prepared.previous_package_id:
        previous["packages"].pop()
    previous["id"] = prepared.previous_package_id
    previous["packages"][0]["name"] = "Rewritten historical package"
    previous_path = workspace / "previous.km"
    previous_path.write_text(
        json.dumps(previous, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )

    try:
        validate_km_release_repository(
            repo_root=target,
            previous_bundle_path=previous_path,
        )
    except KmReleaseValidationError as error:
        assert "historical package was rewritten" in str(error)
    else:
        raise AssertionError("Expected rewritten KM history to fail validation")
