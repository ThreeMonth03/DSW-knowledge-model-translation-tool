"""Synchronize a Git-authoritative translation repo with a pinned KM release."""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .dsw_models_adapter import DswModelsBundleAdapter
from .github_release import (
    Downloader,
    GitHubReleaseError,
    download_verified_km_release,
)
from .km_catalog import build_catalog_from_km
from .translation_repository_build import (
    TranslationRepositoryBuildResult,
    build_translation_repository,
)
from .translation_repository_config import (
    load_translation_repository_config,
    version_paths,
)


class GitHubTranslationSourceError(RuntimeError):
    """Raised when a pinned GitHub KM dependency cannot be synchronized."""


@dataclass(frozen=True)
class GitHubTranslationSourceResult:
    """Summary of a GitHub source dependency check or synchronization."""

    initialized: bool
    changed: bool
    checked_only: bool
    repository: str
    ref: str | None
    source_km_path: Path
    source_po_path: Path
    package_id: str | None
    sha256: str | None
    carried_translation_count: int
    build_result: TranslationRepositoryBuildResult | None


def sync_github_translation_source(
    *,
    repo_root: Path,
    config_path: Path = Path("translation-config.yml"),
    token: str = "",
    api_url: str = "https://api.github.com",
    check: bool = False,
    allow_unreleased: bool = False,
    metadata_downloader: Downloader | None = None,
    asset_downloader: Downloader | None = None,
) -> GitHubTranslationSourceResult:
    """Check or synchronize the KM pinned by a GitHub-only translation config."""

    root = repo_root.resolve()
    resolved_config = config_path if config_path.is_absolute() else root / config_path
    config = load_translation_repository_config(resolved_config)
    if config.workflow.mode != "github":
        raise GitHubTranslationSourceError(
            "GitHub source synchronization requires workflow.mode `github`"
        )

    paths = version_paths(config)
    source_km_path = root / paths.source_km_path
    source_po_path = root / paths.source_po_path
    ref = config.knowledge_model.upstream_ref
    if not ref or ref.upper() == "UNRELEASED":
        if allow_unreleased and not source_km_path.exists() and not source_po_path.exists():
            return GitHubTranslationSourceResult(
                initialized=False,
                changed=False,
                checked_only=check,
                repository=config.knowledge_model.upstream_repository,
                ref=ref,
                source_km_path=source_km_path,
                source_po_path=source_po_path,
                package_id=None,
                sha256=None,
                carried_translation_count=0,
                build_result=None,
            )
        raise GitHubTranslationSourceError(
            "knowledge_model.upstream_ref is UNRELEASED; no source KM may be synchronized yet"
        )

    try:
        release = download_verified_km_release(
            repository=config.knowledge_model.upstream_repository,
            ref=ref,
            organization_id=config.knowledge_model.organization_id,
            km_id=config.knowledge_model.km_id,
            version=config.knowledge_model.version,
            token=token,
            api_url=api_url,
            metadata_downloader=metadata_downloader,
            asset_downloader=asset_downloader,
        )
        _validate_official_schema(release.payload)
    except (GitHubReleaseError, OSError, RuntimeError, ValueError) as error:
        raise GitHubTranslationSourceError(str(error)) from error

    if check:
        if not source_km_path.is_file():
            raise GitHubTranslationSourceError(
                f"Pinned source KM is not checked in: {source_km_path}"
            )
        local_sha = hashlib.sha256(source_km_path.read_bytes()).hexdigest()
        if local_sha != release.sha256:
            raise GitHubTranslationSourceError(
                f"Checked-in source KM does not match {release.repository}@{release.ref}: "
                f"expected {release.sha256}, got {local_sha}"
            )
        return GitHubTranslationSourceResult(
            initialized=True,
            changed=False,
            checked_only=True,
            repository=release.repository,
            ref=release.ref,
            source_km_path=source_km_path,
            source_po_path=source_po_path,
            package_id=release.package_id,
            sha256=release.sha256,
            carried_translation_count=0,
            build_result=None,
        )

    previous_bytes = source_km_path.read_bytes() if source_km_path.is_file() else None
    changed = previous_bytes != release.payload
    _write_bytes_atomically(source_km_path, release.payload)
    previous_po = source_po_path if source_po_path.is_file() else None
    catalog = build_catalog_from_km(
        km_path=source_km_path,
        output_path=source_po_path,
        target_language=config.translation.target_language,
        previous_po_path=previous_po,
    )
    build = build_translation_repository(
        repo_root=root,
        config_path=resolved_config,
    )
    return GitHubTranslationSourceResult(
        initialized=True,
        changed=changed,
        checked_only=False,
        repository=release.repository,
        ref=release.ref,
        source_km_path=source_km_path,
        source_po_path=source_po_path,
        package_id=release.package_id,
        sha256=release.sha256,
        carried_translation_count=catalog.carried_translation_count,
        build_result=build,
    )


def _validate_official_schema(payload: bytes) -> None:
    with tempfile.TemporaryDirectory(prefix="dsw-km-release-") as temporary_dir:
        path = Path(temporary_dir) / "source.km"
        path.write_bytes(payload)
        DswModelsBundleAdapter.load_bundle_events(str(path))


def _write_bytes_atomically(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            handle.write(payload)
            temporary_path = Path(handle.name)
        temporary_path.replace(path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
