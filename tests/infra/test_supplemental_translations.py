"""Tests for translator-maintained KM fields omitted by Localize."""

from __future__ import annotations

PHASE_UUID = "b101f2d0-2476-452d-aa8d-95a41a02b52c"


def write_form(directory, source: str, translation: str, field: str = "title") -> None:
    """Write one strict supplemental phase translation form."""

    form_dir = directory / PHASE_UUID
    form_dir.mkdir(parents=True)
    (form_dir / "translation.md").write_text(
        f"""# Translation

- UUID: `{PHASE_UUID}`
- Event Type: `AddPhaseEvent`
- Edit only the `Translation (zh_Hant)` blocks below.

## {field}

### Source (en)

~~~text
{source}
~~~

### Translation (zh_Hant)

~~~text
{translation}
~~~
""",
        encoding="utf-8",
    )


def test_build_km_applies_supplemental_markdown_translation(
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify omitted phase titles are validated and written to the KM."""

    supplemental_dir = workspace / "supplemental"
    output_km = workspace / "translated.km"
    write_form(
        supplemental_dir,
        source="Before Submitting the Proposal",
        translation="提交計畫申請書前",
    )

    result = workflow.build_km_from_po(
        translated_po_path=str(po_path),
        original_model_path=str(model_path),
        out_model_path=str(output_km),
        supplemental_translations_dir=str(supplemental_dir),
    )

    latest_by_uuid, _ = workflow.model_service.load_model(str(output_km))
    assert result.translations[(PHASE_UUID, "title")] == "提交計畫申請書前"
    assert (
        workflow.model_service.get_event_text_value(latest_by_uuid[PHASE_UUID], "title")
        == "提交計畫申請書前"
    )


def test_build_km_rejects_stale_supplemental_source(
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify upstream KM changes cannot silently invalidate a form."""

    supplemental_dir = workspace / "supplemental"
    write_form(
        supplemental_dir,
        source="Outdated source",
        translation="提交計畫申請書前",
    )

    try:
        workflow.build_km_from_po(
            translated_po_path=str(po_path),
            original_model_path=str(model_path),
            out_model_path=str(workspace / "translated.km"),
            supplemental_translations_dir=str(supplemental_dir),
        )
    except ValueError as error:
        assert "Supplemental translation validation against KM failed" in str(error)
        assert "Source mismatch" in str(error)
    else:
        raise AssertionError("Expected stale supplemental source validation to fail")


def test_build_km_rejects_structural_supplemental_field(
    workflow,
    po_path,
    model_path,
    workspace,
) -> None:
    """Verify supplemental forms cannot rewrite KM relationship fields."""

    supplemental_dir = workspace / "supplemental"
    write_form(
        supplemental_dir,
        source="b101f2d0-2476-452d-aa8d-95a41a02b52c",
        translation="adc9133d-afcd-4616-9aea-db5f475898a2",
        field="requiredPhaseUuid",
    )

    try:
        workflow.build_km_from_po(
            translated_po_path=str(po_path),
            original_model_path=str(model_path),
            out_model_path=str(workspace / "translated.km"),
            supplemental_translations_dir=str(supplemental_dir),
        )
    except ValueError as error:
        assert "Unsupported supplemental translation field 'requiredPhaseUuid'" in str(error)
    else:
        raise AssertionError("Expected structural supplemental field validation to fail")
