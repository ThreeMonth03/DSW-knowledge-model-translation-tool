"""Tests for read-only Weblate check reporting."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

from pytest import MonkeyPatch

from dsw_km_translation_tool.weblate_checks import (
    build_weblate_checks_error_report,
    build_weblate_checks_report,
    render_weblate_checks_markdown,
    resolve_weblate_units_api_url,
    write_weblate_checks_json,
)
from tests.helpers import run_cli_command


def write_config(path: Path, download_url: str) -> None:
    """Write a minimal translation repository config."""

    path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "knowledge_model:",
                "  organization_id: dsw",
                "  km_id: root",
                "  upstream_repository: ds-wizard/dsw-knowledge-models",
                "  version: 2.7.0",
                "translation:",
                "  source_language: en",
                "  target_language: zh_Hant",
                "  target_language_label: zh-Hant",
                "  translated_organization_id: dsw",
                "  translated_km_id: root-zh-hant",
                "  translated_name: Common DSW Knowledge Model (zh-Hant)",
                "branches:",
                "  tracking_branch: master",
                "tooling:",
                "  repository: ThreeMonth03/dsw-km-translation-tool",
                "  ref: master",
                "localize:",
                f"  download_url: {download_url}",
                "  repository: https://localize.ds-wizard.org/",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_resolve_weblate_units_api_url(workspace: Path) -> None:
    """Verify the API URL is derived from the configured Localize download URL."""

    config_path = workspace / "translation-config.yml"
    write_config(
        config_path,
        "https://localize.ds-wizard.org/download/knowledge-models/"
        "common-dsw-knowledge-model/zh_Hant/",
    )

    assert resolve_weblate_units_api_url(
        repo_root=workspace,
        config_path=config_path,
        query="has:check",
        page_size=50,
    ) == (
        "https://localize.ds-wizard.org/api/translations/knowledge-models/"
        "common-dsw-knowledge-model/zh_Hant/units/?q=has%3Acheck&page_size=50"
    )


def test_weblate_checks_report_follows_pagination(workspace: Path) -> None:
    """Verify paginated Weblate API responses are aggregated."""

    config_path = workspace / "translation-config.yml"
    write_config(
        config_path,
        "https://localize.ds-wizard.org/download/knowledge-models/"
        "common-dsw-knowledge-model/zh_Hant/",
    )
    requested_urls: list[str] = []

    def downloader(url: str) -> bytes:
        requested_urls.append(url)
        if len(requested_urls) == 1:
            return json.dumps(
                {
                    "count": 2,
                    "next": "https://localize.example.invalid/page-2",
                    "results": [
                        {
                            "id": 1,
                            "source": ["Source A"],
                            "target": ["Target A"],
                            "state": 20,
                            "context": "",
                            "url": "https://localize.example.invalid/api/units/1/",
                        }
                    ],
                }
            ).encode()
        return json.dumps(
            {
                "count": 2,
                "next": None,
                "results": [
                    {
                        "id": 2,
                        "source": ["Source B"],
                        "target": ["Target B"],
                        "state": 10,
                        "context": "",
                        "url": "https://localize.example.invalid/api/units/2/",
                    }
                ],
            }
        ).encode()

    report = build_weblate_checks_report(
        repo_root=workspace,
        config_path=config_path,
        downloader=downloader,
    )

    assert report.ok is True
    assert report.count == 2
    assert len(report.issues) == 2
    assert report.issues[0].source == ("Source A",)
    assert requested_urls[1] == "https://localize.example.invalid/page-2"
    markdown = render_weblate_checks_markdown(report)
    assert "Matching units: **2**" in markdown
    assert "Source A" in markdown
    assert "Target B" in markdown


def test_weblate_checks_report_can_use_api_token(
    workspace: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Verify authenticated API calls attach an Authorization header."""

    config_path = workspace / "translation-config.yml"
    write_config(
        config_path,
        "https://localize.ds-wizard.org/download/knowledge-models/"
        "common-dsw-knowledge-model/zh_Hant/",
    )
    requested_headers: list[str | None] = []

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            return json.dumps({"count": 0, "next": None, "results": []}).encode()

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        assert timeout == 60
        requested_headers.append(getattr(request, "headers", {}).get("Authorization"))
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    report = build_weblate_checks_report(
        repo_root=workspace,
        config_path=config_path,
        api_token="secret-token",
    )

    assert report.ok is True
    assert requested_headers == ["Bearer secret-token"]


def test_weblate_checks_report_rejects_untrusted_token_origin(workspace: Path) -> None:
    """Verify repository config cannot redirect the API token to another host."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path, "https://attacker.invalid/download/project/component/lang/")

    try:
        build_weblate_checks_report(
            repo_root=workspace,
            config_path=config_path,
            api_token="secret-token",
        )
    except ValueError as error:
        assert "untrusted origin" in str(error)
    else:
        raise AssertionError("an untrusted configured origin was accepted")


def test_weblate_checks_report_rejects_cross_origin_authenticated_pagination(
    workspace: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Verify pagination cannot redirect an authenticated request to another host."""

    config_path = workspace / "translation-config.yml"
    write_config(
        config_path,
        "https://localize.ds-wizard.org/download/project/component/lang/",
    )

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def read() -> bytes:
            return json.dumps(
                {"count": 0, "next": "https://attacker.invalid/page-2", "results": []}
            ).encode()

    monkeypatch.setattr(urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    try:
        build_weblate_checks_report(
            repo_root=workspace,
            config_path=config_path,
            api_token="secret-token",
        )
    except ValueError as error:
        assert "untrusted origin" in str(error)
    else:
        raise AssertionError("a cross-origin pagination URL was accepted")


def test_weblate_checks_error_report_is_diagnostic(workspace: Path) -> None:
    """Verify Weblate API failures can be reported without raising."""

    config_path = workspace / "translation-config.yml"
    write_config(
        config_path,
        "https://localize.ds-wizard.org/download/knowledge-models/"
        "common-dsw-knowledge-model/zh_Hant/",
    )
    report = build_weblate_checks_error_report(
        repo_root=workspace,
        config_path=config_path,
        query="has:check",
        error=RuntimeError("HTTP 429"),
    )

    assert report.ok is False
    assert report.error == "HTTP 429"
    assert "Status: **unavailable**" in render_weblate_checks_markdown(report)


def test_weblate_checks_writes_json(workspace: Path) -> None:
    """Verify JSON output is machine readable."""

    config_path = workspace / "translation-config.yml"
    json_path = workspace / "weblate-checks.json"
    write_config(
        config_path,
        "https://localize.ds-wizard.org/download/knowledge-models/"
        "common-dsw-knowledge-model/zh_Hant/",
    )
    report = build_weblate_checks_error_report(
        repo_root=workspace,
        config_path=config_path,
        query="has:check",
        error=RuntimeError("temporary failure"),
    )
    write_weblate_checks_json(report, json_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["ok"] is False
    assert data["query"] == "has:check"
    assert data["error"] == "temporary failure"


def test_report_weblate_checks_cli_allows_api_failure(
    repo_root: Path,
    workspace: Path,
) -> None:
    """Verify the CLI can write a non-blocking API failure report."""

    config_path = workspace / "translation-config.yml"
    json_path = workspace / "weblate-checks.json"
    details_path = workspace / "weblate-checks.md"
    write_config(
        config_path,
        "file:///download/knowledge-models/common-dsw-knowledge-model/zh_Hant/",
    )

    result = run_cli_command(
        repo_root,
        "dsw-km-report-weblate-checks",
        "--repo-root",
        str(workspace),
        "--config",
        str(config_path),
        "--json-out",
        str(json_path),
        "--details-out",
        str(details_path),
        "--allow-api-failure",
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "## Weblate Check Status" in result.stdout
    assert "Status: **unavailable**" in result.stdout
    assert json.loads(json_path.read_text(encoding="utf-8"))["ok"] is False
    assert details_path.exists()
