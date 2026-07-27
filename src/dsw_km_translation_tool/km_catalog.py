"""Build a deterministic gettext catalog directly from a DSW KM bundle."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constants import FIELD_EXPORT_ORDER
from .knowledge_model_service import KnowledgeModelService
from .po import PoCatalogParser
from .po_support.codec import PoStringCodec


@dataclass(frozen=True)
class KmCatalogBuildResult:
    """Summary of a generated source catalog."""

    output_path: Path
    entry_count: int
    carried_translation_count: int


def build_catalog_from_km(
    *,
    km_path: Path,
    output_path: Path,
    target_language: str,
    previous_po_path: Path | None = None,
) -> KmCatalogBuildResult:
    """Create a PO catalog for every current translatable KM field.

    Existing translations are carried only when the entity UUID, field name,
    and source text are unchanged. New or changed source strings remain empty.
    """

    latest_by_uuid, model_info = KnowledgeModelService.load_model(str(km_path))
    previous = _previous_translations(previous_po_path)
    entries: list[tuple[str, str, str]] = []
    carried_count = 0

    for entity_uuid, entity in sorted(latest_by_uuid.items()):
        content = entity.get("content", {})
        event_type = str(content.get("eventType") or "")
        if event_type.startswith("Delete"):
            continue
        prefix = _reference_prefix(content=content, event_type=event_type)
        for field in FIELD_EXPORT_ORDER:
            source_text = content.get(field)
            if not isinstance(source_text, str) or not source_text.strip():
                continue
            source_text = KnowledgeModelService.get_event_text_value(entity, field)
            if not isinstance(source_text, str) or not source_text:
                continue
            previous_entry = previous.get((entity_uuid, field))
            translation = ""
            if previous_entry and previous_entry[0] == source_text:
                translation = previous_entry[1]
                if translation:
                    carried_count += 1
            entries.append((f"{prefix}:{entity_uuid}:{field}", source_text, translation))

    catalog = _render_catalog(
        project_id=model_info.id or model_info.km_id or "knowledge-model",
        target_language=target_language,
        entries=entries,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(catalog, encoding="utf-8")
    return KmCatalogBuildResult(
        output_path=output_path,
        entry_count=len(entries),
        carried_translation_count=carried_count,
    )


def _previous_translations(
    previous_po_path: Path | None,
) -> dict[tuple[str, str], tuple[str, str]]:
    if previous_po_path is None:
        return {}
    if not previous_po_path.is_file():
        raise ValueError(f"Previous PO catalog does not exist: {previous_po_path}")
    return {
        (entry.uuid, entry.field): (entry.msgid, entry.msgstr)
        for entry in PoCatalogParser(str(previous_po_path)).parse_entries()
    }


def _reference_prefix(*, content: dict[str, Any], event_type: str) -> str:
    if event_type.endswith("ReferenceEvent"):
        reference_type = str(content.get("referenceType") or "")
        if reference_type == "CrossReference":
            return "cross-reference"
        if reference_type == "URLReference":
            return "url-reference"
        if reference_type == "ResourcePageReference":
            return "resource-page-reference"

    entity_type = re.sub(r"^(Add|Edit|Move|Delete)", "", event_type)
    entity_type = re.sub(r"Event$", "", entity_type) or "entity"
    return re.sub(r"(?<!^)(?=[A-Z])", "-", entity_type).lower()


def _render_catalog(
    *,
    project_id: str,
    target_language: str,
    entries: list[tuple[str, str, str]],
) -> str:
    header = (
        f"Project-Id-Version: {project_id}\\n"
        f"Language: {target_language}\\n"
        "MIME-Version: 1.0\\n"
        "Content-Type: text/plain; charset=utf-8\\n"
        "Content-Transfer-Encoding: 8bit\\n"
        "Generated-By: dsw-km-translation-tool\\n"
    )
    sections = [
        "# Generated from a DSW Knowledge Model. Edit translations, not msgids.\n"
        'msgid ""\n'
        f'msgstr "{PoStringCodec.escape(header)}"\n'
    ]
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for reference, msgid, msgstr in entries:
        grouped[(msgid, msgstr)].append(reference)

    for (msgid, msgstr), references in sorted(
        grouped.items(),
        key=lambda item: (item[0][0].casefold(), item[0][0], item[0][1]),
    ):
        sections.append(
            "\n"
            f"#: {' '.join(sorted(references))}\n"
            f'msgid "{PoStringCodec.escape(msgid)}"\n'
            f'msgstr "{PoStringCodec.escape(msgstr)}"\n'
        )
    return "".join(sections)
