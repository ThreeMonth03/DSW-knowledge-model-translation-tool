"""Tests for GitHub-only source KM synchronization."""

from __future__ import annotations

from pathlib import Path

from dsw_km_translation_tool.github_translation_source import (
    sync_github_translation_source,
)
from tests.infra.test_github_release import release_downloaders
from tests.infra.test_translation_repository_config import write_github_config


def test_github_source_sync_hydrates_and_then_checks_repository(
    workspace: Path,
    model_path: Path,
) -> None:
    target = workspace / "translation-repo"
    target.mkdir()
    config_path = target / "translation-config.yml"
    write_github_config(
        config_path,
        organization_id="dsw",
        km_id="root",
        version="2.7.0",
    )
    metadata_downloader, asset_downloader = release_downloaders(payload=model_path.read_bytes())

    synchronized = sync_github_translation_source(
        repo_root=target,
        metadata_downloader=metadata_downloader,
        asset_downloader=asset_downloader,
    )

    assert synchronized.initialized is True
    assert synchronized.changed is True
    assert synchronized.checked_only is False
    assert synchronized.package_id == "dsw:root:2.7.0"
    assert synchronized.source_km_path.read_bytes() == model_path.read_bytes()
    assert synchronized.source_po_path.is_file()
    assert (target / "tree" / "_translation_tree.json").is_file()
    assert (target / "builds" / "final_translated.km").is_file()

    checked = sync_github_translation_source(
        repo_root=target,
        check=True,
        metadata_downloader=metadata_downloader,
        asset_downloader=asset_downloader,
    )

    assert checked.initialized is True
    assert checked.changed is False
    assert checked.checked_only is True


def test_github_source_check_allows_empty_unreleased_repository(
    workspace: Path,
) -> None:
    target = workspace / "translation-repo"
    target.mkdir()
    config_path = target / "translation-config.yml"
    write_github_config(config_path)
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "  upstream_ref: v0.1.0",
            "  upstream_ref: UNRELEASED",
        ),
        encoding="utf-8",
    )

    result = sync_github_translation_source(
        repo_root=target,
        check=True,
        allow_unreleased=True,
    )

    assert result.initialized is False
    assert result.checked_only is True
