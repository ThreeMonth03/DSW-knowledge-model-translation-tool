"""Builder for shared-block translation files and outlines."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import Any

from ..constants import (
    MANIFEST_NAME,
    SHARED_BLOCK_CONTEXT_FILENAME,
    SHARED_BLOCKS_DIRNAME,
    UUID_FILENAME,
)
from ..data_models import (
    PoBlock,
    PoReference,
    SharedBlocksDirectoryBuildResult,
    SharedBlocksOutlineBuildResult,
    TreeFolderSnapshot,
)
from ..outline_support import TranslationOutlineRenderer
from ..path_safety import reject_symlink_path
from ..po import PoCatalogParser
from ..tree import TranslationTreeRepository
from .models import SharedBlockContext, SharedBlockRecord
from .parser import SharedBlocksCatalogParser

SEGMENT_ORDER_RE = re.compile(r"^\d{4}\s+")
SEGMENT_UUID_SUFFIX_RE = re.compile(r" \[[0-9a-f]{8}\]$")


def resolve_shared_blocks_backup_root(
    tree_repository: TranslationTreeRepository,
    tree_dir: str | Path,
) -> Path:
    """Return the local backup directory for split shared-block files."""

    return tree_repository.path_service.backup_root(tree_dir) / SHARED_BLOCKS_DIRNAME


class SharedBlocksCatalogBuilder:
    """Build shared-block translation artifacts from the current tree and PO.

    Args:
        tree_repository: Translation tree repository used to scan the tree.
        source_lang: Source language code shown in the markdown.
        target_lang: Target language code shown in the markdown.
    """

    def __init__(
        self,
        tree_repository: TranslationTreeRepository,
        source_lang: str = "en",
        target_lang: str = "zh_Hant",
    ):
        self.tree_repository = tree_repository
        self.source_lang = source_lang
        self.target_lang = target_lang

    def build_directory(
        self,
        tree_dir: str,
        original_po_path: str,
        output_shared_blocks_root: str,
    ) -> SharedBlocksDirectoryBuildResult:
        """Build and persist only the canonical shared-block directory.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO used as the shared-block source.
            output_shared_blocks_root: Destination shared-block directory path.

        Returns:
            Shared-block directory build result.
        """

        manifest = self.tree_repository.read_existing_manifest(tree_dir)
        if manifest is None:
            raise ValueError(f"Translation tree manifest not found in {tree_dir}/{MANIFEST_NAME}")

        blocks = PoCatalogParser(original_po_path).parse_blocks()
        scan_result = self.tree_repository.scan(tree_dir)
        shared_blocks_root = Path(output_shared_blocks_root)
        records = self._build_records(
            blocks=blocks,
            manifest=manifest,
            tree_dir=Path(tree_dir),
            link_base_dir=shared_blocks_root.parent,
            folders_by_uuid=scan_result.folders_by_uuid,
        )
        written_paths = self._write_group_files(
            shared_blocks_root=shared_blocks_root,
            records=records,
        )
        self._write_shared_blocks_backup(
            tree_dir=tree_dir,
            shared_blocks_root=shared_blocks_root,
            records=records,
        )
        return SharedBlocksDirectoryBuildResult(
            output_shared_blocks_root=shared_blocks_root,
            written_paths=tuple(sorted(written_paths, key=str)),
        )

    def build_outline(
        self,
        tree_dir: str,
        original_po_path: str,
        output_shared_blocks_outline_path: str,
    ) -> SharedBlocksOutlineBuildResult:
        """Build and persist the shared-block outline markdown file.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO used as the shared-block source.
            output_shared_blocks_outline_path: Destination markdown path.

        Returns:
            Shared-block outline build result.
        """

        manifest = self.tree_repository.read_existing_manifest(tree_dir)
        if manifest is None:
            raise ValueError(f"Translation tree manifest not found in {tree_dir}/{MANIFEST_NAME}")

        blocks = PoCatalogParser(original_po_path).parse_blocks()
        scan_result = self.tree_repository.scan(tree_dir)
        output_path = Path(output_shared_blocks_outline_path)
        records = self._build_records(
            blocks=blocks,
            manifest=manifest,
            tree_dir=Path(tree_dir),
            link_base_dir=output_path.parent,
            folders_by_uuid=scan_result.folders_by_uuid,
        )
        markdown_text = self._render_outline(records, output_path=output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown_text, encoding="utf-8")
        return SharedBlocksOutlineBuildResult(
            markdown_text=markdown_text,
            output_shared_blocks_outline=output_path,
        )

    def _build_records(
        self,
        blocks: list[PoBlock],
        manifest: dict[str, Any],
        tree_dir: Path,
        link_base_dir: Path,
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> list[SharedBlockRecord]:
        """Build shared-block records from parsed PO blocks."""

        manifest_nodes = manifest.get("nodes", {})
        if not isinstance(manifest_nodes, dict):
            raise ValueError("Tree manifest nodes must be a dictionary")
        children_by_uuid = self._build_children_index(manifest_nodes)

        records: list[SharedBlockRecord] = []
        for block in blocks:
            if len(block.references) < 2:
                continue
            contexts = tuple(
                self._build_context(
                    reference=reference,
                    tree_dir=tree_dir,
                    link_base_dir=link_base_dir,
                    manifest_nodes=manifest_nodes,
                    children_by_uuid=children_by_uuid,
                    folders_by_uuid=folders_by_uuid,
                )
                for reference in block.references
            )
            records.append(
                SharedBlockRecord(
                    group_key=tuple(
                        (reference.uuid, reference.field) for reference in block.references
                    ),
                    source_text=block.msgid,
                    translation_text=self._resolve_translation_text(
                        block=block,
                        folders_by_uuid=folders_by_uuid,
                    ),
                    contexts=contexts,
                    stable_id=SharedBlocksCatalogParser.stable_group_id(
                        tuple((reference.uuid, reference.field) for reference in block.references)
                    ),
                )
            )

        return records

    def _resolve_translation_text(
        self,
        block: PoBlock,
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> str:
        """Select the current canonical translation for one shared block."""

        candidates: list[tuple[float, str, str]] = []
        for reference in block.references:
            snapshot = folders_by_uuid.get(reference.uuid)
            if snapshot is None:
                continue
            state = snapshot.fields.get(reference.field)
            if state is None:
                continue
            candidates.append(
                (
                    snapshot.field_modified_at.get(reference.field, snapshot.modified_at),
                    snapshot.path,
                    state.target_text,
                )
            )
        if not candidates:
            return block.msgstr
        candidates.sort(reverse=True)
        return candidates[0][2]

    def _build_context(
        self,
        reference: PoReference,
        tree_dir: Path,
        link_base_dir: Path,
        manifest_nodes: dict[str, Any],
        children_by_uuid: dict[str, tuple[str, ...]],
        folders_by_uuid: dict[str, TreeFolderSnapshot],
    ) -> SharedBlockContext:
        """Build one linked context for a shared block."""

        node = manifest_nodes.get(reference.uuid, {})
        relative_node_path = str(node.get("path", ""))
        snapshot = folders_by_uuid.get(reference.uuid)
        link_target = (
            snapshot.translation_path
            if snapshot is not None and snapshot.translation_path is not None
            else tree_dir / relative_node_path / UUID_FILENAME
        )
        relative_link = os.path.relpath(link_target, link_base_dir)
        label = self._display_label(relative_node_path or reference.uuid)
        badge = TranslationOutlineRenderer.event_type_badge(node.get("eventType"))
        context_label = self._build_context_label(
            entity_uuid=reference.uuid,
            relative_node_path=relative_node_path,
            children_by_uuid=children_by_uuid,
            manifest_nodes=manifest_nodes,
        )
        return SharedBlockContext(
            reference=reference,
            badge=badge,
            label=label,
            relative_link=relative_link,
            context_label=context_label,
        )

    def _render_outline(
        self,
        records: list[SharedBlockRecord],
        output_path: Path,
    ) -> str:
        """Render shared-block records into compact overview markdown."""

        indexed_records = list(enumerate(records, start=1))
        translated_count = sum(1 for _, record in indexed_records if record.is_translated)
        untranslated_count = len(indexed_records) - translated_count
        lines = [
            "# Shared Blocks Outline",
            "",
            (
                "Review shared translation progress here. Edit the actual shared"
                f" translations in `{SHARED_BLOCKS_DIRNAME}/`."
            ),
            "",
            f"- Total groups: `{len(records)}`",
            f"- Untranslated: `{untranslated_count}`",
            f"- Translated: `{translated_count}`",
            "",
        ]
        self._render_outline_section(lines, indexed_records, output_path=output_path)
        return "\n".join(lines).rstrip() + "\n"

    def _render_outline_section(
        self,
        lines: list[str],
        indexed_records: list[tuple[int, SharedBlockRecord]],
        output_path: Path,
    ) -> None:
        """Render the shared-block outline in stable group order."""

        for group_index, record in indexed_records:
            checkbox = "x" if record.is_translated else " "
            context_relative_path = os.path.relpath(
                output_path.parent
                / SHARED_BLOCKS_DIRNAME
                / record.stable_id
                / SHARED_BLOCK_CONTEXT_FILENAME,
                output_path.parent,
            )
            translation_destination = TranslationOutlineRenderer.format_link_destination(
                context_relative_path
            )
            source_preview = self._escape_markdown_link_text(self._preview_text(record.source_text))
            lines.append(f"- [{checkbox}] Group {group_index:04d}")
            lines.append("")
            lines.append(f"  [{source_preview}]({translation_destination})")
            lines.append("")

    def _write_group_files(
        self,
        shared_blocks_root: Path,
        records: list[SharedBlockRecord],
    ) -> set[Path]:
        """Write canonical per-group shared-block files.

        Args:
            shared_blocks_root: Canonical shared-block directory root.
            records: Shared-block records to persist.

        Returns:
            Set of generated file paths.
        """

        shared_blocks_root.mkdir(parents=True, exist_ok=True)
        reject_symlink_path(shared_blocks_root)
        expected_group_ids = {record.stable_id for record in records}
        self._prune_stale_group_paths(shared_blocks_root, expected_group_ids)

        written_paths: set[Path] = set()
        for group_index, record in enumerate(records, start=1):
            group_dir = shared_blocks_root / record.stable_id
            group_dir.mkdir(parents=True, exist_ok=True)
            reject_symlink_path(group_dir, shared_blocks_root)
            self._prune_stale_group_member_paths(group_dir)

            context_path = group_dir / SHARED_BLOCK_CONTEXT_FILENAME
            reject_symlink_path(context_path, shared_blocks_root)
            context_path.write_text(
                self._render_group_context(
                    group_index=group_index,
                    record=record,
                    shared_blocks_root=shared_blocks_root,
                ),
                encoding="utf-8",
            )
            written_paths.add(context_path)
        return written_paths

    def _render_group_context(
        self,
        group_index: int,
        record: SharedBlockRecord,
        shared_blocks_root: Path,
    ) -> str:
        """Render one generated shared-block context markdown file."""

        lines = [
            f"# Group {group_index:04d}",
            "",
            (
                f"> Edit only the `Translation ({self.target_lang})` block below. "
                "Other sections are generated."
            ),
            "",
            f"- Status: [{'x' if record.is_translated else ' '}]",
            f"- Stable ID: `{record.stable_id}`",
            (f"- Shared Key: `{SharedBlocksCatalogParser.serialize_group_key(record.group_key)}`"),
            "",
            f"### Source ({self.source_lang})",
            "",
            "~~~text",
            record.source_text,
            "~~~",
            "",
            f"### Translation ({self.target_lang})",
            "",
            "~~~text",
            record.translation_text,
            "~~~",
            "",
            "### Contexts",
            "",
        ]
        group_dir = shared_blocks_root / record.stable_id
        for context in record.contexts:
            link_label = self._escape_markdown_link_text(context.label)
            tree_root_relative_link = shared_blocks_root.parent / context.relative_link
            context_relative_link = os.path.relpath(tree_root_relative_link, group_dir)
            formatted_link = TranslationOutlineRenderer.format_link_destination(
                context_relative_link
            )
            lines.extend(
                [
                    f"- {context.badge} [{link_label}]({formatted_link})",
                    f"  Context: {context.context_label} [{context.reference.field}]",
                    "",
                ]
            )
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _prune_stale_group_paths(shared_blocks_root: Path, expected_group_ids: set[str]) -> None:
        """Remove stale generated group directories from the canonical root."""

        reject_symlink_path(shared_blocks_root)
        for child in shared_blocks_root.iterdir():
            reject_symlink_path(child, shared_blocks_root)
            if child.name in expected_group_ids:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    @staticmethod
    def _prune_stale_group_member_paths(group_dir: Path) -> None:
        """Remove unexpected generated files from one group directory."""

        reject_symlink_path(group_dir)
        expected_names = {
            SHARED_BLOCK_CONTEXT_FILENAME,
        }
        for child in group_dir.iterdir():
            reject_symlink_path(child, group_dir)
            if child.name in expected_names:
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

    @staticmethod
    def _preview_text(value: str, limit: int = 100) -> str:
        """Return a single-line preview for one shared source string."""

        compact = " ".join(value.split())
        if len(compact) <= limit:
            return compact
        return compact[: limit - 3].rstrip() + "..."

    @staticmethod
    def _build_children_index(
        manifest_nodes: dict[str, Any],
    ) -> dict[str, tuple[str, ...]]:
        """Build an ordered child index for manifest nodes.

        Args:
            manifest_nodes: Manifest node mapping keyed by UUID.

        Returns:
            Child UUIDs keyed by parent UUID.
        """

        path_to_uuid: dict[str, str] = {}
        children_by_uuid: dict[str, list[str]] = {}
        for entity_uuid, node in manifest_nodes.items():
            relative_path = str(node.get("path", ""))
            path_to_uuid[relative_path] = entity_uuid
            children_by_uuid.setdefault(entity_uuid, [])

        for entity_uuid, node in manifest_nodes.items():
            relative_path = str(node.get("path", ""))
            parent_path = str(Path(relative_path).parent)
            if parent_path == ".":
                continue
            parent_uuid = path_to_uuid.get(parent_path)
            if parent_uuid is None:
                continue
            children_by_uuid.setdefault(parent_uuid, []).append(entity_uuid)

        ordered_children: dict[str, tuple[str, ...]] = {}
        for entity_uuid, child_uuids in children_by_uuid.items():
            ordered_children[entity_uuid] = tuple(
                sorted(
                    child_uuids,
                    key=lambda child_uuid: str(manifest_nodes[child_uuid]["path"]),
                )
            )
        return ordered_children

    @classmethod
    def _build_context_label(
        cls,
        entity_uuid: str,
        relative_node_path: str,
        children_by_uuid: dict[str, tuple[str, ...]],
        manifest_nodes: dict[str, Any],
    ) -> str:
        """Build a compact parent/self/child summary for one context.

        Args:
            entity_uuid: Node UUID represented by the context.
            relative_node_path: Relative tree path for the node.
            children_by_uuid: Mapping from UUIDs to ordered child UUIDs.
            manifest_nodes: Manifest node mapping keyed by UUID.

        Returns:
            Compact context label that highlights the surrounding node chain.
        """

        current_path = Path(relative_node_path)
        labels: list[str] = []
        parent_path = str(current_path.parent)
        if parent_path != ".":
            labels.append(cls._display_label(parent_path))
        labels.append(cls._display_label(relative_node_path or entity_uuid))

        child_uuids = children_by_uuid.get(entity_uuid, ())
        if child_uuids:
            first_child_uuid = child_uuids[0]
            child_path = str(manifest_nodes[first_child_uuid]["path"])
            labels.append(cls._display_label(child_path))
        return " -> ".join(labels)

    @staticmethod
    def _display_label(relative_path: str) -> str:
        """Return a short display label for one tree path."""

        path_name = Path(relative_path).name
        without_order = SEGMENT_ORDER_RE.sub("", path_name)
        return SEGMENT_UUID_SUFFIX_RE.sub("", without_order)

    @staticmethod
    def _escape_markdown_link_text(value: str) -> str:
        """Escape markdown-sensitive link text characters."""

        return value.replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")

    def _write_shared_blocks_backup(
        self,
        tree_dir: str | Path,
        shared_blocks_root: Path,
        records: list[SharedBlockRecord],
    ) -> None:
        """Persist last-known-good backups of shared-block artifacts.

        Args:
            tree_dir: Translation tree root directory.
            shared_blocks_root: Canonical shared-block directory root.
            records: Shared-block records used to populate the backup tree.
        """

        backup_root = resolve_shared_blocks_backup_root(
            tree_repository=self.tree_repository,
            tree_dir=tree_dir,
        )
        backup_root.mkdir(parents=True, exist_ok=True)
        reject_symlink_path(backup_root)
        expected_group_ids = {record.stable_id for record in records}
        self._prune_stale_group_paths(backup_root, expected_group_ids)
        for group_index, record in enumerate(records, start=1):
            group_dir = backup_root / record.stable_id
            group_dir.mkdir(parents=True, exist_ok=True)
            reject_symlink_path(group_dir, backup_root)
            self._prune_stale_group_member_paths(group_dir)
            context_path = group_dir / SHARED_BLOCK_CONTEXT_FILENAME
            reject_symlink_path(context_path, backup_root)
            context_path.write_text(
                self._render_group_context(
                    group_index=group_index,
                    record=record,
                    shared_blocks_root=shared_blocks_root,
                ),
                encoding="utf-8",
            )
