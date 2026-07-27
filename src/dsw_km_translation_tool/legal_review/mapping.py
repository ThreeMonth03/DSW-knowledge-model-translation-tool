"""Validate curated legal mappings against exact KM questions and sources."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from ..knowledge_model_service import KnowledgeModelService
from .common import LegalReviewError, load_yaml_mapping, sha256


@dataclass(frozen=True)
class LegalMappingValidationResult:
    """Summary of a successfully validated legal mapping."""

    package_id: str
    jurisdiction: str
    mapping_count: int
    content_override_count: int
    question_addition_count: int
    legal_source_count: int
    bundle_sha256: str


_LEGAL_SOURCE_KINDS = {
    "law",
    "regulation",
    "official_guidance",
    "funder_policy",
    "international_guidance",
}
_LEGAL_SOURCE_STATUSES = {
    "in_force",
    "promulgated_not_in_force",
    "guidance",
    "policy",
}
_MAPPING_ACTIONS = {"keep", "rewrite", "replace", "remove"}
_MAPPING_STATUSES = {
    "candidate",
    "proposed",
    "legally_reviewed",
    "implemented",
    "verified",
}
_REVIEW_STATUSES = {"drafting", "legal_review", "ready", "implemented"}
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_GITHUB_REPOSITORY_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GIT_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ADDITION_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_CONTENT_OVERRIDE_FIELDS = {
    "answer": frozenset({"advice", "label"}),
    "choice": frozenset({"label"}),
    "reference": frozenset({"label", "url"}),
    "resource_page": frozenset({"content", "title"}),
}
_ADDITION_QUESTION_TYPES = {"MultiChoiceQuestion", "ValueQuestion"}
_VALUE_QUESTION_TYPES = {
    "StringQuestionValueType",
    "NumberQuestionValueType",
    "DateQuestionValueType",
    "DateTimeQuestionValueType",
    "TimeQuestionValueType",
    "TextQuestionValueType",
    "EmailQuestionValueType",
    "UrlQuestionValueType",
    "ColorQuestionValueType",
}
_ROOT_UUID = "00000000-0000-0000-0000-000000000000"


def validate_legal_mapping(
    *,
    mapping_path: Path,
    km_path: Path,
) -> LegalMappingValidationResult:
    """Validate legal-review metadata and bind mappings to exact KM questions."""

    payload = load_yaml_mapping(mapping_path, "legal mapping")
    latest_by_uuid, model_info = KnowledgeModelService.load_model(str(km_path))
    actual_package_id = model_info.id or model_info.km_id or ""
    actual_sha256 = sha256(km_path)
    errors: list[str] = []

    if payload.get("schema_version") != 2:
        errors.append("schema_version must be 2")

    jurisdiction = _required_string(payload, "jurisdiction", errors, "legal mapping")
    _validated_date(payload.get("as_of"), "as_of", errors)
    review_status = _required_string(payload, "status", errors, "legal mapping")
    if review_status and review_status not in _REVIEW_STATUSES:
        errors.append(f"status must be one of: {', '.join(sorted(_REVIEW_STATUSES))}")

    source = _required_mapping(payload, "source", errors, "legal mapping")
    expected_package_id = _required_string(source, "package_id", errors, "source")
    expected_sha256 = _required_string(source, "bundle_sha256", errors, "source")
    source_repository = _required_string(source, "repository", errors, "source")
    source_ref = _required_string(source, "ref", errors, "source")
    source_bundle_path = _required_string(source, "bundle_path", errors, "source")
    if source_repository and not _GITHUB_REPOSITORY_PATTERN.fullmatch(source_repository):
        errors.append("source.repository must use GitHub owner/name form")
    if source_ref and not _GIT_COMMIT_PATTERN.fullmatch(source_ref):
        errors.append("source.ref must be a full lowercase Git commit SHA")
    if source_bundle_path and not _is_safe_relative_path(source_bundle_path):
        errors.append("source.bundle_path must be a safe relative path")
    if expected_package_id and expected_package_id != actual_package_id:
        errors.append(
            f"source.package_id is {expected_package_id!r}, "
            f"but the KM package is {actual_package_id!r}"
        )
    if expected_sha256:
        if not _SHA256_PATTERN.fullmatch(expected_sha256):
            errors.append("source.bundle_sha256 must be a lowercase SHA-256 digest")
        elif expected_sha256 != actual_sha256:
            errors.append(
                f"source.bundle_sha256 is {expected_sha256}, "
                f"but the KM bundle SHA-256 is {actual_sha256}"
            )

    legal_sources = _validate_legal_sources(payload.get("legal_sources"), errors)
    mappings = _validate_mappings(
        payload.get("mappings"),
        legal_source_ids=set(legal_sources),
        latest_by_uuid=latest_by_uuid,
        errors=errors,
    )
    content_overrides = _validate_content_overrides(
        payload.get("content_overrides", []),
        legal_source_ids=set(legal_sources),
        latest_by_uuid=latest_by_uuid,
        errors=errors,
    )
    question_additions = _validate_question_additions(
        payload.get("question_additions", []),
        legal_source_ids=set(legal_sources),
        latest_by_uuid=latest_by_uuid,
        errors=errors,
    )

    if errors:
        raise LegalReviewError("\n".join(f"- {error}" for error in errors))
    return LegalMappingValidationResult(
        package_id=actual_package_id,
        jurisdiction=jurisdiction,
        mapping_count=len(mappings),
        content_override_count=len(content_overrides),
        question_addition_count=len(question_additions),
        legal_source_count=len(legal_sources),
        bundle_sha256=actual_sha256,
    )


def _validate_legal_sources(
    raw_sources: Any,
    errors: list[str],
) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_sources, list) or not raw_sources:
        errors.append("legal_sources must be a non-empty list")
        return {}

    sources: dict[str, dict[str, Any]] = {}
    for index, source in enumerate(raw_sources):
        context = f"legal_sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{context} must be a mapping")
            continue
        source_id = _required_string(source, "id", errors, context)
        _required_string(source, "title", errors, context)
        _required_string(source, "authority", errors, context)
        kind = _required_string(source, "kind", errors, context)
        status = _required_string(source, "status", errors, context)
        url = _required_string(source, "official_url", errors, context)
        _validated_date(source.get("verified_on"), f"{context}.verified_on", errors)

        if kind and kind not in _LEGAL_SOURCE_KINDS:
            errors.append(
                f"{context}.kind must be one of: {', '.join(sorted(_LEGAL_SOURCE_KINDS))}"
            )
        if status and status not in _LEGAL_SOURCE_STATUSES:
            errors.append(
                f"{context}.status must be one of: {', '.join(sorted(_LEGAL_SOURCE_STATUSES))}"
            )
        if url and not _is_https_url(url):
            errors.append(f"{context}.official_url must be an HTTPS URL")
        if source_id:
            if source_id in sources:
                errors.append(f"duplicate legal source ID: {source_id}")
            else:
                sources[source_id] = source
    return sources


def _validate_mappings(
    raw_mappings: Any,
    *,
    legal_source_ids: set[str],
    latest_by_uuid: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_mappings, list) or not raw_mappings:
        errors.append("mappings must be a non-empty list")
        return []

    mappings: list[dict[str, Any]] = []
    seen_uuids: set[str] = set()
    for index, mapping in enumerate(raw_mappings):
        context = f"mappings[{index}]"
        if not isinstance(mapping, dict):
            errors.append(f"{context} must be a mapping")
            continue
        source_uuid = _required_string(mapping, "source_uuid", errors, context)
        source_title = _required_string(mapping, "source_title", errors, context)
        _required_string(mapping, "topic", errors, context)
        action = _required_string(mapping, "action", errors, context)
        status = _required_string(mapping, "status", errors, context)
        _required_string(mapping, "rationale", errors, context)

        if action and action not in _MAPPING_ACTIONS:
            errors.append(f"{context}.action must be one of: {', '.join(sorted(_MAPPING_ACTIONS))}")
        if status and status not in _MAPPING_STATUSES:
            errors.append(
                f"{context}.status must be one of: {', '.join(sorted(_MAPPING_STATUSES))}"
            )
        if source_uuid:
            if source_uuid in seen_uuids:
                errors.append(f"duplicate mapping source UUID: {source_uuid}")
            seen_uuids.add(source_uuid)
            _validate_question_binding(
                source_uuid=source_uuid,
                source_title=source_title,
                latest_by_uuid=latest_by_uuid,
                context=context,
                errors=errors,
            )

        _validate_authorities(
            mapping.get("authorities"),
            legal_source_ids=legal_source_ids,
            context=context,
            errors=errors,
        )
        if action in {"rewrite", "replace"}:
            proposed = _required_mapping(mapping, "proposed", errors, context)
            _required_string(proposed, "title_en", errors, f"{context}.proposed")
            _required_string(proposed, "guidance_en", errors, f"{context}.proposed")
        mappings.append(mapping)
    return mappings


def _validate_authorities(
    raw_authorities: Any,
    *,
    legal_source_ids: set[str],
    context: str,
    errors: list[str],
) -> None:
    if not isinstance(raw_authorities, list) or not raw_authorities:
        errors.append(f"{context}.authorities must be a non-empty list")
        return

    for index, authority in enumerate(raw_authorities):
        authority_context = f"{context}.authorities[{index}]"
        if not isinstance(authority, dict):
            errors.append(f"{authority_context} must be a mapping")
            continue
        source_id = _required_string(
            authority,
            "source_id",
            errors,
            authority_context,
        )
        if source_id and source_id not in legal_source_ids:
            errors.append(
                f"{authority_context}.source_id refers to unknown legal source {source_id!r}"
            )
        provisions = authority.get("provisions")
        if provisions is not None:
            _string_list(
                provisions,
                f"{authority_context}.provisions",
                errors,
            )


def _validate_content_overrides(
    raw_overrides: Any,
    *,
    legal_source_ids: set[str],
    latest_by_uuid: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_overrides, list):
        errors.append("content_overrides must be a list")
        return []

    overrides: list[dict[str, Any]] = []
    seen_uuids: set[str] = set()
    for index, override in enumerate(raw_overrides):
        context = f"content_overrides[{index}]"
        if not isinstance(override, dict):
            errors.append(f"{context} must be a mapping")
            continue

        source_uuid = _required_string(override, "source_uuid", errors, context)
        source_type = _required_string(override, "source_type", errors, context)
        _required_string(override, "topic", errors, context)
        status = _required_string(override, "status", errors, context)
        _required_string(override, "rationale", errors, context)
        if status and status not in _MAPPING_STATUSES:
            errors.append(
                f"{context}.status must be one of: {', '.join(sorted(_MAPPING_STATUSES))}"
            )

        allowed_fields = _CONTENT_OVERRIDE_FIELDS.get(source_type)
        if source_type and allowed_fields is None:
            errors.append(
                f"{context}.source_type must be one of: "
                f"{', '.join(sorted(_CONTENT_OVERRIDE_FIELDS))}"
            )
            allowed_fields = frozenset()

        source_fields = _required_mapping(override, "source_fields", errors, context)
        proposed_fields = _required_mapping(override, "proposed_fields", errors, context)
        _validate_override_fields(
            fields=source_fields,
            allowed_fields=allowed_fields,
            context=f"{context}.source_fields",
            errors=errors,
        )
        _validate_override_fields(
            fields=proposed_fields,
            allowed_fields=allowed_fields,
            context=f"{context}.proposed_fields",
            errors=errors,
        )
        if source_fields and proposed_fields and source_fields.keys() != proposed_fields.keys():
            errors.append(
                f"{context}.source_fields and proposed_fields must contain the same fields"
            )

        if source_uuid:
            if source_uuid in seen_uuids:
                errors.append(f"duplicate content override source UUID: {source_uuid}")
            seen_uuids.add(source_uuid)
            _validate_content_binding(
                source_uuid=source_uuid,
                source_type=source_type,
                source_fields=source_fields,
                latest_by_uuid=latest_by_uuid,
                context=context,
                errors=errors,
            )

        _validate_authorities(
            override.get("authorities"),
            legal_source_ids=legal_source_ids,
            context=context,
            errors=errors,
        )
        overrides.append(override)
    return overrides


def _validate_question_additions(
    raw_additions: Any,
    *,
    legal_source_ids: set[str],
    latest_by_uuid: dict[str, dict[str, Any]],
    errors: list[str],
) -> list[dict[str, Any]]:
    if not isinstance(raw_additions, list):
        errors.append("question_additions must be a list")
        return []

    additions: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, addition in enumerate(raw_additions):
        context = f"question_additions[{index}]"
        if not isinstance(addition, dict):
            errors.append(f"{context} must be a mapping")
            continue

        addition_id = _required_string(addition, "addition_id", errors, context)
        parent_uuid = _required_string(addition, "parent_uuid", errors, context)
        _required_string(addition, "topic", errors, context)
        status = _required_string(addition, "status", errors, context)
        _required_string(addition, "rationale", errors, context)
        question_type = _required_string(addition, "question_type", errors, context)

        if addition_id:
            if not _ADDITION_ID_PATTERN.fullmatch(addition_id):
                errors.append(
                    f"{context}.addition_id must contain lowercase letters, numbers, "
                    "and single hyphens"
                )
            if addition_id in seen_ids:
                errors.append(f"duplicate question addition ID: {addition_id}")
            seen_ids.add(addition_id)
        if status and status not in _MAPPING_STATUSES:
            errors.append(
                f"{context}.status must be one of: {', '.join(sorted(_MAPPING_STATUSES))}"
            )
        if question_type and question_type not in _ADDITION_QUESTION_TYPES:
            errors.append(
                f"{context}.question_type must be one of: "
                f"{', '.join(sorted(_ADDITION_QUESTION_TYPES))}"
            )

        if parent_uuid:
            _validate_active_entity(
                entity_uuid=parent_uuid,
                latest_by_uuid=latest_by_uuid,
                context=f"{context}.parent_uuid",
                errors=errors,
            )
        required_phase_uuid = addition.get("required_phase_uuid")
        if required_phase_uuid is not None:
            phase_uuid = _non_empty_string(
                required_phase_uuid,
                f"{context}.required_phase_uuid",
                errors,
            )
            if phase_uuid:
                _validate_referenced_entity_type(
                    entity_uuid=phase_uuid,
                    entity_name="phase",
                    event_suffix="PhaseEvent",
                    latest_by_uuid=latest_by_uuid,
                    context=f"{context}.required_phase_uuid",
                    errors=errors,
                )

        tag_uuids = _string_list(addition.get("tag_uuids", []), f"{context}.tag_uuids", errors)
        for tag_index, tag_uuid in enumerate(tag_uuids):
            _validate_referenced_entity_type(
                entity_uuid=tag_uuid,
                entity_name="tag",
                event_suffix="TagEvent",
                latest_by_uuid=latest_by_uuid,
                context=f"{context}.tag_uuids[{tag_index}]",
                errors=errors,
            )

        _validate_authorities(
            addition.get("authorities"),
            legal_source_ids=legal_source_ids,
            context=context,
            errors=errors,
        )
        proposed = _required_mapping(addition, "proposed", errors, context)
        _required_string(proposed, "title_en", errors, f"{context}.proposed")
        _required_string(proposed, "guidance_en", errors, f"{context}.proposed")
        if question_type == "MultiChoiceQuestion":
            _validate_addition_choices(proposed.get("choices"), context=context, errors=errors)
            if "value_type" in proposed:
                errors.append(f"{context}.proposed.value_type is not valid for MultiChoiceQuestion")
        elif question_type == "ValueQuestion":
            value_type = _required_string(
                proposed,
                "value_type",
                errors,
                f"{context}.proposed",
            )
            if value_type and value_type not in _VALUE_QUESTION_TYPES:
                errors.append(
                    f"{context}.proposed.value_type must be one of: "
                    f"{', '.join(sorted(_VALUE_QUESTION_TYPES))}"
                )
            if "choices" in proposed:
                errors.append(f"{context}.proposed.choices is not valid for ValueQuestion")

        additions.append(addition)
    return additions


def _validate_addition_choices(
    raw_choices: Any,
    *,
    context: str,
    errors: list[str],
) -> None:
    choices_context = f"{context}.proposed.choices"
    if not isinstance(raw_choices, list) or not raw_choices:
        errors.append(f"{choices_context} must be a non-empty list")
        return

    seen_ids: set[str] = set()
    for index, choice in enumerate(raw_choices):
        choice_context = f"{choices_context}[{index}]"
        if not isinstance(choice, dict):
            errors.append(f"{choice_context} must be a mapping")
            continue
        choice_id = _required_string(choice, "choice_id", errors, choice_context)
        _required_string(choice, "label_en", errors, choice_context)
        if choice_id:
            if not _ADDITION_ID_PATTERN.fullmatch(choice_id):
                errors.append(
                    f"{choice_context}.choice_id must contain lowercase letters, numbers, "
                    "and single hyphens"
                )
            if choice_id in seen_ids:
                errors.append(f"{choices_context} contains duplicate choice ID: {choice_id}")
            seen_ids.add(choice_id)


def _validate_override_fields(
    *,
    fields: dict[str, Any],
    allowed_fields: frozenset[str],
    context: str,
    errors: list[str],
) -> None:
    if not fields:
        errors.append(f"{context} must not be empty")
        return
    for field, value in fields.items():
        if field not in allowed_fields:
            errors.append(
                f"{context}.{field} is unsupported; allowed fields: "
                f"{', '.join(sorted(allowed_fields))}"
            )
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{context}.{field} must be a non-empty string")


def _validate_content_binding(
    *,
    source_uuid: str,
    source_type: str,
    source_fields: dict[str, Any],
    latest_by_uuid: dict[str, dict[str, Any]],
    context: str,
    errors: list[str],
) -> None:
    entity = latest_by_uuid.get(source_uuid)
    if entity is None:
        errors.append(f"{context}.source_uuid does not exist in the KM: {source_uuid}")
        return
    if not _validate_active_entity(
        entity_uuid=source_uuid,
        latest_by_uuid=latest_by_uuid,
        context=f"{context}.source_uuid",
        errors=errors,
    ):
        return
    content = entity.get("content", {})
    event_type = str(content.get("eventType") or "")
    actual_type = _content_entity_type(event_type)
    if actual_type != source_type:
        errors.append(
            f"{context}.source_type is {source_type!r}, but {source_uuid} is "
            f"{actual_type or 'an unsupported entity'} ({event_type or 'unknown event type'})"
        )
        return
    for field, expected in source_fields.items():
        actual = content.get(field)
        if actual != expected:
            errors.append(
                f"{context}.source_fields.{field} is stale for {source_uuid}: "
                f"expected {expected!r}, found {actual!r}"
            )


def _content_entity_type(event_type: str) -> str:
    if event_type == "MoveReferenceEvent":
        return "reference"
    match = re.fullmatch(r"(?:Add|Edit)(Answer|Choice|Reference|ResourcePage)Event", event_type)
    if match is None:
        return ""
    return {
        "Answer": "answer",
        "Choice": "choice",
        "Reference": "reference",
        "ResourcePage": "resource_page",
    }[match.group(1)]


def _validate_question_binding(
    *,
    source_uuid: str,
    source_title: str,
    latest_by_uuid: dict[str, dict[str, Any]],
    context: str,
    errors: list[str],
) -> None:
    entity = latest_by_uuid.get(source_uuid)
    if entity is None:
        errors.append(f"{context}.source_uuid does not exist in the KM: {source_uuid}")
        return
    content = entity.get("content", {})
    event_type = str(content.get("eventType") or "")
    if event_type.startswith("Delete") or not event_type.endswith("QuestionEvent"):
        errors.append(
            f"{context}.source_uuid is not an active question: "
            f"{source_uuid} ({event_type or 'unknown event type'})"
        )
        return
    if not _validate_active_entity(
        entity_uuid=source_uuid,
        latest_by_uuid=latest_by_uuid,
        context=f"{context}.source_uuid",
        errors=errors,
    ):
        return
    actual_title = _question_title(content)
    if _single_line(source_title) != _single_line(actual_title):
        errors.append(
            f"{context}.source_title is {_single_line(source_title)!r}, "
            f"but the KM title is {_single_line(actual_title)!r}"
        )


def _validate_referenced_entity_type(
    *,
    entity_uuid: str,
    entity_name: str,
    event_suffix: str,
    latest_by_uuid: dict[str, dict[str, Any]],
    context: str,
    errors: list[str],
) -> None:
    entity = latest_by_uuid.get(entity_uuid)
    if entity is None:
        errors.append(f"{context} does not exist in the KM: {entity_uuid}")
        return
    event_type = str(entity.get("content", {}).get("eventType") or "")
    if event_type.startswith("Delete") or not event_type.endswith(event_suffix):
        errors.append(
            f"{context} is not an active {entity_name}: "
            f"{entity_uuid} ({event_type or 'unknown event type'})"
        )
        return
    _validate_active_entity(
        entity_uuid=entity_uuid,
        latest_by_uuid=latest_by_uuid,
        context=context,
        errors=errors,
    )


def _validate_active_entity(
    *,
    entity_uuid: str,
    latest_by_uuid: dict[str, dict[str, Any]],
    context: str,
    errors: list[str],
) -> bool:
    """Reject deleted entities and entities hidden below deleted ancestors."""

    visited: set[str] = set()
    current_uuid = entity_uuid
    while current_uuid != _ROOT_UUID:
        if current_uuid in visited:
            errors.append(f"{context} has a cyclic ancestor path at {current_uuid}")
            return False
        visited.add(current_uuid)
        entity = latest_by_uuid.get(current_uuid)
        if entity is None:
            errors.append(f"{context} has a missing ancestor in the KM: {current_uuid}")
            return False
        event_type = str(entity.get("content", {}).get("eventType") or "")
        if event_type.startswith("Delete"):
            relationship = "entity" if current_uuid == entity_uuid else "ancestor"
            errors.append(
                f"{context} targets an unreachable entity; its {relationship} "
                f"{current_uuid} is deleted ({event_type})"
            )
            return False
        parent_uuid = entity.get("parentUuid")
        if not isinstance(parent_uuid, str) or not parent_uuid:
            errors.append(f"{context} has no valid parent UUID at {current_uuid}")
            return False
        current_uuid = parent_uuid
    return True


def _question_title(content: dict[str, Any]) -> str:
    title = content.get("title")
    if isinstance(title, str) and title.strip():
        return title
    return "<untitled question>"


def _required_mapping(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    context: str,
) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        errors.append(f"{context}.{key} must be a mapping")
        return {}
    return value


def _required_string(
    payload: dict[str, Any],
    key: str,
    errors: list[str],
    context: str,
) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{context}.{key} must be a non-empty string")
        return ""
    return value.strip()


def _non_empty_string(value: Any, context: str, errors: list[str]) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{context} must be a non-empty string")
        return ""
    candidate = value.strip()
    try:
        UUID(candidate)
    except ValueError:
        errors.append(f"{context} must be a UUID")
        return ""
    return candidate


def _string_list(value: Any, context: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{context} must be a list of non-empty strings")
        return []
    strings: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{context}[{index}] must be a non-empty string")
            continue
        strings.append(item.strip())
    return strings


def _validated_date(value: Any, context: str, errors: list[str]) -> str:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        try:
            return date.fromisoformat(value).isoformat()
        except ValueError:
            pass
    errors.append(f"{context} must be an ISO date (YYYY-MM-DD)")
    return ""


def _single_line(value: str) -> str:
    return " ".join(value.split())


def _is_https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _is_safe_relative_path(value: str) -> bool:
    path = Path(value)
    return not path.is_absolute() and ".." not in path.parts and value == path.as_posix()
