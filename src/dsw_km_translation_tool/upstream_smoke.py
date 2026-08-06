"""Integration smoke test against current upstream KM and Weblate inputs."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from .alignment_status import build_alignment_status_report
from .km_bundle_sync import BundleDownloader, pull_km_bundle
from .km_latest_sync import update_knowledge_model_version
from .km_registry import Downloader, discover_km_versions
from .localize_sync import Downloader as LocalizeDownloader
from .localize_sync import pull_localize_po
from .translation_repository_config import (
    load_translation_repository_config,
    version_paths,
)
from .workflow import TranslationWorkflowService


class UpstreamSmokeError(RuntimeError):
    """Raised when the upstream smoke test cannot complete."""


@dataclass(frozen=True)
class UpstreamSmokeResult:
    """Summary of one upstream integration smoke run."""

    status: str
    work_dir: str
    config_path: str
    configured_version: str
    registry_version: str | None
    source_km_path: str | None = None
    localize_po_path: str | None = None
    final_po_path: str | None = None
    final_km_path: str | None = None
    km_bundle_changed: bool = False
    km_bundle_initialized: bool = False
    localize_po_changed: bool = False
    localize_po_initialized: bool = False
    alignment_aligned: bool = False
    skipped_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-ready representation."""

        return asdict(self)


def run_upstream_smoke(
    *,
    work_dir: Path,
    config_template_path: Path,
    registry_token: str,
    skip_without_token: bool = False,
    registry_downloader: Downloader | None = None,
    bundle_downloader: BundleDownloader | None = None,
    localize_downloader: LocalizeDownloader | None = None,
) -> UpstreamSmokeResult:
    """Run a read-only integration check against current upstream sources.

    The smoke workspace is disposable and cacheable. The KM bundle is written
    under ``sources/knowledge-models`` and reused when the Registry returns the
    same content. Changed upstream content refreshes the cached snapshot before
    the full translation and alignment checks run.
    """

    resolved_work_dir = work_dir.resolve()
    resolved_work_dir.mkdir(parents=True, exist_ok=True)
    config_path = resolved_work_dir / "translation-config.yml"
    shutil.copyfile(config_template_path, config_path)

    initial_config = load_translation_repository_config(config_path)
    configured_version = initial_config.knowledge_model.version
    discovery = discover_km_versions(
        config_path=config_path,
        downloader=registry_downloader,
    )
    registry_version = discovery.latest_registry_version
    if registry_version is None:
        raise UpstreamSmokeError("Registry did not return any KM versions")
    if not registry_token.strip():
        if skip_without_token:
            return UpstreamSmokeResult(
                status="skipped:missing-registry-token",
                work_dir=str(resolved_work_dir),
                config_path=str(config_path),
                configured_version=configured_version,
                registry_version=registry_version,
                skipped_reason="missing-registry-token",
            )
        raise UpstreamSmokeError("DSW Registry token is required for upstream smoke")

    update_knowledge_model_version(config_path, registry_version)
    updated_config = load_translation_repository_config(config_path)
    paths = version_paths(updated_config)

    km_result = pull_km_bundle(
        config_path=config_path,
        repo_root=resolved_work_dir,
        token=registry_token,
        downloader=bundle_downloader,
        allow_existing_change=True,
    )
    localize_result = pull_localize_po(
        config_path=config_path,
        repo_root=resolved_work_dir,
        downloader=localize_downloader,
    )

    source_km_path = resolved_work_dir / paths.source_km_path
    latest_po_path = resolved_work_dir / paths.localize_latest_po_path
    tree_dir = resolved_work_dir / paths.translation_tree_dir
    final_po_path = resolved_work_dir / paths.final_po_path
    final_km_path = resolved_work_dir / paths.final_km_path

    workflow = TranslationWorkflowService(
        source_lang=updated_config.translation.source_language,
        target_lang=updated_config.translation.target_language,
    )
    workflow.export_tree(
        po_path=str(latest_po_path),
        model_path=str(source_km_path),
        out_dir=str(tree_dir),
        preserve_existing_translations=False,
    )
    workflow.sync_shared_strings(
        tree_dir=str(tree_dir),
        original_po_path=str(latest_po_path),
        out_po_path=str(final_po_path),
        outline_out_path=str(tree_dir / "outline.md"),
        shared_blocks_root_path=str(tree_dir / "shared_blocks"),
        shared_blocks_outline_out_path=str(tree_dir / "shared_blocks_outline.md"),
        group_by="shared-block",
    )
    workflow.build_km_from_po(
        translated_po_path=str(final_po_path),
        original_model_path=str(source_km_path),
        out_model_path=str(final_km_path),
        output_organization_id=updated_config.translation.translated_organization_id,
        output_km_id=updated_config.translation.translated_km_id,
        output_name=updated_config.translation.translated_name,
        package_identity_mappings=updated_config.translation.package_identity_mappings,
    )

    alignment = build_alignment_status_report(
        repo_root=resolved_work_dir,
        config_path=config_path,
        downloader=lambda _url: latest_po_path.read_bytes(),
    )
    if not alignment.aligned:
        raise UpstreamSmokeError("Generated upstream smoke artifacts are not aligned")

    return UpstreamSmokeResult(
        status="passed",
        work_dir=str(resolved_work_dir),
        config_path=str(config_path),
        configured_version=configured_version,
        registry_version=registry_version,
        source_km_path=str(source_km_path),
        localize_po_path=str(latest_po_path),
        final_po_path=str(final_po_path),
        final_km_path=str(final_km_path),
        km_bundle_changed=km_result.changed,
        km_bundle_initialized=km_result.initialized,
        localize_po_changed=localize_result.changed,
        localize_po_initialized=localize_result.initialized,
        alignment_aligned=alignment.aligned,
    )


def render_upstream_smoke_markdown(result: UpstreamSmokeResult) -> str:
    """Render an upstream smoke result as maintainer-readable Markdown."""

    lines = [
        "## Upstream Smoke",
        "",
        f"Status: **{result.status}**",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Work dir | `{result.work_dir}` |",
        f"| Configured version before run | {_format_value(result.configured_version)} |",
        f"| Registry latest version | {_format_value(result.registry_version)} |",
        f"| Source KM | {_format_value(result.source_km_path)} |",
        f"| Localize PO | {_format_value(result.localize_po_path)} |",
        f"| Final PO | {_format_value(result.final_po_path)} |",
        f"| Final KM | {_format_value(result.final_km_path)} |",
        f"| KM bundle changed | {'yes' if result.km_bundle_changed else 'no'} |",
        f"| Localize PO changed | {'yes' if result.localize_po_changed else 'no'} |",
        f"| Alignment | {'aligned' if result.alignment_aligned else 'not checked'} |",
        f"| Skipped reason | {_format_value(result.skipped_reason)} |",
    ]
    return "\n".join(lines) + "\n"


def write_upstream_smoke_report(
    *,
    result: UpstreamSmokeResult,
    report_path: Path,
) -> None:
    """Write an upstream smoke result as pretty JSON."""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_upstream_smoke_markdown(
    *,
    result: UpstreamSmokeResult,
    report_path: Path,
) -> None:
    """Write an upstream smoke result as Markdown."""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_upstream_smoke_markdown(result), encoding="utf-8")


def _format_value(value: object | None) -> str:
    if value is None or value == "":
        return "(none)"
    return f"`{value}`"
