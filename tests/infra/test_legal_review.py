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
RESEARCH_PROJECTS_LIST_UUID = "c3dabaaf-c946-4a0d-889c-ede966f97667"
DELETED_BRANCH_ANSWER_UUID = "6dc3766a-79d7-4adc-b0e8-d72b73eb8d32"
MOVED_REFERENCE_UUID = "8fe4a165-09a6-4e5d-835d-3255db21d0de"


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
    assert result.question_addition_count == 1
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


def test_legal_mapping_accepts_moved_reference_override(
    workspace: Path,
    model_path: Path,
) -> None:
    payload = _valid_mapping_payload(model_path)
    payload["content_overrides"][0].update(
        {
            "source_uuid": MOVED_REFERENCE_UUID,
            "source_type": "reference",
            "source_fields": {
                "label": "EC Guidelines on DPIAs",
                "url": "https://ec.europa.eu/newsroom/article29/items/611236/en",
            },
            "proposed_fields": {
                "label": "Taiwan privacy guidance",
                "url": "https://law.moj.gov.tw/",
            },
        }
    )
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    result = validate_legal_mapping(
        mapping_path=mapping_path,
        km_path=model_path,
    )

    assert result.content_override_count == 1


def test_legal_mapping_rejects_content_below_deleted_ancestor(
    workspace: Path,
    model_path: Path,
) -> None:
    payload = _valid_mapping_payload(model_path)
    payload["content_overrides"][0].update(
        {
            "source_uuid": DELETED_BRANCH_ANSWER_UUID,
            "source_type": "answer",
            "source_fields": {
                "label": "Compliance with a legal obligation",
            },
            "proposed_fields": {
                "label": "Applicable statutory duty",
            },
        }
    )
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(LegalReviewError, match=r"ancestor .* is deleted"):
        validate_legal_mapping(
            mapping_path=mapping_path,
            km_path=model_path,
        )


def test_legal_mapping_rejects_addition_below_deleted_parent(
    workspace: Path,
    model_path: Path,
) -> None:
    payload = _valid_mapping_payload(model_path)
    payload["question_additions"][0]["parent_uuid"] = "e1ae38ed-14fb-4143-8a76-3883bd794b9b"
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(LegalReviewError, match="deleted"):
        validate_legal_mapping(
            mapping_path=mapping_path,
            km_path=model_path,
        )


@pytest.mark.parametrize(
    "parent_uuid",
    [
        "00000000-0000-0000-0000-000000000000",
        "b101f2d0-2476-452d-aa8d-95a41a02b52c",
        GDPR_CHOICE_UUID,
    ],
)
def test_legal_mapping_rejects_invalid_question_addition_parent(
    workspace: Path,
    model_path: Path,
    parent_uuid: str,
) -> None:
    payload = _valid_mapping_payload(model_path)
    payload["question_additions"][0]["parent_uuid"] = parent_uuid
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(LegalReviewError, match="not a valid question parent"):
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
    assert result.event_count == 5
    assert draft["id"] == result.package_id
    child = draft["packages"][-1]
    assert child["forkOfPackageId"] == result.parent_package_id
    assert child["previousPackageId"] == result.parent_package_id
    assert child["id"] == result.package_id
    assert len(child["events"]) == 5

    latest_by_uuid, model_info = KnowledgeModelService.load_model(str(first))
    question = latest_by_uuid[PERSONAL_DATA_QUESTION_UUID]["content"]
    assert model_info.id == result.package_id
    assert question["title"] == "Will you collect personal data?"
    assert question["text"] == "Apply the Taiwan statutory definition."
    assert latest_by_uuid[GDPR_CHOICE_UUID]["content"]["label"] == (
        "Taiwan Personal Data Protection Act"
    )
    route_question = next(
        entity
        for entity in latest_by_uuid.values()
        if entity["content"].get("title") == "Which Taiwan legal routes may apply?"
    )
    assert route_question["parentUuid"] == RESEARCH_PROJECTS_LIST_UUID
    assert route_question["content"]["questionType"] == "MultiChoiceQuestion"
    route_choices = {
        entity["content"]["label"]
        for entity in latest_by_uuid.values()
        if entity["parentUuid"] == route_question["entityUuid"]
    }
    assert route_choices == {"Human-subject research", "None or undetermined"}


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


def test_legal_draft_rejects_as_of_before_edited_entity_history(
    workspace: Path,
    model_path: Path,
) -> None:
    payload = _valid_mapping_payload(model_path)
    payload["as_of"] = "2021-01-01"
    mapping_path = workspace / "legal-mapping.yml"
    mapping_path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(LegalReviewError, match="as_of must be later than the source history"):
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
        "schema_version": 2,
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
        "question_additions": [
            {
                "addition_id": "tw-legal-routes",
                "parent_uuid": RESEARCH_PROJECTS_LIST_UUID,
                "topic": "legal-routing",
                "status": "proposed",
                "rationale": "Add a jurisdiction-specific applicability route.",
                "authorities": [
                    {
                        "source_id": "pdpa",
                        "provisions": ["Article 2"],
                    }
                ],
                "question_type": "MultiChoiceQuestion",
                "required_phase_uuid": "b101f2d0-2476-452d-aa8d-95a41a02b52c",
                "tag_uuids": [],
                "proposed": {
                    "title_en": "Which Taiwan legal routes may apply?",
                    "guidance_en": "Select every route that requires a documented review.",
                    "choices": [
                        {
                            "choice_id": "human-subject-research",
                            "label_en": "Human-subject research",
                        },
                        {
                            "choice_id": "none-or-undetermined",
                            "label_en": "None or undetermined",
                        },
                    ],
                },
            }
        ],
    }
