#!/usr/bin/env python3
"""Check or synchronize a GitHub-only translation source KM."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dsw_km_translation_tool.github_translation_source import (
    GitHubTranslationSourceError,
    sync_github_translation_source,
)
from dsw_km_translation_tool.translation_repository_config import (
    TranslationRepositoryConfigError,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Download and verify the KM release pinned by a GitHub-only translation-config.yml."
        ),
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--config", default="translation-config.yml")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--github-api-url", default="https://api.github.com")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the checked-in source KM without changing files.",
    )
    parser.add_argument(
        "--allow-unreleased",
        action="store_true",
        help="Accept an empty repository whose upstream ref is UNRELEASED.",
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    try:
        result = sync_github_translation_source(
            repo_root=Path(args.repo_root),
            config_path=Path(args.config),
            token=os.environ.get(args.github_token_env, ""),
            api_url=args.github_api_url,
            check=args.check,
            allow_unreleased=args.allow_unreleased,
        )
    except (
        GitHubTranslationSourceError,
        TranslationRepositoryConfigError,
        OSError,
        ValueError,
    ) as error:
        raise SystemExit(f"Unable to synchronize GitHub KM release: {error}") from error

    if not result.initialized:
        print("GitHub source dependency is valid and awaiting its first release.")
        return
    action = "Checked" if result.checked_only else "Synchronized"
    print(f"{action}: {result.repository}@{result.ref}")
    print(f"Package: {result.package_id}")
    print(f"SHA-256: {result.sha256}")
    print(f"Source KM: {result.source_km_path}")
    if not result.checked_only:
        print(f"Source catalog: {result.source_po_path}")
        print(f"Carried translations: {result.carried_translation_count}")


if __name__ == "__main__":
    main()
