#!/usr/bin/env python3
"""Validate a source KM repository and its current release."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dsw_km_translation_tool.github_release import GitHubReleaseError
from dsw_km_translation_tool.km_release import (
    KmReleaseValidationError,
    validate_km_release_repository,
)
from dsw_km_translation_tool.km_release_history import (
    validate_km_release_with_github_history,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate append-only KM package history and release metadata.",
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--config", default="km-repository.yml")
    parser.add_argument("--tag", help="Optional Git tag, for example v0.1.0.")
    parser.add_argument("--previous-bundle")
    parser.add_argument(
        "--github-repository",
        help=(
            "GitHub owner/name source repository. When the manifest has a "
            "previous package, download and compare its immutable release asset."
        ),
    )
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--github-api-url", default="https://api.github.com")
    parser.add_argument(
        "--allow-unreleased",
        action="store_true",
        help="Accept a scaffold with neither a bundle nor release manifest.",
    )
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    if args.previous_bundle and args.github_repository:
        raise SystemExit("Use only one of --previous-bundle and --github-repository.")

    try:
        if args.github_repository:
            result = validate_km_release_with_github_history(
                repo_root=Path(args.repo_root),
                config_path=Path(args.config),
                github_repository=args.github_repository,
                tag=args.tag,
                token=os.environ.get(args.github_token_env, ""),
                api_url=args.github_api_url,
                allow_unreleased=args.allow_unreleased,
            )
        else:
            result = validate_km_release_repository(
                repo_root=Path(args.repo_root),
                config_path=Path(args.config),
                tag=args.tag,
                previous_bundle_path=(Path(args.previous_bundle) if args.previous_bundle else None),
                allow_unreleased=args.allow_unreleased,
            )
    except (GitHubReleaseError, KmReleaseValidationError) as error:
        raise SystemExit(f"Invalid KM release:\n{error}") from error

    if not result.released:
        print("KM source repository is valid and awaiting its first release.")
        return
    print(f"Package: {result.package_id}")
    print(f"Version: {result.version}")
    print(f"Packages: {result.package_count}")
    print(f"Events: {result.event_count}")
    print(f"SHA-256: {result.bundle_sha256}")


if __name__ == "__main__":
    main()
