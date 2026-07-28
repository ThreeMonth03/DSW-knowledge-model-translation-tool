"""Build deterministic jurisdiction-specific KM draft packages."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ..dsw_models_adapter import DswModelsBundleAdapter
from ..knowledge_model_service import KnowledgeModelService
from .common import LegalReviewError, load_yaml_mapping
from .mapping import validate_legal_mapping

_SEMANTIC_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_SUPPORTED_ACTIONS = {"rewrite", "replace"}
_QUESTION_CHILD_FIELDS = {
    "FileQuestion": ("maxSize", "fileTypes"),
    "IntegrationQuestion": ("integrationUuid", "variables"),
    "ItemSelectQuestion": ("listQuestionUuid",),
    "ListQuestion": ("itemTemplateQuestionUuids",),
    "MultiChoiceQuestion": ("choiceUuids",),
    "OptionsQuestion": ("answerUuids",),
    "ValueQuestion": ("valueType", "validations"),
}


@dataclass(frozen=True)
class LegalDraftBuildResult:
    """Summary of a generated jurisdiction-specific KM draft."""

    output_path: Path
    package_id: str
    parent_package_id: str
    event_count: int


def build_legal_draft(
    *,
    km_path: Path,
    mapping_path: Path,
    output_path: Path,
    organization_id: str,
    km_id: str,
    version: str,
    name: str,
    description: str,
    license_id: str,
    readme: str,
) -> LegalDraftBuildResult:
    """Append one deterministic child package from a curated legal mapping.

    The input package history is preserved byte-for-byte at the JSON object
    level. Each ``rewrite`` or ``replace`` mapping becomes one question edit
    event that changes only the question title and guidance text. Optional
    ``content_overrides`` add exact, source-bound edits for inherited answer,
    choice, URL-reference, or resource-page text. ``question_additions`` add
    deterministic questions and choices whose entity UUIDs remain stable
    across package versions.
    """

    validate_legal_mapping(mapping_path=mapping_path, km_path=km_path)
    mapping = load_yaml_mapping(mapping_path, "legal mapping")
    source_root = _load_bundle(km_path)
    latest_by_uuid, _ = KnowledgeModelService.load_model(str(km_path))
    parent_package_id = _required_bundle_string(source_root, "id")
    metamodel_version = source_root.get("metamodelVersion")
    if not isinstance(metamodel_version, int):
        raise LegalReviewError("KM bundle metamodelVersion must be an integer")

    _validate_package_metadata(
        organization_id=organization_id,
        km_id=km_id,
        version=version,
        name=name,
        description=description,
        license_id=license_id,
        readme=readme,
    )
    package_id = f"{organization_id}:{km_id}:{version}"
    packages = source_root.get("packages")
    if not isinstance(packages, list):
        raise LegalReviewError("KM bundle packages must be a list")
    if any(isinstance(package, dict) and package.get("id") == package_id for package in packages):
        raise LegalReviewError(f"KM bundle already contains package {package_id}")

    as_of = _mapping_date(mapping.get("as_of"))
    question_events = _build_question_events(
        mapping=mapping,
        latest_by_uuid=latest_by_uuid,
        package_id=package_id,
        as_of=as_of,
    )
    content_override_events = _build_content_override_events(
        mapping=mapping,
        latest_by_uuid=latest_by_uuid,
        package_id=package_id,
        as_of=as_of,
    )
    question_addition_events = _build_question_addition_events(
        mapping=mapping,
        latest_by_uuid=latest_by_uuid,
        package_id=package_id,
        as_of=as_of,
    )
    events = question_events + content_override_events + question_addition_events
    child_package = {
        "createdAt": _format_timestamp(as_of),
        "description": description,
        "events": events,
        "forkOfPackageId": parent_package_id,
        "id": package_id,
        "kmId": km_id,
        "license": license_id,
        "mergeCheckpointPackageId": None,
        "metamodelVersion": metamodel_version,
        "name": name,
        "nonEditable": False,
        "organizationId": organization_id,
        "phase": "ReleasedKnowledgeModelPackagePhase",
        "previousPackageId": parent_package_id,
        "readme": readme,
        "version": version,
    }

    output_root = copy.deepcopy(source_root)
    output_root.update(
        {
            "id": package_id,
            "kmId": km_id,
            "name": name,
            "organizationId": organization_id,
            "version": version,
        }
    )
    output_root["packages"].append(child_package)
    DswModelsBundleAdapter.validate_bundle_root(output_root)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output_root, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return LegalDraftBuildResult(
        output_path=output_path,
        package_id=package_id,
        parent_package_id=parent_package_id,
        event_count=len(events),
    )


def _load_bundle(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise LegalReviewError(f"Unable to read KM bundle {path}: {error}") from error
    if not isinstance(payload, dict):
        raise LegalReviewError("KM bundle must be a JSON object")
    return payload


def _build_question_events(
    *,
    mapping: dict[str, Any],
    latest_by_uuid: dict[str, dict[str, Any]],
    package_id: str,
    as_of: date,
) -> list[dict[str, Any]]:
    raw_mappings = mapping.get("mappings")
    if not isinstance(raw_mappings, list):
        raise LegalReviewError("legal mapping mappings must be a list")

    events: list[dict[str, Any]] = []
    for item in sorted(raw_mappings, key=lambda candidate: str(candidate.get("source_uuid", ""))):
        action = item.get("action")
        if action not in _SUPPORTED_ACTIONS:
            raise LegalReviewError(
                f"Cannot build action {action!r}; legal drafts support only "
                f"{', '.join(sorted(_SUPPORTED_ACTIONS))}"
            )

        entity_uuid = str(item["source_uuid"])
        entity = latest_by_uuid[entity_uuid]
        content = entity["content"]
        question_type = str(content.get("questionType") or "")
        proposed = item["proposed"]
        event_content = _edit_question_content(
            question_type=question_type,
            title=str(proposed["title_en"]),
            guidance=str(proposed["guidance_en"]),
        )
        event_name = "\n".join(
            (
                package_id,
                entity_uuid,
                str(proposed["title_en"]),
                str(proposed["guidance_en"]),
            )
        )
        events.append(
            {
                "content": event_content,
                "createdAt": _format_timestamp(as_of),
                "entityUuid": entity_uuid,
                "parentUuid": str(entity["parentUuid"]),
                "uuid": str(uuid5(NAMESPACE_URL, event_name)),
            }
        )
    return events


def _build_content_override_events(
    *,
    mapping: dict[str, Any],
    latest_by_uuid: dict[str, dict[str, Any]],
    package_id: str,
    as_of: date,
) -> list[dict[str, Any]]:
    raw_overrides = mapping.get("content_overrides", [])
    if not isinstance(raw_overrides, list):
        raise LegalReviewError("legal mapping content_overrides must be a list")

    events: list[dict[str, Any]] = []
    for item in sorted(raw_overrides, key=lambda candidate: str(candidate.get("source_uuid", ""))):
        entity_uuid = str(item["source_uuid"])
        entity = latest_by_uuid[entity_uuid]
        source_type = str(item["source_type"])
        proposed_fields = {
            str(field): str(value) for field, value in item["proposed_fields"].items()
        }
        event_content = _edit_content_override(
            source_type=source_type,
            source_content=entity["content"],
            proposed_fields=proposed_fields,
        )
        event_name = "\n".join(
            (
                package_id,
                entity_uuid,
                json.dumps(proposed_fields, ensure_ascii=False, sort_keys=True),
            )
        )
        events.append(
            {
                "content": event_content,
                "createdAt": _format_timestamp(as_of),
                "entityUuid": entity_uuid,
                "parentUuid": str(entity["parentUuid"]),
                "uuid": str(uuid5(NAMESPACE_URL, event_name)),
            }
        )
    return events


def _build_question_addition_events(
    *,
    mapping: dict[str, Any],
    latest_by_uuid: dict[str, dict[str, Any]],
    package_id: str,
    as_of: date,
) -> list[dict[str, Any]]:
    raw_additions = mapping.get("question_additions", [])
    if not isinstance(raw_additions, list):
        raise LegalReviewError("legal mapping question_additions must be a list")

    jurisdiction = str(mapping["jurisdiction"])
    generated_entity_uuids: set[str] = set()
    events: list[dict[str, Any]] = []
    for item in raw_additions:
        addition_id = str(item["addition_id"])
        question_uuid = _addition_entity_uuid(
            jurisdiction=jurisdiction,
            entity_kind="question",
            stable_id=addition_id,
        )
        _claim_addition_entity_uuid(
            entity_uuid=question_uuid,
            generated_entity_uuids=generated_entity_uuids,
            latest_by_uuid=latest_by_uuid,
        )

        question_type = str(item["question_type"])
        proposed = item["proposed"]
        question_content: dict[str, Any] = {
            "annotations": [],
            "eventType": "AddQuestionEvent",
            "questionType": question_type,
            "requiredPhaseUuid": item.get("required_phase_uuid"),
            "tagUuids": list(item.get("tag_uuids", [])),
            "text": str(proposed["guidance_en"]),
            "title": str(proposed["title_en"]),
        }
        if question_type == "ValueQuestion":
            question_content.update(
                {
                    "validations": [],
                    "valueType": str(proposed["value_type"]),
                }
            )
        events.append(
            _addition_event(
                package_id=package_id,
                entity_uuid=question_uuid,
                parent_uuid=str(item["parent_uuid"]),
                content=question_content,
                as_of=as_of,
            )
        )

        if question_type != "MultiChoiceQuestion":
            continue
        for choice in proposed["choices"]:
            choice_uuid = _addition_entity_uuid(
                jurisdiction=jurisdiction,
                entity_kind="choice",
                stable_id=f"{addition_id}/{choice['choice_id']}",
            )
            _claim_addition_entity_uuid(
                entity_uuid=choice_uuid,
                generated_entity_uuids=generated_entity_uuids,
                latest_by_uuid=latest_by_uuid,
            )
            events.append(
                _addition_event(
                    package_id=package_id,
                    entity_uuid=choice_uuid,
                    parent_uuid=question_uuid,
                    content={
                        "annotations": [],
                        "eventType": "AddChoiceEvent",
                        "label": str(choice["label_en"]),
                    },
                    as_of=as_of,
                )
            )
    return events


def _addition_entity_uuid(
    *,
    jurisdiction: str,
    entity_kind: str,
    stable_id: str,
) -> str:
    identity = f"dsw-legal-addition/{jurisdiction}/{entity_kind}/{stable_id}"
    return str(uuid5(NAMESPACE_URL, identity))


def _claim_addition_entity_uuid(
    *,
    entity_uuid: str,
    generated_entity_uuids: set[str],
    latest_by_uuid: dict[str, dict[str, Any]],
) -> None:
    if entity_uuid in latest_by_uuid:
        raise LegalReviewError(
            f"Generated question addition entity UUID already exists in the KM: {entity_uuid}"
        )
    if entity_uuid in generated_entity_uuids:
        raise LegalReviewError(f"Duplicate generated question addition entity UUID: {entity_uuid}")
    generated_entity_uuids.add(entity_uuid)


def _addition_event(
    *,
    package_id: str,
    entity_uuid: str,
    parent_uuid: str,
    content: dict[str, Any],
    as_of: date,
) -> dict[str, Any]:
    event_identity = "\n".join(
        (
            package_id,
            entity_uuid,
            parent_uuid,
            json.dumps(content, ensure_ascii=False, sort_keys=True),
        )
    )
    return {
        "content": content,
        "createdAt": _format_timestamp(as_of),
        "entityUuid": entity_uuid,
        "parentUuid": parent_uuid,
        "uuid": str(uuid5(NAMESPACE_URL, event_identity)),
    }


def _edit_question_content(
    *,
    question_type: str,
    title: str,
    guidance: str,
) -> dict[str, Any]:
    child_fields = _QUESTION_CHILD_FIELDS.get(question_type)
    if child_fields is None:
        raise LegalReviewError(f"Unsupported DSW question type: {question_type!r}")

    content: dict[str, Any] = {
        "annotations": {"changed": False},
        "eventType": "EditQuestionEvent",
        "expertUuids": {"changed": False},
        "questionType": question_type,
        "referenceUuids": {"changed": False},
        "requiredPhaseUuid": {"changed": False},
        "tagUuids": {"changed": False},
        "text": {"changed": True, "value": guidance},
        "title": {"changed": True, "value": title},
    }
    for field in child_fields:
        content[field] = {"changed": False}
    return content


def _edit_content_override(
    *,
    source_type: str,
    source_content: dict[str, Any],
    proposed_fields: dict[str, str],
) -> dict[str, Any]:
    if source_type == "answer":
        fields = ("advice", "label")
        content = {
            "annotations": {"changed": False},
            "eventType": "EditAnswerEvent",
            "followUpUuids": {"changed": False},
            "metricMeasures": {"changed": False},
        }
    elif source_type == "choice":
        fields = ("label",)
        content = {
            "annotations": {"changed": False},
            "eventType": "EditChoiceEvent",
        }
    elif source_type == "reference":
        if source_content.get("referenceType") != "URLReference":
            raise LegalReviewError("Legal content overrides currently support only URL references")
        fields = ("label", "url")
        content = {
            "annotations": {"changed": False},
            "eventType": "EditReferenceEvent",
            "referenceType": "URLReference",
        }
    elif source_type == "resource_page":
        fields = ("content", "title")
        content = {
            "annotations": {"changed": False},
            "eventType": "EditResourcePageEvent",
        }
    else:
        raise LegalReviewError(f"Unsupported legal content override type: {source_type!r}")

    for field in fields:
        if field in proposed_fields:
            content[field] = {"changed": True, "value": proposed_fields[field]}
        else:
            content[field] = {"changed": False}
    return content


def _validate_package_metadata(
    *,
    organization_id: str,
    km_id: str,
    version: str,
    name: str,
    description: str,
    license_id: str,
    readme: str,
) -> None:
    errors: list[str] = []
    for label, value in (
        ("organization ID", organization_id),
        ("KM ID", km_id),
    ):
        if not value or not _IDENTIFIER.fullmatch(value):
            errors.append(f"{label} must match {_IDENTIFIER.pattern}")
    if not _SEMANTIC_VERSION.fullmatch(version):
        errors.append("version must use major.minor.patch numeric form")
    for label, value in (
        ("name", name),
        ("description", description),
        ("license", license_id),
        ("readme", readme),
    ):
        if not value.strip():
            errors.append(f"{label} must not be empty")
    if errors:
        raise LegalReviewError("\n".join(f"- {error}" for error in errors))


def _required_bundle_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise LegalReviewError(f"KM bundle {key} must be a non-empty string")
    return value


def _mapping_date(value: Any) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise LegalReviewError("legal mapping as_of must be an ISO date")


def _format_timestamp(value: date) -> str:
    timestamp = datetime(
        value.year,
        value.month,
        value.day,
        tzinfo=timezone.utc,
    )
    return timestamp.isoformat(timespec="seconds").replace("+00:00", "Z")
