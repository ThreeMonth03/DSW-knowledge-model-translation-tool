"""Build deterministic keyword-based legal-question inventories."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..knowledge_model_service import KnowledgeModelService
from .common import LegalReviewError, load_yaml_mapping, sha256


@dataclass(frozen=True)
class LegalQuestionInventoryResult:
    """Summary of a generated legal-question candidate inventory."""

    output_path: Path
    package_id: str
    question_count: int
    bundle_sha256: str


def build_legal_question_inventory(
    *,
    km_path: Path,
    rules_path: Path,
    output_path: Path,
) -> LegalQuestionInventoryResult:
    """Create a deterministic inventory of questions matching review rules.

    The result is triage input only. A keyword match does not establish that a
    law applies or that a questionnaire change is required.
    """

    rules = _load_rules(rules_path)
    latest_by_uuid, model_info = KnowledgeModelService.load_model(str(km_path))
    bundle_sha256 = sha256(km_path)
    questions: list[dict[str, Any]] = []

    for entity_uuid, entity in sorted(latest_by_uuid.items()):
        content = entity.get("content", {})
        event_type = str(content.get("eventType") or "")
        if event_type.startswith("Delete") or not event_type.endswith("QuestionEvent"):
            continue

        matches = _match_topics(content=content, topics=rules)
        if not matches:
            continue
        questions.append(
            {
                "uuid": entity_uuid,
                "event_type": event_type,
                "title": _question_title(content),
                "path": _entity_path(
                    entity_uuid=entity_uuid,
                    latest_by_uuid=latest_by_uuid,
                    model_name=model_info.name,
                ),
                "matches": matches,
            }
        )

    package_id = model_info.id or model_info.km_id or ""
    payload = {
        "schema_version": 1,
        "notice": (
            "Keyword-generated triage inventory; inclusion does not establish "
            "legal applicability or replace professional review."
        ),
        "source": {
            "package_id": package_id,
            "bundle_sha256": bundle_sha256,
            "rules_sha256": sha256(rules_path),
        },
        "questions": questions,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=100),
        encoding="utf-8",
    )
    return LegalQuestionInventoryResult(
        output_path=output_path,
        package_id=package_id,
        question_count=len(questions),
        bundle_sha256=bundle_sha256,
    )


def _load_rules(path: Path) -> dict[str, dict[str, tuple[str, ...]]]:
    payload = load_yaml_mapping(path, "legal inventory rules")
    errors: list[str] = []
    if payload.get("schema_version") != 1:
        errors.append("schema_version must be 1")

    raw_topics = payload.get("topics")
    if not isinstance(raw_topics, dict) or not raw_topics:
        errors.append("topics must be a non-empty mapping")
        raw_topics = {}

    topics: dict[str, dict[str, tuple[str, ...]]] = {}
    for topic_id, raw_topic in raw_topics.items():
        context = f"topics.{topic_id}"
        if not isinstance(topic_id, str) or not topic_id.strip():
            errors.append("topic IDs must be non-empty strings")
            continue
        if not isinstance(raw_topic, dict):
            errors.append(f"{context} must be a mapping")
            continue
        fields = _string_list(raw_topic.get("fields"), f"{context}.fields", errors)
        terms = _string_list(raw_topic.get("terms"), f"{context}.terms", errors)
        if not fields:
            errors.append(f"{context}.fields must not be empty")
        if not terms:
            errors.append(f"{context}.terms must not be empty")
        topics[topic_id.strip()] = {
            "fields": tuple(fields),
            "terms": tuple(terms),
        }

    if errors:
        raise LegalReviewError("\n".join(f"- {error}" for error in errors))
    return topics


def _match_topics(
    *,
    content: dict[str, Any],
    topics: dict[str, dict[str, tuple[str, ...]]],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for topic_id, topic in topics.items():
        matched_fields: set[str] = set()
        matched_terms: set[str] = set()
        for field in topic["fields"]:
            raw_value = content.get(field)
            if not isinstance(raw_value, str):
                continue
            value = raw_value.casefold()
            for term in topic["terms"]:
                if term.casefold() in value:
                    matched_fields.add(field)
                    matched_terms.add(term)
        if matched_terms:
            matches.append(
                {
                    "topic": topic_id,
                    "fields": sorted(matched_fields),
                    "terms": sorted(matched_terms, key=str.casefold),
                }
            )
    return matches


def _entity_path(
    *,
    entity_uuid: str,
    latest_by_uuid: dict[str, dict[str, Any]],
    model_name: str | None,
) -> list[dict[str, str]]:
    lineage: list[tuple[str, dict[str, Any]]] = []
    visited: set[str] = set()
    current_uuid: str | None = entity_uuid
    while current_uuid and current_uuid not in visited:
        visited.add(current_uuid)
        entity = latest_by_uuid.get(current_uuid)
        if entity is None:
            break
        lineage.append((current_uuid, entity))
        parent_uuid = entity.get("parentUuid")
        current_uuid = parent_uuid if isinstance(parent_uuid, str) else None

    path: list[dict[str, str]] = []
    for current_uuid, entity in reversed(lineage):
        content = entity.get("content", {})
        event_type = str(content.get("eventType") or "")
        if event_type.endswith("KnowledgeModelEvent"):
            continue
        display_name, _ = KnowledgeModelService.resolve_node_display_name(
            current_uuid,
            latest_by_uuid,
            model_name=model_name,
        )
        path.append(
            {
                "uuid": current_uuid,
                "entity_type": _entity_type(event_type),
                "label": _single_line(display_name),
            }
        )
    return path


def _question_title(content: dict[str, Any]) -> str:
    title = content.get("title")
    if isinstance(title, str) and title.strip():
        return title
    return "<untitled question>"


def _entity_type(event_type: str) -> str:
    entity_type = re.sub(r"^(Add|Edit|Move|Delete)", "", event_type)
    return re.sub(r"Event$", "", entity_type) or "Entity"


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


def _single_line(value: str) -> str:
    return " ".join(value.split())
