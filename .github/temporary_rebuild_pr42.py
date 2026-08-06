#!/usr/bin/env python3
"""Rebuild PR 42 on current master without weakening newer security policy."""

from pathlib import Path
from textwrap import dedent


def github_expression(expression: str) -> str:
    return "$" + "{{ " + expression + " }}"


def replace_exact(
    path: str,
    old: str,
    new: str,
    *,
    expected: int = 1,
) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise SystemExit(
            f"{path}: expected {expected} occurrence(s) of {old!r}, found {count}"
        )
    file_path.write_text(text.replace(old, new), encoding="utf-8")


env_config = github_expression("env.TRANSLATION_CONFIG")
env_root = github_expression("env.TRANSLATION_ROOT")
env_branch = github_expression("env.TRACKING_BRANCH")
env_lang = github_expression("env.TARGET_LANG")
repository_context = github_expression("github.repository")

import_workflow = "examples/github-actions/github_translation_import_template.yml"
replace_exact(
    import_workflow,
    f'--config "{env_config}"',
    '--config "$TRANSLATION_CONFIG"',
    expected=2,
)
replace_exact(
    import_workflow,
    f'--translation-root "{env_root}"',
    '--translation-root "$TRANSLATION_ROOT"',
)
replace_exact(
    import_workflow,
    f'--target-ref "{env_branch}"',
    '--target-ref "$TRACKING_BRANCH"',
)
replace_exact(
    import_workflow,
    f'--restore-source-ref "origin/{env_branch}"',
    '--restore-source-ref "origin/$TRACKING_BRANCH"',
)

version_workflow = "examples/github-actions/km_version_auto_update_template.yml"
replace_exact(
    version_workflow,
    f'--config "{env_config}"',
    '--config "$TRANSLATION_CONFIG"',
)
replace_exact(
    version_workflow,
    f'--target-ref "{env_branch}"',
    '--target-ref "$TRACKING_BRANCH"',
)

alignment_workflow = "examples/github-actions/localize_alignment_report_template.yml"
replace_exact(
    alignment_workflow,
    f'--config "{env_config}"',
    '--config "$TRANSLATION_CONFIG"',
)

status_workflow = "examples/github-actions/localize_status_report_template.yml"
replace_exact(
    status_workflow,
    f'--config "{env_config}"',
    '--config "$TRANSLATION_CONFIG"',
    expected=2,
)
replace_exact(
    status_workflow,
    f'/sources/localize/{env_lang}/latest.po"',
    '/sources/localize/$TARGET_LANG/latest.po"',
)

sync_workflow = "examples/github-actions/localize_auto_sync_template.yml"
old_fetch = (
    "      - name: Fetch tracking branch for recovery restores\n"
    "        working-directory: translation-repo\n"
    "        run: >-\n"
    f'          git fetch "https://github.com/{repository_context}.git"\n'
    f'          "{env_branch}:refs/remotes/base/{env_branch}"\n'
)
new_fetch = (
    "      - name: Fetch tracking branch for recovery restores\n"
    "        working-directory: translation-repo\n"
    "        env:\n"
    f"          REPOSITORY: {repository_context}\n"
    "        run: >-\n"
    '          git fetch "https://github.com/$REPOSITORY.git"\n'
    '          "$TRACKING_BRANCH:refs/remotes/base/$TRACKING_BRANCH"\n'
)
replace_exact(sync_workflow, old_fetch, new_fetch)
replace_exact(
    sync_workflow,
    f'--config "{env_config}"',
    '--config "$TRANSLATION_CONFIG"',
)
replace_exact(
    sync_workflow,
    f'--translation-root "{env_root}"',
    '--translation-root "$TRANSLATION_ROOT"',
)
replace_exact(
    sync_workflow,
    f'--target-ref "{env_branch}"',
    '--target-ref "$TRACKING_BRANCH"',
)
replace_exact(
    sync_workflow,
    f'--restore-source-ref "base/{env_branch}"',
    '--restore-source-ref "base/$TRACKING_BRANCH"',
)

workflow_tests = Path("tests/infra/test_github_workflows.py")
workflow_test_text = workflow_tests.read_text(encoding="utf-8")
replace_pairs = (
    (
        f'    assert "refs/remotes/base/{env_branch}" in workflow_text\n',
        '    assert "refs/remotes/base/$TRACKING_BRANCH" in workflow_text\n',
    ),
    (
        f'    assert "base/{env_branch}" in workflow_text\n',
        '    assert "base/$TRACKING_BRANCH" in workflow_text\n',
    ),
)
for old, new in replace_pairs:
    if workflow_test_text.count(old) != 1:
        raise SystemExit(f"workflow test assertion not found exactly once: {old!r}")
    workflow_test_text = workflow_test_text.replace(old, new, 1)

test_name = "test_workflow_run_blocks_do_not_interpolate_repository_config"
if test_name not in workflow_test_text:
    workflow_test_text += dedent(
        '''


def test_workflow_run_blocks_do_not_interpolate_repository_config(
    repo_root: Path,
) -> None:
    """Repository-config values must reach shells through quoted variables."""

    template_names = (
        "github_translation_import_template.yml",
        "km_version_auto_update_template.yml",
        "localize_alignment_report_template.yml",
        "localize_auto_sync_template.yml",
        "localize_status_report_template.yml",
    )
    expression_prefix = "$" + "{{ env."
    for template_name in template_names:
        workflow, _ = load_rendered_workflow(repo_root, template_name)
        run_blocks = [
            step["run"]
            for job in workflow["jobs"].values()
            for step in job["steps"]
            if "run" in step
        ]
        assert run_blocks
        assert all(expression_prefix not in run_block for run_block in run_blocks)
'''
    )
workflow_tests.write_text(workflow_test_text, encoding="utf-8")

config_tests = Path("tests/infra/test_translation_repository_config.py")
config_test_text = config_tests.read_text(encoding="utf-8")
unsafe_case = '        ("tooling.ref", "$(printenv${IFS}DSW_REGISTRY_TOKEN)"),\n'
if unsafe_case not in config_test_text:
    anchor = '        ("branches.tracking_branch", "translation/../main"),\n'
    if anchor not in config_test_text:
        raise SystemExit("unsafe-ref parameter anchor not found")
    config_test_text = config_test_text.replace(anchor, anchor + unsafe_case, 1)
config_tests.write_text(config_test_text, encoding="utf-8")
