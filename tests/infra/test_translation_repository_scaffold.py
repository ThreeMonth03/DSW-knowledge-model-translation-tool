"""Tests for managed translation repository docs and workflows."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsw_km_translation_tool.translation_repository_scaffold import (
    TranslationRepositoryScaffoldError,
    check_translation_repository_scaffold,
    sync_translation_repository_scaffold,
)
from tests.helpers import run_cli_command
from tests.infra.test_translation_repository_config import (
    write_config,
    write_github_git_config,
)


def test_scaffold_sync_is_idempotent_and_preserves_config(
    repo_root: Path,
    workspace: Path,
) -> None:
    """Verify scaffold sync changes only managed docs and workflows."""

    target_repo = workspace / "translation-repo"
    target_repo.mkdir()
    config_path = target_repo / "translation-config.yml"
    write_config(config_path)
    original_config = config_path.read_bytes()

    first_sync = sync_translation_repository_scaffold(
        repo_root=target_repo,
        tooling_repo=repo_root,
    )

    assert first_sync.changed_files
    assert Path("translation-config.yml") not in first_sync.managed_files
    assert config_path.read_bytes() == original_config
    assert check_translation_repository_scaffold(
        repo_root=target_repo,
        tooling_repo=repo_root,
    ).aligned

    second_sync = sync_translation_repository_scaffold(
        repo_root=target_repo,
        tooling_repo=repo_root,
    )

    assert second_sync.changed_files == ()
    assert config_path.read_bytes() == original_config


def test_scaffold_check_reports_drift_and_sync_repairs_it(
    repo_root: Path,
    workspace: Path,
) -> None:
    """Verify one edited managed file is reported and restored."""

    target_repo = workspace / "translation-repo"
    target_repo.mkdir()
    write_config(target_repo / "translation-config.yml")
    sync_translation_repository_scaffold(repo_root=target_repo, tooling_repo=repo_root)
    readme_path = target_repo / "docs" / "README.md"
    readme_path.write_text("drift\n", encoding="utf-8")

    check = check_translation_repository_scaffold(
        repo_root=target_repo,
        tooling_repo=repo_root,
    )

    assert check.changed_files == (Path("docs/README.md"),)
    sync = sync_translation_repository_scaffold(
        repo_root=target_repo,
        tooling_repo=repo_root,
    )
    assert sync.changed_files == (Path("docs/README.md"),)
    assert check_translation_repository_scaffold(
        repo_root=target_repo,
        tooling_repo=repo_root,
    ).aligned


def test_scaffold_rejects_unknown_template_tokens(
    workspace: Path,
) -> None:
    """Verify misspelled template tokens fail instead of leaking into output."""

    tooling_repo = workspace / "tooling"
    template_dir = tooling_repo / "examples" / "translation-repository"
    workflow_dir = tooling_repo / "examples" / "github-actions"
    template_dir.mkdir(parents=True)
    workflow_dir.mkdir(parents=True)
    (template_dir / "README.md").write_text("{{unknown_value}}\n", encoding="utf-8")
    target_repo = workspace / "translation-repo"
    target_repo.mkdir()
    write_config(target_repo / "translation-config.yml")

    with pytest.raises(TranslationRepositoryScaffoldError, match="unknown_value"):
        check_translation_repository_scaffold(
            repo_root=target_repo,
            tooling_repo=tooling_repo,
        )


def test_scaffold_cli_check_fails_on_drift(
    repo_root: Path,
    workspace: Path,
) -> None:
    """Verify the packaged check command returns a useful nonzero result."""

    target_repo = workspace / "translation-repo"
    target_repo.mkdir()
    write_config(target_repo / "translation-config.yml")

    result = run_cli_command(
        repo_root,
        "dsw-km-scaffold",
        "check",
        "--repo-root",
        str(target_repo),
        "--tooling-repo",
        str(repo_root),
    )

    assert result.returncode == 1
    assert "Changed" in result.stdout
    assert "docs/README.md" in result.stdout


def test_scaffold_renders_pinned_git_source_profile(
    repo_root: Path,
    workspace: Path,
) -> None:
    target_repo = workspace / "translation-repo"
    target_repo.mkdir()
    write_github_git_config(target_repo / "translation-config.yml")

    result = sync_translation_repository_scaffold(
        repo_root=target_repo,
        tooling_repo=repo_root,
    )

    assert result.aligned is False
    workflow = (target_repo / ".github/workflows/translation_ci.yml").read_text(encoding="utf-8")
    release_workflow = (target_repo / ".github/workflows/release.yml").read_text(encoding="utf-8")
    readme = (target_repo / "README.md").read_text(encoding="utf-8")
    assert "dsw-km-sync-git-source" in workflow
    assert 'SOURCE_REF: "' + "1" * 40 + '"' in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "tw-root-tw-zh-hant-${{ github.sha }}" in workflow
    assert "gh release create" in release_workflow
    assert "tw-root-tw-zh-hant-${version}.km" in release_workflow
    assert "translation-config.yml" in release_workflow
    assert "bundle: `km/root-tw.km`" in readme
    assert check_translation_repository_scaffold(
        repo_root=target_repo,
        tooling_repo=repo_root,
    ).aligned
