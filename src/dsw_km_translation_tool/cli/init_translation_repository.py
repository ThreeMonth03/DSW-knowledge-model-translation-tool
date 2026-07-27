#!/usr/bin/env python3
"""Initialize a dedicated KM translation repository checkout."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dsw_km_translation_tool.translation_repository_bootstrap import (
    TranslationRepositoryBootstrapError,
    bootstrap_translation_repository,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""

    parser = argparse.ArgumentParser(
        description=(
            "Scaffold a translation repository from tooling templates and "
            "optionally hydrate it from the DSW Registry and Localize/Weblate."
        ),
    )
    parser.add_argument("--repo-root", required=True, help="Target translation repo path.")
    parser.add_argument(
        "--tooling-repo",
        default=".",
        help="Tooling repository path containing examples and workflow templates.",
    )
    parser.add_argument(
        "--config-template",
        default=None,
        help=(
            "Optional translation-config.yml template. Relative paths are resolved "
            "inside --tooling-repo."
        ),
    )
    parser.add_argument("--registry-token-env", default="DSW_REGISTRY_TOKEN")
    parser.add_argument(
        "--source-km",
        help="Local .km input used to hydrate a GitHub-only repository.",
    )
    parser.add_argument(
        "--source-po",
        help=(
            "Optional local PO seed for GitHub-only hydration. If omitted, "
            "an empty catalog is generated from --source-km."
        ),
    )
    parser.add_argument(
        "--scaffold-only",
        action="store_true",
        help="Only write config/docs/workflows; do not download KM/PO inputs.",
    )
    parser.add_argument(
        "--skip-without-token",
        action="store_true",
        help="Leave a scaffolded repo instead of failing when the Registry token is missing.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite managed scaffold files that already exist.",
    )
    return parser


def main() -> None:
    """Run translation repository initialization."""

    args = build_argument_parser().parse_args()
    token = os.environ.get(args.registry_token_env, "")
    try:
        result = bootstrap_translation_repository(
            repo_root=Path(args.repo_root),
            tooling_repo=Path(args.tooling_repo),
            config_template_path=(
                Path(args.config_template) if args.config_template is not None else None
            ),
            registry_token=token,
            hydrate=not args.scaffold_only,
            overwrite=args.overwrite,
            skip_without_token=args.skip_without_token,
            source_km_input=Path(args.source_km) if args.source_km else None,
            source_po_input=Path(args.source_po) if args.source_po else None,
        )
    except TranslationRepositoryBootstrapError as error:
        raise SystemExit(f"Unable to initialize translation repository: {error}") from error

    print("Translation repository initialization")
    print(f"  Repository : {result.repo_root}")
    print(f"  Config     : {result.config_path}")
    print(f"  Hydrated   : {'yes' if result.hydrated else 'no'}")
    if result.skipped_reason:
        print(f"  Skipped    : {result.skipped_reason}")
    if result.km_version:
        print(f"  KM version : {result.km_version}")
    print(f"  Written    : {len(result.written_files)}")
    print(f"  Skipped    : {len(result.skipped_files)}")
    if result.final_km_path:
        print(f"  Final KM   : {result.final_km_path}")


if __name__ == "__main__":
    main()
