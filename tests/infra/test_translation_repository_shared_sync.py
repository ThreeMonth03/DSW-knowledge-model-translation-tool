"""Tests for repository-level shared-translation synchronization."""

from __future__ import annotations

import shutil

from dsw_km_translation_tool.translation_repository_shared_sync import (
    sync_translation_repository_shared_strings,
)
from tests.helpers import (
    export_tree_for_test,
    select_multi_reference_block,
    update_shared_block_translation,
    update_tree_field,
    validate_tree,
)
from tests.infra.test_translation_repository_config import write_config


def test_repository_shared_sync_updates_only_translation_tree(
    workflow,
    po_path,
    model_path,
    po_blocks,
    po_entries,
    workspace,
) -> None:
    """Verify canonical shared translations expand without building outputs."""

    target_repo = workspace / "translation-repo"
    source_po = target_repo / "sources/localize/zh_Hant/latest.po"
    source_po.parent.mkdir(parents=True)
    shutil.copy2(po_path, source_po)
    write_config(target_repo / "translation-config.yml")

    tree_dir = target_repo / "tree"
    export_tree_for_test(
        workflow=workflow,
        po_path=source_po,
        model_path=model_path,
        tree_dir=tree_dir,
    )
    shared_blocks_dir = tree_dir / "shared_blocks"
    workflow.build_shared_blocks_directory(
        tree_dir=str(tree_dir),
        original_po_path=str(source_po),
        out_shared_blocks_root=str(shared_blocks_dir),
    )
    scan_result = validate_tree(
        workflow=workflow,
        tree_dir=tree_dir,
        entries=po_entries,
    )
    block, available_keys = select_multi_reference_block(po_blocks, scan_result)
    group_key = tuple((reference.uuid, reference.field) for reference in block.references)
    canonical_translation = "[REPOSITORY_SHARED_SYNC]"
    update_shared_block_translation(
        shared_blocks_root=shared_blocks_dir,
        group_key=group_key,
        target_text=canonical_translation,
    )
    for uuid, field in available_keys:
        update_tree_field(
            workflow=workflow,
            scan_result=scan_result,
            uuid=uuid,
            field=field,
            target_text="",
        )

    result = sync_translation_repository_shared_strings(repo_root=target_repo)

    assert result.tree_dir == tree_dir
    assert result.shared_blocks_dir == shared_blocks_dir
    assert result.groups_updated == 1
    assert result.fields_updated == len(available_keys)
    assert set(result.changed_tree_paths) == {
        scan_result.folders_by_uuid[uuid].translation_path for uuid, _ in available_keys
    }
    synced_scan = workflow.tree_repository.scan(str(tree_dir))
    for uuid, field in available_keys:
        assert synced_scan.folders_by_uuid[uuid].fields[field].target_text == canonical_translation
    for output_dir in ("builds", "reports", "reviews"):
        assert not (target_repo / output_dir).exists()
