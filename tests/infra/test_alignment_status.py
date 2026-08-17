"""Tests for read-only Localize/repository alignment reporting."""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Callable
from pathlib import Path

from dsw_km_translation_tool.alignment_status import (
    build_alignment_status_report,
    render_alignment_status_markdown,
    write_alignment_status_json,
)
from dsw_km_translation_tool import alignment_status
from dsw_km_translation_tool.cli import report_alignment_status


def prepare_translation_repo_fixture(
    *,
    workspace: Path,
    po_path: Path,
    model_path: Path,
    workflow,
    download_url: str = "https://localize.example.invalid/latest.po",
) -> Path:
    """Prepare a versioned translation repository fixture."""

    repo_root = workspace / "translation-repo"
    latest_po = repo_root / "sources" / "localize" / "zh_Hant" / "latest.po"
    source_km = repo_root / "sources" / "knowledge-models" / "dsw-root-2.7.0" / "dsw-root-2.7.0.km"
    final_po = repo_root / "builds" / "final_translated.po"
    final_km = repo_root / "builds" / "final_translated.km"
    config_path = repo_root / "translation-config.yml"

    latest_po.parent.mkdir(parents=True, exist_ok=True)
    source_km.parent.mkdir(parents=True, exist_ok=True)
    final_po.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(po_path, latest_po)
    shutil.copyfile(model_path, source_km)

    workflow.export_tree(
        po_path=str(latest_po),
        model_path=str(source_km),
        out_dir=str(repo_root / "tree"),
    )
    workflow.build_po_from_tree(
        tree_dir=str(repo_root / "tree"),
        original_po_path=str(latest_po),
        out_po_path=str(final_po),
    )
    workflow.build_km_from_po(
        translated_po_path=str(final_po),
        original_model_path=str(source_km),
        out_model_path=str(final_km),
        output_organization_id="dsw",
        output_km_id="root-zh-hant",
        output_name="Common DSW Knowledge Model (zh-Hant)",
    )

    config_path.write_text(
        "\n".join(
            [
                "schema_version: 1",
                "knowledge_model:",
                "  organization_id: dsw",
                "  km_id: root",
                "  upstream_repository: ds-wizard/dsw-knowledge-models",
                "  bundle_path: sources/knowledge-models/dsw-root-2.7.0/dsw-root-2.7.0.km",
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
                "registry:",
                "  api_url: https://api.registry.ds-wizard.org",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return repo_root


def test_alignment_status_report_accepts_aligned_repository(
    workspace: Path,
    po_path: Path,
    model_path: Path,
    workflow,
) -> None:
    """Verify the report passes when Localize, tree, PO, and KM are aligned."""

    repo_root = prepare_translation_repo_fixture(
        workspace=workspace,
        po_path=po_path,
        model_path=model_path,
        workflow=workflow,
    )
    latest_po = repo_root / "sources" / "localize" / "zh_Hant" / "latest.po"
    artifact_dir = workspace / "artifacts"

    report = build_alignment_status_report(
        repo_root=repo_root,
        config_path=repo_root / "translation-config.yml",
        artifact_dir=artifact_dir,
        downloader=_static_downloader(latest_po.read_bytes()),
    )

    assert report.aligned is True
    assert [check.matched for check in report.checks] == [True, True, True]
    assert not (artifact_dir / "weblate-latest.po").exists()
    assert (artifact_dir / "tree-rebuilt.po").exists()
    assert (artifact_dir / "final-po-rebuilt.km").exists()
    markdown = render_alignment_status_markdown(report)
    assert "Status: **aligned**" in markdown
    assert "| Weblate download matches checked-in latest PO | pass |" in markdown


def test_alignment_status_report_flags_weblate_mismatch(
    workspace: Path,
    po_path: Path,
    model_path: Path,
    workflow,
) -> None:
    """Verify a stale checked-in Localize snapshot is reported as a mismatch."""

    repo_root = prepare_translation_repo_fixture(
        workspace=workspace,
        po_path=po_path,
        model_path=model_path,
        workflow=workflow,
    )

    report = build_alignment_status_report(
        repo_root=repo_root,
        config_path=repo_root / "translation-config.yml",
        downloader=_static_downloader(b"stale remote content\n"),
    )

    assert report.aligned is False
    assert [check.matched for check in report.checks] == [False, True, True]
    markdown = render_alignment_status_markdown(report)
    assert "Status: **not aligned**" in markdown
    assert "Run the Localize pull/sync workflow" in markdown


def test_alignment_status_writes_json(
    workspace: Path,
    po_path: Path,
    model_path: Path,
    workflow,
) -> None:
    """Verify JSON output is stable and machine readable."""

    repo_root = prepare_translation_repo_fixture(
        workspace=workspace,
        po_path=po_path,
        model_path=model_path,
        workflow=workflow,
    )
    latest_po = repo_root / "sources" / "localize" / "zh_Hant" / "latest.po"
    json_path = workspace / "alignment.json"

    report = build_alignment_status_report(
        repo_root=repo_root,
        config_path=repo_root / "translation-config.yml",
        downloader=_static_downloader(latest_po.read_bytes()),
    )
    write_alignment_status_json(report, json_path)

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["aligned"] is True
    assert data["version"] == "2.7.0"
    assert len(data["checks"]) == 3
    assert data["checks"][0]["name"] == "Weblate download matches checked-in latest PO"


def test_report_alignment_status_cli_writes_outputs(
    workspace: Path,
    po_path: Path,
    model_path: Path,
    workflow,
    monkeypatch,
    capsys,
) -> None:
    """Verify the alignment CLI writes JSON, summary, and artifact outputs."""

    translation_repo = prepare_translation_repo_fixture(
        workspace=workspace,
        po_path=po_path,
        model_path=model_path,
        workflow=workflow,
    )
    json_path = workspace / "alignment.json"
    summary_path = workspace / "summary.md"
    details_path = workspace / "details.md"
    artifact_dir = workspace / "alignment-artifacts"

    latest_po = translation_repo / "sources/localize/zh_Hant/latest.po"
    monkeypatch.setattr(
        alignment_status, "_download_url", _static_downloader(latest_po.read_bytes())
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-report-alignment",
            "--repo-root",
            str(translation_repo),
            "--config",
            str(translation_repo / "translation-config.yml"),
            "--json-out",
            str(json_path),
            "--summary",
            str(summary_path),
            "--details-out",
            str(details_path),
            "--artifact-dir",
            str(artifact_dir),
            "--fail-on-mismatch",
        ],
    )
    report_alignment_status.main()
    stdout = capsys.readouterr().out

    assert "## Localize/Repository Alignment" in stdout
    assert "Status: **aligned**" in stdout
    assert json.loads(json_path.read_text(encoding="utf-8"))["aligned"] is True
    assert "## Localize/Repository Alignment" in summary_path.read_text(encoding="utf-8")
    assert details_path.exists()
    assert not (artifact_dir / "weblate-latest.po").exists()


def _static_downloader(payload: bytes) -> Callable[[str], bytes]:
    """Return a downloader that always yields the supplied payload."""

    def download(_url: str) -> bytes:
        return payload

    return download
