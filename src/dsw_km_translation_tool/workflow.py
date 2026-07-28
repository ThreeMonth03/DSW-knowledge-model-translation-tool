"""Facade for the local PO, translation tree, and KM build workflow.

Most command-line scripts should call this service instead of coordinating PO
parsing, tree storage, shared-string sync, review diffs, and KM rewriting
directly.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .data_models import (
    KmBuildResult,
    KnowledgeModelPackageIdentityMapping,
    OutlineBuildResult,
    PoBuildResult,
    PoDiffReviewResult,
    PoEntry,
    SharedBlocksDirectoryBuildResult,
    SharedBlocksOutlineBuildResult,
    SharedStringSyncResult,
    TranslationStatusReport,
    WorkflowContext,
)
from .knowledge_model_service import KnowledgeModelService
from .knowledge_model_support import KnowledgeModelBundleWriter
from .outline import TranslationOutlineBuilder
from .po import PoCatalogWriter
from .review import PoDiffReviewer
from .shared_blocks import SharedBlocksCatalogBuilder
from .supplemental_translations import SupplementalTranslationCatalog
from .sync import SharedStringSynchronizer
from .tree import TranslationTreeRepository
from .workflow_support import (
    TranslationWorkflowContextBuilder,
    TranslationWorkflowOutputService,
)


class TranslationWorkflowService:
    """Coordinate PO parsing, KM loading, tree export, and PO rebuild steps.

    Args:
        source_lang: Source language code used by the workflow.
        target_lang: Target language code used by the workflow.
        tree_repository: Optional injected translation tree repository.
        model_service: Optional injected model service class or instance.
        po_writer: Optional injected PO writer.
        km_writer: Optional injected KM writer.
        reviewer: Optional injected PO diff reviewer.
        synchronizer: Optional injected shared-string synchronizer.
        outline_builder: Optional injected outline builder.
        context_builder: Optional injected workflow-context builder.
        output_service: Optional injected workflow-output writer service.
        shared_blocks_builder: Optional injected shared-block markdown builder.
    """

    def __init__(
        self,
        source_lang: str = "en",
        target_lang: str = "zh_Hant",
        tree_repository: TranslationTreeRepository | None = None,
        model_service: KnowledgeModelService | None = None,
        po_writer: PoCatalogWriter | None = None,
        km_writer: KnowledgeModelBundleWriter | None = None,
        reviewer: PoDiffReviewer | None = None,
        synchronizer: SharedStringSynchronizer | None = None,
        outline_builder: TranslationOutlineBuilder | None = None,
        context_builder: TranslationWorkflowContextBuilder | None = None,
        output_service: TranslationWorkflowOutputService | None = None,
        shared_blocks_builder: SharedBlocksCatalogBuilder | None = None,
    ):
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.tree_repository = tree_repository or TranslationTreeRepository(
            source_lang=source_lang,
            target_lang=target_lang,
        )
        self.model_service = model_service or KnowledgeModelService()
        self.po_writer = po_writer or PoCatalogWriter()
        self.km_writer = km_writer or KnowledgeModelBundleWriter()
        self.reviewer = reviewer or PoDiffReviewer()
        self.synchronizer = synchronizer or SharedStringSynchronizer(
            tree_repository=self.tree_repository,
            po_writer=self.po_writer,
        )
        self.outline_builder = outline_builder or TranslationOutlineBuilder(
            tree_repository=self.tree_repository,
        )
        self.context_builder = context_builder or TranslationWorkflowContextBuilder(
            model_service=self.model_service,
        )
        self.output_service = output_service or TranslationWorkflowOutputService(
            po_writer=self.po_writer,
        )
        self.shared_blocks_builder = shared_blocks_builder or SharedBlocksCatalogBuilder(
            tree_repository=self.tree_repository,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    def build_tree_context(self, po_path: str, model_path: str) -> WorkflowContext:
        """Build the in-memory workflow context for a PO/KM pair.

        Args:
            po_path: Source PO file path.
            model_path: KM or JSON model path.

        Returns:
            Workflow context used by export and validation steps.
        """

        return self.context_builder.build(po_path=po_path, model_path=model_path)

    def export_tree(
        self,
        po_path: str,
        model_path: str,
        out_dir: str,
        preserve_existing_translations: bool = True,
    ) -> WorkflowContext:
        """Export a PO/KM pair into the translation tree folder structure.

        Args:
            po_path: Source PO file path.
            model_path: KM or JSON model path.
            out_dir: Output tree directory.
            preserve_existing_translations: Whether to preserve already edited
                target strings in the existing tree.

        Returns:
            Workflow context including the exported manifest.
        """

        context = self.build_tree_context(po_path=po_path, model_path=model_path)
        manifest = self.tree_repository.export_tree(
            out_dir=out_dir,
            tree_roots=context.roots,
            latest_by_uuid=context.latest_by_uuid,
            model_name=context.model_info.name,
            shared_reference_keys=context.shared_reference_keys,
            preserve_existing_translations=preserve_existing_translations,
        )
        return WorkflowContext(
            report=context.report,
            model_info=context.model_info,
            roots=context.roots,
            entries=context.entries,
            latest_by_uuid=context.latest_by_uuid,
            manifest=manifest,
            shared_reference_keys=context.shared_reference_keys,
        )

    def validate_po_against_model(self, po_path: str, model_path: str) -> dict[str, Any]:
        """Validate one PO file against the latest KM model.

        Args:
            po_path: PO file to validate.
            model_path: KM or JSON model path.

        Returns:
            Validation report dictionary.
        """

        return self.context_builder.validate_po_against_model(
            po_path=po_path,
            model_path=model_path,
        )

    def write_report(self, report: dict[str, Any], report_path: str) -> None:
        """Write a validation report to disk as JSON.

        Args:
            report: Report dictionary to serialize.
            report_path: Output JSON file path.
        """

        self.output_service.write_report(
            report=report,
            report_path=report_path,
        )

    def build_po_from_tree(
        self,
        tree_dir: str,
        original_po_path: str,
        out_po_path: str,
    ) -> PoBuildResult:
        """Generate a PO file from the exported tree.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO used as the structural template.
            out_po_path: Destination path for the generated PO.

        Returns:
            Result containing generated PO content and validation data.

        Raises:
            ValueError: If tree validation fails.
        """

        po_entries = self.context_builder.parse_po_entries(original_po_path)
        tree_validation = self.tree_repository.validate(tree_dir, po_entries)
        if tree_validation.errors:
            preview = "\n".join(tree_validation.errors[:50])
            raise ValueError(f"Translation tree validation failed:\n{preview}")

        return self.output_service.build_po_result(
            original_po_path=original_po_path,
            out_po_path=out_po_path,
            validation=tree_validation,
        )

    def build_km_from_po(
        self,
        translated_po_path: str,
        original_model_path: str,
        out_model_path: str,
        output_organization_id: str | None = None,
        output_km_id: str | None = None,
        output_name: str | None = None,
        supplemental_translations_dir: str | None = None,
        package_identity_mappings: tuple[KnowledgeModelPackageIdentityMapping, ...] = (),
    ) -> KmBuildResult:
        """Generate a translated KM bundle directly from a translated PO file.

        Args:
            translated_po_path: Translated PO file containing target `msgstr`
                values.
            original_model_path: Original KM bundle used as the structural
                source.
            out_model_path: Destination path for the generated KM bundle.
            output_organization_id: Optional organization ID for the generated
                translated KM. Defaults to the source organization.
            output_km_id: Optional KM ID for the generated translated KM.
                Defaults to the source KM ID suffixed with target language.
            output_name: Optional display name for the generated translated KM.
                Defaults to the source name suffixed with target language.
            supplemental_translations_dir: Optional directory of strict
                Markdown forms for KM fields omitted from the upstream PO.
            package_identity_mappings: Explicit translated identities for
                additional package coordinates in mixed-lineage bundles.

        Returns:
            Result containing generated KM content and application summary.

        Raises:
            ValueError: If the PO file does not validate against the original
                KM model or if the generated KM cannot be verified.
        """

        po_entries = self.context_builder.parse_po_entries(translated_po_path)
        report = self.validate_po_against_model(
            po_path=translated_po_path,
            model_path=original_model_path,
        )
        if self._report_has_model_errors(report):
            preview = "\n".join(self._format_model_validation_preview(report)[:50])
            raise ValueError(f"PO validation against KM failed:\n{preview}")

        if supplemental_translations_dir:
            supplemental_entries = SupplementalTranslationCatalog(
                source_lang=self.source_lang,
                target_lang=self.target_lang,
            ).load(supplemental_translations_dir)
            supplemental_report = self._validate_entries_against_model(
                po_entries=supplemental_entries,
                model_path=original_model_path,
            )
            if self._report_has_model_errors(supplemental_report):
                preview = "\n".join(self._format_model_validation_preview(supplemental_report)[:50])
                raise ValueError(
                    f"Supplemental translation validation against KM failed:\n{preview}"
                )
            base_keys = {(entry.uuid, entry.field) for entry in po_entries}
            duplicate_keys = sorted(
                base_keys & {(entry.uuid, entry.field) for entry in supplemental_entries}
            )
            if duplicate_keys:
                preview = ", ".join(f"{uuid}:{field}" for uuid, field in duplicate_keys[:10])
                raise ValueError(
                    f"Supplemental translations duplicate upstream PO entries: {preview}"
                )
            po_entries.extend(supplemental_entries)

        km_content, translations = self.km_writer.rewrite_translations(
            original_model_path=original_model_path,
            po_entries=po_entries,
            output_organization_id=output_organization_id,
            output_km_id=output_km_id,
            output_name=output_name,
            target_lang=self.target_lang,
            package_identity_mappings=package_identity_mappings,
        )
        out_km_file = Path(out_model_path)
        out_km_file.parent.mkdir(parents=True, exist_ok=True)
        out_km_file.write_text(km_content, encoding="utf-8")

        self._verify_generated_km_output(
            po_entries=po_entries,
            generated_model_path=str(out_km_file),
        )
        generated_root = json.loads(km_content)
        return KmBuildResult(
            km_content=km_content,
            translations=translations,
            total_entries=len(po_entries),
            translated_entries=len(translations),
            preserved_entries=len(po_entries) - len(translations),
            output_km=out_km_file,
            output_package_id=generated_root.get("id"),
            output_organization_id=generated_root.get("organizationId"),
            output_km_id=generated_root.get("kmId"),
            output_name=generated_root.get("name"),
        )

    def collect_status(self, tree_dir: str) -> TranslationStatusReport:
        """Collect translation status from the exported tree.

        Args:
            tree_dir: Translation tree directory.

        Returns:
            Translation status report.
        """

        return self.tree_repository.collect_status(tree_dir)

    def sync_shared_strings(
        self,
        tree_dir: str,
        original_po_path: str,
        out_po_path: str | None = None,
        outline_out_path: str | None = None,
        shared_blocks_root_path: str | None = None,
        shared_blocks_outline_out_path: str | None = None,
        group_by: str = "shared-block",
    ) -> SharedStringSyncResult:
        """Synchronize repeated translation groups across an exported tree.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO file used as the grouping source.
            out_po_path: Optional destination path for the refreshed PO file.
            outline_out_path: Optional destination path for outline markdown.
            shared_blocks_root_path: Optional destination path for the
                canonical split shared-block directory.
            shared_blocks_outline_out_path: Optional destination path for
                shared-block overview markdown.
            group_by: Grouping strategy used to define shared-string sets.

        Returns:
            Summary of the shared-string synchronization run.
        """

        result = self.synchronizer.sync(
            tree_dir=tree_dir,
            original_po_path=original_po_path,
            out_po_path=out_po_path,
            shared_blocks_root=shared_blocks_root_path,
            group_by=group_by,
        )
        if shared_blocks_root_path:
            shared_blocks_result = self.build_shared_blocks_directory(
                tree_dir=tree_dir,
                original_po_path=original_po_path,
                out_shared_blocks_root=shared_blocks_root_path,
            )
            result = replace(
                result,
                written_artifact_paths=tuple(
                    sorted(
                        {
                            *result.written_artifact_paths,
                            *(str(path) for path in shared_blocks_result.written_paths),
                        }
                    )
                ),
            )
        if shared_blocks_outline_out_path:
            shared_blocks_outline_result = self.build_shared_blocks_outline_markdown(
                tree_dir=tree_dir,
                original_po_path=original_po_path,
                out_shared_blocks_outline_path=shared_blocks_outline_out_path,
            )
            result = replace(
                result,
                output_shared_blocks_outline=str(
                    shared_blocks_outline_result.output_shared_blocks_outline
                ),
                written_artifact_paths=tuple(
                    sorted(
                        {
                            *result.written_artifact_paths,
                            str(shared_blocks_outline_result.output_shared_blocks_outline),
                        }
                    )
                ),
            )
        if not outline_out_path:
            return result

        outline_result = self.build_outline_markdown(
            tree_dir=tree_dir,
            out_outline_path=outline_out_path,
        )
        return replace(
            result,
            output_outline=str(outline_result.output_outline),
        )

    def _validate_entries_against_model(
        self,
        po_entries: list[PoEntry],
        model_path: str,
    ) -> dict[str, Any]:
        """Validate in-memory translation entries against a KM bundle."""

        latest_by_uuid, _ = self.model_service.load_model(model_path)
        return self.model_service.validate_po_entries(po_entries, latest_by_uuid)

    @staticmethod
    def _report_has_model_errors(report: dict[str, Any]) -> bool:
        """Return whether a PO-versus-KM validation report contains errors."""

        return any(report.get(key, 0) for key in ("missingEntities", "missingFields", "mismatches"))

    @staticmethod
    def _format_model_validation_preview(report: dict[str, Any]) -> list[str]:
        """Build a human-readable preview from a PO-versus-KM validation report."""

        preview: list[str] = []
        for detail in report.get("missingEntitiesDetails", ()):
            preview.append(f"Missing entity: {detail['uuid']}:{detail['field']}")
        for detail in report.get("missingFieldsDetails", ()):
            preview.append(f"Missing field: {detail['uuid']}:{detail['field']}")
        for detail in report.get("mismatchesDetails", ()):
            preview.append(
                "Source mismatch: "
                f"{detail['uuid']}:{detail['field']} "
                f"PO msgid={detail['msgid']!r} KM={detail['actual']!r}"
            )
        if not preview:
            preview.append("Unknown validation error.")
        return preview

    def _verify_generated_km_output(
        self,
        po_entries: list,
        generated_model_path: str,
    ) -> None:
        """Verify that generated KM text matches the PO-driven expected state.

        Args:
            po_entries: Flattened PO entries used to build the output.
            generated_model_path: Generated KM path to reload and verify.

        Raises:
            ValueError: If any final KM field does not match its expected PO
                translation or preserved source text.
        """

        latest_by_uuid, _ = self.model_service.load_model(generated_model_path)
        mismatches: list[str] = []
        for entry in po_entries:
            expected_text = self._normalize_expected_translation(entry.msgstr or entry.msgid)
            actual_text = self.model_service.get_event_text_value(
                latest_by_uuid.get(entry.uuid),
                entry.field,
            )
            if actual_text == expected_text:
                continue
            mismatches.append(
                f"{entry.uuid}:{entry.field} expected {expected_text!r} but got {actual_text!r}"
            )
            if len(mismatches) >= 50:
                break

        if mismatches:
            raise ValueError("Generated KM verification failed:\n" + "\n".join(mismatches))

    @staticmethod
    def _normalize_expected_translation(value: Any) -> Any:
        """Normalize expected verification text using KM string rules."""

        if not isinstance(value, str):
            return value
        return value.replace("\u2028", "").replace("\u2029", "")

    def build_shared_blocks_directory(
        self,
        tree_dir: str,
        original_po_path: str,
        out_shared_blocks_root: str,
    ) -> SharedBlocksDirectoryBuildResult:
        """Build the canonical split shared-block directory for the tree.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO file used as the shared-block source.
            out_shared_blocks_root: Destination shared-block directory path.

        Returns:
            Shared-block directory build result.
        """

        return self.shared_blocks_builder.build_directory(
            tree_dir=tree_dir,
            original_po_path=original_po_path,
            output_shared_blocks_root=out_shared_blocks_root,
        )

    def build_shared_blocks_outline_markdown(
        self,
        tree_dir: str,
        original_po_path: str,
        out_shared_blocks_outline_path: str,
    ) -> SharedBlocksOutlineBuildResult:
        """Build a compact shared-block overview markdown file.

        Args:
            tree_dir: Translation tree directory.
            original_po_path: Original PO file used as the shared-block source.
            out_shared_blocks_outline_path: Destination markdown path.

        Returns:
            Shared-block outline build result.
        """

        return self.shared_blocks_builder.build_outline(
            tree_dir=tree_dir,
            original_po_path=original_po_path,
            output_shared_blocks_outline_path=out_shared_blocks_outline_path,
        )

    def build_outline_markdown(
        self,
        tree_dir: str,
        out_outline_path: str,
    ) -> OutlineBuildResult:
        """Build a markdown outline for the current translation tree.

        Args:
            tree_dir: Translation tree directory.
            out_outline_path: Destination markdown path.

        Returns:
            Outline build result.
        """

        return self.outline_builder.build(
            tree_dir=tree_dir,
            output_outline_path=out_outline_path,
        )

    def review_po_changes(
        self,
        original_po_path: str,
        generated_po_path: str,
        diff_out_path: str | None = None,
    ) -> PoDiffReviewResult:
        """Review semantic and textual differences between two PO files.

        Args:
            original_po_path: Original PO template path.
            generated_po_path: Generated PO file path to review.
            diff_out_path: Optional destination path for unified diff output.

        Returns:
            Structured diff-review result.
        """

        review = self.reviewer.review(
            original_po_path=original_po_path,
            generated_po_path=generated_po_path,
        )
        return self.output_service.write_diff_review(
            review=review,
            diff_out_path=diff_out_path,
        )
