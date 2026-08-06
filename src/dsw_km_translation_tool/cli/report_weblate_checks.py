#!/usr/bin/env python3
"""Report Weblate units matching a check query."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from dsw_km_translation_tool.weblate_checks import (
    build_weblate_checks_error_report,
    build_weblate_checks_report,
    render_weblate_checks_markdown,
    write_weblate_checks_json,
    write_weblate_checks_markdown,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build CLI arguments."""

    parser = argparse.ArgumentParser(
        description="Report Weblate units matching a query such as has:check.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Translation repository root.",
    )
    parser.add_argument(
        "--config",
        default="translation-config.yml",
        help="Path to translation-config.yml.",
    )
    parser.add_argument(
        "--query",
        default="has:check",
        help="Weblate unit search query.",
    )
    parser.add_argument(
        "--json-out",
        help="Optional path to write the Weblate checks report as JSON.",
    )
    parser.add_argument(
        "--summary",
        help="Optional Markdown summary path, for example $GITHUB_STEP_SUMMARY.",
    )
    parser.add_argument(
        "--details-out",
        help="Optional path to write a full Markdown report.",
    )
    parser.add_argument(
        "--issue-limit",
        type=int,
        default=20,
        help="Maximum issue rows to print. Use 0 to print all.",
    )
    parser.add_argument(
        "--allow-api-failure",
        action="store_true",
        help="Write a diagnostic report and exit 0 when Weblate API calls fail.",
    )
    parser.add_argument(
        "--api-token-env",
        default="LOCALIZE_API_TOKEN",
        help=(
            "Environment variable containing an optional Weblate API token. "
            "When unset, the report uses anonymous read-only API access."
        ),
    )
    parser.add_argument(
        "--trusted-api-origin",
        default="https://localize.ds-wizard.org",
        help="HTTPS origin allowed to receive the Weblate API token.",
    )
    return parser


def main() -> None:
    """Run the Weblate checks report CLI."""

    args = build_argument_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = repo_root / config_path

    try:
        report = build_weblate_checks_report(
            repo_root=repo_root,
            config_path=config_path,
            query=args.query,
            api_token=os.environ.get(args.api_token_env, ""),
            trusted_api_origin=args.trusted_api_origin,
        )
    except Exception as error:
        if not args.allow_api_failure:
            raise
        report = build_weblate_checks_error_report(
            repo_root=repo_root,
            config_path=config_path,
            query=args.query,
            error=error,
        )

    issue_limit = None if args.issue_limit == 0 else args.issue_limit
    print(render_weblate_checks_markdown(report, issue_limit=issue_limit), end="")
    if args.json_out:
        write_weblate_checks_json(report, args.json_out)
        print(f"JSON report written to {args.json_out}")
    if args.summary:
        write_weblate_checks_markdown(report, args.summary, issue_limit=issue_limit)
    if args.details_out:
        write_weblate_checks_markdown(report, args.details_out, issue_limit=None)
        print(f"Markdown details written to {args.details_out}")


if __name__ == "__main__":
    main()
