"""Tests for traceable KM legal-review tooling."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from dsw_km_translation_tool.knowledge_model_service import KnowledgeModelService
from dsw_km_translation_tool.legal_review import (
    LegalReviewError,
    build_legal_draft,
    build_legal_question_inventory,
    validate_legal_mapping,
)

PERSONAL_DATA_QUESTION_UUID = "49c009cb-a38c-4836-9780-8a8b3dd1cbac"
PERSONAL_DATA_QUESTION_TITLE = 'Will you collect any data connected to a person, "personal data"?'
GDPR_CHOICE_UUID = "caac09f2-be5c-4ba4-82dc-7f0ee33ab67d"


def test_legal_inventory_is_deterministic_and_traceable(
    workspace: Path,
    model_path: Path,
) -> None:
    rules_path = workspace / "rules.yml"
    rules_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "topics": {
                    "personal-data": {
                        "fields": ["title", "text"],
                        "terms": ["personal data", "GDPR"],
                    },
                    "ethics": {
                        "fields": ["title", "text"],
                        "terms": ["ethical approval", "human subjects"],
                    },
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    first = workspace / "first.yml"
    second = workspace / "second.yml"

    result = build_legal_question_inventory(
        km_path=model_path,
        rules_path=rules_path,
        output_path=first,
    )
    build_legal_question_inventory(
        km_path=model_path,
        rules_path=rules_path,
        output_path=second,
    )

    assert first.read_bytes() == second.read_bytes()
    payload = yaml.safe_load(first.read_text(encoding="utf-8"))
    questions = payload["questions"]
    assert result.question_count == len(questions)
    assert payload["source"]["package_id"] == "dsw:root:2.7.0"
    assert [question["uuid"] for question in questions] == sorted(
        question["uuid"] for question in questions
    )
    personal_data = next(
        question for question in questions if question["uuid"] == PERSONAL_DATA_QUESTION_UUID
    )
    assert personal_data["title"] == PERSONAL_DATA_QUESTION_TITLE
    assert personal_data["path"][-1]["uuid"] == PERSONAL_DATA_QUESTION_UUID
    assert personal_data["matches"][0]["topic"] == "personal-data"


def test_legal_mapping_binds_sources_and_questions(
    workspace: Path,
    model_path: Path,
) -> None:
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(
            _valid_mapping_payload(model_path),
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = validate_legal_mapping(
        mapping_path=mapping_path,
        km_path=model_path,
    )

    assert result.package_id == "dsw:root:2.7.0"
    assert result.jurisdiction == "TW"
    assert result.mapping_count == 1
    assert result.content_override_count == 1
    assert result.legal_source_count == 1


def test_legal_mapping_rejects_stale_question_and_unknown_authority(
    workspace: Path,
    model_path: Path,
) -> None:
    payload = _valid_mapping_payload(model_path)
    payload["mappings"][0]["source_title"] = "Stale upstream title"
    payload["mappings"][0]["authorities"][0]["source_id"] = "missing-law"
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(LegalReviewError) as error:
        validate_legal_mapping(
            mapping_path=mapping_path,
            km_path=model_path,
        )

    message = str(error.value)
    assert "but the KM title is" in message
    assert "unknown legal source 'missing-law'" in message


def test_legal_mapping_rejects_wrong_bundle_checksum(
    workspace: Path,
    model_path: Path,
) -> None:
    payload = _valid_mapping_payload(model_path)
    payload["source"]["bundle_sha256"] = "0" * 64
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(LegalReviewError, match="KM bundle SHA-256"):
        validate_legal_mapping(
            mapping_path=mapping_path,
            km_path=model_path,
        )


def test_legal_mapping_rejects_stale_content_override(
    workspace: Path,
    model_path: Path,
) -> None:
    payload = _valid_mapping_payload(model_path)
    payload["content_overrides"][0]["source_fields"]["label"] = "Stale label"
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(LegalReviewError, match="source_fields.label is stale"):
        validate_legal_mapping(
            mapping_path=mapping_path,
            km_path=model_path,
        )


def test_legal_draft_appends_valid_deterministic_child_package(
    workspace: Path,
    model_path: Path,
) -> None:
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(_valid_mapping_payload(model_path), sort_keys=False),
        encoding="utf-8",
    )
    first = workspace / "first.km"
    second = workspace / "second.km"
    options = {
        "km_path": model_path,
        "mapping_path": mapping_path,
        "organization_id": "tw",
        "km_id": "root-tw",
        "version": "0.1.0",
        "name": "Taiwan DSW Knowledge Model",
        "description": "Taiwan legal meeting draft.",
        "license_id": "Apache-2.0",
        "readme": "# Taiwan DSW Knowledge Model\n",
    }

    result = build_legal_draft(output_path=first, **options)
    build_legal_draft(output_path=second, **options)

    assert first.read_bytes() == second.read_bytes()
    source = json.loads(model_path.read_text(encoding="utf-8"))
    draft = json.loads(first.read_text(encoding="utf-8"))
    assert draft["packages"][:-1] == source["packages"]
    assert result.package_id == "tw:root-tw:0.1.0"
    assert result.parent_package_id == "dsw:root:2.7.0"
    assert result.event_count == 2
    assert draft["id"] == result.package_id
    child = draft["packages"][-1]
    assert child["forkOfPackageId"] == result.parent_package_id
    assert child["previousPackageId"] is None
    assert child["id"] == result.package_id
    assert len(child["events"]) == 2

    latest_by_uuid, model_info = KnowledgeModelService.load_model(str(first))
    question = latest_by_uuid[PERSONAL_DATA_QUESTION_UUID]["content"]
    assert model_info.id == result.package_id
    assert question["title"] == "Will you collect personal data?"
    assert question["text"] == "Apply the Taiwan statutory definition."
    assert latest_by_uuid[GDPR_CHOICE_UUID]["content"]["label"] == (
        "Taiwan Personal Data Protection Act"
    )


def test_legal_draft_rejects_structural_mapping_actions(
    workspace: Path,
    model_path: Path,
) -> None:
    payload = _valid_mapping_payload(model_path)
    payload["mappings"][0]["action"] = "remove"
    payload["mappings"][0].pop("proposed")
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(LegalReviewError, match="legal drafts support only"):
        build_legal_draft(
            km_path=model_path,
            mapping_path=mapping_path,
            output_path=workspace / "draft.km",
            organization_id="tw",
            km_id="root-tw",
            version="0.1.0",
            name="Taiwan DSW Knowledge Model",
            description="Taiwan legal meeting draft.",
            license_id="Apache-2.0",
            readme="# Taiwan DSW Knowledge Model\n",
        )


def _valid_mapping_payload(model_path: Path) -> dict[str, object]:
    _, model_info = KnowledgeModelService.load_model(str(model_path))
    return {
        "schema_version": 1,
        "jurisdiction": "TW",
        "as_of": "2026-07-27",
        "status": "drafting",
        "source": {
            "package_id": model_info.id,
            "bundle_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
            "repository": "example/source-km",
            "ref": "1" * 40,
            "bundle_path": "sources/dsw-root.km",
        },
        "legal_sources": [
            {
                "id": "pdpa",
                "title": "Personal Data Protection Act",
                "authority": "Ministry of Justice",
                "kind": "law",
                "status": "in_force",
                "official_url": ("https://law.moj.gov.tw/ENG/LawClass/LawAll.aspx?pcode=I0050021"),
                "verified_on": "2026-07-27",
            }
        ],
        "mappings": [
            {
                "source_uuid": PERSONAL_DATA_QUESTION_UUID,
                "source_title": PERSONAL_DATA_QUESTION_TITLE,
                "topic": "personal-data",
                "action": "rewrite",
                "status": "proposed",
                "rationale": "Replace jurisdiction-specific legal terminology.",
                "authorities": [
                    {
                        "source_id": "pdpa",
                        "provisions": ["Article 2"],
                    }
                ],
                "proposed": {
                    "title_en": "Will you collect personal data?",
                    "guidance_en": "Apply the Taiwan statutory definition.",
                },
            }
        ],
        "content_overrides": [
            {
                "source_uuid": GDPR_CHOICE_UUID,
                "source_type": "choice",
                "topic": "personal-data",
                "status": "proposed",
                "rationale": "Replace an inherited GDPR choice label.",
                "authorities": [
                    {
                        "source_id": "pdpa",
                        "provisions": ["Article 2"],
                    }
                ],
                "source_fields": {
                    "label": "GDPR",
                },
                "proposed_fields": {
                    "label": "Taiwan Personal Data Protection Act",
                },
            }
        ],
    }
