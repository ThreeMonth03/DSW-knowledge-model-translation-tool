#!/usr/bin/env python3
"""Initialize a Git repository for a source DSW Knowledge Model."""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw_km_translation_tool.km_source_repository_scaffold import (
    KmSourceRepositoryScaffoldError,
    scaffold_km_source_repository,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scaffold a source KM release repository.")
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--tooling-repo", default=".")
    parser.add_argument("--organization-id", required=True)
    parser.add_argument("--km-id", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--initial-parent-package-id", required=True)
    parser.add_argument("--tooling-repository", required=True)
    parser.add_argument("--tooling-ref", required=True)
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    try:
        result = scaffold_km_source_repository(
            repo_root=Path(args.repo_root),
            tooling_repo=Path(args.tooling_repo),
            organization_id=args.organization_id,
            km_id=args.km_id,
            name=args.name,
            initial_parent_package_id=args.initial_parent_package_id,
            tooling_repository=args.tooling_repository,
            tooling_ref=args.tooling_ref,
            overwrite=args.overwrite,
        )
    except KmSourceRepositoryScaffoldError as error:
        raise SystemExit(f"Unable to initialize source KM repository: {error}") from error
    print(f"Repository: {result.repo_root}")
    print(f"Written: {len(result.written_files)}")
    print(f"Skipped: {len(result.skipped_files)}")


if __name__ == "__main__":
    main()
