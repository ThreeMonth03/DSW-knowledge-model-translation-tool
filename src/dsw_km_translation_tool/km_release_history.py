"""Validate a source KM release against its previous GitHub Release."""

from __future__ import annotations

import tempfile
from pathlib import Path

from .github_release import Downloader, download_verified_km_release
from .km_release import (
    KmReleaseValidationError,
    KmReleaseValidationResult,
    load_km_release_manifest,
    load_km_source_repository_config,
    validate_km_release_repository,
)


def validate_km_release_with_github_history(
    *,
    repo_root: Path,
    github_repository: str,
    config_path: Path = Path("km-repository.yml"),
    tag: str | None = None,
    token: str = "",
    api_url: str = "https://api.github.com",
    allow_unreleased: bool = False,
    metadata_downloader: Downloader | None = None,
    asset_downloader: Downloader | None = None,
) -> KmReleaseValidationResult:
    """Download the previous release when present, then validate KM history."""

    root = repo_root.resolve()
    resolved_config = config_path if config_path.is_absolute() else root / config_path
    config = load_km_source_repository_config(resolved_config)
    manifest_path = root / config.manifest_path
    if not manifest_path.is_file():
        return validate_km_release_repository(
            repo_root=root,
            config_path=resolved_config,
            tag=tag,
            allow_unreleased=allow_unreleased,
        )

    manifest = load_km_release_manifest(manifest_path)
    if manifest.previous_package_id is None:
        return validate_km_release_repository(
            repo_root=root,
            config_path=resolved_config,
            tag=tag,
            allow_unreleased=allow_unreleased,
        )
    if manifest.previous_package_id == config.initial_parent_package_id:
        return validate_km_release_repository(
            repo_root=root,
            config_path=resolved_config,
            tag=tag,
            allow_unreleased=allow_unreleased,
        )

    prefix = f"{config.organization_id}:{config.km_id}:"
    if not manifest.previous_package_id.startswith(prefix):
        raise KmReleaseValidationError(
            "previous_package_id does not belong to the configured KM lineage: "
            f"{manifest.previous_package_id}"
        )
    previous_version = manifest.previous_package_id.removeprefix(prefix)
    previous_release = download_verified_km_release(
        repository=github_repository,
        ref=f"{config.tag_prefix}{previous_version}",
        organization_id=config.organization_id,
        km_id=config.km_id,
        version=previous_version,
        tag_prefix=config.tag_prefix,
        token=token,
        api_url=api_url,
        metadata_downloader=metadata_downloader,
        asset_downloader=asset_downloader,
    )

    with tempfile.TemporaryDirectory(prefix="dsw-km-previous-release-") as temporary_dir:
        previous_bundle_path = Path(temporary_dir) / previous_release.asset_name
        previous_bundle_path.write_bytes(previous_release.payload)
        return validate_km_release_repository(
            repo_root=root,
            config_path=resolved_config,
            tag=tag,
            previous_bundle_path=previous_bundle_path,
            allow_unreleased=allow_unreleased,
        )
