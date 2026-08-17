"""Tests for Localize/Weblate PO source pulls."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsw_km_translation_tool.cli import sync_from_localize
from dsw_km_translation_tool.localize_sync import (
    LocalizePullResult,
    _download_url,
    pull_localize_po,
)
from dsw_km_translation_tool.translation_repository_config import (
    TranslationRepositoryConfigError,
)
from tests.infra.test_translation_repository_config import write_config


def test_pull_localize_po_initializes_latest(workspace: Path) -> None:
    """Verify the first pull writes the latest Weblate snapshot."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    result = pull_localize_po(
        config_path=config_path,
        repo_root=workspace,
        downloader=lambda _url: b"new po",
    )

    assert result.changed is True
    assert result.initialized is True
    assert result.latest_po_path.read_bytes() == b"new po"


def test_downloader_rejects_local_file_urls() -> None:
    """Verify the standard downloader cannot read runner-local files."""

    with pytest.raises(TranslationRepositoryConfigError, match="must be an HTTPS URL"):
        _download_url("file:///tmp/runner-secret")


def test_pull_localize_po_uses_configured_rolling_download_url(
    workspace: Path,
) -> None:
    """Verify Localize pulls use the rolling project URL from config."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path, version="2.8.0")
    requested_urls: list[str] = []

    result = pull_localize_po(
        config_path=config_path,
        repo_root=workspace,
        downloader=lambda url: requested_urls.append(url) or b"new po",
    )

    expected_url = (
        "https://localize.ds-wizard.org/download/knowledge-models/"
        "common-dsw-knowledge-model/zh_Hant/"
    )
    assert requested_urls == [expected_url]
    assert result.url == expected_url


def test_pull_localize_po_replaces_previous_latest(workspace: Path) -> None:
    """Verify changed pulls replace the checked-in Weblate snapshot."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    latest_path = workspace / "sources/localize/zh_Hant/latest.po"
    latest_path.parent.mkdir(parents=True)
    latest_path.write_bytes(b"old latest")

    result = pull_localize_po(
        config_path=config_path,
        repo_root=workspace,
        downloader=lambda _url: b"new latest",
    )

    assert result.changed is True
    assert result.initialized is False
    assert latest_path.read_bytes() == b"new latest"


def test_pull_localize_po_noops_when_latest_is_unchanged(workspace: Path) -> None:
    """Verify unchanged pulls leave the checked-in snapshot untouched."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    latest_path = workspace / "sources/localize/zh_Hant/latest.po"
    latest_path.parent.mkdir(parents=True)
    latest_path.write_bytes(b"same")

    result = pull_localize_po(
        config_path=config_path,
        repo_root=workspace,
        downloader=lambda _url: b"same",
    )

    assert result.changed is False
    assert result.initialized is False
    assert latest_path.read_bytes() == b"same"


def test_sync_from_localize_runs_pull_refresh_and_commit(
    monkeypatch,
    workspace: Path,
) -> None:
    """Verify the Localize sync CLI wires its three explicit phases."""

    host_repo = workspace / "translation-repo"
    tooling_repo = workspace / "tooling-repo"
    host_repo.mkdir()
    tooling_repo.mkdir()
    write_config(host_repo / "translation-config.yml")
    recorded_config: dict[str, object] = {}

    def fake_pull_localize_po(**kwargs):
        assert set(kwargs) == {"config_path", "repo_root"}
        return LocalizePullResult(
            version="2.7.0",
            url="https://example.test/localize.po",
            latest_po_path=host_repo / "sources/localize/zh_Hant/latest.po",
            changed=False,
            initialized=False,
            bytes_downloaded=0,
        )

    def fake_build_repository_ci_sync_config(**kwargs):
        recorded_config.update(kwargs)
        return object()

    def fake_refresh_tree_from_localize(**_kwargs):
        return SimpleNamespace(
            version="2.7.0",
            tree_dir=host_repo / "tree",
            folder_count=0,
            root_count=0,
            shared_block_file_count=0,
        )

    monkeypatch.setattr(sync_from_localize, "pull_localize_po", fake_pull_localize_po)
    monkeypatch.setattr(
        sync_from_localize,
        "build_repository_ci_sync_config",
        fake_build_repository_ci_sync_config,
    )
    monkeypatch.setattr(
        sync_from_localize,
        "refresh_tree_from_localize",
        fake_refresh_tree_from_localize,
    )
    monkeypatch.setattr(sync_from_localize, "run_ci_sync_commit", lambda _config: False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-sync-localize",
            "--host-repo",
            str(host_repo),
            "--tooling-repo",
            str(tooling_repo),
            "--mode",
            "pull_request",
        ],
    )

    sync_from_localize.main()

    assert recorded_config["host_repo_path"] == host_repo
    assert recorded_config["mode"] == "pull_request"
