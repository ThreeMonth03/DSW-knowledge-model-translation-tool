"""Synchronize canonical shared translations in a translation repository."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .translation_repository_config import (
    load_translation_repository_config,
    version_paths,
)
from .workflow import TranslationWorkflowService


class TranslationRepositorySharedSyncError(RuntimeError):
    """Raised when repository shared translations cannot be synchronized."""


@dataclass(frozen=True)
class TranslationRepositorySharedSyncResult:
    """Summary of one repository shared-translation synchronization."""

    tree_dir: Path
    shared_blocks_dir: Path
    groups_scanned: int
    groups_updated: int
    fields_updated: int
    changed_tree_paths: tuple[Path, ...]


def sync_translation_repository_shared_strings(
    *,
    repo_root: Path,
    config_path: Path = Path("translation-config.yml"),
) -> TranslationRepositorySharedSyncResult:
    """Expand canonical shared-block translations into their tree fields.

    This repository-level operation intentionally updates only the translation
    tree. Full PO, KM, report, and review artifacts remain the responsibility
    of the repository build and release workflows.
    """

    root = repo_root.resolve()
    resolved_config = config_path if config_path.is_absolute() else root / config_path
    config = load_translation_repository_config(resolved_config)
    paths = version_paths(config)
    source_po = root / paths.source_po_path
    tree_dir = root / paths.translation_tree_dir
    shared_blocks_dir = tree_dir / "shared_blocks"

    _require_file(source_po, "source catalog")
    _require_directory(tree_dir, "translation tree")
    _require_directory(shared_blocks_dir, "canonical shared-block directory")

    workflow = TranslationWorkflowService(
        source_lang=config.translation.source_language,
        target_lang=config.translation.target_language,
    )
    result = workflow.sync_shared_strings(
        tree_dir=str(tree_dir),
        original_po_path=str(source_po),
        shared_blocks_root_path=str(shared_blocks_dir),
        group_by="shared-block",
    )
    if result.conflicts:
        raise TranslationRepositorySharedSyncError(
            f"Shared translation synchronization found {len(result.conflicts)} conflict(s)"
        )

    return TranslationRepositorySharedSyncResult(
        tree_dir=tree_dir,
        shared_blocks_dir=shared_blocks_dir,
        groups_scanned=result.groups_scanned,
        groups_updated=result.groups_updated,
        fields_updated=result.fields_updated,
        changed_tree_paths=tuple(Path(path) for path in result.written_tree_paths),
    )


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise TranslationRepositorySharedSyncError(f"Missing {label}: {path}")


def _require_directory(path: Path, label: str) -> None:
    if not path.is_dir():
        raise TranslationRepositorySharedSyncError(f"Missing {label}: {path}")
