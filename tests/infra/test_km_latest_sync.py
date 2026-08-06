"""Tests for single-branch latest-KM synchronization helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml

from dsw_km_translation_tool.km_latest_sync import (
    KmLatestSyncError,
    render_km_latest_sync_markdown,
    sync_latest_km_version,
    update_knowledge_model_version,
    write_km_latest_sync_report,
)
from tests.infra.test_translation_repository_config import write_config


def registry_payload(*versions: str) -> bytes:
    """Build a minimal Registry package response."""

    return json.dumps(
        [
            {
                "organizationId": "dsw",
                "kmId": "root",
                "version": version,
                "name": "Common DSW Knowledge Model",
            }
            for version in versions
        ]
    ).encode("utf-8")


def test_sync_latest_km_noops_when_config_is_current(workspace: Path) -> None:
    """Verify latest-KM sync is a no-op when Registry and config agree."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)

    result = sync_latest_km_version(
        repo_root=workspace,
        tooling_repo=workspace / "tooling",
        config_path=Path("translation-config.yml"),
        registry_token="",
        downloader=lambda _url: registry_payload("2.7.0"),
        skip_without_token=True,
    )

    assert result.changed is False
    assert result.configured_version == "2.7.0"
    assert result.registry_version == "2.7.0"
    assert result.target_ref == "translation/latest"
    assert result.skipped_reason is None


def test_sync_latest_km_does_not_downgrade_to_registry_version(
    workspace: Path,
) -> None:
    """Verify stale Registry responses cannot move the configured KM backward."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path, version="2.8.0")

    result = sync_latest_km_version(
        repo_root=workspace,
        tooling_repo=workspace / "tooling",
        config_path=Path("translation-config.yml"),
        registry_token="secret",
        downloader=lambda _url: registry_payload("2.7.0"),
    )

    assert result.changed is False
    assert result.configured_version == "2.8.0"
    assert result.registry_version == "2.7.0"
    assert result.status == "current"
    assert (
        yaml.safe_load(config_path.read_text(encoding="utf-8"))["knowledge_model"]["version"]
        == "2.8.0"
    )


def test_sync_latest_km_skips_new_version_without_token(workspace: Path) -> None:
    """Verify new Registry versions can be safely skipped until a token is configured."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)

    result = sync_latest_km_version(
        repo_root=workspace,
        tooling_repo=workspace / "tooling",
        config_path=Path("translation-config.yml"),
        registry_token="",
        downloader=lambda _url: registry_payload("2.7.0", "2.8.0"),
        skip_without_token=True,
    )

    assert result.changed is False
    assert result.configured_version == "2.7.0"
    assert result.registry_version == "2.8.0"
    assert result.target_ref == "translation/latest"
    assert result.skipped_reason == "missing-registry-token"


@pytest.mark.parametrize(
    "api_url",
    [
        "http://api.registry.ds-wizard.org",
        "https://attacker.example",
        "https://api.registry.ds-wizard.org.attacker.example",
        "https://api.registry.ds-wizard.org@attacker.example",
        "https://api.registry.ds-wizard.org:invalid",
    ],
)
def test_sync_latest_km_rejects_untrusted_registry_before_network_access(
    workspace: Path,
    api_url: str,
) -> None:
    """Verify repo-controlled URLs cannot receive or trigger use of the Registry token."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    payload["registry"]["api_url"] = api_url
    config_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    network_calls: list[str] = []

    with pytest.raises(KmLatestSyncError, match="untrusted Registry API URL"):
        sync_latest_km_version(
            repo_root=workspace,
            tooling_repo=workspace / "tooling",
            config_path=Path("translation-config.yml"),
            registry_token="secret",
            downloader=lambda url: network_calls.append(url) or registry_payload("2.8.0"),
        )

    assert network_calls == []


def test_sync_latest_km_updates_validates_and_pushes_target_ref(
    workspace: Path,
) -> None:
    """Verify a new Registry KM updates only after validation commands pass."""

    config_path = workspace / "translation-config.yml"
    tooling_repo = workspace / "tooling"
    tooling_repo.mkdir()
    (tooling_repo / ".venv" / "bin").mkdir(parents=True)
    (tooling_repo / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    write_config(config_path)
    runner = RecordingRunner()

    result = sync_latest_km_version(
        repo_root=workspace,
        tooling_repo=tooling_repo,
        config_path=Path("translation-config.yml"),
        registry_token="secret",
        target_ref="master",
        downloader=lambda _url: registry_payload("2.7.0", "2.8.0"),
        bundle_downloader=lambda _url, _token: b"km 2.8",
        localize_downloader=lambda _url: b"latest po",
        runner=runner,
    )

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["knowledge_model"]["version"] == "2.8.0"
    assert config["knowledge_model"]["bundle_path"] == (
        "sources/knowledge-models/dsw-root-2.8.0/dsw-root-2.8.0.km"
    )
    assert (
        workspace / "sources/knowledge-models/dsw-root-2.8.0/dsw-root-2.8.0.km"
    ).read_bytes() == b"km 2.8"
    assert (workspace / "sources/localize/zh_Hant/latest.po").read_bytes() == b"latest po"
    assert result.changed is True
    assert result.status == "updated"
    assert result.target_ref == "master"
    assert runner.command_names == [
        "git status --porcelain",
        "dsw-km-validate-config",
        "dsw-km-export-tree",
        "dsw-km-sync-shared-strings",
        "dsw-km-po-to-km",
        "python -m pytest",
        "dsw-km-report-alignment",
        "git config user.name github-actions[bot]",
        "git config user.email 41898282+github-actions[bot]@users.noreply.github.com",
        "git add -A -- .",
        "git status --porcelain",
        "git commit -m chore(sync): update source KM to 2.8.0",
        "git push origin HEAD:master",
    ]


def test_sync_latest_km_does_not_push_when_validation_fails(workspace: Path) -> None:
    """Verify failed validation stops before committing any generated changes."""

    config_path = workspace / "translation-config.yml"
    tooling_repo = workspace / "tooling"
    tooling_repo.mkdir()
    write_config(config_path)
    runner = RecordingRunner(fail_on="dsw-km-report-alignment")

    try:
        sync_latest_km_version(
            repo_root=workspace,
            tooling_repo=tooling_repo,
            config_path=Path("translation-config.yml"),
            registry_token="secret",
            target_ref="master",
            downloader=lambda _url: registry_payload("2.7.0", "2.8.0"),
            bundle_downloader=lambda _url, _token: b"km 2.8",
            localize_downloader=lambda _url: b"latest po",
            runner=runner,
        )
    except RuntimeError as error:
        assert "verify Localize/repository alignment" in str(error)
    else:
        raise AssertionError("Expected latest-KM sync to fail")

    assert not any(command.startswith("git commit") for command in runner.command_names)
    assert not any(command.startswith("git push") for command in runner.command_names)


def test_update_knowledge_model_version_replaces_current_version(
    workspace: Path,
) -> None:
    """Verify the updater replaces the current KM version and bundle path."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)

    updated = update_knowledge_model_version(config_path, "v2.9.0")

    assert updated == "2.9.0"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert payload["knowledge_model"]["version"] == "2.9.0"
    assert payload["knowledge_model"]["bundle_path"] == (
        "sources/knowledge-models/dsw-root-2.9.0/dsw-root-2.9.0.km"
    )


def test_km_latest_sync_report_outputs_json_and_markdown(workspace: Path) -> None:
    """Verify auto-update reports are stable and readable."""

    config_path = workspace / "translation-config.yml"
    report_path = workspace / "km_auto_update_report.json"
    write_config(config_path)
    result = sync_latest_km_version(
        repo_root=workspace,
        tooling_repo=workspace / "tooling",
        config_path=Path("translation-config.yml"),
        registry_token="",
        target_ref="master",
        downloader=lambda _url: registry_payload("2.7.0"),
        skip_without_token=True,
    )

    markdown = render_km_latest_sync_markdown(result)
    write_km_latest_sync_report(result=result, report_path=report_path)

    assert "Status: **current**" in markdown
    assert json.loads(report_path.read_text(encoding="utf-8"))["status"] == "current"


class RecordingRunner:
    """Record latest-KM subprocess commands without running external tools."""

    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.command_names: list[str] = []
        self._status_calls = 0

    def __call__(
        self,
        args: list[str] | tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del cwd, env
        command_name = self._command_name(args)
        self.command_names.append(command_name)
        if self.fail_on and self.fail_on == command_name:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="alignment failed")
        stdout = ""
        if list(args) == ["git", "status", "--porcelain"]:
            self._status_calls += 1
            stdout = "" if self._status_calls == 1 else "M translation-config.yml\n"
        return subprocess.CompletedProcess(args, 0, stdout=stdout, stderr="")

    def _command_name(self, args: list[str] | tuple[str, ...]) -> str:
        display_args = [
            "python" if str(arg).endswith("/.venv/bin/python") else str(arg) for arg in args
        ]
        if display_args[:3] == ["python", "-m", "pytest"]:
            return "python -m pytest"
        first_arg = Path(display_args[0])
        if first_arg.parent.name == "bin" and first_arg.name.startswith("dsw-km-"):
            return first_arg.name
        return " ".join(display_args)
