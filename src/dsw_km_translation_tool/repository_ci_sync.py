"""Build CI writer configuration from ``translation-config.yml``.

Packaged CLI commands and GitHub Actions should not duplicate path, branch, or
language defaults. This module is the adapter between a dedicated translation
repository config file and the lower-level sync writer.
"""

from __future__ import annotations

from pathlib import Path

from .ci_sync import DEFAULT_SYNC_COMMIT_MESSAGE, CiSyncCommitConfig
from .translation_repository_config import (
    load_translation_repository_config,
    tracking_branch,
    version_paths,
)


def build_repository_ci_sync_config(
    *,
    host_repo_path: Path,
    tooling_repo_path: Path,
    config_path: Path,
    mode: str,
    translation_root: str | None = None,
    target_ref: str | None = None,
    source_lang: str | None = None,
    target_lang: str | None = None,
    commit_message: str = DEFAULT_SYNC_COMMIT_MESSAGE,
    source_po_path: Path | None = None,
    source_km_path: Path | None = None,
    output_organization_id: str | None = None,
    output_km_id: str | None = None,
    output_name: str | None = None,
    restore_source_ref: str | None = None,
) -> CiSyncCommitConfig:
    """Build sync automation config from a translation repository config.

    Args:
        host_repo_path: Translation repository checkout path.
        tooling_repo_path: Tooling repository checkout path.
        config_path: Path to ``translation-config.yml``. Relative paths are
            resolved inside ``host_repo_path``.
        mode: CI trigger mode.
        translation_root: Translation artifact root inside the host repository.
            Defaults to ``.`` for tracking branches.
        target_ref: Branch/ref that should receive generated commits. Defaults
            to the configured tracking branch.
        source_lang: Optional source language override.
        target_lang: Optional target language override.
        commit_message: Commit message used when sync changes are detected.
        source_po_path: Optional PO source override.
        source_km_path: Optional KM source override.
        output_organization_id: Optional translated KM organization override.
        output_km_id: Optional translated KM ID override.
        output_name: Optional translated KM display name override.
        restore_source_ref: Optional git ref used for recovery restores. Defaults
            to ``origin/<tracking branch>``.

    Returns:
        Populated CI sync configuration.
    """

    host_repo = host_repo_path.resolve()
    resolved_config_path = _resolve_host_path(host_repo, config_path)
    repository_config = load_translation_repository_config(resolved_config_path)
    paths = version_paths(repository_config)
    branch = tracking_branch(repository_config)
    return CiSyncCommitConfig(
        host_repo_path=host_repo,
        tooling_repo_path=tooling_repo_path,
        translation_root=translation_root or ".",
        target_ref=target_ref or branch,
        mode=mode,
        source_lang=source_lang or repository_config.translation.source_language,
        target_lang=target_lang or repository_config.translation.target_language,
        commit_message=commit_message,
        source_po_path=source_po_path or paths.source_po_path,
        source_km_path=source_km_path or paths.source_km_path,
        output_organization_id=(
            output_organization_id or repository_config.translation.translated_organization_id
        ),
        output_km_id=output_km_id or repository_config.translation.translated_km_id,
        output_name=output_name or repository_config.translation.translated_name,
        supplemental_translations_path=(repository_config.translation.supplemental_directory),
        package_identity_mappings=(repository_config.translation.package_identity_mappings),
        restore_source_ref=restore_source_ref or f"origin/{branch}",
    )


def _resolve_host_path(host_repo: Path, path: Path) -> Path:
    """Resolve a path relative to the host repository when needed."""

    if path.is_absolute():
        return path.resolve()
    return (host_repo / path).resolve()
