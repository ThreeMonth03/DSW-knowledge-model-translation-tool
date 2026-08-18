"""Security coverage for repository-aware documentation links."""

from __future__ import annotations

from pathlib import Path

SECURITY_LINKS = {
    "docs/architecture.md": {
        "github-import-template": (
            "repo-file:examples/github-actions/github_translation_import_template.yml"
        ),
        "km-auto-update-template": (
            "repo-file:examples/github-actions/km_version_auto_update_template.yml"
        ),
        "localize-alignment-template": (
            "repo-file:examples/github-actions/localize_alignment_report_template.yml"
        ),
        "localize-auto-sync-template": (
            "repo-file:examples/github-actions/localize_auto_sync_template.yml"
        ),
        "localize-status-template": (
            "repo-file:examples/github-actions/localize_status_report_template.yml"
        ),
        "unittest-workflow": "repo-file:.github/workflows/unittest.yml",
        "upstream-smoke-workflow": "repo-file:.github/workflows/upstream_smoke.yml",
        "validate-config-template": (
            "repo-file:examples/github-actions/validate_translation_config_template.yml"
        ),
    },
    "docs/repository-transfer-checklist.md": {
        "example-translation-config": "repo-file:examples/translation-config.yml",
        "github-actions-templates": "repo-tree:examples/github-actions",
        "test-github-workflows": "repo-file:tests/infra/test_github_workflows.py",
    },
    "docs/security-and-permissions.md": {
        "km-auto-update-template": (
            "repo-file:examples/github-actions/km_version_auto_update_template.yml"
        ),
        "github-import-template": (
            "repo-file:examples/github-actions/github_translation_import_template.yml"
        ),
        "github-actions-templates": "repo-tree:examples/github-actions",
        "localize-alignment-template": (
            "repo-file:examples/github-actions/localize_alignment_report_template.yml"
        ),
        "localize-auto-sync-template": (
            "repo-file:examples/github-actions/localize_auto_sync_template.yml"
        ),
        "localize-status-template": (
            "repo-file:examples/github-actions/localize_status_report_template.yml"
        ),
        "upstream-smoke-workflow": "repo-file:.github/workflows/upstream_smoke.yml",
    },
}


def test_security_links_use_repository_aware_schemes(repo_root: Path) -> None:
    """Sensitive links must resolve from the repository being documented."""

    mutable_prefix = "https://github.com/ThreeMonth03/dsw-km-translation-tool/blob/master/"
    for relative_path, links in SECURITY_LINKS.items():
        text = (repo_root / relative_path).read_text(encoding="utf-8")
        assert mutable_prefix not in text
        for label, destination in links.items():
            assert f"[{label}]: {destination}" in text


def test_sphinx_repository_schemes_follow_build_environment(
    repo_root: Path,
    monkeypatch,
) -> None:
    """Published links use the repository and exact commit being built."""

    repository = "transferred-owner/transferred-repository"
    commit = "a" * 40
    monkeypatch.setenv("GITHUB_REPOSITORY", repository)
    monkeypatch.setenv("GITHUB_SHA", commit)

    config_path = repo_root / "docs/sphinx/conf.py"
    config: dict[str, object] = {}
    exec(
        compile(config_path.read_text(encoding="utf-8"), str(config_path), "exec"),
        config,
    )
    schemes = config["myst_url_schemes"]
    assert isinstance(schemes, dict)

    assert schemes["repo-file"]["url"] == (
        f"https://github.com/{repository}/blob/{commit}/{{{{path}}}}"
    )
    assert schemes["repo-tree"]["url"] == (
        f"https://github.com/{repository}/tree/{commit}/{{{{path}}}}"
    )
