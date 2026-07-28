#!/usr/bin/env python3
"""Convert a translated PO file back into a KM/JSON bundle."""

from __future__ import annotations

import argparse

from dsw_km_translation_tool import (
    DEFAULT_LAYOUT,
    DEFAULT_MODEL_PATH,
    DEFAULT_SOURCE_LANG,
    DEFAULT_TARGET_LANG,
    TranslationWorkflowService,
)
from dsw_km_translation_tool.data_models import KnowledgeModelPackageIdentityMapping


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser.

    Returns:
        Configured argument parser for this command.
    """

    parser = argparse.ArgumentParser(
        description="Convert a translated PO file back into a KM bundle.",
    )
    parser.add_argument(
        "--translated-po",
        default=str(DEFAULT_LAYOUT.final_po_path),
        help="Path to the translated PO file.",
    )
    parser.add_argument(
        "--original-km",
        default=str(DEFAULT_MODEL_PATH),
        help="Path to the original KM/JSON bundle.",
    )
    parser.add_argument(
        "--out-km",
        default=str(DEFAULT_LAYOUT.final_km_path),
        help="Output KM file path.",
    )
    parser.add_argument("--source-lang", default=DEFAULT_SOURCE_LANG)
    parser.add_argument("--target-lang", default=DEFAULT_TARGET_LANG)
    parser.add_argument(
        "--output-organization-id",
        default=None,
        help="Organization ID for the generated translated KM. Defaults to the source org.",
    )
    parser.add_argument(
        "--output-km-id",
        default=None,
        help=(
            "KM ID for the generated translated KM. Defaults to the source KM ID "
            "suffixed with the target language."
        ),
    )
    parser.add_argument(
        "--output-name",
        default=None,
        help=(
            "Display name for the generated translated KM. Defaults to the source "
            "name suffixed with the target language."
        ),
    )
    parser.add_argument(
        "--supplemental-translations-dir",
        default=None,
        help=(
            "Directory containing Markdown forms for KM fields omitted from "
            "the upstream PO catalog."
        ),
    )
    parser.add_argument(
        "--package-identity-mapping",
        action="append",
        nargs=5,
        default=[],
        metavar=(
            "SOURCE_ORG",
            "SOURCE_KM",
            "TRANSLATED_ORG",
            "TRANSLATED_KM",
            "TRANSLATED_NAME",
        ),
        help=(
            "Map an additional source package coordinate in a mixed-lineage "
            "bundle to a distinct translated coordinate and name. Repeat for "
            "each non-root source coordinate."
        ),
    )
    return parser


def main() -> None:
    """Run the PO-to-KM CLI."""

    args = build_argument_parser().parse_args()
    try:
        workflow = TranslationWorkflowService(
            source_lang=args.source_lang,
            target_lang=args.target_lang,
        )
        result = workflow.build_km_from_po(
            translated_po_path=args.translated_po,
            original_model_path=args.original_km,
            out_model_path=args.out_km,
            output_organization_id=args.output_organization_id,
            output_km_id=args.output_km_id,
            output_name=args.output_name,
            supplemental_translations_dir=args.supplemental_translations_dir,
            package_identity_mappings=tuple(
                KnowledgeModelPackageIdentityMapping(
                    source_organization_id=values[0],
                    source_km_id=values[1],
                    translated_organization_id=values[2],
                    translated_km_id=values[3],
                    translated_name=values[4],
                )
                for values in args.package_identity_mapping
            ),
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error

    print(
        f"Generated KM file: {result.output_km} "
        f"as {result.output_package_id} "
        f"({result.total_entries} PO entries scanned, "
        f"{result.translated_entries} translated fields applied)"
    )


if __name__ == "__main__":
    main()
