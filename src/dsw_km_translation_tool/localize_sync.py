"""Helpers for pulling Localize/Weblate PO snapshots into translation branches."""

from __future__ import annotations

import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .translation_repository_config import (
    _validate_https_url,
    load_translation_repository_config,
    require_localize_config,
    version_paths,
)

Downloader = Callable[[str], bytes]


@dataclass(frozen=True)
class LocalizePullResult:
    """Summary of one Localize PO pull."""

    version: str
    url: str
    latest_po_path: Path
    changed: bool
    initialized: bool
    bytes_downloaded: int


def pull_localize_po(
    *,
    config_path: Path,
    repo_root: Path,
    downloader: Downloader | None = None,
) -> LocalizePullResult:
    """Download and store the latest Localize PO snapshot.

    Args:
        config_path: Path to ``translation-config.yml``.
        repo_root: Translation repository checkout root.
        downloader: Optional injectable downloader used by tests.

    Returns:
        Pull summary.
    """

    repository_config = load_translation_repository_config(config_path)
    localize = require_localize_config(repository_config)
    version = repository_config.knowledge_model.version
    paths = version_paths(repository_config)
    latest_po_path = repo_root / paths.localize_latest_po_path
    url = localize.download_url
    download = downloader or _download_url
    downloaded = download(url)

    latest_exists = latest_po_path.exists()
    previous_latest = latest_po_path.read_bytes() if latest_exists else None
    if previous_latest == downloaded:
        return LocalizePullResult(
            version=version,
            url=url,
            latest_po_path=latest_po_path,
            changed=False,
            initialized=False,
            bytes_downloaded=len(downloaded),
        )

    latest_po_path.parent.mkdir(parents=True, exist_ok=True)
    latest_po_path.write_bytes(downloaded)

    return LocalizePullResult(
        version=version,
        url=url,
        latest_po_path=latest_po_path,
        changed=True,
        initialized=previous_latest is None,
        bytes_downloaded=len(downloaded),
    )


def _download_url(url: str) -> bytes:
    """Download one URL using the Python standard library."""

    _validate_https_url(url, "localize.download_url")
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()
