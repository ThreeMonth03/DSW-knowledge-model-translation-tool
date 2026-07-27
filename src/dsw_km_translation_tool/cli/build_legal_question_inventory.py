#!/usr/bin/env python3
"""Build a keyword-based inventory of KM questions for legal review."""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw_km_translation_tool.legal_review import (
    LegalReviewError,
    build_legal_question_inventory,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=("Build deterministic legal-review triage candidates from a DSW KM bundle."),
    )
    parser.add_argument("--km", required=True, help="Source .km bundle.")
    parser.add_argument("--rules", required=True, help="Keyword topic rules in YAML.")
    parser.add_argument("--out", required=True, help="Output inventory YAML.")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    try:
        result = build_legal_question_inventory(
            km_path=Path(args.km),
            rules_path=Path(args.rules),
            output_path=Path(args.out),
        )
    except LegalReviewError as error:
        raise SystemExit(f"Unable to build legal-question inventory:\n{error}") from error

    print(f"Package: {result.package_id}")
    print(f"Questions: {result.question_count}")
    print(f"SHA-256: {result.bundle_sha256}")
    print(f"Inventory: {result.output_path}")


if __name__ == "__main__":
    main()
