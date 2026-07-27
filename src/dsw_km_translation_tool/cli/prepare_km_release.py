#!/usr/bin/env python3
"""Generate release metadata from an exported source KM bundle."""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw_km_translation_tool.km_release import (
    KmReleaseValidationError,
    prepare_km_release_manifest,
)


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate and validate release-manifest.yml from the configured KM bundle.",
    )
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--config", default="km-repository.yml")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def main() -> None:
    args = build_argument_parser().parse_args()
    try:
        result = prepare_km_release_manifest(
            repo_root=Path(args.repo_root),
            config_path=Path(args.config),
            overwrite=args.overwrite,
        )
    except (KmReleaseValidationError, OSError, ValueError) as error:
        raise SystemExit(f"Unable to prepare KM release: {error}") from error

    print(f"Manifest: {result.manifest_path}")
    print(f"Package: {result.package_id}")
    print(f"Version: {result.version}")
    print(f"Previous package: {result.previous_package_id or '(initial release)'}")
    print(f"SHA-256: {result.bundle_sha256}")


if __name__ == "__main__":
    main()
