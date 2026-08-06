"""Regression tests for repository-controlled artifact symlinks."""

from pathlib import Path

import pytest

from dsw_km_translation_tool.path_safety import reject_symlink_path
from dsw_km_translation_tool.shared_blocks import SharedBlocksCatalogBuilder


def test_reject_symlink_path_rejects_symlinked_managed_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    managed_root = tmp_path / "shared_blocks"
    managed_root.symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked artifact path"):
        reject_symlink_path(managed_root)


def test_pruning_rejects_symlinked_group_without_touching_target(
    tmp_path: Path,
) -> None:
    shared_blocks_root = tmp_path / "shared_blocks"
    shared_blocks_root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    protected_file = outside / "workflow.yml"
    protected_file.write_text("protected", encoding="utf-8")
    (shared_blocks_root / "group-id").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinked artifact path"):
        SharedBlocksCatalogBuilder._prune_stale_group_paths(shared_blocks_root, set())

    assert protected_file.read_text(encoding="utf-8") == "protected"


def test_pruning_rejects_symlinked_context_file(tmp_path: Path) -> None:
    group_dir = tmp_path / "group-id"
    group_dir.mkdir()
    protected_file = tmp_path / "protected.md"
    protected_file.write_text("protected", encoding="utf-8")
    (group_dir / "context.md").symlink_to(protected_file)

    with pytest.raises(ValueError, match="symlinked artifact path"):
        SharedBlocksCatalogBuilder._prune_stale_group_member_paths(group_dir)

    assert protected_file.read_text(encoding="utf-8") == "protected"
