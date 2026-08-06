"""Tests that validate the checked-in translation tree fixture."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dsw_km_translation_tool.shared_blocks import SharedBlocksCatalogParser
from tests.helpers import (
    build_entry_map,
    build_outline_markdown,
    build_shared_blocks_outline_markdown,
    corrupt_translation_by_appending_outside_fence,
    corrupt_translation_by_breaking_final_fence,
    inspect_translation_tree_disk_state,
    parse_po_blocks,
    parse_po_entries,
    read_translation_markdown_header,
    read_tree_manifest,
)


def test_translation_fixture_tree_disk_state_matches_expected_uuid_field_mapping(
    workflow,
    po_entries,
    translation_tree_dir,
) -> None:
    """Verify that the checked-in tree fixture is structurally intact.

    This test reads the real-tree fixture directly from disk. It is meant to
    fail when files are deleted, folders are removed, fenced blocks are edited
    incorrectly, or the markdown template breaks.

    Args:
        workflow: Workflow service fixture.
        po_entries: Flattened source PO entries fixture.
        translation_tree_dir: Checked-in tree fixture directory.
    """

    _, field_states = inspect_translation_tree_disk_state(
        workflow=workflow,
        tree_dir=translation_tree_dir,
    )
    source_entry_map = build_entry_map(po_entries)

    assert set(field_states) == set(source_entry_map)
    for key, state in field_states.items():
        entry = source_entry_map[key]
        assert state.source_text == entry.msgid


def test_translation_fixture_translation_markdown_headers_match_manifest_metadata(
    translation_tree_dir,
) -> None:
    """Verify that fixture translation headers match manifest metadata.

    Args:
        translation_tree_dir: Checked-in tree fixture directory.
    """

    manifest = read_tree_manifest(translation_tree_dir)
    for entity_uuid, node in manifest["nodes"].items():
        if not node.get("fields"):
            continue
        translation_path = translation_tree_dir / node["path"] / "translation.md"
        header_uuid, header_event_type = read_translation_markdown_header(translation_path)
        assert header_uuid == entity_uuid
        assert header_event_type == node.get("eventType")


def test_translation_fixture_tree_and_generated_po_stay_in_sync(
    workflow,
    po_path,
    po_entries,
    model_path,
    translation_tree_dir,
    translation_final_po_path,
) -> None:
    """Verify that fixture tree translations match the generated PO file.

    This test is intentionally strict for translation-tree workflows. If someone
    edits `translation.md` but forgets to run `make sync`, `make sync-watch`,
    or `make tree-to-po`, the test must fail and point at the mismatch.

    Args:
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        po_entries: Flattened source PO entries fixture.
        model_path: Fixture KM file path.
        translation_tree_dir: Checked-in tree fixture directory.
        translation_final_po_path: Checked-in generated PO fixture path.
    """

    manifest, field_states = inspect_translation_tree_disk_state(
        workflow=workflow,
        tree_dir=translation_tree_dir,
    )
    assert translation_final_po_path.exists(), (
        "Missing generated fixture PO file: "
        f"{translation_final_po_path}\n"
        "Run `make sync` or `make tree-to-po` before running translation tests."
    )

    po_entry_map = build_entry_map(parse_po_entries(translation_final_po_path))
    source_entry_map = build_entry_map(po_entries)

    assert set(po_entry_map) == set(field_states)
    for key, state in field_states.items():
        uuid, field = key
        node = manifest["nodes"][uuid]
        translation_path = translation_tree_dir / node["path"] / "translation.md"
        built_entry = po_entry_map[key]
        source_entry = source_entry_map[key]
        assert built_entry.msgid == source_entry.msgid
        assert built_entry.msgid == state.source_text
        assert built_entry.msgstr == state.target_text, (
            "Checked-in tree and generated PO are out of sync.\n"
            f"File: {translation_path}\n"
            f"UUID: {uuid}\n"
            f"Field: {field}\n"
            f"Tree target: {state.target_text!r}\n"
            f"PO msgstr: {built_entry.msgstr!r}\n"
            "Run `make sync`, `make sync-watch`, or `make tree-to-po`."
        )

    report = workflow.validate_po_against_model(
        str(translation_final_po_path),
        str(model_path),
    )
    assert report["missingEntities"] == 0
    assert report["missingFields"] == 0
    assert report["mismatches"] == 0

    review = workflow.review_po_changes(
        original_po_path=str(po_path),
        generated_po_path=str(translation_final_po_path),
    )
    assert review.msgstr_only, (
        "Generated fixture PO changed more than msgstr blocks.\n"
        f"Changed msgid blocks: {review.changed_msgid_blocks}\n"
        f"Changed reference blocks: {review.changed_reference_blocks}\n"
        f"Changed fuzzy blocks: {review.changed_fuzzy_blocks}\n"
        f"Inserted blocks: {review.inserted_blocks}\n"
        f"Deleted blocks: {review.deleted_blocks}"
    )


def test_translation_fixture_generated_diff_matches_current_po_review(
    workflow,
    po_path,
    translation_final_po_path,
    translation_diff_path,
) -> None:
    """Verify that the fixture diff matches the current generated PO review.

    Args:
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        translation_final_po_path: Checked-in generated PO fixture path.
        translation_diff_path: Checked-in generated diff fixture path.
    """

    assert translation_final_po_path.exists(), (
        f"Missing generated fixture PO file: {translation_final_po_path}"
    )
    assert translation_diff_path.exists(), (
        "Missing generated fixture diff file: "
        f"{translation_diff_path}\n"
        "Run `make sync` or `make review-po` before running translation tests."
    )

    review = workflow.review_po_changes(
        original_po_path=str(po_path),
        generated_po_path=str(translation_final_po_path),
    )
    recorded_diff = translation_diff_path.read_text(encoding="utf-8")

    assert recorded_diff == review.diff_text, (
        "Checked-in diff file does not match the current PO review output.\n"
        f"Diff file: {translation_diff_path}\n"
        f"Generated PO: {translation_final_po_path}\n"
        "Run `make sync` or `make review-po` to refresh the diff."
    )


def test_translation_fixture_outline_matches_current_tree_progress(
    workflow,
    translation_tree_dir,
    translation_outline_path,
) -> None:
    """Verify that the fixture outline matches the current tree state.

    Args:
        workflow: Workflow service fixture.
        translation_tree_dir: Checked-in tree fixture directory.
        translation_outline_path: Checked-in outline markdown path.
    """

    assert translation_outline_path.exists(), (
        "Missing fixture outline markdown file: "
        f"{translation_outline_path}\n"
        "Run `make sync` before running translation tests."
    )

    generated_outline_path = translation_outline_path.with_name(".outline.test.generated.md")
    try:
        result = build_outline_markdown(
            workflow=workflow,
            tree_dir=translation_tree_dir,
            output_outline_path=generated_outline_path,
        )
        recorded_outline = translation_outline_path.read_text(encoding="utf-8")

        assert recorded_outline == result.markdown_text, (
            "Checked-in outline markdown does not match the current tree state.\n"
            f"Outline file: {translation_outline_path}\n"
            f"Generated file: {generated_outline_path}\n"
            "Run `make sync` to refresh the outline."
        )
        assert "- [x] [layer 1] 0001 Common DSW Knowledge Model" in recorded_outline
        assert "[shared]" in recorded_outline
        assert "[KM] [uuid](" in recorded_outline
        assert "[Q] [translation](" in recorded_outline
    finally:
        generated_outline_path.unlink(missing_ok=True)


def test_outline_generation_does_not_follow_output_symlink(
    workflow,
    translation_tree_dir,
    tmp_path,
) -> None:
    """Verify that generating an outline cannot clobber a symlink target."""

    victim_path = tmp_path / "victim.txt"
    victim_path.write_text("do not overwrite\n", encoding="utf-8")
    outline_path = tmp_path / "outline.md"
    outline_path.symlink_to(victim_path)

    result = build_outline_markdown(
        workflow=workflow,
        tree_dir=translation_tree_dir,
        output_outline_path=outline_path,
    )

    assert victim_path.read_text(encoding="utf-8") == "do not overwrite\n"
    assert not outline_path.is_symlink()
    assert outline_path.read_text(encoding="utf-8") == result.markdown_text


def test_translation_fixture_shared_block_translations_are_fully_synchronized_in_tree(
    workflow,
    po_path,
    translation_tree_dir,
    translation_shared_blocks_dir,
) -> None:
    """Verify every shared PO group matches every linked fixture field.

    Args:
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        translation_tree_dir: Checked-in tree fixture directory.
        translation_shared_blocks_dir: Checked-in shared-block directory path.
    """

    _, field_states = inspect_translation_tree_disk_state(
        workflow=workflow,
        tree_dir=translation_tree_dir,
    )
    shared_blocks = [block for block in parse_po_blocks(po_path) if len(block.references) >= 2]
    expected_group_keys = {
        tuple((reference.uuid, reference.field) for reference in block.references)
        for block in shared_blocks
    }
    shared_blocks_map = SharedBlocksCatalogParser().parse(
        str(translation_shared_blocks_dir),
        expected_group_keys=expected_group_keys,
    )

    assert set(shared_blocks_map) == expected_group_keys, (
        "Shared-block markdown does not cover the same group set as the source PO.\n"
        f"Missing groups: {sorted(expected_group_keys - set(shared_blocks_map))[:10]}\n"
        f"Unexpected groups: {sorted(set(shared_blocks_map) - expected_group_keys)[:10]}"
    )

    for block in shared_blocks:
        group_key = tuple((reference.uuid, reference.field) for reference in block.references)
        canonical_translation = shared_blocks_map[group_key]
        serialized_group_key = SharedBlocksCatalogParser.serialize_group_key(group_key)

        for reference in block.references:
            tree_key = (reference.uuid, reference.field)
            assert tree_key in field_states, (
                "Shared-block reference is missing from the translation tree.\n"
                f"Group: {serialized_group_key}\n"
                f"Missing tree key: {tree_key}"
            )
            actual_translation = field_states[tree_key].target_text
            assert actual_translation == canonical_translation, (
                "Shared-block translation is not synchronized across all linked tree "
                "fields.\n"
                f"Group: {serialized_group_key}\n"
                f"Tree key: {tree_key}\n"
                f"Canonical translation: {canonical_translation!r}\n"
                f"Actual tree translation: {actual_translation!r}\n"
                "Run `make sync` to re-apply the canonical shared-block translation."
            )


def test_translation_fixture_shared_blocks_outline_matches_current_tree_state(
    workflow,
    po_path,
    translation_tree_dir,
    translation_shared_blocks_outline_path,
) -> None:
    """Verify that the fixture shared-block outline matches the current tree.

    Args:
        workflow: Workflow service fixture.
        po_path: Fixture PO file path.
        translation_tree_dir: Checked-in tree fixture directory.
        translation_shared_blocks_outline_path: Checked-in shared-block
            overview markdown path.
    """

    assert translation_shared_blocks_outline_path.exists(), (
        "Missing fixture shared-block outline markdown file: "
        f"{translation_shared_blocks_outline_path}\n"
        "Run `make sync` or `make export-tree` before running translation tests."
    )

    generated_outline_path = translation_shared_blocks_outline_path.with_name(
        ".shared_blocks_outline.test.generated.md"
    )
    try:
        result = build_shared_blocks_outline_markdown(
            workflow=workflow,
            tree_dir=translation_tree_dir,
            original_po_path=po_path,
            output_shared_blocks_outline_path=generated_outline_path,
        )
        recorded_outline = translation_shared_blocks_outline_path.read_text(encoding="utf-8")
        assert recorded_outline == result.markdown_text, (
            "Checked-in shared-block outline markdown does not match the current "
            "tree state.\n"
            f"Outline file: {translation_shared_blocks_outline_path}\n"
            f"Generated file: {generated_outline_path}\n"
            "Run `make sync` to refresh the shared-block outline."
        )
        assert "# Shared Blocks Outline" in recorded_outline
        assert "## Untranslated" not in recorded_outline
        assert "## Translated" not in recorded_outline
        assert "- [x] Group " in recorded_outline or "- [ ] Group " in recorded_outline
        assert "](<shared_blocks/" in recorded_outline
        assert "- [x] [Group " not in recorded_outline
        assert "- [ ] [Group " not in recorded_outline
        assert "refs=`" not in recorded_outline
        assert "fields=`" not in recorded_outline
    finally:
        generated_outline_path.unlink(missing_ok=True)


def _read_directory_files(root: Path) -> dict[str, str]:
    """Return a normalized snapshot of all files below one directory root."""

    result: dict[str, str] = {}
    for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
        result[file_path.relative_to(root).as_posix()] = file_path.read_text(encoding="utf-8")
    return result


def _po_block_skeleton(block) -> tuple[tuple[str, ...], str, bool]:
    """Return the non-translation identity of one PO block.

    Args:
        block: Parsed PO block.

    Returns:
        Tuple containing references, `msgid`, and fuzzy status.
    """

    return (
        tuple(reference.comment for reference in block.references),
        block.msgid,
        block.is_fuzzy,
    )


def test_translation_fixture_generated_po_preserves_translation_block_count(
    po_path,
    translation_final_po_path,
) -> None:
    """Verify that the generated fixture PO keeps the original block count.

    This protects shared PO blocks from being silently split into extra
    translation strings in the checked-in fixture output.

    Args:
        po_path: Fixture PO file path.
        translation_final_po_path: Checked-in generated PO fixture path.
    """

    assert translation_final_po_path.exists(), (
        "Missing generated fixture PO file: "
        f"{translation_final_po_path}\n"
        "Run `make sync` or `make tree-to-po` before running translation tests."
    )

    source_blocks = parse_po_blocks(po_path)
    generated_blocks = parse_po_blocks(translation_final_po_path)

    assert len(generated_blocks) == len(source_blocks), (
        "Generated fixture PO does not preserve the original translation "
        "string count.\n"
        f"Source PO blocks: {len(source_blocks)}\n"
        f"Generated PO blocks: {len(generated_blocks)}\n"
        "This usually means a shared PO block was split unexpectedly.\n"
        "Run `make sync` and check whether conflicting translations were "
        "introduced into nodes that originally shared one PO block."
    )
    assert [_po_block_skeleton(block) for block in generated_blocks] == [
        _po_block_skeleton(block) for block in source_blocks
    ], (
        "Generated fixture PO changed non-translation content.\n"
        "Only `msgstr` values are allowed to differ from the source PO.\n"
        "Check for changed references, `msgid`, fuzzy flags, block order, or "
        "unexpected shared-block splitting."
    )


def test_translation_fixture_tree_validation_catches_missing_translation_markdown(
    workflow,
    translation_tree_dir,
    workspace,
) -> None:
    """Verify that translation validation fails when `translation.md` is deleted.

    Args:
        workflow: Workflow service fixture.
        translation_tree_dir: Checked-in tree fixture directory.
        workspace: Per-test temporary workspace fixture.
    """

    tree_copy = workspace / "tree"
    shutil.copytree(translation_tree_dir, tree_copy)

    manifest = read_tree_manifest(tree_copy)
    entity_uuid, node = next(
        (entity_uuid, node) for entity_uuid, node in manifest["nodes"].items() if node.get("fields")
    )
    translation_path = tree_copy / node["path"] / "translation.md"
    translation_path.unlink()

    with pytest.raises(AssertionError, match="Missing translation markdown"):
        inspect_translation_tree_disk_state(
            workflow=workflow,
            tree_dir=tree_copy,
        )


def test_translation_fixture_tree_validation_catches_missing_node_folder(
    workflow,
    translation_tree_dir,
    workspace,
) -> None:
    """Verify that translation validation fails when a node folder is deleted.

    Args:
        workflow: Workflow service fixture.
        translation_tree_dir: Checked-in tree fixture directory.
        workspace: Per-test temporary workspace fixture.
    """

    tree_copy = workspace / "tree"
    shutil.copytree(translation_tree_dir, tree_copy)

    manifest = read_tree_manifest(tree_copy)
    _, node = next(
        (entity_uuid, node) for entity_uuid, node in manifest["nodes"].items() if node.get("fields")
    )
    shutil.rmtree(tree_copy / node["path"])

    with pytest.raises(AssertionError, match="Tree folder UUID set does not match manifest"):
        inspect_translation_tree_disk_state(
            workflow=workflow,
            tree_dir=tree_copy,
        )


def test_translation_fixture_tree_validation_catches_text_outside_fence(
    workflow,
    translation_tree_dir,
    workspace,
) -> None:
    """Verify that translation validation fails on text appended outside fences.

    Args:
        workflow: Workflow service fixture.
        translation_tree_dir: Checked-in tree fixture directory.
        workspace: Per-test temporary workspace fixture.
    """

    tree_copy = workspace / "tree"
    shutil.copytree(translation_tree_dir, tree_copy)

    manifest = read_tree_manifest(tree_copy)
    _, node = next(
        (entity_uuid, node) for entity_uuid, node in manifest["nodes"].items() if node.get("fields")
    )
    corrupt_translation_by_appending_outside_fence(tree_copy / node["path"] / "translation.md")

    with pytest.raises(ValueError, match="Unexpected content outside a fenced translation block"):
        inspect_translation_tree_disk_state(
            workflow=workflow,
            tree_dir=tree_copy,
        )


def test_translation_fixture_tree_validation_catches_broken_fence(
    workflow,
    translation_tree_dir,
    workspace,
) -> None:
    """Verify that translation validation fails when a closing fence is broken.

    Args:
        workflow: Workflow service fixture.
        translation_tree_dir: Checked-in tree fixture directory.
        workspace: Per-test temporary workspace fixture.
    """

    tree_copy = workspace / "tree"
    shutil.copytree(translation_tree_dir, tree_copy)

    manifest = read_tree_manifest(tree_copy)
    _, node = next(
        (entity_uuid, node) for entity_uuid, node in manifest["nodes"].items() if node.get("fields")
    )
    corrupt_translation_by_breaking_final_fence(tree_copy / node["path"] / "translation.md")

    with pytest.raises(ValueError, match="Broken fence detected|Unclosed fence"):
        inspect_translation_tree_disk_state(
            workflow=workflow,
            tree_dir=tree_copy,
        )
