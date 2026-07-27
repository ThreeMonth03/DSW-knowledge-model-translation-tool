"""Tests for pinned GitHub Release KM dependencies."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from dsw_km_translation_tool.github_release import (
    GitHubReleaseError,
    download_verified_km_release,
)


def release_downloaders(
    *,
    payload: bytes,
    checksum: str | None = None,
) -> tuple[object, object]:
    """Return deterministic metadata and asset downloaders."""

    asset_name = "root-2.7.0.km"
    checksum_name = f"{asset_name}.sha256"
    metadata = {
        "tag_name": "v2.7.0",
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
            f"{checksum or hashlib.sha256(payload).hexdigest()}  {asset_name}\n".encode()
        ),
    }

    def metadata_downloader(_url: str, _token: str) -> bytes:
        return json.dumps(metadata).encode()

    def asset_downloader(url: str, _token: str) -> bytes:
        return assets[url]

    return metadata_downloader, asset_downloader


def test_download_verified_km_release_checks_tag_checksum_and_identity(
    model_path: Path,
) -> None:
    payload = model_path.read_bytes()
    metadata_downloader, asset_downloader = release_downloaders(payload=payload)

    result = download_verified_km_release(
        repository="ds-wizard/dsw-root",
        ref="v2.7.0",
        organization_id="dsw",
        km_id="root",
        version="2.7.0",
        metadata_downloader=metadata_downloader,
        asset_downloader=asset_downloader,
    )

    assert result.package_id == "dsw:root:2.7.0"
    assert result.asset_name == "root-2.7.0.km"
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.payload == payload


def test_download_verified_km_release_rejects_wrong_checksum(
    model_path: Path,
) -> None:
    metadata_downloader, asset_downloader = release_downloaders(
        payload=model_path.read_bytes(),
        checksum="0" * 64,
    )

    try:
        download_verified_km_release(
            repository="ds-wizard/dsw-root",
            ref="v2.7.0",
            organization_id="dsw",
            km_id="root",
            version="2.7.0",
            metadata_downloader=metadata_downloader,
            asset_downloader=asset_downloader,
        )
    except GitHubReleaseError as error:
        assert "Checksum mismatch" in str(error)
    else:
        raise AssertionError("Expected a mismatched GitHub Release checksum to fail")


def test_download_verified_km_release_rejects_version_ref_drift() -> None:
    try:
        download_verified_km_release(
            repository="ds-wizard/dsw-root",
            ref="v2.6.0",
            organization_id="dsw",
            km_id="root",
            version="2.7.0",
        )
    except GitHubReleaseError as error:
        assert "must be 'v2.7.0'" in str(error)
    else:
        raise AssertionError("Expected a mismatched GitHub Release ref to fail")
