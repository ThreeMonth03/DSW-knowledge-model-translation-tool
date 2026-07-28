"""Knowledge-model data models used by the KM translation tooling."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .po import PoEntry


@dataclass(frozen=True)
class KnowledgeModelPackageIdentityMapping:
    """Map one source KM package coordinate to its translated coordinate.

    Args:
        source_organization_id: Organization ID used by source packages.
        source_km_id: KM ID used by source packages.
        translated_organization_id: Organization ID for translated packages.
        translated_km_id: KM ID for translated packages.
        translated_name: Display name for translated packages.
    """

    source_organization_id: str
    source_km_id: str
    translated_organization_id: str
    translated_km_id: str
    translated_name: str

    @property
    def source_coordinate(self) -> tuple[str, str]:
        """Return the source `(organization ID, KM ID)` pair."""

        return self.source_organization_id, self.source_km_id

    @property
    def translated_coordinate(self) -> tuple[str, str]:
        """Return the translated `(organization ID, KM ID)` pair."""

        return self.translated_organization_id, self.translated_km_id


@dataclass(frozen=True)
class ModelInfo:
    """Metadata describing the loaded DSW knowledge model.

    Args:
        id: Root model identifier.
        km_id: Knowledge model identifier.
        name: Human-readable model name.
    """

    id: str | None
    km_id: str | None
    name: str


@dataclass
class TreeNode:
    """Node in the exported translation tree.

    Args:
        entity_uuid: UUID of the node.
        parent_uuid: UUID of the parent node, if any.
        event_type: DSW event type.
        content: Latest merged node content from the KM.
        po_refs: Flattened PO entries attached to this node.
        children: Child nodes in tree order.
    """

    entity_uuid: str
    parent_uuid: str | None
    event_type: str | None
    content: dict[str, Any]
    po_refs: list[PoEntry] = field(default_factory=list)
    children: list["TreeNode"] = field(default_factory=list)
