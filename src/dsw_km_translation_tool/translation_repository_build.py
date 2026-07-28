"""Rebuild a Git-authoritative translation repository from checked-in inputs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .translation_repository_config import (
    load_translation_repository_config,
    version_paths,
)
from .workflow import TranslationWorkflowService


class TranslationRepositoryBuildError(RuntimeError):
    """Raised when a Git-managed translation repository cannot be rebuilt."""


@dataclass(frozen=True)
class TranslationRepositoryBuildResult:
    """Summary of one repository rebuild."""

    initialized: bool
    source_km_path: Path
    source_po_path: Path
    tree_dir: Path
    final_po_path: Path
    final_km_path: Path


def build_translation_repository(
    *,
    repo_root: Path,
    config_path: Path = Path("translation-config.yml"),
    allow_uninitialized: bool = False,
    preserve_existing_translations: bool = True,
) -> TranslationRepositoryBuildResult:
    """Rebuild tree, PO, review report, and KM from Git-managed inputs.

    ``preserve_existing_translations`` is intended for ordinary tree-to-output
    rebuilds. Source synchronization must disable it after carrying exact
    source matches into the catalog, otherwise stale tree text could survive a
    changed source string.
    """

    root = repo_root.resolve()
    resolved_config = config_path if config_path.is_absolute() else root / config_path
    config = load_translation_repository_config(resolved_config)
    paths = version_paths(config)
    source_km = root / paths.source_km_path
    source_po = root / paths.source_po_path
    tree_dir = root / paths.translation_tree_dir
    final_po = root / paths.final_po_path
    final_km = root / paths.final_km_path

    existing_inputs = (source_km.is_file(), source_po.is_file())
    if not any(existing_inputs) and allow_uninitialized:
        return TranslationRepositoryBuildResult(
            initialized=False,
            source_km_path=source_km,
            source_po_path=source_po,
            tree_dir=tree_dir,
            final_po_path=final_po,
            final_km_path=final_km,
        )
    if not all(existing_inputs):
        missing = source_km if not source_km.is_file() else source_po
        raise TranslationRepositoryBuildError(
            f"Translation repository is partially initialized; missing {missing}"
        )

    workflow = TranslationWorkflowService(
        source_lang=config.translation.source_language,
        target_lang=config.translation.target_language,
    )
    context = workflow.export_tree(
        po_path=str(source_po),
        model_path=str(source_km),
        out_dir=str(tree_dir),
        preserve_existing_translations=preserve_existing_translations,
    )
    workflow.write_report(
        report=context.report,
        report_path=str(root / paths.validation_report_path),
    )
    workflow.build_shared_blocks_directory(
        tree_dir=str(tree_dir),
        original_po_path=str(source_po),
        out_shared_blocks_root=str(tree_dir / "shared_blocks"),
    )
    workflow.sync_shared_strings(
        tree_dir=str(tree_dir),
        original_po_path=str(source_po),
        out_po_path=str(final_po),
        outline_out_path=str(tree_dir / "outline.md"),
        shared_blocks_root_path=str(tree_dir / "shared_blocks"),
        shared_blocks_outline_out_path=str(tree_dir / "shared_blocks_outline.md"),
        group_by="shared-block",
    )
    workflow.review_po_changes(
        original_po_path=str(source_po),
        generated_po_path=str(final_po),
        diff_out_path=str(root / paths.review_diff_path),
    )
    workflow.build_km_from_po(
        translated_po_path=str(final_po),
        original_model_path=str(source_km),
        out_model_path=str(final_km),
        output_organization_id=config.translation.translated_organization_id,
        output_km_id=config.translation.translated_km_id,
        output_name=config.translation.translated_name,
        package_identity_mappings=config.translation.package_identity_mappings,
        supplemental_translations_dir=(
            str(root / config.translation.supplemental_directory)
            if config.translation.supplemental_directory
            else None
        ),
    )
    return TranslationRepositoryBuildResult(
        initialized=True,
        source_km_path=source_km,
        source_po_path=source_po,
        tree_dir=tree_dir,
        final_po_path=final_po,
        final_km_path=final_km,
    )
