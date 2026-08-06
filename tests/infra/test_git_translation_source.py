"""Tests for translation synchronization from a pinned Git checkout."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from dsw_km_translation_tool.git_translation_source import (
    GitTranslationSourceError,
    sync_git_translation_source,
)
from dsw_km_translation_tool.po_support.state import parse_po_entry_states
from tests.infra.test_translation_repository_config import write_github_git_config

PROTECTED_PERSONAL_DATA_QUESTION_UUID = "d5990471-0618-42cd-92cb-bbbfd4f61532"
ETHICS_QUESTION_UUID = "dbb99f35-bdd9-4637-890e-23ba5bc19d6a"


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


def test_git_source_sync_rebuilds_shared_blocks_when_groups_change(
    workspace: Path,
    model_path: Path,
    po_path: Path,
) -> None:
    source_repo = workspace / "source-repo"
    bundle_path = source_repo / "km" / "root.km"
    bundle_path.parent.mkdir(parents=True)
    shutil.copyfile(model_path, bundle_path)
    _commit_repository(source_repo)

    translation_repo = workspace / "translation-repo"
    translation_repo.mkdir()
    config_path = translation_repo / "translation-config.yml"
    write_github_git_config(
        config_path,
        source_ref=_git_output(source_repo, "rev-parse", "HEAD"),
        organization_id="dsw",
        km_id="root",
        version="2.7.0",
        upstream_bundle_path="km/root.km",
    )
    initial_result = sync_git_translation_source(
        repo_root=translation_repo,
        source_repo=source_repo,
        seed_po_path=po_path,
    )
    initial_states = parse_po_entry_states(initial_result.build_result.final_po_path)
    assert initial_states[(PROTECTED_PERSONAL_DATA_QUESTION_UUID, "title")].msgstr
    shared_blocks = translation_repo / "tree" / "shared_blocks"
    initial_group_ids = {path.name for path in shared_blocks.iterdir() if path.is_dir()}

    _replace_latest_question_title(
        bundle_path,
        entity_uuid=PROTECTED_PERSONAL_DATA_QUESTION_UUID,
        title="Shared legal review prompt",
    )
    _replace_latest_question_title(
        bundle_path,
        entity_uuid=ETHICS_QUESTION_UUID,
        title="Shared legal review prompt",
    )
    _commit_change(source_repo, "Change source grouping")
    write_github_git_config(
        config_path,
        source_ref=_git_output(source_repo, "rev-parse", "HEAD"),
        organization_id="dsw",
        km_id="root",
        version="2.7.0",
        upstream_bundle_path="km/root.km",
    )

    updated_result = sync_git_translation_source(
        repo_root=translation_repo,
        source_repo=source_repo,
    )

    updated_group_ids = {path.name for path in shared_blocks.iterdir() if path.is_dir()}
    assert updated_group_ids != initial_group_ids
    updated_states = parse_po_entry_states(updated_result.build_result.final_po_path)
    assert updated_states[(PROTECTED_PERSONAL_DATA_QUESTION_UUID, "title")].msgstr == ""


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


def test_git_source_sync_rejects_tracked_symlink(
    workspace: Path,
    model_path: Path,
) -> None:
    external_bundle = workspace / "external.km"
    shutil.copyfile(model_path, external_bundle)
    source_repo = workspace / "source-repo"
    bundle_path = source_repo / "km" / "root.km"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.symlink_to(external_bundle)
    _commit_repository(source_repo)

    translation_repo = workspace / "translation-repo"
    translation_repo.mkdir()
    write_github_git_config(
        translation_repo / "translation-config.yml",
        source_ref=_git_output(source_repo, "rev-parse", "HEAD"),
        organization_id="dsw",
        km_id="root",
        version="2.7.0",
        upstream_bundle_path="km/root.km",
    )

    with pytest.raises(GitTranslationSourceError, match="not a regular file"):
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


def _commit_change(repo: Path, message: str) -> None:
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
            message,
        ],
        check=True,
    )


def _replace_latest_question_title(
    bundle_path: Path,
    *,
    entity_uuid: str,
    title: str,
) -> None:
    payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    for package in reversed(payload["packages"]):
        for event in reversed(package["events"]):
            if event.get("entityUuid") != entity_uuid:
                continue
            current_title = event["content"].get("title")
            if isinstance(current_title, dict):
                current_title.update({"changed": True, "value": title})
            else:
                event["content"]["title"] = title
            bundle_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return
    raise AssertionError(f"Question not found: {entity_uuid}")


def _git_output(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
