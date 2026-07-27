#!/usr/bin/env python3
"""Import accepted GitHub translation changes into Weblate."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from dsw_km_translation_tool.cli.github_outputs import (
    append_github_outputs,
    append_markdown_summary,
)
from dsw_km_translation_tool.github_translation_contributions import (
    GitHubTranslationReport,
    build_github_translation_report,
    find_unapplied_weblate_imports,
    write_github_translation_json,
    write_github_translation_markdown,
    write_import_po,
)
from dsw_km_translation_tool.localize_sync import pull_localize_po
from dsw_km_translation_tool.translation_repository_config import (
    load_translation_repository_config,
    require_localize_config,
)
from dsw_km_translation_tool.weblate_upload import (
    resolve_weblate_file_api_url,
    upload_translation_file,
)


def build_argument_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for GitHub-to-Weblate imports."""

    parser = argparse.ArgumentParser(
        description=(
            "Import reviewed GitHub translation changes into Weblate, failing "
            "when Weblate changed the same entries differently."
        ),
    )
    parser.add_argument("--repo-root", required=True, help="Translation repository root.")
    parser.add_argument(
        "--config",
        default="translation-config.yml",
        help="Path to translation-config.yml, relative to --repo-root unless absolute.",
    )
    parser.add_argument("--base-ref", required=True, help="Accepted base Git ref.")
    parser.add_argument("--head-ref", default="HEAD", help="Merged Git ref to import.")
    parser.add_argument("--json-out", required=True, help="JSON report output path.")
    parser.add_argument("--details-out", required=True, help="Markdown report output path.")
    parser.add_argument("--summary", default=None, help="Optional GitHub step summary path.")
    parser.add_argument("--github-output", default=None, help="Optional GitHub output file path.")
    parser.add_argument(
        "--token-env",
        default="LOCALIZE_API_TOKEN",
        help="Environment variable containing the Weblate API token.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Do not upload to Weblate.")
    return parser


def main() -> None:
    """Run the GitHub-to-Weblate import workflow."""

    args = build_argument_parser().parse_args()
    repo_root = Path(args.repo_root).resolve()
    config_path = _resolve_repo_path(repo_root, Path(args.config))
    repository_config = load_translation_repository_config(config_path)
    localize = require_localize_config(repository_config)
    with TemporaryDirectory(prefix="dsw-github-import-") as temp_dir:
        temp_root = Path(temp_dir)
        pull_result = pull_localize_po(
            config_path=config_path,
            repo_root=temp_root,
        )
        report = build_github_translation_report(
            repo_root=repo_root,
            base_ref=args.base_ref,
            head_ref=args.head_ref,
            latest_po_path=pull_result.latest_po_path,
            source_lang=repository_config.translation.source_language,
            target_lang=repository_config.translation.target_language,
        )
        write_github_translation_json(report, args.json_out)
        write_github_translation_markdown(report, args.details_out)
        append_markdown_summary(
            summary_path=args.summary,
            markdown_path=Path(args.details_out),
        )
        if report.has_format_errors:
            _write_github_translation_outputs(
                output_path=args.github_output,
                report=report,
                uploaded=False,
            )
            raise SystemExit(
                "GitHub translation import contains Markdown format errors. "
                "Review the report before updating Weblate."
            )
        if report.has_conflicts:
            _write_github_translation_outputs(
                output_path=args.github_output,
                report=report,
                uploaded=False,
            )
            raise SystemExit(
                "GitHub translation import has conflicts. Review the report before "
                "updating Weblate."
            )
        if report.has_shared_block_errors:
            _write_github_translation_outputs(
                output_path=args.github_output,
                report=report,
                uploaded=False,
            )
            raise SystemExit(
                "GitHub translation import leaves shared blocks out of sync. "
                "Run shared-string sync before updating Weblate."
            )
        if report.importable_entries == 0:
            _write_github_translation_outputs(
                output_path=args.github_output,
                report=report,
                uploaded=False,
            )
            print("[github-translation-import] No GitHub translations need Weblate import.")
            return

        import_po_path = write_import_po(
            report=report,
            output_path=temp_root / "github_translation_import.po",
            language=repository_config.translation.target_language,
        )
        if args.dry_run:
            _write_github_translation_outputs(
                output_path=args.github_output,
                report=report,
                uploaded=False,
            )
            print("[github-translation-import] Dry run; Weblate upload skipped.")
            return
        token = os.environ.get(args.token_env, "").strip()
        if not token:
            raise SystemExit(
                f"Missing Weblate API token in ${args.token_env}; cannot import "
                "GitHub translations."
            )
        result = upload_translation_file(
            api_url=resolve_weblate_file_api_url(localize.download_url),
            po_path=import_po_path,
            token=token,
        )
        verification_pull = pull_localize_po(
            config_path=config_path,
            repo_root=temp_root / "verification",
        )
        unapplied = find_unapplied_weblate_imports(
            report=report,
            latest_po_path=verification_pull.latest_po_path,
        )
        if unapplied:
            _write_github_translation_outputs(
                output_path=args.github_output,
                report=report,
                uploaded=False,
            )
            keys = ", ".join(f"{decision.uuid}:{decision.field}" for decision in unapplied[:10])
            raise SystemExit(
                f"Weblate did not apply {len(unapplied)} uploaded translation entries: {keys}"
            )
        _write_github_translation_outputs(
            output_path=args.github_output,
            report=report,
            uploaded=True,
        )
        print(
            "[github-translation-import] Uploaded "
            f"{report.importable_entries} entries to {result.api_url}."
        )


def _resolve_repo_path(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _write_github_translation_outputs(
    *,
    output_path: str | None,
    report: GitHubTranslationReport,
    uploaded: bool,
) -> None:
    append_github_outputs(
        output_path=output_path,
        values={
            "has_translation_changes": report.has_translation_changes,
            "has_conflicts": report.has_conflicts,
            "has_format_errors": report.has_format_errors,
            "has_shared_block_errors": report.has_shared_block_errors,
            "importable_entries": report.importable_entries,
            "uploaded": uploaded,
        },
    )


if __name__ == "__main__":
    main()
