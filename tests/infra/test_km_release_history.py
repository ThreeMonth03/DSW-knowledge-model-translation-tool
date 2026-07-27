"""Tests for previous-release resolution and KM history validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dsw_km_translation_tool.km_release import prepare_km_release_manifest
from dsw_km_translation_tool.km_release_history import (
    validate_km_release_with_github_history,
)
from dsw_km_translation_tool.km_source_repository_scaffold import (
    scaffold_km_source_repository,
)
from tests.infra.test_km_release import write_tw_bundle


def test_validate_release_downloads_previous_github_bundle(
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
    manifest = prepare_km_release_manifest(repo_root=target)
    assert manifest.previous_package_id is not None
    previous_version = manifest.previous_package_id.rsplit(":", maxsplit=1)[1]

    previous = json.loads(json.dumps(current))
    while previous["packages"][-1]["id"] != manifest.previous_package_id:
        previous["packages"].pop()
    previous["id"] = manifest.previous_package_id
    previous["version"] = previous_version
    payload = json.dumps(
        previous,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    asset_name = f"root-tw-{previous_version}.km"
    checksum_name = f"{asset_name}.sha256"
    metadata = {
        "tag_name": f"v{previous_version}",
        "draft": False,
        "assets": [
            {
                "name": asset_name,
                "browser_download_url": f"https://assets.invalid/{asset_name}",
            },
            {
                "name": checksum_name,
                "browser_download_url": f"https://assets.invalid/{checksum_name}",
            },
        ],
    }
    assets = {
        f"https://assets.invalid/{asset_name}": payload,
        f"https://assets.invalid/{checksum_name}": (
            f"{hashlib.sha256(payload).hexdigest()}  {asset_name}\n".encode()
        ),
    }

    result = validate_km_release_with_github_history(
        repo_root=target,
        github_repository="ThreeMonth03/dsw-root-tw",
        metadata_downloader=lambda _url, _token: json.dumps(metadata).encode(),
        asset_downloader=lambda url, _token: assets[url],
    )

    assert result.released is True
    assert result.package_id == current["id"]
