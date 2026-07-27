#!/usr/bin/env python3
"""Generate or update a Git-managed PO catalog from a KM bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw_km_translation_tool.km_catalog import build_catalog_from_km


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build a deterministic PO catalog directly from a DSW KM bundle.",
    )
    parser.add_argument("--km", required=True, help="Source .km bundle.")
    parser.add_argument("--out", required=True, help="Output PO catalog.")
    parser.add_argument("--target-language", required=True)
    parser.add_argument(
        "--previous-po",
        help="Optional previous PO whose unchanged translations should be carried.",
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    result = build_catalog_from_km(
        km_path=Path(args.km),
        output_path=Path(args.out),
        target_language=args.target_language,
        previous_po_path=Path(args.previous_po) if args.previous_po else None,
    )
    print(f"Catalog: {result.output_path}")
    print(f"Entries: {result.entry_count}")
    print(f"Carried translations: {result.carried_translation_count}")


if __name__ == "__main__":
    main()
