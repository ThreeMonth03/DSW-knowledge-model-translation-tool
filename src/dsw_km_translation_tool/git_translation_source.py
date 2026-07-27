"""Synchronize a translation repository from a pinned local Git checkout."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .dsw_models_adapter import DswModelsBundleAdapter
from .km_catalog import build_catalog_from_km
from .translation_repository_build import (
    TranslationRepositoryBuildResult,
    build_translation_repository,
)
from .translation_repository_config import (
    format_package_id,
    load_translation_repository_config,
    version_paths,
)


class GitTranslationSourceError(RuntimeError):
    """Raised when a pinned Git source cannot be synchronized safely."""


@dataclass(frozen=True)
class GitTranslationSourceResult:
    """Summary of one pinned Git source synchronization."""

    repository: str
    ref: str
    upstream_bundle_path: Path
    source_km_path: Path
    source_po_path: Path
    package_id: str
    sha256: str
    catalog_entry_count: int
    carried_translation_count: int
    build_result: TranslationRepositoryBuildResult


def sync_git_translation_source(
    *,
    repo_root: Path,
    source_repo: Path,
    config_path: Path = Path("translation-config.yml"),
    seed_po_path: Path | None = None,
) -> GitTranslationSourceResult:
    """Copy a KM from an exact Git commit and rebuild translation outputs."""

    root = repo_root.resolve()
    source_root = source_repo.resolve()
    resolved_config = config_path if config_path.is_absolute() else root / config_path
    config = load_translation_repository_config(resolved_config)
    if config.workflow.mode != "github" or config.workflow.source != "git":
        raise GitTranslationSourceError(
            "Git source synchronization requires workflow.mode `github` and workflow.source `git`"
        )

    ref = config.knowledge_model.upstream_ref or ""
    _validate_commit_ref(ref)
    _require_checkout_ref(source_root=source_root, expected_ref=ref)
    upstream_bundle_path = config.knowledge_model.upstream_bundle_path
    if upstream_bundle_path is None:
        raise GitTranslationSourceError(
            "knowledge_model.upstream_bundle_path is required for a Git source"
        )
    _require_committed_bundle(
        source_root=source_root,
        upstream_bundle_path=upstream_bundle_path,
    )

    upstream_bundle = source_root / upstream_bundle_path
    if not upstream_bundle.is_file():
        raise GitTranslationSourceError(f"Pinned source bundle does not exist: {upstream_bundle}")
    expected_package_id = format_package_id(
        config.knowledge_model.organization_id,
        config.knowledge_model.km_id,
        config.knowledge_model.version,
    )
    _validate_bundle(bundle_path=upstream_bundle, expected_package_id=expected_package_id)

    paths = version_paths(config)
    source_km_path = root / paths.source_km_path
    source_po_path = root / paths.source_po_path
    previous_po = _previous_po_path(
        root=root,
        final_po_path=paths.final_po_path,
        source_po_path=paths.source_po_path,
        seed_po_path=seed_po_path,
    )
    source_km_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(upstream_bundle, source_km_path)
    catalog = build_catalog_from_km(
        km_path=source_km_path,
        output_path=source_po_path,
        target_language=config.translation.target_language,
        previous_po_path=previous_po,
    )
    build = build_translation_repository(
        repo_root=root,
        config_path=resolved_config,
        preserve_existing_translations=False,
    )
    return GitTranslationSourceResult(
        repository=config.knowledge_model.upstream_repository,
        ref=ref,
        upstream_bundle_path=upstream_bundle_path,
        source_km_path=source_km_path,
        source_po_path=source_po_path,
        package_id=expected_package_id,
        sha256=hashlib.sha256(source_km_path.read_bytes()).hexdigest(),
        catalog_entry_count=catalog.entry_count,
        carried_translation_count=catalog.carried_translation_count,
        build_result=build,
    )


def _validate_commit_ref(ref: str) -> None:
    if len(ref) != 40 or any(character not in "0123456789abcdef" for character in ref):
        raise GitTranslationSourceError(
            "knowledge_model.upstream_ref must be a full lowercase Git commit SHA"
        )


def _require_checkout_ref(*, source_root: Path, expected_ref: str) -> None:
    try:
        result = subprocess.run(
            ["git", "-C", str(source_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise GitTranslationSourceError(
            f"Unable to inspect source checkout {source_root}: {error}"
        ) from error
    actual_ref = result.stdout.strip()
    if actual_ref != expected_ref:
        raise GitTranslationSourceError(
            f"Source checkout is {actual_ref}, but config pins {expected_ref}"
        )


def _validate_bundle(*, bundle_path: Path, expected_package_id: str) -> None:
    try:
        DswModelsBundleAdapter.load_bundle_events(str(bundle_path))
        payload = json.loads(bundle_path.read_text(encoding="utf-8"))
    except (OSError, RuntimeError, ValueError) as error:
        raise GitTranslationSourceError(
            f"Pinned source bundle is not a valid DSW KM: {error}"
        ) from error
    actual_package_id = payload.get("id") if isinstance(payload, dict) else None
    if actual_package_id != expected_package_id:
        raise GitTranslationSourceError(
            f"Pinned source bundle is {actual_package_id!r}; expected {expected_package_id!r}"
        )


def _require_committed_bundle(
    *,
    source_root: Path,
    upstream_bundle_path: Path,
) -> None:
    try:
        tracked = subprocess.run(
            [
                "git",
                "-C",
                str(source_root),
                "ls-files",
                "--error-unmatch",
                upstream_bundle_path.as_posix(),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        unchanged = subprocess.run(
            [
                "git",
                "-C",
                str(source_root),
                "diff",
                "--quiet",
                "HEAD",
                "--",
                upstream_bundle_path.as_posix(),
            ],
            check=False,
        )
    except OSError as error:
        raise GitTranslationSourceError(
            f"Unable to inspect source bundle state: {error}"
        ) from error
    if tracked.returncode != 0:
        raise GitTranslationSourceError(
            f"Pinned source bundle is not tracked: {upstream_bundle_path}"
        )
    if unchanged.returncode != 0:
        raise GitTranslationSourceError(
            f"Source bundle differs from pinned commit: {upstream_bundle_path}"
        )


def _previous_po_path(
    *,
    root: Path,
    final_po_path: Path,
    source_po_path: Path,
    seed_po_path: Path | None,
) -> Path | None:
    final_po = root / final_po_path
    if final_po.is_file():
        return final_po
    source_po = root / source_po_path
    if source_po.is_file():
        return source_po
    if seed_po_path is None:
        return None
    seed_po = seed_po_path.resolve()
    if not seed_po.is_file():
        raise GitTranslationSourceError(f"Seed PO does not exist: {seed_po}")
    return seed_po
