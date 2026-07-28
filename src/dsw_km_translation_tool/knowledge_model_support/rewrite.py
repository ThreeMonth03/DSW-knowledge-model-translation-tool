"""Rewrite helpers for applying PO translations back into KM bundles."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..data_models import KnowledgeModelPackageIdentityMapping, PoEntry
from .event_ordering import event_type_priority


@dataclass(frozen=True)
class KnowledgeModelFieldTarget:
    """Identify the raw KM event slot that defines one current text field.

    Args:
        package_index: Package index within the KM bundle.
        event_index: Event index within the package.
        entity_uuid: Entity UUID owning the field.
        field: Translatable field name.
        event_type: Event type of the defining event.
        created_at: Event timestamp used for effective ordering.
    """

    package_index: int
    event_index: int
    entity_uuid: str
    field: str
    event_type: str
    created_at: str


class KnowledgeModelBundleWriter:
    """Rewrite a KM bundle by applying translated PO `msgstr` values."""

    def rewrite_translations(
        self,
        original_model_path: str,
        po_entries: list[PoEntry],
        output_organization_id: str | None = None,
        output_km_id: str | None = None,
        output_name: str | None = None,
        target_lang: str | None = None,
        package_identity_mappings: tuple[KnowledgeModelPackageIdentityMapping, ...] = (),
    ) -> tuple[str, dict[tuple[str, str], str]]:
        """Apply translated PO strings to the defining KM events.

        Args:
            original_model_path: Source KM bundle path.
            po_entries: Flattened PO entries carrying `msgstr` values.
            output_organization_id: Optional organization ID for the rewritten
                package identity. Defaults to the source organization.
            output_km_id: Optional KM ID for the rewritten package identity.
                Defaults to the source KM ID suffixed with the target language.
            output_name: Optional human-readable KM name for the rewritten
                bundle. Defaults to the source name suffixed with target
                language.
            target_lang: Target language used to derive default translated
                package identity values.
            package_identity_mappings: Explicit translations for additional
                package coordinates in a mixed-lineage bundle.

        Returns:
            Tuple of serialized KM JSON text and applied translation mapping.

        Raises:
            ValueError: If any translated PO key cannot be mapped back into the
                source KM bundle.
        """

        bundle_root = json.loads(Path(original_model_path).read_text(encoding="utf-8"))
        self.rewrite_bundle_identity(
            bundle_root=bundle_root,
            output_organization_id=output_organization_id,
            output_km_id=output_km_id,
            output_name=output_name,
            target_lang=target_lang,
            package_identity_mappings=package_identity_mappings,
        )
        translations_by_key = self.build_translation_map(po_entries)
        if translations_by_key:
            field_targets = self.locate_field_targets(
                bundle_root=bundle_root,
                target_keys=set(translations_by_key),
            )
            missing_keys = sorted(set(translations_by_key) - set(field_targets))
            if missing_keys:
                preview = ", ".join(
                    f"{entity_uuid}:{field}" for entity_uuid, field in missing_keys[:10]
                )
                raise ValueError(
                    f"Unable to map translated PO entries back into the KM bundle: {preview}"
                )

            for key, translated_text in translations_by_key.items():
                self.apply_translation(
                    bundle_root=bundle_root,
                    target=field_targets[key],
                    translated_text=translated_text,
                )

        return json.dumps(bundle_root, ensure_ascii=False, indent=2) + "\n", translations_by_key

    def rewrite_bundle_identity(
        self,
        bundle_root: dict[str, Any],
        output_organization_id: str | None = None,
        output_km_id: str | None = None,
        output_name: str | None = None,
        target_lang: str | None = None,
        package_identity_mappings: tuple[KnowledgeModelPackageIdentityMapping, ...] = (),
    ) -> None:
        """Rewrite package identity so translated KMs import as separate KMs.

        Args:
            bundle_root: Parsed KM bundle JSON to mutate.
            output_organization_id: Optional replacement organization ID.
            output_km_id: Optional replacement KM ID.
            output_name: Optional replacement display name.
            target_lang: Target language used for default suffixes.
            package_identity_mappings: Explicit translations for additional
                package coordinates in a mixed-lineage bundle.
        """

        original_organization_id = str(bundle_root.get("organizationId") or "")
        original_km_id = str(bundle_root.get("kmId") or "")
        original_name = str(bundle_root.get("name") or original_km_id or "Knowledge Model")
        language_slug = self.slugify_identifier(target_lang or "translated")
        new_organization_id = output_organization_id or original_organization_id
        new_km_id = output_km_id or self.build_translated_km_id(
            original_km_id=original_km_id,
            language_slug=language_slug,
        )
        new_name = output_name or self.build_translated_name(
            original_name=original_name,
            target_lang=target_lang,
        )

        primary_mapping = KnowledgeModelPackageIdentityMapping(
            source_organization_id=original_organization_id,
            source_km_id=original_km_id,
            translated_organization_id=new_organization_id,
            translated_km_id=new_km_id,
            translated_name=new_name,
        )
        mappings_by_source = self.build_identity_mapping_index(
            bundle_root=bundle_root,
            primary_mapping=primary_mapping,
            package_identity_mappings=package_identity_mappings,
        )
        id_map = self.build_package_id_map(
            bundle_root=bundle_root,
            mappings_by_source=mappings_by_source,
        )

        bundle_root["organizationId"] = new_organization_id
        bundle_root["kmId"] = new_km_id
        bundle_root["name"] = new_name
        if bundle_root.get("version"):
            bundle_root["id"] = self.format_package_id(
                organization_id=new_organization_id,
                km_id=new_km_id,
                version=str(bundle_root["version"]),
            )

        for package in bundle_root.get("packages", ()):
            if not isinstance(package, dict):
                continue
            original_package_id = str(package.get("id") or "")
            source_coordinate = self.package_coordinate(package)
            mapping = mappings_by_source[source_coordinate]
            package["organizationId"] = mapping.translated_organization_id
            package["kmId"] = mapping.translated_km_id
            package["name"] = mapping.translated_name
            if original_package_id in id_map:
                package["id"] = id_map[original_package_id]

            for reference_key in (
                "previousPackageId",
                "forkOfPackageId",
                "mergeCheckpointPackageId",
            ):
                reference = package.get(reference_key)
                if reference in id_map:
                    package[reference_key] = id_map[reference]

    def build_identity_mapping_index(
        self,
        bundle_root: dict[str, Any],
        primary_mapping: KnowledgeModelPackageIdentityMapping,
        package_identity_mappings: tuple[KnowledgeModelPackageIdentityMapping, ...],
    ) -> dict[tuple[str, str], KnowledgeModelPackageIdentityMapping]:
        """Validate and index identity mappings for every package coordinate.

        Args:
            bundle_root: Parsed KM bundle JSON.
            primary_mapping: Implicit mapping for the bundle's root KM.
            package_identity_mappings: Explicit mappings for ancestor or fork
                package coordinates.

        Returns:
            Mappings keyed by source package coordinate.

        Raises:
            ValueError: If a mixed lineage has missing, duplicate, or
                many-to-one identity mappings.
        """

        mappings_by_source = {primary_mapping.source_coordinate: primary_mapping}
        translated_coordinates = {primary_mapping.translated_coordinate}
        for mapping in package_identity_mappings:
            if mapping.source_coordinate in mappings_by_source:
                source = ":".join(mapping.source_coordinate)
                raise ValueError(f"Duplicate package identity mapping for {source}")
            if mapping.translated_coordinate in translated_coordinates:
                target = ":".join(mapping.translated_coordinate)
                raise ValueError(
                    f"Package identity mappings must not collapse multiple lineages into {target}"
                )
            mappings_by_source[mapping.source_coordinate] = mapping
            translated_coordinates.add(mapping.translated_coordinate)

        source_coordinates = {
            self.package_coordinate(package)
            for package in bundle_root.get("packages", ())
            if isinstance(package, dict)
        }
        missing_coordinates = sorted(source_coordinates - mappings_by_source.keys())
        if missing_coordinates:
            missing = ", ".join(":".join(coordinate) for coordinate in missing_coordinates)
            raise ValueError(
                "Mixed-lineage KM bundles require explicit translated package "
                f"identity mappings; missing: {missing}"
            )
        unused_coordinates = sorted(mappings_by_source.keys() - source_coordinates)
        if unused_coordinates:
            unused = ", ".join(":".join(coordinate) for coordinate in unused_coordinates)
            raise ValueError(f"Package identity mappings do not match bundle packages: {unused}")
        return mappings_by_source

    def build_package_id_map(
        self,
        bundle_root: dict[str, Any],
        mappings_by_source: dict[tuple[str, str], KnowledgeModelPackageIdentityMapping],
    ) -> dict[str, str]:
        """Build old-to-new package ID mapping for one KM bundle.

        Args:
            bundle_root: Parsed KM bundle JSON.
            mappings_by_source: Validated mappings keyed by source coordinate.

        Returns:
            Mapping from source package IDs to translated package IDs.
        """

        id_map: dict[str, str] = {}
        for package in bundle_root.get("packages", ()):
            if not isinstance(package, dict):
                continue
            package_id = str(package.get("id") or "")
            version = str(package.get("version") or "")
            if not package_id or not version:
                continue
            mapping = mappings_by_source[self.package_coordinate(package)]
            id_map[package_id] = self.format_package_id(
                organization_id=mapping.translated_organization_id,
                km_id=mapping.translated_km_id,
                version=version,
            )
        return id_map

    @staticmethod
    def package_coordinate(package: dict[str, Any]) -> tuple[str, str]:
        """Return and validate one package's source coordinate."""

        organization_id = str(package.get("organizationId") or "")
        km_id = str(package.get("kmId") or "")
        if not organization_id or not km_id:
            raise ValueError("KM bundle packages must define organizationId and kmId")
        return organization_id, km_id

    @staticmethod
    def build_translated_km_id(original_km_id: str, language_slug: str) -> str:
        """Build a non-conflicting translated KM ID.

        Args:
            original_km_id: Source KM ID.
            language_slug: Safe target-language slug.

        Returns:
            KM ID suffixed with the language slug.
        """

        base_km_id = original_km_id or "knowledge-model"
        suffix = f"-{language_slug}"
        if base_km_id.endswith(suffix):
            return base_km_id
        return f"{base_km_id}{suffix}"

    @staticmethod
    def build_translated_name(original_name: str, target_lang: str | None) -> str:
        """Build a readable translated KM name.

        Args:
            original_name: Source KM name.
            target_lang: Target language suffix.

        Returns:
            Display name with a target-language marker.
        """

        if not target_lang:
            return f"{original_name} (translated)"
        suffix = f"({target_lang})"
        if original_name.endswith(f" {suffix}"):
            return original_name
        return f"{original_name} {suffix}"

    @staticmethod
    def slugify_identifier(value: str) -> str:
        """Convert a language or user value into a DSW-friendly ID segment.

        Args:
            value: Raw value to normalize.

        Returns:
            Lowercase hyphenated identifier segment.
        """

        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "translated"

    @staticmethod
    def format_package_id(organization_id: str, km_id: str, version: str) -> str:
        """Format a DSW package ID.

        Args:
            organization_id: Organization ID segment.
            km_id: KM ID segment.
            version: Semantic version segment.

        Returns:
            Formatted package ID.
        """

        return f"{organization_id}:{km_id}:{version}"

    @staticmethod
    def build_translation_map(po_entries: list[PoEntry]) -> dict[tuple[str, str], str]:
        """Collect non-empty translated PO strings keyed by `(uuid, field)`.

        Args:
            po_entries: Flattened PO entries.

        Returns:
            Translation mapping used for KM rewriting.
        """

        return {(entry.uuid, entry.field): entry.msgstr for entry in po_entries if entry.msgstr}

    def locate_field_targets(
        self,
        bundle_root: dict[str, Any],
        target_keys: set[tuple[str, str]],
    ) -> dict[tuple[str, str], KnowledgeModelFieldTarget]:
        """Locate the last raw event that defines each requested field.

        Args:
            bundle_root: Parsed KM bundle JSON.
            target_keys: Requested `(uuid, field)` targets.

        Returns:
            Field target lookup keyed by `(uuid, field)`.
        """

        target_fields_by_uuid: dict[str, set[str]] = defaultdict(set)
        for entity_uuid, field in target_keys:
            target_fields_by_uuid[entity_uuid].add(field)

        located_targets: dict[tuple[str, str], KnowledgeModelFieldTarget] = {}
        located_sort_keys: dict[tuple[str, str], tuple[str, int, int]] = {}
        for package_index, package in enumerate(bundle_root.get("packages", ())):
            for event_index, event in enumerate(package.get("events", ())):
                entity_uuid = str(event.get("entityUuid") or "")
                requested_fields = target_fields_by_uuid.get(entity_uuid)
                if not requested_fields:
                    continue

                content = event.get("content", {})
                if not isinstance(content, dict):
                    continue
                event_type = str(content.get("eventType") or "")
                created_at = str(event.get("createdAt") or "")
                sort_key = (
                    created_at,
                    package_index,
                    event_type_priority(event_type),
                    event_index,
                )

                for field in requested_fields:
                    if not self.event_defines_field(
                        content=content,
                        field=field,
                        event_type=event_type,
                    ):
                        continue
                    key = (entity_uuid, field)
                    if key in located_sort_keys and sort_key < located_sort_keys[key]:
                        continue
                    located_sort_keys[key] = sort_key
                    located_targets[(entity_uuid, field)] = KnowledgeModelFieldTarget(
                        package_index=package_index,
                        event_index=event_index,
                        entity_uuid=entity_uuid,
                        field=field,
                        event_type=event_type,
                        created_at=created_at,
                    )

        return located_targets

    @staticmethod
    def event_defines_field(
        content: dict[str, Any],
        field: str,
        event_type: str,
    ) -> bool:
        """Return whether one raw event currently defines the requested field.

        Args:
            content: Raw event content dictionary.
            field: Requested translatable field name.
            event_type: Raw event type string.

        Returns:
            `True` when the event assigns the field's effective current value.
        """

        if field not in content:
            return False

        value = content[field]
        if event_type.startswith("Add"):
            return value is not None
        if event_type.startswith("Edit"):
            if isinstance(value, dict) and "changed" in value:
                return bool(value.get("changed"))
            return value is not None
        return False

    @staticmethod
    def apply_translation(
        bundle_root: dict[str, Any],
        target: KnowledgeModelFieldTarget,
        translated_text: str,
    ) -> None:
        """Apply one translated string to the located raw KM event.

        Args:
            bundle_root: Parsed KM bundle JSON.
            target: Target raw event slot to rewrite.
            translated_text: Replacement translated text.
        """

        event = bundle_root["packages"][target.package_index]["events"][target.event_index]
        content = event["content"]
        current_value = content.get(target.field)
        if target.event_type.startswith("Edit") and isinstance(current_value, dict):
            current_value["changed"] = True
            current_value["value"] = translated_text
            return
        content[target.field] = translated_text
