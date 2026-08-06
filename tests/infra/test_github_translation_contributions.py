"""Tests for GitHub-originated translation contribution handling."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsw_km_translation_tool.cli import (
    import_github_translations,
    report_github_translations,
)
from dsw_km_translation_tool.github_translation_contributions import (
    CONFLICT_DECISION,
    IMPORT_DECISION,
    GitHubTranslationContributionError,
    build_github_translation_report,
    write_import_po,
)
from tests.infra.test_translation_repository_config import write_config

TEST_UUID = "11111111-1111-1111-1111-111111111111"


def test_github_translation_report_marks_safe_imports(workspace: Path) -> None:
    """Verify GitHub translations can be imported when Weblate did not change."""

    repo = initialize_translation_repo(workspace)
    base_ref = commit_translation(repo, "base", "舊翻譯")
    head_ref = commit_translation(repo, "github", "GitHub 新翻譯")
    latest_po = write_latest_po(workspace / "latest.po", "舊翻譯")

    report = build_github_translation_report(
        repo_root=repo,
        base_ref=base_ref,
        head_ref=head_ref,
        latest_po_path=latest_po,
    )

    assert report.has_translation_changes is True
    assert report.has_conflicts is False
    assert report.importable_entries == 1
    assert report.decisions[0].decision == IMPORT_DECISION
    assert report.decisions[0].github == "GitHub 新翻譯"


def test_github_translation_report_rejects_unmanifested_spoof_file(
    workspace: Path,
) -> None:
    """Verify an arbitrary tree file cannot impersonate a canonical node."""

    repo = initialize_translation_repo(workspace)
    base_ref = commit_translation(repo, "base", "舊翻譯")
    spoof_path = repo / "tree" / "zzzz" / "translation.md"
    spoof_path.parent.mkdir(parents=True)
    spoof_path.write_text(render_translation_markdown("ATTACKER TRANSLATION"), encoding="utf-8")
    run_git(repo, "add", "tree/zzzz/translation.md")
    run_git(repo, "commit", "-m", "spoof")
    head_ref = run_git(repo, "rev-parse", "HEAD").stdout.strip()

    with pytest.raises(GitHubTranslationContributionError, match="not a canonical manifest node"):
        build_github_translation_report(
            repo_root=repo,
            base_ref=base_ref,
            head_ref=head_ref,
            latest_po_path=write_latest_po(workspace / "latest.po", "舊翻譯"),
        )


def test_github_translation_report_marks_conflicts(workspace: Path) -> None:
    """Verify conflicts require review instead of last-writer-wins import."""

    repo = initialize_translation_repo(workspace)
    base_ref = commit_translation(repo, "base", "舊翻譯")
    head_ref = commit_translation(repo, "github", "GitHub 新翻譯")
    latest_po = write_latest_po(workspace / "latest.po", "Weblate 新翻譯")

    report = build_github_translation_report(
        repo_root=repo,
        base_ref=base_ref,
        head_ref=head_ref,
        latest_po_path=latest_po,
    )

    assert report.has_conflicts is True
    assert report.importable_entries == 0
    assert report.conflict_entries == 1
    assert report.decisions[0].decision == CONFLICT_DECISION


def test_github_translation_report_rejects_broken_markdown(workspace: Path) -> None:
    """Verify changed translations must preserve source Markdown structure."""

    repo, base_ref, head_ref, latest_po = prepare_markdown_error_case(workspace)

    report = build_github_translation_report(
        repo_root=repo,
        base_ref=base_ref,
        head_ref=head_ref,
        latest_po_path=latest_po,
    )

    assert report.has_format_errors is True
    assert report.format_error_entries == 1
    assert report.importable_entries == 0
    assert report.decisions[0].format_issues == (
        "strong emphasis: source has 1, translation has 0",
    )


def test_github_translation_report_rejects_unsynced_shared_blocks(
    workspace: Path,
) -> None:
    """Verify canonical shared edits must be expanded into their tree fields."""

    repo, base_ref, head_ref, latest_po = prepare_shared_block_error_case(workspace)

    report = build_github_translation_report(
        repo_root=repo,
        base_ref=base_ref,
        head_ref=head_ref,
        latest_po_path=latest_po,
    )

    assert report.has_translation_changes is False
    assert report.has_shared_block_errors is True
    assert len(report.shared_block_issues) == 1
    assert "Run shared-string sync" in report.shared_block_issues[0].message


def test_github_translation_report_accepts_synced_shared_blocks(
    workspace: Path,
) -> None:
    """Verify canonical shared edits pass after their tree fields are expanded."""

    repo = initialize_translation_repo(workspace)
    commit_translation(repo, "base tree", "舊翻譯")
    base_ref = commit_shared_translation(repo, "base shared", "舊翻譯")
    head_ref = commit_shared_translation(
        repo,
        "synced shared",
        "GitHub 新翻譯",
        tree_target="GitHub 新翻譯",
    )
    latest_po = write_latest_po(workspace / "latest.po", "舊翻譯")

    report = build_github_translation_report(
        repo_root=repo,
        base_ref=base_ref,
        head_ref=head_ref,
        latest_po_path=latest_po,
    )

    assert report.has_shared_block_errors is False
    assert report.importable_entries == 1


def test_write_import_po_contains_only_importable_entries(workspace: Path) -> None:
    """Verify partial PO output contains safe GitHub translations."""

    repo = initialize_translation_repo(workspace)
    base_ref = commit_translation(repo, "base", "舊翻譯")
    head_ref = commit_translation(repo, "github", "GitHub 新翻譯")
    latest_po = write_latest_po(workspace / "latest.po", "舊翻譯")
    report = build_github_translation_report(
        repo_root=repo,
        base_ref=base_ref,
        head_ref=head_ref,
        latest_po_path=latest_po,
    )
    import_po = write_import_po(
        report=report,
        output_path=workspace / "github-import.po",
        language="zh_Hant",
    )

    text = import_po.read_text(encoding="utf-8")
    assert f"#: github:{TEST_UUID}:title" in text
    assert 'msgid "Source title"' in text
    assert 'msgstr "GitHub 新翻譯"' in text


def test_report_github_translations_cli_writes_outputs(
    monkeypatch,
    workspace: Path,
) -> None:
    """Verify the PR report CLI exposes safe GitHub Actions outputs."""

    repo = initialize_translation_repo(workspace)
    write_config(repo / "translation-config.yml")
    base_ref = commit_translation(repo, "base", "舊翻譯")
    head_ref = commit_translation(repo, "github", "GitHub 新翻譯")
    latest_po = write_latest_po(workspace / "latest.po", "舊翻譯")
    json_out = workspace / "report.json"
    details_out = workspace / "report.md"
    github_output = workspace / "github-output.txt"

    monkeypatch.setattr(
        report_github_translations,
        "pull_localize_po",
        lambda **_kwargs: SimpleNamespace(latest_po_path=latest_po),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-report-github-translations",
            "--repo-root",
            str(repo),
            "--config",
            "translation-config.yml",
            "--base-ref",
            base_ref,
            "--head-ref",
            head_ref,
            "--json-out",
            str(json_out),
            "--details-out",
            str(details_out),
            "--github-output",
            str(github_output),
        ],
    )

    report_github_translations.main()

    assert '"importable_entries": 1' in json_out.read_text(encoding="utf-8")
    assert "GitHub Translation Contributions" in details_out.read_text(encoding="utf-8")
    outputs = github_output.read_text(encoding="utf-8")
    assert "has_translation_changes=true" in outputs
    assert "has_conflicts=false" in outputs
    assert "has_format_errors=false" in outputs
    assert "has_shared_block_errors=false" in outputs
    assert "importable_entries=1" in outputs


def test_report_github_translations_cli_fails_on_markdown_errors(
    monkeypatch,
    workspace: Path,
) -> None:
    """Verify a translation PR cannot pass with broken Markdown structure."""

    repo, base_ref, head_ref, latest_po = prepare_markdown_error_case(workspace)
    write_config(repo / "translation-config.yml")
    github_output = workspace / "github-output.txt"

    monkeypatch.setattr(
        report_github_translations,
        "pull_localize_po",
        lambda **_kwargs: SimpleNamespace(latest_po_path=latest_po),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-report-github-translations",
            "--repo-root",
            str(repo),
            "--config",
            "translation-config.yml",
            "--base-ref",
            base_ref,
            "--head-ref",
            head_ref,
            "--json-out",
            str(workspace / "report.json"),
            "--details-out",
            str(workspace / "report.md"),
            "--github-output",
            str(github_output),
        ],
    )

    with pytest.raises(SystemExit, match="Markdown format errors"):
        report_github_translations.main()

    outputs = github_output.read_text(encoding="utf-8")
    assert "has_format_errors=true" in outputs
    assert "importable_entries=0" in outputs


def test_report_github_translations_cli_fails_on_conflicts(
    monkeypatch,
    workspace: Path,
) -> None:
    """Verify a translation PR cannot pass when Weblate changed the same entry."""

    repo = initialize_translation_repo(workspace)
    write_config(repo / "translation-config.yml")
    base_ref = commit_translation(repo, "base", "舊翻譯")
    head_ref = commit_translation(repo, "github", "GitHub 新翻譯")
    latest_po = write_latest_po(workspace / "latest.po", "Weblate 新翻譯")
    github_output = workspace / "github-output.txt"

    monkeypatch.setattr(
        report_github_translations,
        "pull_localize_po",
        lambda **_kwargs: SimpleNamespace(latest_po_path=latest_po),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-report-github-translations",
            "--repo-root",
            str(repo),
            "--config",
            "translation-config.yml",
            "--base-ref",
            base_ref,
            "--head-ref",
            head_ref,
            "--json-out",
            str(workspace / "report.json"),
            "--details-out",
            str(workspace / "report.md"),
            "--github-output",
            str(github_output),
        ],
    )

    with pytest.raises(SystemExit, match="conflict with the current Weblate state"):
        report_github_translations.main()

    outputs = github_output.read_text(encoding="utf-8")
    assert "has_conflicts=true" in outputs
    assert "importable_entries=0" in outputs


def test_report_github_translations_cli_fails_on_unsynced_shared_blocks(
    monkeypatch,
    workspace: Path,
) -> None:
    """Verify a translation PR cannot pass with a stale expanded tree."""

    repo, base_ref, head_ref, latest_po = prepare_shared_block_error_case(workspace)
    write_config(repo / "translation-config.yml")
    github_output = workspace / "github-output.txt"

    monkeypatch.setattr(
        report_github_translations,
        "pull_localize_po",
        lambda **_kwargs: SimpleNamespace(latest_po_path=latest_po),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-report-github-translations",
            "--repo-root",
            str(repo),
            "--config",
            "translation-config.yml",
            "--base-ref",
            base_ref,
            "--head-ref",
            head_ref,
            "--json-out",
            str(workspace / "report.json"),
            "--details-out",
            str(workspace / "report.md"),
            "--github-output",
            str(github_output),
        ],
    )

    with pytest.raises(SystemExit, match="shared blocks out of sync"):
        report_github_translations.main()

    outputs = github_output.read_text(encoding="utf-8")
    assert "has_translation_changes=false" in outputs
    assert "has_shared_block_errors=true" in outputs


def test_import_github_translations_cli_blocks_conflicts(
    monkeypatch,
    workspace: Path,
) -> None:
    """Verify post-merge import does not upload conflicting GitHub edits."""

    repo = initialize_translation_repo(workspace)
    write_config(repo / "translation-config.yml")
    base_ref = commit_translation(repo, "base", "舊翻譯")
    head_ref = commit_translation(repo, "github", "GitHub 新翻譯")
    latest_po = write_latest_po(workspace / "latest.po", "Weblate 新翻譯")
    github_output = workspace / "github-output.txt"

    monkeypatch.setattr(
        import_github_translations,
        "pull_localize_po",
        lambda **_kwargs: SimpleNamespace(latest_po_path=latest_po),
    )

    def fail_upload(**_kwargs) -> None:
        raise AssertionError("unexpected upload")

    monkeypatch.setattr(
        import_github_translations,
        "upload_translation_file",
        fail_upload,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-import-github-translations",
            "--repo-root",
            str(repo),
            "--config",
            "translation-config.yml",
            "--base-ref",
            base_ref,
            "--head-ref",
            head_ref,
            "--json-out",
            str(workspace / "import.json"),
            "--details-out",
            str(workspace / "import.md"),
            "--github-output",
            str(github_output),
        ],
    )

    try:
        import_github_translations.main()
    except SystemExit as error:
        assert "has conflicts" in str(error)
    else:
        raise AssertionError("Expected conflict imports to fail")

    outputs = github_output.read_text(encoding="utf-8")
    assert "has_conflicts=true" in outputs
    assert "uploaded=false" in outputs


def test_import_github_translations_cli_blocks_markdown_errors(
    monkeypatch,
    workspace: Path,
) -> None:
    """Verify post-merge import revalidates Markdown before Weblate upload."""

    repo, base_ref, head_ref, latest_po = prepare_markdown_error_case(workspace)
    write_config(repo / "translation-config.yml")
    github_output = workspace / "github-output.txt"

    monkeypatch.setattr(
        import_github_translations,
        "pull_localize_po",
        lambda **_kwargs: SimpleNamespace(latest_po_path=latest_po),
    )
    monkeypatch.setattr(
        import_github_translations,
        "upload_translation_file",
        lambda **_kwargs: pytest.fail("unexpected upload"),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-import-github-translations",
            "--repo-root",
            str(repo),
            "--config",
            "translation-config.yml",
            "--base-ref",
            base_ref,
            "--head-ref",
            head_ref,
            "--json-out",
            str(workspace / "import.json"),
            "--details-out",
            str(workspace / "import.md"),
            "--github-output",
            str(github_output),
        ],
    )

    with pytest.raises(SystemExit, match="Markdown format errors"):
        import_github_translations.main()

    outputs = github_output.read_text(encoding="utf-8")
    assert "has_format_errors=true" in outputs
    assert "uploaded=false" in outputs


def test_import_github_translations_cli_verifies_weblate_upload(
    monkeypatch,
    workspace: Path,
) -> None:
    """Verify a successful import is confirmed against a fresh Weblate PO."""

    repo = initialize_translation_repo(workspace)
    write_config(repo / "translation-config.yml")
    base_ref = commit_translation(repo, "base", "舊翻譯")
    head_ref = commit_translation(repo, "github", "GitHub 新翻譯")
    latest_before = write_latest_po(workspace / "before.po", "舊翻譯")
    latest_after = write_latest_po(workspace / "after.po", "GitHub 新翻譯")
    pulls = iter((latest_before, latest_after))
    github_output = workspace / "github-output.txt"

    monkeypatch.setattr(
        import_github_translations,
        "pull_localize_po",
        lambda **_kwargs: SimpleNamespace(latest_po_path=next(pulls)),
    )
    monkeypatch.setattr(
        import_github_translations,
        "upload_translation_file",
        lambda **_kwargs: SimpleNamespace(api_url="https://weblate.test/api/file/"),
    )
    monkeypatch.setenv("LOCALIZE_API_TOKEN", "test-token")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-import-github-translations",
            "--repo-root",
            str(repo),
            "--config",
            "translation-config.yml",
            "--base-ref",
            base_ref,
            "--head-ref",
            head_ref,
            "--json-out",
            str(workspace / "import.json"),
            "--details-out",
            str(workspace / "import.md"),
            "--github-output",
            str(github_output),
        ],
    )

    import_github_translations.main()

    assert "uploaded=true" in github_output.read_text(encoding="utf-8")


def test_import_github_translations_cli_rejects_unapplied_upload(
    monkeypatch,
    workspace: Path,
) -> None:
    """Verify Weblate file-import skips cannot be reported as successful."""

    repo = initialize_translation_repo(workspace)
    write_config(repo / "translation-config.yml")
    base_ref = commit_translation(repo, "base", "舊翻譯")
    head_ref = commit_translation(repo, "github", "GitHub 新翻譯")
    latest_po = write_latest_po(workspace / "latest.po", "舊翻譯")
    github_output = workspace / "github-output.txt"

    monkeypatch.setattr(
        import_github_translations,
        "pull_localize_po",
        lambda **_kwargs: SimpleNamespace(latest_po_path=latest_po),
    )
    monkeypatch.setattr(
        import_github_translations,
        "upload_translation_file",
        lambda **_kwargs: SimpleNamespace(api_url="https://weblate.test/api/file/"),
    )
    monkeypatch.setenv("LOCALIZE_API_TOKEN", "test-token")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-import-github-translations",
            "--repo-root",
            str(repo),
            "--config",
            "translation-config.yml",
            "--base-ref",
            base_ref,
            "--head-ref",
            head_ref,
            "--json-out",
            str(workspace / "import.json"),
            "--details-out",
            str(workspace / "import.md"),
            "--github-output",
            str(github_output),
        ],
    )

    with pytest.raises(SystemExit, match="Weblate did not apply 1"):
        import_github_translations.main()

    assert "uploaded=false" in github_output.read_text(encoding="utf-8")


def initialize_translation_repo(workspace: Path) -> Path:
    """Create a small Git repository for translation contribution tests."""

    repo = workspace / "repo"
    repo.mkdir()
    run_git(repo, "init")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "config", "user.email", "test@example.invalid")
    return repo


def prepare_markdown_error_case(workspace: Path) -> tuple[Path, str, str, Path]:
    """Create a Git/Weblate fixture containing broken translated Markdown."""

    source = "*The **processor** definition.*"
    repo = initialize_translation_repo(workspace)
    base_ref = commit_translation(repo, "base", "*舊的 **資料處理者** 定義。*", source=source)
    head_ref = commit_translation(
        repo,
        "github",
        "*「**「資料處理者」**是指……。」*",
        source=source,
    )
    latest_po = write_latest_po(
        workspace / "latest.po",
        "*舊的 **資料處理者** 定義。*",
        source=source,
    )
    return repo, base_ref, head_ref, latest_po


def prepare_shared_block_error_case(workspace: Path) -> tuple[Path, str, str, Path]:
    """Create a Git fixture whose canonical shared edit was not expanded."""

    repo = initialize_translation_repo(workspace)
    commit_translation(repo, "base tree", "舊翻譯")
    base_ref = commit_shared_translation(repo, "base shared", "舊翻譯")
    head_ref = commit_shared_translation(repo, "unsynced shared", "GitHub 新翻譯")
    latest_po = write_latest_po(workspace / "latest.po", "舊翻譯")
    return repo, base_ref, head_ref, latest_po


def commit_translation(
    repo: Path,
    message: str,
    target: str,
    *,
    source: str = "Source title",
) -> str:
    """Write one translation value and commit it."""

    translation_path = repo / "tree" / "node" / "translation.md"
    translation_path.parent.mkdir(parents=True, exist_ok=True)
    (translation_path.parent / "_uuid.txt").write_text(TEST_UUID, encoding="utf-8")
    (repo / "tree" / "_translation_tree.json").write_text(
        json.dumps(
            {
                "rootPaths": ["node"],
                "nodes": {
                    TEST_UUID: {
                        "path": "node",
                        "fields": ["title"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    translation_path.write_text(
        render_translation_markdown(target, source=source),
        encoding="utf-8",
    )
    run_git(
        repo,
        "add",
        "tree/node/translation.md",
        "tree/node/_uuid.txt",
        "tree/_translation_tree.json",
    )
    run_git(repo, "commit", "-m", message)
    return run_git(repo, "rev-parse", "HEAD").stdout.strip()


def commit_shared_translation(
    repo: Path,
    message: str,
    target: str,
    *,
    tree_target: str | None = None,
) -> str:
    """Write one canonical shared translation and optionally expand it."""

    shared_path = repo / "tree" / "shared_blocks" / "shared-group" / "context.md"
    shared_path.parent.mkdir(parents=True, exist_ok=True)
    shared_path.write_text(
        "\n".join(
            [
                "# Group 0001",
                "",
                f"- Shared Key: `{TEST_UUID}:title`",
                "",
                "### Translation (zh_Hant)",
                "",
                "~~~text",
                target,
                "~~~",
                "",
            ]
        ),
        encoding="utf-8",
    )
    run_git(repo, "add", "tree/shared_blocks/shared-group/context.md")
    if tree_target is not None:
        translation_path = repo / "tree" / "node" / "translation.md"
        translation_path.write_text(
            render_translation_markdown(tree_target),
            encoding="utf-8",
        )
        run_git(repo, "add", "tree/node/translation.md")
    run_git(repo, "commit", "-m", message)
    return run_git(repo, "rev-parse", "HEAD").stdout.strip()


def render_translation_markdown(target: str, *, source: str = "Source title") -> str:
    """Render a minimal translation markdown file."""

    return "\n".join(
        [
            "# Translation",
            "",
            f"- UUID: `{TEST_UUID}`",
            "- Event Type: `EditQuestionEvent`",
            "- Edit only the `Translation (zh_Hant)` blocks below.",
            "",
            "## title",
            "",
            "### Source (en)",
            "",
            "~~~text",
            source,
            "~~~",
            "",
            "### Translation (zh_Hant)",
            "",
            "~~~text",
            target,
            "~~~",
            "",
        ]
    )


def write_latest_po(
    path: Path,
    target: str,
    *,
    source: str = "Source title",
) -> Path:
    """Write a minimal Weblate PO fixture."""

    path.write_text(
        "\n".join(
            [
                'msgid ""',
                'msgstr ""',
                '"Language: zh_Hant\\n"',
                "",
                f"#: question:{TEST_UUID}:title",
                f'msgid "{source}"',
                f'msgstr "{target}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a Git command in a test repository."""

    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    return result
