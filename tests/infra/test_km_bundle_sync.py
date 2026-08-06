"""Tests for DSW Registry KM bundle pulls."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsw_km_translation_tool.km_bundle_sync import pull_km_bundle
from dsw_km_translation_tool.km_registry import KmRegistryError
from tests.helpers import run_cli_command
from tests.infra.test_translation_repository_config import write_config


def test_pull_km_bundle_initializes_source_snapshot(workspace: Path) -> None:
    """Verify the first bundle pull writes the conventional source KM path."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    requested: list[tuple[str, str]] = []

    def downloader(url: str, token: str) -> bytes:
        requested.append((url, token))
        return b"km bundle"

    result = pull_km_bundle(
        config_path=config_path,
        repo_root=workspace,
        token="secret",
        downloader=downloader,
    )

    assert requested == [
        (
            "https://api.registry.ds-wizard.org/knowledge-model-packages/dsw%3Aroot%3A2.7.0/bundle",
            "secret",
        )
    ]
    assert result.changed is True
    assert result.initialized is True
    assert result.target_path == (
        workspace / "sources/knowledge-models/dsw-root-2.7.0/dsw-root-2.7.0.km"
    )
    assert result.target_path.read_bytes() == b"km bundle"


def test_pull_km_bundle_leaves_matching_existing_snapshot(workspace: Path) -> None:
    """Verify repeated pulls with identical bytes are unchanged."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    target_path = workspace / "sources/knowledge-models/dsw-root-2.7.0/dsw-root-2.7.0.km"
    target_path.parent.mkdir(parents=True)
    target_path.write_bytes(b"same bundle")

    result = pull_km_bundle(
        config_path=config_path,
        repo_root=workspace,
        token="secret",
        downloader=lambda _url, _token: b"same bundle",
    )

    assert result.changed is False
    assert result.initialized is False
    assert result.previous_sha256 == result.sha256
    assert target_path.read_bytes() == b"same bundle"


def test_pull_km_bundle_accepts_equivalent_json_snapshot(workspace: Path) -> None:
    """Verify JSON serialization differences do not violate immutability."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    target_path = workspace / "sources/knowledge-models/dsw-root-2.7.0/dsw-root-2.7.0.km"
    target_path.parent.mkdir(parents=True)
    cached = b'{\n  "packages": [{"version": "2.7.0", "events": []}],\n  "name": "Root"\n}\n'
    downloaded = b'{"name":"Root","packages":[{"events":[],"version":"2.7.0"}]}'
    target_path.write_bytes(cached)

    result = pull_km_bundle(
        config_path=config_path,
        repo_root=workspace,
        token="secret",
        downloader=lambda _url, _token: downloaded,
    )

    assert result.changed is False
    assert result.initialized is False
    assert result.previous_sha256 != result.sha256
    assert target_path.read_bytes() == cached


def test_pull_km_bundle_refuses_changed_existing_snapshot(workspace: Path) -> None:
    """Verify existing version snapshots are immutable by default."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    target_path = workspace / "sources/knowledge-models/dsw-root-2.7.0/dsw-root-2.7.0.km"
    target_path.parent.mkdir(parents=True)
    target_path.write_bytes(b"old bundle")

    with pytest.raises(KmRegistryError, match="Refusing to overwrite") as error:
        pull_km_bundle(
            config_path=config_path,
            repo_root=workspace,
            token="secret",
            downloader=lambda _url, _token: b"new bundle",
        )

    assert "Previous SHA256:" in str(error.value)
    assert "downloaded SHA256:" in str(error.value)
    assert target_path.read_bytes() == b"old bundle"


def test_pull_km_bundle_requires_token(workspace: Path) -> None:
    """Verify missing Registry tokens are rejected before download."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)

    with pytest.raises(KmRegistryError, match="requires a token"):
        pull_km_bundle(
            config_path=config_path,
            repo_root=workspace,
            token="",
            downloader=lambda _url, _token: b"unused",
        )


def test_pull_km_bundle_cli_can_skip_without_token(repo_root: Path, workspace: Path) -> None:
    """Verify workflows can safely skip bundle pulls until a token is configured."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)

    result = run_cli_command(
        repo_root,
        "dsw-km-pull-bundle",
        "--repo-root",
        str(workspace),
        "--config",
        "translation-config.yml",
        "--registry-token-env",
        "MISSING_DSW_REGISTRY_TOKEN_FOR_TEST",
        "--skip-without-token",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Skipping KM bundle pull" in result.stdout
