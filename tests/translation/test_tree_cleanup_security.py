"""Security coverage for translation-tree cleanup."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dsw_km_translation_tool.constants import MANIFEST_NAME
from dsw_km_translation_tool.tree import TranslationTreeRepository


@pytest.mark.parametrize("root_path", ["../victim", "{absolute}"])
def test_remove_previous_export_rejects_paths_outside_tree(
    tmp_path: Path,
    root_path: str,
) -> None:
    """An untrusted manifest cannot delete directories outside its tree."""

    tree_dir = tmp_path / "tree"
    victim_dir = tmp_path / "victim"
    tree_dir.mkdir()
    victim_dir.mkdir()
    victim_file = victim_dir / "keep.txt"
    victim_file.write_text("keep", encoding="utf-8")
    manifest_path = tree_dir / MANIFEST_NAME
    manifest_path.write_text(
        json.dumps({"rootPaths": [root_path.format(absolute=victim_dir)]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsafe tree manifest root path"):
        TranslationTreeRepository().remove_previous_export(str(tree_dir))

    assert victim_file.read_text(encoding="utf-8") == "keep"
    assert manifest_path.is_file()


def test_remove_previous_export_rejects_root_symlink(tmp_path: Path) -> None:
    """A root symlink cannot redirect cleanup outside the translation tree."""

    tree_dir = tmp_path / "tree"
    victim_dir = tmp_path / "victim"
    tree_dir.mkdir()
    victim_dir.mkdir()
    victim_file = victim_dir / "keep.txt"
    victim_file.write_text("keep", encoding="utf-8")
    (tree_dir / "root").symlink_to(victim_dir, target_is_directory=True)
    (tree_dir / MANIFEST_NAME).write_text(
        json.dumps({"rootPaths": ["root"]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unsafe tree manifest root path"):
        TranslationTreeRepository().remove_previous_export(str(tree_dir))

    assert victim_file.read_text(encoding="utf-8") == "keep"
