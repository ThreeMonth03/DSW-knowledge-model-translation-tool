"""Helpers for pulling Localize/Weblate PO snapshots into translation branches."""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from .translation_repository_config import (
    TranslationRepositoryConfigError,
    _validate_https_url,
    load_translation_repository_config,
    require_localize_config,
    version_paths,
)

Downloader = Callable[[str], bytes]
_LOGGER = logging.getLogger(__name__)
_RETRYABLE_HTTP_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
_DEFAULT_DOWNLOAD_ATTEMPTS = 5
_MAX_RETRY_DELAY_SECONDS = 30.0


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


class _SameOriginHttpsRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Permit redirects only within the download URL's original HTTPS origin."""

    def __init__(self, trusted_url: str) -> None:
        self._trusted_origin = _url_origin(trusted_url)
        super().__init__()

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Validate a redirect before urllib sends the follow-up request."""

        resolved_url = urllib.parse.urljoin(req.full_url, newurl)
        _validate_https_url(resolved_url, "localize.download_url redirect")
        if _url_origin(resolved_url) != self._trusted_origin:
            raise TranslationRepositoryConfigError(
                "localize.download_url redirects must remain on the original HTTPS origin"
            )
        return super().redirect_request(req, fp, code, msg, headers, resolved_url)


def _url_origin(url: str) -> tuple[str, str, int]:
    """Return a normalized HTTPS origin for redirect comparison."""

    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise TranslationRepositoryConfigError(
            "localize.download_url contains an invalid port"
        ) from exc
    return parsed.scheme.lower(), (parsed.hostname or "").lower(), port or 443


def _download_url(
    url: str,
    *,
    max_attempts: int = _DEFAULT_DOWNLOAD_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
    opener: urllib.request.OpenerDirector | None = None,
) -> bytes:
    """Download one URL, retrying transient failures without relaxing URL safety."""

    _validate_https_url(url, "localize.download_url")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    trusted_opener = opener or urllib.request.build_opener(
        _SameOriginHttpsRedirectHandler(url)
    )
    for attempt in range(1, max_attempts + 1):
        try:
            with trusted_opener.open(url, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in _RETRYABLE_HTTP_STATUS_CODES or attempt == max_attempts:
                raise
            delay = _retry_delay_seconds(
                attempt=attempt,
                retry_after=error.headers.get("Retry-After") if error.headers else None,
            )
            error.close()
            _LOGGER.warning(
                "Localize download returned HTTP %s; retrying attempt %s/%s in %.1fs",
                error.code,
                attempt + 1,
                max_attempts,
                delay,
            )
        except (urllib.error.URLError, TimeoutError) as error:
            if attempt == max_attempts:
                raise
            delay = _retry_delay_seconds(attempt=attempt, retry_after=None)
            _LOGGER.warning(
                "Localize download failed temporarily (%s); retrying attempt %s/%s in %.1fs",
                error,
                attempt + 1,
                max_attempts,
                delay,
            )
        sleep(delay)

    raise AssertionError("Localize download retry loop exited unexpectedly")


def _retry_delay_seconds(*, attempt: int, retry_after: str | None) -> float:
    """Return a bounded Retry-After or exponential-backoff delay."""

    if retry_after:
        try:
            seconds = float(retry_after)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(retry_after)
            except (TypeError, ValueError, OverflowError):
                retry_at = None
            if retry_at is not None:
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
            else:
                seconds = -1.0
        if seconds >= 0:
            return min(seconds, _MAX_RETRY_DELAY_SECONDS)

    return min(float(2 ** (attempt - 1)), 8.0)
