#!/usr/bin/env python3
"""Validate a KM translation repository configuration."""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw_km_translation_tool.translation_repository_config import (
    TranslationRepositoryConfigError,
    load_translation_repository_config,
    tracking_branch,
    version_paths,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Validate translation-config.yml for KM translation repos.",
    )
    parser.add_argument(
        "--config",
        default="translation-config.yml",
        help="Path to translation-config.yml.",
    )
    parser.add_argument(
        "--summary",
        help="Optional markdown summary path, for example $GITHUB_STEP_SUMMARY.",
    )
    return parser


def main() -> None:
    """Run config validation and print a compact summary."""

    args = build_argument_parser().parse_args()
    config_path = Path(args.config)
    try:
        config = load_translation_repository_config(config_path)
    except TranslationRepositoryConfigError as error:
        raise SystemExit(f"Invalid translation config: {error}") from error

    version = config.knowledge_model.version
    paths = version_paths(config)
    lines = [
        "KM translation config is valid.",
        f"Knowledge model: {config.knowledge_model.organization_id}:{config.knowledge_model.km_id}",
        f"Target language: {config.translation.target_language}",
        f"KM version: {version}",
        f"Workflow mode: {config.workflow.mode}",
        f"Source mode: {config.workflow.source}",
        f"Tracking branch: {tracking_branch(config)}",
        f"Source KM path: {paths.source_km_path.as_posix()}",
        f"Source PO path: {paths.source_po_path.as_posix()}",
        f"Registry API: {config.registry.api_url}",
        f"Translation tree path: {paths.translation_tree_dir.as_posix()}",
    ]
    if config.knowledge_model.upstream_ref:
        lines.append(f"Source KM ref: {config.knowledge_model.upstream_ref}")
    if config.localize:
        lines.append(f"Localize PO URL: {config.localize.download_url}")
    if config.translation.supplemental_directory:
        lines.append(
            f"Supplemental translations: {config.translation.supplemental_directory.as_posix()}"
        )
    print("\n".join(lines))
    if args.summary:
        write_summary(Path(args.summary), lines)


def write_summary(path: Path, lines: list[str]) -> None:
    """Append a markdown validation summary."""

    with path.open("a", encoding="utf-8") as handle:
        handle.write("## KM Translation Config\n\n")
        for line in lines:
            handle.write(f"- {line}\n")


if __name__ == "__main__":
    main()
