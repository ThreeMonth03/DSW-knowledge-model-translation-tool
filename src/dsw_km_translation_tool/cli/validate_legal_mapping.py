#!/usr/bin/env python3
"""Validate a legal mapping against an exact DSW KM bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw_km_translation_tool.legal_review import LegalReviewError, validate_legal_mapping


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate legal sources and bind mappings to exact KM questions.",
    )
    parser.add_argument("--mapping", required=True, help="Legal mapping YAML.")
    parser.add_argument("--km", required=True, help="Reviewed source .km bundle.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    try:
        result = validate_legal_mapping(
            mapping_path=Path(args.mapping),
            km_path=Path(args.km),
        )
    except LegalReviewError as error:
        raise SystemExit(f"Invalid legal mapping:\n{error}") from error

    print(f"Package: {result.package_id}")
    print(f"Jurisdiction: {result.jurisdiction}")
    print(f"Mappings: {result.mapping_count}")
    print(f"Legal sources: {result.legal_source_count}")
    print(f"SHA-256: {result.bundle_sha256}")


if __name__ == "__main__":
    main()
