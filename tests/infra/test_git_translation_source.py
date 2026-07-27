"""Tests for translation synchronization from a pinned Git checkout."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from dsw_km_translation_tool.git_translation_source import (
    GitTranslationSourceError,
    sync_git_translation_source,
)
from tests.infra.test_translation_repository_config import write_github_git_config


def test_git_source_sync_validates_commit_and_rebuilds(
    workspace: Path,
    model_path: Path,
    po_path: Path,
) -> None:
    source_repo = workspace / "source-repo"
    bundle_path = source_repo / "km" / "root.km"
    bundle_path.parent.mkdir(parents=True)
    shutil.copyfile(model_path, bundle_path)
    _commit_repository(source_repo)
    source_ref = _git_output(source_repo, "rev-parse", "HEAD")

    translation_repo = workspace / "translation-repo"
    translation_repo.mkdir()
    write_github_git_config(
        translation_repo / "translation-config.yml",
        source_ref=source_ref,
        organization_id="dsw",
        km_id="root",
        version="2.7.0",
        upstream_bundle_path="km/root.km",
    )

    result = sync_git_translation_source(
        repo_root=translation_repo,
        source_repo=source_repo,
        seed_po_path=po_path,
    )

    assert result.ref == source_ref
    assert result.package_id == "dsw:root:2.7.0"
    assert result.source_km_path.read_bytes() == model_path.read_bytes()
    assert result.carried_translation_count > 0
    assert result.build_result.final_po_path.is_file()
    assert result.build_result.final_km_path.is_file()


def test_git_source_sync_rejects_moved_checkout(
    workspace: Path,
    model_path: Path,
) -> None:
    source_repo = workspace / "source-repo"
    bundle_path = source_repo / "km" / "root.km"
    bundle_path.parent.mkdir(parents=True)
    shutil.copyfile(model_path, bundle_path)
    _commit_repository(source_repo)

    translation_repo = workspace / "translation-repo"
    translation_repo.mkdir()
    write_github_git_config(
        translation_repo / "translation-config.yml",
        source_ref="1" * 40,
        organization_id="dsw",
        km_id="root",
        version="2.7.0",
        upstream_bundle_path="km/root.km",
    )

    with pytest.raises(GitTranslationSourceError, match="config pins"):
        sync_git_translation_source(
            repo_root=translation_repo,
            source_repo=source_repo,
        )


def test_git_source_sync_rejects_uncommitted_bundle(
    workspace: Path,
    model_path: Path,
) -> None:
    source_repo = workspace / "source-repo"
    bundle_path = source_repo / "km" / "root.km"
    bundle_path.parent.mkdir(parents=True)
    shutil.copyfile(model_path, bundle_path)
    _commit_repository(source_repo)
    source_ref = _git_output(source_repo, "rev-parse", "HEAD")
    bundle_path.write_text("{}\n", encoding="utf-8")

    translation_repo = workspace / "translation-repo"
    translation_repo.mkdir()
    write_github_git_config(
        translation_repo / "translation-config.yml",
        source_ref=source_ref,
        organization_id="dsw",
        km_id="root",
        version="2.7.0",
        upstream_bundle_path="km/root.km",
    )

    with pytest.raises(GitTranslationSourceError, match="differs from pinned commit"):
        sync_git_translation_source(
            repo_root=translation_repo,
            source_repo=source_repo,
        )


def _commit_repository(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "km/root.km"], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-q",
            "-m",
            "Add source",
        ],
        check=True,
    )


def _git_output(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
