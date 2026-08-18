"""Download and verify immutable DSW KM assets from GitHub Releases."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .translation_repository_config import normalize_version


class GitHubReleaseError(RuntimeError):
    """Raised when a pinned GitHub Release asset cannot be verified."""


Downloader = Callable[[str, str], bytes]
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class VerifiedKmRelease:
    """A KM release asset after tag, checksum, and identity validation."""

    repository: str
    ref: str
    asset_name: str
    checksum_asset_name: str
    package_id: str
    sha256: str
    payload: bytes


def download_verified_km_release(
    *,
    repository: str,
    ref: str,
    organization_id: str,
    km_id: str,
    version: str,
    tag_prefix: str = "v",
    token: str = "",
    api_url: str = "https://api.github.com",
    metadata_downloader: Downloader | None = None,
    asset_downloader: Downloader | None = None,
) -> VerifiedKmRelease:
    """Download one versioned KM asset and verify its sidecar checksum."""

    normalized_version = normalize_version(version)
    expected_ref = f"{tag_prefix}{normalized_version}"
    if ref != expected_ref:
        raise GitHubReleaseError(
            f"Pinned upstream ref must be {expected_ref!r} for version "
            f"{normalized_version}; got {ref!r}"
        )
    if not REPOSITORY_RE.fullmatch(repository):
        raise GitHubReleaseError(
            f"GitHub repository must use owner/name syntax; got {repository!r}"
        )

    metadata = _download_release_metadata(
        repository=repository,
        ref=ref,
        token=token,
        api_url=api_url,
        downloader=metadata_downloader or _download,
    )
    assets = metadata.get("assets")
    if not isinstance(assets, list):
        raise GitHubReleaseError(f"GitHub Release {repository}@{ref} has no asset list")

    asset_name = f"{organization_id}-{km_id}-{normalized_version}.km"
    checksum_asset_name = f"{asset_name}.sha256"
    published_names = {
        asset.get("name") for asset in assets if isinstance(asset, dict)
    }
    if asset_name not in published_names and checksum_asset_name not in published_names:
        # Releases created before the source-repository scaffold adopted its
        # organization-qualified asset stem remain valid dependencies.
        asset_name = f"{km_id}-{normalized_version}.km"
        checksum_asset_name = f"{asset_name}.sha256"

    download = asset_downloader or _download
    payload = download(
        _asset_url(assets=assets, name=asset_name, repository=repository, ref=ref),
        token,
    )
    checksum_payload = download(
        _asset_url(
            assets=assets,
            name=checksum_asset_name,
            repository=repository,
            ref=ref,
        ),
        token,
    )
    if not payload:
        raise GitHubReleaseError(f"GitHub Release asset is empty: {asset_name}")

    expected_sha = _parse_checksum(checksum_payload, checksum_asset_name)
    actual_sha = hashlib.sha256(payload).hexdigest()
    if actual_sha != expected_sha:
        raise GitHubReleaseError(
            f"Checksum mismatch for {repository}@{ref}/{asset_name}: "
            f"expected {expected_sha}, got {actual_sha}"
        )

    try:
        bundle = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GitHubReleaseError(f"KM release asset is not valid JSON: {asset_name}") from error
    if not isinstance(bundle, dict):
        raise GitHubReleaseError(f"KM release asset must contain a JSON object: {asset_name}")
    expected_package_id = f"{organization_id}:{km_id}:{normalized_version}"
    actual_package_id = bundle.get("id")
    if actual_package_id != expected_package_id:
        raise GitHubReleaseError(
            f"KM release identity mismatch: expected {expected_package_id!r}, "
            f"got {actual_package_id!r}"
        )

    return VerifiedKmRelease(
        repository=repository,
        ref=ref,
        asset_name=asset_name,
        checksum_asset_name=checksum_asset_name,
        package_id=expected_package_id,
        sha256=actual_sha,
        payload=payload,
    )


def _download_release_metadata(
    *,
    repository: str,
    ref: str,
    token: str,
    api_url: str,
    downloader: Downloader,
) -> dict[str, object]:
    url = f"{api_url.rstrip('/')}/repos/{repository}/releases/tags/{quote(ref, safe='')}"
    try:
        payload = json.loads(downloader(url, token))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GitHubReleaseError(
            f"GitHub Release metadata is not valid JSON: {repository}@{ref}"
        ) from error
    if not isinstance(payload, dict):
        raise GitHubReleaseError(
            f"GitHub Release metadata must contain an object: {repository}@{ref}"
        )
    if payload.get("tag_name") != ref:
        raise GitHubReleaseError(
            f"GitHub Release tag mismatch: expected {ref!r}, got {payload.get('tag_name')!r}"
        )
    if payload.get("draft") is True:
        raise GitHubReleaseError(f"GitHub Release is still a draft: {repository}@{ref}")
    return payload


def _asset_url(
    *,
    assets: list[object],
    name: str,
    repository: str,
    ref: str,
) -> str:
    matches = [
        asset.get("browser_download_url")
        for asset in assets
        if isinstance(asset, dict) and asset.get("name") == name
    ]
    if len(matches) != 1 or not isinstance(matches[0], str) or not matches[0]:
        raise GitHubReleaseError(
            f"Expected exactly one {name!r} asset in {repository}@{ref}; found {len(matches)}"
        )
    return matches[0]


def _parse_checksum(payload: bytes, asset_name: str) -> str:
    try:
        fields = payload.decode("utf-8").strip().split()
    except UnicodeDecodeError as error:
        raise GitHubReleaseError(f"Checksum asset is not UTF-8 text: {asset_name}") from error
    if not fields or not SHA256_RE.fullmatch(fields[0].lower()):
        raise GitHubReleaseError(f"Checksum asset has no valid SHA-256: {asset_name}")
    return fields[0].lower()


def _download(url: str, token: str) -> bytes:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "dsw-km-translation-tool",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token.strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=60) as response:
            return response.read()
    except (HTTPError, URLError, TimeoutError) as error:
        raise GitHubReleaseError(f"Unable to download {url}: {error}") from error
