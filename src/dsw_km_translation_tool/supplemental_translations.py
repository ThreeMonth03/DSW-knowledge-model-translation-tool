"""Translator-facing entries omitted from the upstream Localize catalog."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from .data_models import PoEntry
from .tree_support.document import TranslationMarkdownDocument

SUPPLEMENTAL_TRANSLATION_FIELDS = frozenset(
    {"advice", "description", "label", "name", "text", "title", "url"}
)


class SupplementalTranslationCatalog:
    """Load strict Markdown translation forms from a dedicated directory."""

    def __init__(self, source_lang: str, target_lang: str) -> None:
        self.document = TranslationMarkdownDocument(
            source_lang=source_lang,
            target_lang=target_lang,
        )

    def load(self, directory: str | Path) -> list[PoEntry]:
        """Load ``<uuid>/translation.md`` forms as PO-compatible entries.

        The supplemental catalog is intentionally separate from the generated
        Weblate tree. This keeps omitted upstream fields editable while making
        every Localize refresh safe and reproducible.
        """

        root = Path(directory)
        if not root.is_dir():
            raise ValueError(
                f"Supplemental translation directory does not exist: {root}"
            )

        entries: list[PoEntry] = []
        seen: set[tuple[str, str]] = set()
        for translation_path in sorted(root.glob("*/translation.md")):
            entity_uuid = translation_path.parent.name
            try:
                UUID(entity_uuid)
            except ValueError as error:
                raise ValueError(
                    f"Supplemental translation folder must be a UUID: {translation_path.parent}"
                ) from error

            fields = self.document.parse(str(translation_path))
            for field, state in fields.items():
                if field not in SUPPLEMENTAL_TRANSLATION_FIELDS:
                    allowed = ", ".join(sorted(SUPPLEMENTAL_TRANSLATION_FIELDS))
                    raise ValueError(
                        f"Unsupported supplemental translation field {field!r} in "
                        f"{translation_path}; allowed fields: {allowed}"
                    )
                key = (entity_uuid, field)
                if key in seen:
                    raise ValueError(
                        f"Duplicate supplemental translation entry: {entity_uuid}:{field}"
                    )
                seen.add(key)
                entries.append(
                    PoEntry(
                        prefix="supplemental",
                        uuid=entity_uuid,
                        field=field,
                        comment=f"supplemental/{entity_uuid}/{field}",
                        msgid=state.source_text,
                        msgstr=state.target_text,
                    )
                )

        if not entries:
            raise ValueError(f"No supplemental translation forms found in: {root}")
        return entries
