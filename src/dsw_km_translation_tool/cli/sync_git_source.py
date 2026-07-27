#!/usr/bin/env python3
"""Synchronize a Git-authoritative translation repo from a pinned checkout."""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw_km_translation_tool.git_translation_source import (
    GitTranslationSourceError,
    sync_git_translation_source,
)
from dsw_km_translation_tool.translation_repository_config import (
    TranslationRepositoryConfigError,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path("."))
    parser.add_argument("--source-repo", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("translation-config.yml"))
    parser.add_argument("--seed-po", type=Path)
    return parser


def main() -> None:
    """Run the pinned Git source synchronization."""

    args = build_argument_parser().parse_args()
    try:
        result = sync_git_translation_source(
            repo_root=args.repo_root,
            source_repo=args.source_repo,
            config_path=args.config,
            seed_po_path=args.seed_po,
        )
    except (
        GitTranslationSourceError,
        TranslationRepositoryConfigError,
        OSError,
        ValueError,
    ) as error:
        raise SystemExit(f"Unable to synchronize Git KM source: {error}") from error

    print(f"Synchronized: {result.repository}@{result.ref}")
    print(f"Bundle: {result.upstream_bundle_path}")
    print(f"Package: {result.package_id}")
    print(f"SHA-256: {result.sha256}")
    print(f"Catalog entries: {result.catalog_entry_count}")
    print(f"Carried translations: {result.carried_translation_count}")
    print(f"Translated KM: {result.build_result.final_km_path}")


if __name__ == "__main__":
    main()
