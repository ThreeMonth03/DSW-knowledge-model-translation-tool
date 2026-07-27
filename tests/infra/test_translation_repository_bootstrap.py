"""Tests for initializing dedicated translation repositories."""

from __future__ import annotations

from pathlib import Path

from dsw_km_translation_tool.translation_repository_bootstrap import (
    TranslationRepositoryBootstrapError,
    bootstrap_translation_repository,
)
from tests.helpers import run_cli_command
from tests.infra.test_translation_repository_config import write_config, write_github_config


def test_bootstrap_scaffolds_config_docs_and_workflows(
    repo_root: Path,
    workspace: Path,
) -> None:
    """Verify scaffold-only bootstrap copies managed repository files."""

    config_template = workspace / "template.yml"
    target_repo = workspace / "translation-repo"
    write_config(config_template)

    result = bootstrap_translation_repository(
        repo_root=target_repo,
        tooling_repo=repo_root,
        config_template_path=config_template,
        hydrate=False,
    )

    assert result.hydrated is False
    assert (target_repo / "translation-config.yml").exists()
    assert (target_repo / "README.md").exists()
    docs_readme = target_repo / "docs" / "README.md"
    assert docs_readme.exists()
    docs_text = docs_readme.read_text(encoding="utf-8")
    assert "the zh-Hant Common DSW Knowledge Model translation" in docs_text
    assert "ThreeMonth03/dsw-km-translation-tool/tree/master" in docs_text
    assert "{{" not in docs_text
    handoff_text = (target_repo / "docs" / "handoff-checklist.md").read_text(encoding="utf-8")
    assert "Formal zh-Hant translation mirror" in handoff_text
    assert "ThreeMonth03/dsw-km-translation-tool" in handoff_text
    workflow = target_repo / ".github" / "workflows" / "localize_auto_sync.yml"
    assert workflow.exists()
    workflow_text = workflow.read_text(encoding="utf-8")
    assert "TOOLING_REPOSITORY: ThreeMonth03/dsw-km-translation-tool" in workflow_text
    assert "TRACKING_BRANCH: translation/latest" in workflow_text
    assert 'branches: ["translation/latest"]' in workflow_text
    assert result.written_files
    assert result.skipped_files == ()


def test_bootstrap_hydrates_tree_and_build_outputs(
    repo_root: Path,
    workspace: Path,
    po_path: Path,
    model_path: Path,
) -> None:
    """Verify bootstrap can hydrate a repo from injected KM and PO downloads."""

    config_template = workspace / "template.yml"
    target_repo = workspace / "translation-repo"
    write_config(config_template)

    result = bootstrap_translation_repository(
        repo_root=target_repo,
        tooling_repo=repo_root,
        config_template_path=config_template,
        registry_token="token",
        bundle_downloader=lambda _url, _token: model_path.read_bytes(),
        localize_downloader=lambda _url: po_path.read_bytes(),
    )

    assert result.hydrated is True
    assert result.km_version == "2.7.0"
    assert result.source_km_path == (
        target_repo / "sources" / "knowledge-models" / "dsw-root-2.7.0" / "dsw-root-2.7.0.km"
    )
    assert result.localize_po_path == target_repo / "sources" / "localize" / "zh_Hant" / "latest.po"
    assert (target_repo / "tree" / "_translation_tree.json").exists()
    assert (target_repo / "builds" / "final_translated.po").exists()
    assert (target_repo / "builds" / "final_translated.km").exists()
    assert (target_repo / "reviews" / "final_translated.diff").exists()


def test_bootstrap_requires_registry_token_for_hydration(
    repo_root: Path,
    workspace: Path,
) -> None:
    """Verify hydration fails clearly when no Registry token is available."""

    config_template = workspace / "template.yml"
    write_config(config_template)

    try:
        bootstrap_translation_repository(
            repo_root=workspace / "translation-repo",
            tooling_repo=repo_root,
            config_template_path=config_template,
            registry_token="",
        )
    except TranslationRepositoryBootstrapError as error:
        assert "DSW_REGISTRY_TOKEN" in str(error)
    else:
        raise AssertionError("Expected bootstrap to require a Registry token")


def test_bootstrap_skips_config_when_source_and_target_are_the_same(
    repo_root: Path,
    workspace: Path,
) -> None:
    """Verify an existing config is not copied onto itself during scaffold review."""

    target_repo = workspace / "translation-repo"
    target_repo.mkdir()
    config_path = target_repo / "translation-config.yml"
    write_config(config_path)
    original_config = config_path.read_bytes()

    result = bootstrap_translation_repository(
        repo_root=target_repo,
        tooling_repo=repo_root,
        config_template_path=config_path,
        hydrate=False,
        overwrite=True,
    )

    assert config_path in result.skipped_files
    assert config_path.read_bytes() == original_config


def test_init_translation_repo_cli_scaffold_only(
    repo_root: Path,
    workspace: Path,
) -> None:
    """Verify the packaged CLI can scaffold a repository without downloads."""

    config_template = workspace / "template.yml"
    target_repo = workspace / "translation-repo"
    write_config(config_template)

    result = run_cli_command(
        repo_root,
        "dsw-km-init-translation-repo",
        "--repo-root",
        str(target_repo),
        "--tooling-repo",
        str(repo_root),
        "--config-template",
        str(config_template),
        "--scaffold-only",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Hydrated   : no" in result.stdout
    assert (target_repo / ".github" / "workflows" / "validate_translation_config.yml").exists()


def test_github_bootstrap_scaffolds_without_weblate(
    repo_root: Path,
    workspace: Path,
) -> None:
    config_template = workspace / "github.yml"
    target_repo = workspace / "translation-repo"
    write_github_config(config_template)

    result = bootstrap_translation_repository(
        repo_root=target_repo,
        tooling_repo=repo_root,
        config_template_path=config_template,
        hydrate=False,
    )

    assert result.hydrated is False
    assert (target_repo / ".github" / "workflows" / "translation_ci.yml").exists()
    assert not (target_repo / ".github" / "workflows" / "localize_auto_sync.yml").exists()
    assert "no Weblate dependency" in (target_repo / "README.md").read_text(encoding="utf-8")


def test_github_bootstrap_generates_empty_catalog_from_km(
    repo_root: Path,
    workspace: Path,
    model_path: Path,
) -> None:
    config_template = workspace / "github.yml"
    target_repo = workspace / "translation-repo"
    write_github_config(
        config_template,
        organization_id="dsw",
        km_id="root",
        version="2.7.0",
    )

    result = bootstrap_translation_repository(
        repo_root=target_repo,
        tooling_repo=repo_root,
        config_template_path=config_template,
        source_km_input=model_path,
    )

    assert result.hydrated is True
    assert result.source_po_path == target_repo / "sources/catalog/zh_Hant/catalog.po"
    assert result.source_po_path.exists()
    assert (target_repo / "tree" / "_translation_tree.json").exists()
    assert (target_repo / "builds" / "final_translated.km").exists()
