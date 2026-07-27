"""Tests for Git-managed catalog generation from KM bundles."""

from __future__ import annotations

from pathlib import Path

from dsw_km_translation_tool.km_catalog import build_catalog_from_km
from dsw_km_translation_tool.po import PoCatalogParser


def test_catalog_from_km_is_deterministic_and_parseable(
    workspace: Path,
    model_path: Path,
) -> None:
    first = workspace / "first.po"
    second = workspace / "second.po"

    first_result = build_catalog_from_km(
        km_path=model_path,
        output_path=first,
        target_language="zh_Hant",
    )
    build_catalog_from_km(
        km_path=model_path,
        output_path=second,
        target_language="zh_Hant",
    )

    assert first_result.entry_count > 100
    assert first_result.carried_translation_count == 0
    assert first.read_bytes() == second.read_bytes()
    entries = PoCatalogParser(str(first)).parse_entries()
    assert len(entries) == first_result.entry_count
    assert all(entry.msgstr == "" for entry in entries)
    assert any(entry.prefix == "question" for entry in entries)
    assert any(entry.prefix == "answer" for entry in entries)


def test_catalog_carries_only_unchanged_source_translations(
    workspace: Path,
    model_path: Path,
) -> None:
    catalog = workspace / "catalog.po"
    build_catalog_from_km(
        km_path=model_path,
        output_path=catalog,
        target_language="zh_Hant",
    )
    text = catalog.read_text(encoding="utf-8")
    text = text.replace(
        'msgid "10 years"\nmsgstr ""',
        'msgid "10 years"\nmsgstr "10 年"',
        1,
    )
    catalog.write_text(text, encoding="utf-8")

    updated = workspace / "updated.po"
    result = build_catalog_from_km(
        km_path=model_path,
        output_path=updated,
        target_language="zh_Hant",
        previous_po_path=catalog,
    )

    assert result.carried_translation_count == 1
    translated = {
        (entry.uuid, entry.field): entry.msgstr
        for entry in PoCatalogParser(str(updated)).parse_entries()
        if entry.msgid == "10 years"
    }
    assert translated
    assert set(translated.values()) == {"10 年"}
