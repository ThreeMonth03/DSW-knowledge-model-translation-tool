"""Automation for keeping one translation branch on the latest KM version."""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from .command import (
    CommandRunner,
    configure_github_actions_git_identity,
    default_command_runner,
    make_checked_runner,
    tooling_virtualenv_command_path,
    tooling_virtualenv_python_path,
)
from .km_bundle_sync import BundleDownloader, pull_km_bundle
from .km_registry import Downloader, discover_km_versions
from .localize_sync import Downloader as LocalizeDownloader
from .localize_sync import pull_localize_po
from .translation_repository_config import (
    DEFAULT_REGISTRY_API_URL,
    TranslationRepositoryConfig,
    TranslationRepositoryConfigError,
    format_package_id,
    load_translation_repository_config,
    normalize_version,
    tracking_branch,
    version_paths,
)


class KmLatestSyncError(RuntimeError):
    """Raised when latest-KM synchronization cannot complete."""


_run_checked = make_checked_runner(KmLatestSyncError, include_command=False)


@dataclass(frozen=True)
class KmLatestSyncResult:
    """Summary of one latest-KM sync run."""

    configured_version: str
    registry_version: str | None
    target_ref: str | None
    changed: bool
    skipped_reason: str | None = None
    dry_run: bool = False

    @property
    def status(self) -> str:
        """Return a compact status label for reports."""

        if self.dry_run:
            return "dry-run"
        if self.skipped_reason:
            return f"skipped:{self.skipped_reason}"
        if self.changed:
            return "updated"
        return "current"

    def to_report_dict(self) -> dict[str, object]:
        """Return a stable JSON-serializable report."""

        return {
            "configured_version": self.configured_version,
            "registry_version": self.registry_version,
            "target_ref": self.target_ref,
            "changed": self.changed,
            "skipped_reason": self.skipped_reason,
            "dry_run": self.dry_run,
            "status": self.status,
        }


def sync_latest_km_version(
    *,
    repo_root: Path,
    tooling_repo: Path,
    config_path: Path,
    registry_token: str,
    target_ref: str | None = None,
    skip_without_token: bool = False,
    dry_run: bool = False,
    downloader: Downloader | None = None,
    bundle_downloader: BundleDownloader | None = None,
    localize_downloader: LocalizeDownloader | None = None,
    runner: CommandRunner | None = None,
) -> KmLatestSyncResult:
    """Update the current translation branch when the Registry has a newer KM."""

    host_repo = repo_root.resolve()
    tooling_root = tooling_repo.resolve()
    resolved_config_path = _resolve_repo_path(host_repo, config_path)
    config = load_translation_repository_config(resolved_config_path)
    configured_version = config.knowledge_model.version
    push_ref = target_ref or tracking_branch(config)
    if registry_token.strip():
        _ensure_trusted_registry(config.registry.api_url)
    discovery = discover_km_versions(config_path=resolved_config_path, downloader=downloader)
    registry_version = discovery.latest_registry_version
    if not discovery.newer_versions:
        return KmLatestSyncResult(
            configured_version=configured_version,
            registry_version=registry_version,
            target_ref=push_ref,
            changed=False,
            dry_run=dry_run,
        )
    if not registry_token.strip():
        if skip_without_token:
            return KmLatestSyncResult(
                configured_version=configured_version,
                registry_version=registry_version,
                target_ref=push_ref,
                changed=False,
                skipped_reason="missing-registry-token",
                dry_run=dry_run,
            )
        raise KmLatestSyncError("A newer KM exists, but no DSW Registry token was provided.")
    if dry_run:
        return KmLatestSyncResult(
            configured_version=configured_version,
            registry_version=registry_version,
            target_ref=push_ref,
            changed=False,
            dry_run=True,
        )

    run = runner or default_command_runner
    _ensure_git_repo_is_clean(host_repo, run)
    target_version = discovery.newer_versions[-1]
    update_knowledge_model_version(resolved_config_path, target_version)
    pull_km_bundle(
        config_path=resolved_config_path,
        repo_root=host_repo,
        token=registry_token,
        downloader=bundle_downloader,
    )
    pull_localize_po(
        config_path=resolved_config_path,
        repo_root=host_repo,
        downloader=localize_downloader,
    )
    _run_validate_config(
        repo_root=host_repo,
        tooling_repo=tooling_root,
        config_path=config_path,
        runner=run,
    )
    _run_export_tree(
        repo_root=host_repo,
        tooling_repo=tooling_root,
        config_path=resolved_config_path,
        runner=run,
    )
    _run_sync_build_and_tests(
        repo_root=host_repo,
        tooling_repo=tooling_root,
        config_path=config_path,
        runner=run,
    )
    _run_alignment_check(
        repo_root=host_repo,
        tooling_repo=tooling_root,
        config_path=config_path,
        runner=run,
    )
    committed = _commit_and_push(
        repo_root=host_repo,
        target_ref=push_ref,
        message=f"chore(sync): update source KM to {target_version}",
        runner=run,
    )
    return KmLatestSyncResult(
        configured_version=configured_version,
        registry_version=registry_version,
        target_ref=push_ref,
        changed=committed,
        dry_run=False,
    )


def _ensure_trusted_registry(api_url: str) -> None:
    """Reject repo-controlled Registry destinations before handling a token."""

    try:
        configured = urllib.parse.urlsplit(api_url)
        trusted = urllib.parse.urlsplit(DEFAULT_REGISTRY_API_URL)
        trusted_destination = (
            configured.scheme == "https"
            and configured.hostname == trusted.hostname
            and configured.port in (None, 443)
            and configured.username is None
            and configured.password is None
            and configured.path.rstrip("/") == trusted.path.rstrip("/")
            and not configured.query
            and not configured.fragment
        )
    except ValueError:
        trusted_destination = False
    if not trusted_destination:
        raise KmLatestSyncError(
            "Refusing to use DSW_REGISTRY_TOKEN with untrusted Registry API URL "
            f"{api_url!r}; expected {DEFAULT_REGISTRY_API_URL!r}."
        )


def update_knowledge_model_version(config_path: Path, version: str) -> str:
    """Replace the configured KM version and bundle path."""

    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TranslationRepositoryConfigError("translation-config.yml must contain a mapping")
    knowledge_model = payload.get("knowledge_model")
    if not isinstance(knowledge_model, dict):
        raise TranslationRepositoryConfigError("Expected mapping at `knowledge_model`")
    normalized = normalize_version(version)
    knowledge_model["version"] = normalized
    knowledge_model["bundle_path"] = _source_km_path_from_config_payload(
        knowledge_model,
        normalized,
    ).as_posix()
    config_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return normalized


def render_km_latest_sync_markdown(result: KmLatestSyncResult) -> str:
    """Render latest-KM sync results as maintainer-readable Markdown."""

    lines = [
        "## KM Version Auto Update",
        "",
        f"Status: **{result.status}**",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Configured version before run | {_format_value(result.configured_version)} |",
        f"| Registry latest version | {_format_value(result.registry_version)} |",
        f"| Target ref | {_format_value(result.target_ref)} |",
        f"| Changed Git | {'yes' if result.changed else 'no'} |",
        f"| Dry run | {'yes' if result.dry_run else 'no'} |",
        f"| Skipped reason | {_format_value(result.skipped_reason)} |",
    ]
    if result.changed:
        lines.extend(
            [
                "",
                "The newer published KM was pulled, Localize/Weblate was mirrored, "
                "translation artifacts were rebuilt, validation passed, and the update "
                "was pushed to Git.",
            ]
        )
    elif result.skipped_reason:
        lines.extend(
            [
                "",
                "No Git update was pushed. Fix the skipped condition and let the next "
                "scheduled run retry.",
            ]
        )
    else:
        lines.extend(["", "No newer published KM is available."])
    return "\n".join(lines) + "\n"


def write_km_latest_sync_report(
    *,
    result: KmLatestSyncResult,
    report_path: Path,
) -> None:
    """Write latest-KM sync results as pretty JSON."""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result.to_report_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_km_latest_sync_markdown(
    *,
    result: KmLatestSyncResult,
    report_path: Path,
) -> None:
    """Append latest-KM sync results as Markdown."""

    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("a", encoding="utf-8") as handle:
        handle.write(render_km_latest_sync_markdown(result))


def _run_validate_config(
    *,
    repo_root: Path,
    tooling_repo: Path,
    config_path: Path,
    runner: CommandRunner,
) -> None:
    _run_checked(
        runner,
        [
            str(tooling_virtualenv_command_path(tooling_repo, "dsw-km-validate-config")),
            "--config",
            str(_resolve_repo_path(repo_root, config_path)),
        ],
        cwd=tooling_repo,
        description="validate updated translation config",
        echo_output=True,
    )


def _run_export_tree(
    *,
    repo_root: Path,
    tooling_repo: Path,
    config_path: Path,
    runner: CommandRunner,
) -> None:
    config = load_translation_repository_config(config_path)
    paths = version_paths(config)
    _run_checked(
        runner,
        [
            str(tooling_virtualenv_command_path(tooling_repo, "dsw-km-export-tree")),
            "--po",
            str(repo_root / paths.localize_latest_po_path),
            "--json",
            str(repo_root / paths.source_km_path),
            "--out-dir",
            str(repo_root / paths.translation_tree_dir),
            "--outline-out",
            str(repo_root / paths.translation_tree_dir / "outline.md"),
            "--shared-blocks-dir-out",
            str(repo_root / paths.translation_tree_dir / "shared_blocks"),
            "--source-lang",
            config.translation.source_language,
            "--target-lang",
            config.translation.target_language,
            "--force",
            "--yes",
        ],
        cwd=tooling_repo,
        description=f"export translation tree for KM {paths.version}",
        echo_output=True,
    )


def _run_sync_build_and_tests(
    *,
    repo_root: Path,
    tooling_repo: Path,
    config_path: Path,
    runner: CommandRunner,
) -> None:
    config = load_translation_repository_config(_resolve_repo_path(repo_root, config_path))
    paths = version_paths(config)
    _run_checked(
        runner,
        [
            str(tooling_virtualenv_command_path(tooling_repo, "dsw-km-sync-shared-strings")),
            "--tree-dir",
            str(repo_root / paths.translation_tree_dir),
            "--original-po",
            str(repo_root / paths.localize_latest_po_path),
            "--out-po",
            str(repo_root / paths.final_po_path),
            "--diff-out",
            str(repo_root / paths.review_diff_path),
            "--outline-out",
            str(repo_root / paths.translation_tree_dir / "outline.md"),
            "--shared-blocks-dir-out",
            str(repo_root / paths.translation_tree_dir / "shared_blocks"),
            "--shared-blocks-outline-out",
            str(repo_root / paths.translation_tree_dir / "shared_blocks_outline.md"),
            "--source-lang",
            config.translation.source_language,
            "--target-lang",
            config.translation.target_language,
            "--group-by",
            "shared-block",
        ],
        cwd=tooling_repo,
        description=f"sync translation artifacts for KM {paths.version}",
        echo_output=True,
    )
    _run_checked(
        runner,
        [
            str(tooling_virtualenv_command_path(tooling_repo, "dsw-km-po-to-km")),
            "--translated-po",
            str(repo_root / paths.final_po_path),
            "--original-km",
            str(repo_root / paths.source_km_path),
            "--out-km",
            str(repo_root / paths.final_km_path),
            "--source-lang",
            config.translation.source_language,
            "--target-lang",
            config.translation.target_language,
            "--output-organization-id",
            config.translation.translated_organization_id,
            "--output-km-id",
            config.translation.translated_km_id,
            "--output-name",
            config.translation.translated_name,
        ]
        + _supplemental_po_to_km_args(repo_root, config)
        + _package_identity_mapping_args(config),
        cwd=tooling_repo,
        description=f"build translated KM for KM {paths.version}",
        echo_output=True,
    )
    _run_checked(
        runner,
        [
            str(tooling_virtualenv_python_path(tooling_repo)),
            "-m",
            "pytest",
            "tests/translation",
        ],
        cwd=tooling_repo,
        env={"DSW_TRANSLATION_OUTPUT_ROOT": str(repo_root)},
        description=f"run translation tests for KM {paths.version}",
        echo_output=True,
    )


def _supplemental_po_to_km_args(
    repo_root: Path,
    config: TranslationRepositoryConfig,
) -> list[str]:
    """Build PO-to-KM flags for configured supplemental forms."""

    directory = config.translation.supplemental_directory
    if directory is None:
        return []
    return ["--supplemental-translations-dir", str(repo_root / directory)]


def _package_identity_mapping_args(
    config: TranslationRepositoryConfig,
) -> list[str]:
    """Build PO-to-KM flags for mixed-lineage package identities."""

    args: list[str] = []
    for mapping in config.translation.package_identity_mappings:
        args.extend(
            [
                "--package-identity-mapping",
                mapping.source_organization_id,
                mapping.source_km_id,
                mapping.translated_organization_id,
                mapping.translated_km_id,
                mapping.translated_name,
            ]
        )
    return args


def _run_alignment_check(
    *,
    repo_root: Path,
    tooling_repo: Path,
    config_path: Path,
    runner: CommandRunner,
) -> None:
    _run_checked(
        runner,
        [
            str(tooling_virtualenv_command_path(tooling_repo, "dsw-km-report-alignment")),
            "--repo-root",
            str(repo_root),
            "--config",
            config_path.as_posix(),
            "--fail-on-mismatch",
        ],
        cwd=tooling_repo,
        description="verify Localize/repository alignment",
        echo_output=True,
    )


def _commit_and_push(
    *,
    repo_root: Path,
    target_ref: str,
    message: str,
    runner: CommandRunner,
) -> bool:
    configure_github_actions_git_identity(
        repo_root=repo_root,
        runner=runner,
        error_factory=KmLatestSyncError,
        include_command=False,
    )
    _run_checked(
        runner,
        ["git", "add", "-A", "--", "."],
        cwd=repo_root,
        description="stage repository changes",
    )
    status = _run_checked(
        runner,
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        description="inspect repository changes",
    )
    if not status.stdout.strip():
        return False
    _run_checked(
        runner,
        ["git", "commit", "-m", message],
        cwd=repo_root,
        description="create latest-KM sync commit",
    )
    _run_checked(
        runner,
        ["git", "push", "origin", f"HEAD:{target_ref}"],
        cwd=repo_root,
        description=f"push latest-KM sync commit to {target_ref}",
    )
    return True


def _ensure_git_repo_is_clean(repo_root: Path, runner: CommandRunner) -> None:
    status = _run_checked(
        runner,
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        description="inspect repository cleanliness",
    )
    if status.stdout.strip():
        raise KmLatestSyncError("Repository has uncommitted changes; refusing latest-KM sync")


def _resolve_repo_path(repo_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _source_km_path_from_config_payload(
    knowledge_model: Mapping[str, object],
    version: str,
) -> Path:
    organization_id = str(knowledge_model.get("organization_id", "")).strip()
    km_id = str(knowledge_model.get("km_id", "")).strip()
    if not organization_id or not km_id:
        raise TranslationRepositoryConfigError(
            "knowledge_model.organization_id and knowledge_model.km_id are required"
        )
    normalized = normalize_version(version)
    package_id = format_package_id(
        organization_id=organization_id,
        km_id=km_id,
        version=normalized,
    )
    source_slug = package_id.replace(":", "-")
    return Path("sources") / "knowledge-models" / source_slug / f"{source_slug}.km"


def _format_value(value: object | None) -> str:
    if value is None or value == "":
        return "(none)"
    return f"`{value}`"
