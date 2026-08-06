"""Tests for checked-in GitHub workflow policy and wiring."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import yaml

from dsw_km_translation_tool.translation_repository_config import (
    load_translation_repository_config,
)
from dsw_km_translation_tool.translation_repository_scaffold import (
    render_translation_repository_scaffold,
)
from tests.infra.test_translation_repository_config import write_github_config

EXPECTED_TOOLING_REPOSITORY = "ThreeMonth03/dsw-km-translation-tool"
EXPECTED_TOOLING_REF = "master"


def load_workflow_yaml(path: Path) -> dict[str, object]:
    """Load one workflow file with a YAML loader that preserves `on`.

    Args:
        path: Workflow YAML path.

    Returns:
        Parsed workflow payload.
    """

    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def load_rendered_workflow(
    repo_root: Path,
    template_name: str,
) -> tuple[dict[str, object], str]:
    """Render one workflow template with the example repository config."""

    target_name = template_name.removesuffix("_template.yml") + ".yml"
    target_path = Path(".github") / "workflows" / target_name
    config = load_translation_repository_config(repo_root / "examples" / "translation-config.yml")
    files = render_translation_repository_scaffold(tooling_repo=repo_root, config=config)
    rendered = next(item.content for item in files if item.path == target_path)
    return yaml.load(rendered, Loader=yaml.BaseLoader), rendered


def assert_tooling_checkout_env(workflow: dict[str, object]) -> None:
    """Verify a workflow checks out the expected tooling repository ref."""

    assert workflow["env"]["TOOLING_REPOSITORY"] == EXPECTED_TOOLING_REPOSITORY
    assert workflow["env"]["TOOLING_REF"] == EXPECTED_TOOLING_REF


def test_localize_auto_sync_template_matches_writer_policy(
    repo_root: Path,
) -> None:
    """Verify the Localize auto-sync template matches the intended CI policy.

    Args:
        repo_root: Repository root fixture.
    """

    workflow, workflow_text = load_rendered_workflow(
        repo_root,
        "localize_auto_sync_template.yml",
    )

    assert workflow["on"]["schedule"][0]["cron"] == "0 1,13 * * *"
    assert "pull_request" not in workflow["on"]
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"]["contents"] == "write"
    assert workflow["concurrency"]["queue"] == "max"
    assert_tooling_checkout_env(workflow)
    assert workflow["env"]["TRACKING_BRANCH"] == "master"
    assert workflow["env"]["TRANSLATION_CONFIG"] == "translation-config.yml"
    assert workflow["env"]["TRANSLATION_ROOT"] == "."
    assert "if" not in workflow["jobs"]["sync-writer"]
    assert "translation-state-master" in workflow_text
    assert "refs/remotes/base/${{ env.TRACKING_BRANCH }}" in workflow_text
    assert "tooling-repo/.venv/bin/dsw-km-sync-localize" in workflow_text
    assert "tooling-repo/src/" not in workflow_text
    assert "dsw-km-discover-versions" not in workflow_text
    assert "dsw-km-sync-latest-km" not in workflow_text
    assert "dsw-km-pull-localize-po" not in workflow_text
    assert "DSW_REGISTRY_TOKEN" not in workflow_text
    assert "--config" in workflow_text
    assert "--km-version" not in workflow_text
    assert "--skip-without-token" not in workflow_text
    assert "reviews/km_version_discovery.json" not in workflow_text
    assert "--restore-source-ref" in workflow_text
    assert "base/${{ env.TRACKING_BRANCH }}" in workflow_text
    assert "github.event.pull_request" not in workflow_text


def test_github_translation_import_template_is_guarded_writer(repo_root: Path) -> None:
    """Verify GitHub translation import writes Weblate only after merge."""

    workflow, workflow_text = load_rendered_workflow(
        repo_root,
        "github_translation_import_template.yml",
    )

    assert workflow["on"]["push"]["branches"] == ["master"]
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["on"]["workflow_dispatch"]["inputs"]["base_ref"]["default"] == "HEAD^"
    assert workflow["on"]["workflow_dispatch"]["inputs"]["head_ref"]["default"] == "HEAD"
    assert workflow["permissions"]["contents"] == "write"
    assert workflow["concurrency"]["group"] == "translation-state-master"
    assert workflow["concurrency"]["queue"] == "max"
    assert "github.actor != 'github-actions[bot]'" in workflow_text
    assert_tooling_checkout_env(workflow)
    assert workflow["env"]["TRACKING_BRANCH"] == "master"
    assert workflow["env"]["TRANSLATION_CONFIG"] == "translation-config.yml"
    assert "secrets.LOCALIZE_API_TOKEN" in workflow_text
    assert "tooling-repo/.venv/bin/dsw-km-import-github-translations" in workflow_text
    assert "tooling-repo/.venv/bin/dsw-km-sync-localize" in workflow_text
    assert "steps.import-github-translations.outputs.uploaded == 'true'" in workflow_text
    assert "github-translation-import" in workflow_text
    assert "pull_request" not in workflow["on"]
    assert "DSW_REGISTRY_TOKEN" not in workflow_text
    assert "tooling-repo/src/" not in workflow_text


def test_localize_status_report_template_is_read_only(repo_root: Path) -> None:
    """Verify the status report template cannot write translations."""

    workflow, workflow_text = load_rendered_workflow(
        repo_root,
        "localize_status_report_template.yml",
    )

    assert workflow["on"]["schedule"][0]["cron"] == "30 1,13 * * *"
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"]["contents"] == "read"
    assert_tooling_checkout_env(workflow)
    assert workflow["env"]["TRACKING_BRANCH"] == "master"
    assert workflow["env"]["TARGET_LANG"] == "zh_Hant"
    assert workflow["env"]["TRANSLATION_CONFIG"] == "translation-config.yml"
    assert "KNOWN_FUZZY_REFERENCES" not in workflow["env"]
    assert "tooling-repo/.venv/bin/dsw-km-pull-localize-po" in workflow_text
    assert "tooling-repo/.venv/bin/dsw-km-report-localize-status" in workflow_text
    assert "tooling-repo/.venv/bin/dsw-km-report-weblate-checks" in workflow_text
    assert "secrets.LOCALIZE_API_TOKEN" in workflow_text
    assert "translation-repo/reviews/localize_status_report.json" in workflow_text
    assert "translation-repo/reviews/localize_status_report.md" in workflow_text
    assert "translation-repo/reviews/weblate_checks_report.json" in workflow_text
    assert "translation-repo/reviews/weblate_checks_report.md" in workflow_text
    assert "--details-out" in workflow_text
    assert "--known-" not in workflow_text
    assert "--allow-api-failure" in workflow_text
    assert "actions/upload-artifact@v7" in workflow_text
    assert "dsw-km-sync-localize" not in workflow_text
    assert "tooling-repo/src/" not in workflow_text
    assert "contents: write" not in workflow_text


def test_localize_alignment_report_template_is_read_only(repo_root: Path) -> None:
    """Verify the alignment report template only checks repository consistency."""

    workflow, workflow_text = load_rendered_workflow(
        repo_root,
        "localize_alignment_report_template.yml",
    )

    assert workflow["on"]["schedule"][0]["cron"] == "45 1,13 * * *"
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"]["contents"] == "read"
    assert_tooling_checkout_env(workflow)
    assert workflow["env"]["TRACKING_BRANCH"] == "master"
    assert workflow["env"]["TRANSLATION_CONFIG"] == "translation-config.yml"
    assert "tooling-repo/.venv/bin/dsw-km-report-alignment" in workflow_text
    assert "--fail-on-mismatch" in workflow_text
    assert "translation-repo/reviews/localize_alignment_report.json" in workflow_text
    assert "translation-repo/reviews/localize_alignment_artifacts/" in workflow_text
    assert "actions/upload-artifact@v7" in workflow_text
    assert "dsw-km-pull-localize-po" not in workflow_text
    assert "dsw-km-sync-localize" not in workflow_text
    assert "tooling-repo/src/" not in workflow_text
    assert "contents: write" not in workflow_text


def test_km_version_auto_update_template_is_guarded_writer(repo_root: Path) -> None:
    """Verify the KM version auto-update template writes Git only after validation."""

    workflow, workflow_text = load_rendered_workflow(
        repo_root,
        "km_version_auto_update_template.yml",
    )

    assert workflow["on"]["schedule"][0]["cron"] == "15 2 * * *"
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"]["contents"] == "write"
    assert workflow["concurrency"]["group"] == "translation-state-master"
    assert workflow["concurrency"]["queue"] == "max"
    assert "github.actor != 'github-actions[bot]'" in workflow_text
    assert_tooling_checkout_env(workflow)
    assert workflow["env"]["TRACKING_BRANCH"] == "master"
    assert workflow["env"]["TRANSLATION_CONFIG"] == "translation-config.yml"
    assert "tooling-repo/.venv/bin/dsw-km-sync-latest-km" in workflow_text
    assert "--target-ref" in workflow_text
    assert '--report "$RUNNER_TEMP/km_auto_update_report.json"' in workflow_text
    assert '--details-out "$RUNNER_TEMP/km_auto_update_report.md"' in workflow_text
    assert "secrets.DSW_REGISTRY_TOKEN" in workflow_text
    assert "km-version-auto-update" in workflow_text
    assert "if-no-files-found: ignore" in workflow_text
    assert "actions/upload-artifact@v7" in workflow_text
    assert "dsw-km-sync-localize" not in workflow_text
    assert "tooling-repo/src/" not in workflow_text


def test_validate_translation_config_template_is_read_only(repo_root: Path) -> None:
    """Verify the config validation template cannot write translations."""

    workflow, workflow_text = load_rendered_workflow(
        repo_root,
        "validate_translation_config_template.yml",
    )

    assert workflow["on"]["pull_request"]["branches"] == ["master"]
    assert workflow["on"]["push"]["branches"] == ["master"]
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"]["contents"] == "read"
    assert_tooling_checkout_env(workflow)
    assert "tooling-repo/.venv/bin/dsw-km-validate-config" in workflow_text
    assert "tooling-repo/.venv/bin/dsw-km-scaffold check" in workflow_text
    assert "--summary" in workflow_text
    assert "dsw-km-sync-localize" not in workflow_text
    assert "dsw-km-sync-latest-km" not in workflow_text
    assert "tooling-repo/src/" not in workflow_text
    assert "DSW_REGISTRY_TOKEN" not in workflow_text
    assert "contents: write" not in workflow_text


def test_workflow_templates_render_non_default_tracking_branch(repo_root: Path) -> None:
    """Verify every branch placeholder follows repository configuration."""

    config = load_translation_repository_config(repo_root / "examples" / "translation-config.yml")
    config = replace(
        config,
        branches=replace(config.branches, tracking_branch="release"),
    )
    files = render_translation_repository_scaffold(tooling_repo=repo_root, config=config)
    workflows = {
        item.path.name: (yaml.load(item.content, Loader=yaml.BaseLoader), item.content)
        for item in files
        if item.path.parent == Path(".github/workflows")
    }

    validation, _ = workflows["validate_translation_config.yml"]
    assert validation["on"]["pull_request"]["branches"] == ["release"]
    assert validation["on"]["push"]["branches"] == ["release"]

    auto_sync, auto_sync_text = workflows["localize_auto_sync.yml"]
    assert "pull_request" not in auto_sync["on"]
    assert "translation-state-release" in auto_sync_text

    github_import, _ = workflows["github_translation_import.yml"]
    assert github_import["on"]["push"]["branches"] == ["release"]
    assert github_import["concurrency"]["group"] == "translation-state-release"

    for _, workflow_text in workflows.values():
        for token in ("TOOLING_REPOSITORY", "TOOLING_REF", "TRACKING_BRANCH"):
            assert f"{{{{{token}}}}}" not in workflow_text


def test_upstream_smoke_workflow_is_tooling_integration_check(repo_root: Path) -> None:
    """Verify the tooling repo smoke workflow checks live upstream sources."""

    workflow_path = repo_root / ".github" / "workflows" / "upstream_smoke.yml"
    workflow = load_workflow_yaml(workflow_path)
    workflow_text = workflow_path.read_text(encoding="utf-8")

    assert workflow["on"]["schedule"][0]["cron"] == "20 3 * * *"
    assert "workflow_dispatch" in workflow["on"]
    assert workflow["permissions"]["contents"] == "read"
    assert "actions/cache/restore@v5" in workflow_text
    assert "actions/cache/save@v5" in workflow_text
    assert ".cache/upstream-smoke/sources/knowledge-models" in workflow_text
    assert "make upstream-smoke" in workflow_text
    assert "secrets.DSW_REGISTRY_TOKEN" in workflow_text
    assert "actions/upload-artifact@v7" in workflow_text
    assert "git push" not in workflow_text
    assert "contents: write" not in workflow_text


def test_github_only_translation_workflow_has_no_weblate_dependency(
    repo_root: Path,
    workspace: Path,
) -> None:
    config_path = workspace / "translation-config.yml"
    write_github_config(config_path)
    config = load_translation_repository_config(config_path)
    files = render_translation_repository_scaffold(tooling_repo=repo_root, config=config)
    workflow_item = next(
        item for item in files if item.path == Path(".github/workflows/translation_ci.yml")
    )
    workflow = yaml.load(workflow_item.content, Loader=yaml.BaseLoader)

    assert workflow["permissions"]["contents"] == "read"
    assert workflow["on"]["pull_request"]["branches"] == ["main"]
    assert "dsw-km-build-translation-repo" in workflow_item.content
    assert "dsw-km-sync-github-release" in workflow_item.content
    assert "--check" in workflow_item.content
    assert "--allow-uninitialized" in workflow_item.content
    assert "git diff --exit-code" in workflow_item.content
    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow_item.content
    assert "LOCALIZE_API_TOKEN" not in workflow_item.content
    assert "Weblate" not in workflow_item.content


def test_source_workflows_verify_previous_github_release(repo_root: Path) -> None:
    template_root = repo_root / "examples" / "km-source-repository" / ".github" / "workflows"
    for name in ("validate.yml", "release.yml"):
        text = (template_root / name).read_text(encoding="utf-8")
        assert "GITHUB_TOKEN: ${{ github.token }}" in text
        assert '--github-repository "$GITHUB_REPOSITORY"' in text
