"""Security coverage for recoverable translation field-state storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from dsw_km_translation_tool.tree_support import (
    TranslationFieldStateStore,
    TranslationTreePathService,
)


@pytest.mark.parametrize("invalid_state", [b"{not-json", b"\xff"])
def test_field_state_store_ignores_invalid_cache(
    tmp_path: Path,
    invalid_state: bytes,
) -> None:
    """Malformed local cache data cannot prevent translation-tree scans."""

    tree_dir = tmp_path / "tree"
    path_service = TranslationTreePathService()
    state_path = path_service.field_state_path(tree_dir)
    state_path.parent.mkdir(parents=True)
    state_path.write_bytes(invalid_state)

    store = TranslationFieldStateStore(path_service)

    assert store.load(tree_dir) == {}
