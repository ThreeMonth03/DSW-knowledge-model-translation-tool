"""Regression tests for the typed `dsw-models` KM adapter."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from dsw_km_translation_tool.dsw_models_adapter import (
    DswModelsBundleAdapter,
    TypedKnowledgeModelEvent,
)
from dsw_km_translation_tool.knowledge_model_service import KnowledgeModelService
from dsw_km_translation_tool.knowledge_model_support import KnowledgeModelEventMerger

MOVED_QUESTION_UUID = "ab4b3f39-dfab-45a5-9489-2d46ceacbb73"
MOVED_QUESTION_OLD_PARENT_UUID = "c4eda690-066f-495a-8c29-8e8a258ac487"
MOVED_QUESTION_NEW_PARENT_UUID = "b1df3c74-0b1f-4574-81c4-4cc2d780c1af"
MOVED_ENTITY_PARENT_EXPECTATIONS = {
    MOVED_QUESTION_UUID: MOVED_QUESTION_NEW_PARENT_UUID,
    "bb71dd81-e53a-4ee3-ab8e-bdd687329b91": "8c962e6f-17ee-4b22-8ebb-9f06f779e3b3",
    "a2b1fa38-792a-4628-9765-93476a38cffb": "761d20f2-d2ce-496b-8a91-a52ff0513e7b",
}
SAME_TIMESTAMP_ENTITY_UUID = "426bdcb5-d012-4f1d-b99e-36dc3efe6e50"
SAME_TIMESTAMP_PARENT_UUID = "70cc627a-4a9f-4d3e-8fdb-7a09b6684bec"


def assert_parent_uuid(
    latest_by_uuid: dict[str, dict[str, object]],
    entity_uuid: str,
    expected_parent_uuid: str,
) -> None:
    """Assert that one loaded entity has the expected final parent UUID.

    Args:
        latest_by_uuid: Loaded latest-entity mapping.
        entity_uuid: Entity UUID under verification.
        expected_parent_uuid: Expected final parent UUID.
    """

    assert latest_by_uuid[entity_uuid]["parentUuid"] == expected_parent_uuid


def test_model_loader_uses_move_event_target_uuid_for_moved_entities(
    model_path: Path,
) -> None:
    """Ensure move events update the final parent UUID to `targetUuid`.

    Args:
        model_path: Fixture KM file path.
    """

    latest_by_uuid, _ = KnowledgeModelService.load_model(str(model_path))

    for entity_uuid, expected_parent_uuid in MOVED_ENTITY_PARENT_EXPECTATIONS.items():
        assert_parent_uuid(latest_by_uuid, entity_uuid, expected_parent_uuid)


def test_tree_builder_places_moved_question_under_the_new_parent(
    model_path: Path,
) -> None:
    """Ensure the built translation tree follows move-event target parents.

    Args:
        model_path: Fixture KM file path.
    """

    latest_by_uuid, _ = KnowledgeModelService.load_model(str(model_path))

    relevant_uuids = KnowledgeModelService.build_ancestor_set(
        latest_by_uuid,
        {
            MOVED_QUESTION_UUID,
            MOVED_QUESTION_OLD_PARENT_UUID,
            MOVED_QUESTION_NEW_PARENT_UUID,
        },
    )
    _, nodes_map = KnowledgeModelService.build_tree(
        latest_by_uuid,
        relevant_uuids,
    )

    assert nodes_map[MOVED_QUESTION_UUID].parent_uuid == MOVED_QUESTION_NEW_PARENT_UUID
    assert any(
        child.entity_uuid == MOVED_QUESTION_UUID
        for child in nodes_map[MOVED_QUESTION_NEW_PARENT_UUID].children
    )
    assert all(
        child.entity_uuid != MOVED_QUESTION_UUID
        for child in nodes_map[MOVED_QUESTION_OLD_PARENT_UUID].children
    )


def test_event_merger_applies_same_timestamp_add_before_edit() -> None:
    """Ensure Registry event ordering cannot erase same-timestamp edits."""

    merger = KnowledgeModelEventMerger()
    latest_by_uuid = merger.build_latest_entities(
        {
            SAME_TIMESTAMP_ENTITY_UUID: [
                make_typed_event(
                    event_type="EditQuestionEvent",
                    event_index=0,
                    content={
                        "title": {
                            "changed": True,
                            "value": "Are there any other outputs?",
                        }
                    },
                ),
                make_typed_event(
                    event_type="AddQuestionEvent",
                    event_index=1,
                    content={
                        "annotations": [],
                        "questionType": "OptionsQuestion",
                        "requiredPhaseUuid": None,
                        "tagUuids": [],
                        "text": None,
                        "title": "",
                    },
                ),
            ]
        }
    )

    content = latest_by_uuid[SAME_TIMESTAMP_ENTITY_UUID]["content"]
    assert content["eventType"] == "EditQuestionEvent"
    assert content["title"] == "Are there any other outputs?"


def test_model_loader_ignores_packages_outside_selected_lineage(
    workspace: Path,
    model_path: Path,
) -> None:
    """Match DSW's previous-package traversal when a fork is disconnected."""

    root = json.loads(model_path.read_text(encoding="utf-8"))
    disconnected = copy.deepcopy(root["packages"][-1])
    disconnected["id"] = "example:disconnected:1.0.0"
    disconnected["organizationId"] = "example"
    disconnected["kmId"] = "disconnected"
    disconnected["version"] = "1.0.0"
    disconnected["previousPackageId"] = None
    disconnected["forkOfPackageId"] = root["id"]
    disconnected["events"] = disconnected["events"][:1]
    root["packages"].append(disconnected)
    root["id"] = disconnected["id"]
    root["organizationId"] = disconnected["organizationId"]
    root["kmId"] = disconnected["kmId"]
    root["version"] = disconnected["version"]
    disconnected_path = workspace / "disconnected.km"
    disconnected_path.write_text(
        json.dumps(root, ensure_ascii=False),
        encoding="utf-8",
    )

    events, _ = DswModelsBundleAdapter.load_bundle_events(str(disconnected_path))

    assert len(events) == 1
    assert events[0].package_index == len(root["packages"]) - 1


def make_typed_event(
    *,
    event_type: str,
    event_index: int,
    content: dict[str, object],
) -> TypedKnowledgeModelEvent:
    """Build a typed KM event for entity-ordering tests."""

    return TypedKnowledgeModelEvent(
        uuid=f"event-{event_index}",
        entity_uuid=SAME_TIMESTAMP_ENTITY_UUID,
        parent_uuid=SAME_TIMESTAMP_PARENT_UUID,
        effective_parent_uuid=SAME_TIMESTAMP_PARENT_UUID,
        created_at="2025-11-25T12:31:45Z",
        package_index=0,
        event_index=event_index,
        content={"eventType": event_type, **content},
    )
