"""Tests for upstream integration smoke helpers."""

from __future__ import annotations

import json
from pathlib import Path

from dsw_km_translation_tool.upstream_smoke import (
    render_upstream_smoke_markdown,
    run_upstream_smoke,
    write_upstream_smoke_markdown,
    write_upstream_smoke_report,
)
from tests.infra.test_km_latest_sync import registry_payload
from tests.infra.test_translation_repository_config import write_config


def test_upstream_smoke_builds_current_upstream_inputs(
    workspace: Path,
    po_path: Path,
    model_path: Path,
) -> None:
    """Verify upstream smoke pulls sources and builds aligned artifacts."""

    config_template = workspace / "template.yml"
    work_dir = workspace / "upstream-smoke"
    write_config(config_template)

    result = run_upstream_smoke(
        work_dir=work_dir,
        config_template_path=config_template,
        registry_token="secret",
        registry_downloader=lambda _url: registry_payload("2.7.0"),
        bundle_downloader=lambda _url, _token: model_path.read_bytes(),
        localize_downloader=lambda _url: po_path.read_bytes(),
    )

    assert result.status == "passed"
    assert result.configured_version == "2.7.0"
    assert result.registry_version == "2.7.0"
    assert result.km_bundle_initialized is True
    assert result.localize_po_initialized is True
    assert result.alignment_aligned is True
    assert (work_dir / "sources/localize/zh_Hant/latest.po").exists()
    assert (work_dir / "sources/knowledge-models/dsw-root-2.7.0/dsw-root-2.7.0.km").exists()
    assert (work_dir / "builds/final_translated.po").exists()
    assert (work_dir / "builds/final_translated.km").exists()
    assert "Status: **passed**" in render_upstream_smoke_markdown(result)


def test_upstream_smoke_reuses_matching_cached_km_bundle(
    workspace: Path,
    po_path: Path,
    model_path: Path,
) -> None:
    """Verify cached immutable KM snapshots do not force repeated writes."""

    config_template = workspace / "template.yml"
    work_dir = workspace / "upstream-smoke"
    write_config(config_template)
    kwargs = {
        "work_dir": work_dir,
        "config_template_path": config_template,
        "registry_token": "secret",
        "registry_downloader": lambda _url: registry_payload("2.7.0"),
        "bundle_downloader": lambda _url, _token: model_path.read_bytes(),
        "localize_downloader": lambda _url: po_path.read_bytes(),
    }

    first = run_upstream_smoke(**kwargs)
    second = run_upstream_smoke(**kwargs)

    assert first.km_bundle_initialized is True
    assert second.km_bundle_initialized is False
    assert second.km_bundle_changed is False


def test_upstream_smoke_refreshes_changed_cached_km_bundle(
    workspace: Path,
    po_path: Path,
    model_path: Path,
) -> None:
    """Verify a stale disposable cache is refreshed before smoke checks."""

    config_template = workspace / "template.yml"
    work_dir = workspace / "upstream-smoke"
    target_path = work_dir / "sources/knowledge-models/dsw-root-2.7.0/dsw-root-2.7.0.km"
    write_config(config_template)
    target_path.parent.mkdir(parents=True)
    target_path.write_bytes(b"stale cached bundle")

    result = run_upstream_smoke(
        work_dir=work_dir,
        config_template_path=config_template,
        registry_token="secret",
        registry_downloader=lambda _url: registry_payload("2.7.0"),
        bundle_downloader=lambda _url, _token: model_path.read_bytes(),
        localize_downloader=lambda _url: po_path.read_bytes(),
    )

    assert result.status == "passed"
    assert result.km_bundle_initialized is False
    assert result.km_bundle_changed is True
    assert result.alignment_aligned is True
    assert target_path.read_bytes() == model_path.read_bytes()


def test_upstream_smoke_can_skip_when_registry_token_is_missing(
    workspace: Path,
) -> None:
    """Verify scheduled smoke can opt into a clean skip while secrets are absent."""

    config_template = workspace / "template.yml"
    write_config(config_template)

    result = run_upstream_smoke(
        work_dir=workspace / "upstream-smoke",
        config_template_path=config_template,
        registry_token="",
        skip_without_token=True,
        registry_downloader=lambda _url: registry_payload("2.7.0"),
    )

    assert result.status == "skipped:missing-registry-token"
    assert result.skipped_reason == "missing-registry-token"


def test_upstream_smoke_report_outputs_json(workspace: Path) -> None:
    """Verify smoke reports use stable JSON keys."""

    config_template = workspace / "template.yml"
    report_path = workspace / "report.json"
    write_config(config_template)
    result = run_upstream_smoke(
        work_dir=workspace / "upstream-smoke",
        config_template_path=config_template,
        registry_token="",
        skip_without_token=True,
        registry_downloader=lambda _url: registry_payload("2.7.0"),
    )

    write_upstream_smoke_report(result=result, report_path=report_path)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "skipped:missing-registry-token"
    assert report["registry_version"] == "2.7.0"


def test_upstream_smoke_markdown_report_overwrites_previous_run(
    workspace: Path,
) -> None:
    """Verify repeated smoke runs leave a single current Markdown report."""

    config_template = workspace / "template.yml"
    report_path = workspace / "report.md"
    write_config(config_template)
    result = run_upstream_smoke(
        work_dir=workspace / "upstream-smoke",
        config_template_path=config_template,
        registry_token="",
        skip_without_token=True,
        registry_downloader=lambda _url: registry_payload("2.7.0"),
    )

    report_path.write_text("stale report\n", encoding="utf-8")
    write_upstream_smoke_markdown(result=result, report_path=report_path)

    report = report_path.read_text(encoding="utf-8")
    assert "stale report" not in report
    assert report.count("## Upstream Smoke") == 1
