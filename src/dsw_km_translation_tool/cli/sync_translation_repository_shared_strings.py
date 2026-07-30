#!/usr/bin/env python3
"""Synchronize canonical shared translations in a translation repository."""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw_km_translation_tool.translation_repository_shared_sync import (
    TranslationRepositorySharedSyncError,
    sync_translation_repository_shared_strings,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Expand canonical shared-block translations into their checked-in "
            "translation-tree fields."
        ),
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--config", default="translation-config.yml")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    try:
        result = sync_translation_repository_shared_strings(
            repo_root=Path(args.repo_root),
            config_path=Path(args.config),
        )
    except (OSError, ValueError, TranslationRepositorySharedSyncError) as error:
        raise SystemExit(
            f"Unable to synchronize repository shared translations: {error}"
        ) from error

    print("Repository Shared Translation Sync")
    print(f"  Translation tree : {result.tree_dir}")
    print(f"  Shared blocks    : {result.shared_blocks_dir}")
    print(f"  Groups scanned   : {result.groups_scanned}")
    print(f"  Groups updated   : {result.groups_updated}")
    print(f"  Fields updated   : {result.fields_updated}")


if __name__ == "__main__":
    main()
