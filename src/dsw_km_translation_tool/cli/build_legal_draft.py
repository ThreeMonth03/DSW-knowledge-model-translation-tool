#!/usr/bin/env python3
"""Build a jurisdiction-specific DSW KM draft from a legal mapping."""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw_km_translation_tool.legal_review import LegalReviewError, build_legal_draft


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        description="Append a child KM package from curated legal question rewrites.",
    )
    parser.add_argument("--km", required=True, type=Path, help="Exact parent KM bundle.")
    parser.add_argument("--mapping", required=True, type=Path, help="Curated legal mapping YAML.")
    parser.add_argument("--output", required=True, type=Path, help="Generated child KM bundle.")
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--km-id", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--description", required=True)
    parser.add_argument("--license", dest="license_id", required=True)
    parser.add_argument("--readme-file", required=True, type=Path)
    return parser


def main() -> None:
    """Run the legal-draft builder."""

    args = build_argument_parser().parse_args()
    try:
        readme = args.readme_file.read_text(encoding="utf-8")
        result = build_legal_draft(
            km_path=args.km,
            mapping_path=args.mapping,
            output_path=args.output,
            organization_id=args.organization_id,
            km_id=args.km_id,
            version=args.version,
            name=args.name,
            description=args.description,
            license_id=args.license_id,
            readme=readme,
        )
    except (OSError, LegalReviewError) as error:
        raise SystemExit(str(error)) from error

    print(
        f"Generated {result.package_id} from {result.parent_package_id} "
        f"with {result.event_count} legal edit events: {result.output_path}"
    )


if __name__ == "__main__":
    main()
