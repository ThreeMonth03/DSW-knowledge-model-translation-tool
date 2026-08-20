"""Tests for Localize/Weblate PO source pulls."""

from __future__ import annotations

import io
import sys
import urllib.error
import urllib.request
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

import pytest

from dsw_km_translation_tool.cli import sync_from_localize
from dsw_km_translation_tool.localize_sync import (
    LocalizePullResult,
    _download_url,
    _SameOriginHttpsRedirectHandler,
    pull_localize_po,
)
from dsw_km_translation_tool.translation_repository_config import (
    TranslationRepositoryConfigError,
)
from tests.infra.test_translation_repository_config import write_config


class _FakeResponse:
    """Small context-managed response used by downloader retry tests."""

    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> bool:
        return False

    def read(self) -> bytes:
        return self._payload


class _SequenceOpener:
    """Return or raise deterministic outcomes for successive open calls."""

    def __init__(self, outcomes: list[object]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def open(self, _url: str, *, timeout: int):
        assert timeout == 60
        self.calls += 1
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _http_error(url: str, code: int, *, retry_after: str | None = None):
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        url,
        code,
        "test HTTP failure",
        headers,
        io.BytesIO(),
    )


def test_pull_localize_po_initializes_latest(workspace: Path) -> None:
    """Verify the first pull writes the latest Weblate snapshot."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    result = pull_localize_po(
        config_path=config_path,
        repo_root=workspace,
        downloader=lambda _url: b"new po",
    )

    assert result.changed is True
    assert result.initialized is True
    assert result.latest_po_path.read_bytes() == b"new po"


def test_downloader_rejects_local_file_urls() -> None:
    """Verify the standard downloader cannot read runner-local files."""

    with pytest.raises(TranslationRepositoryConfigError, match="must be an HTTPS URL"):
        _download_url("file:///tmp/runner-secret")


def test_downloader_retries_transient_http_failures() -> None:
    """A short Localize 502/503 outage should not fail the whole scheduled smoke."""

    url = "https://localize.example.test/download/latest.po"
    opener = _SequenceOpener(
        [
            _http_error(url, 502),
            _http_error(url, 503, retry_after="3"),
            _FakeResponse(b'msgid "ready"\n'),
        ]
    )
    sleeps: list[float] = []

    payload = _download_url(url, opener=opener, sleep=sleeps.append)

    assert payload == b'msgid "ready"\n'
    assert opener.calls == 3
    assert sleeps == [1.0, 3.0]


def test_downloader_does_not_retry_non_transient_http_failures() -> None:
    """Authentication and missing-resource failures must remain fail-fast."""

    url = "https://localize.example.test/download/latest.po"
    opener = _SequenceOpener([_http_error(url, 404)])
    sleeps: list[float] = []

    with pytest.raises(urllib.error.HTTPError) as error_info:
        _download_url(url, opener=opener, sleep=sleeps.append)

    assert error_info.value.code == 404
    assert opener.calls == 1
    assert sleeps == []


def test_downloader_stops_after_configured_transient_attempts() -> None:
    """Persistent upstream failure remains visible after bounded retries."""

    url = "https://localize.example.test/download/latest.po"
    opener = _SequenceOpener(
        [
            _http_error(url, 502),
            _http_error(url, 502),
            _http_error(url, 502),
        ]
    )
    sleeps: list[float] = []

    with pytest.raises(urllib.error.HTTPError) as error_info:
        _download_url(
            url,
            max_attempts=3,
            opener=opener,
            sleep=sleeps.append,
        )

    assert error_info.value.code == 502
    assert opener.calls == 3
    assert sleeps == [1.0, 2.0]


def test_redirect_handler_allows_same_origin_https_redirect() -> None:
    """A normal relative redirect on the configured Localize origin is allowed."""

    request = urllib.request.Request("https://localize.example.test/download/latest.po")
    handler = _SameOriginHttpsRedirectHandler(request.full_url)

    redirected = handler.redirect_request(
        request,
        None,
        302,
        "Found",
        {},
        "/downloads/current.po",
    )

    assert redirected is not None
    assert redirected.full_url == "https://localize.example.test/downloads/current.po"


def test_redirect_handler_rejects_https_downgrade() -> None:
    """An HTTPS endpoint cannot redirect the downloader to an HTTP resource."""

    request = urllib.request.Request("https://localize.example.test/download/latest.po")
    handler = _SameOriginHttpsRedirectHandler(request.full_url)

    with pytest.raises(TranslationRepositoryConfigError, match="must be an HTTPS URL"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "http://localize.example.test/internal",
        )


def test_redirect_handler_rejects_cross_origin_redirect() -> None:
    """A configured endpoint cannot bounce the downloader to another HTTPS host."""

    request = urllib.request.Request("https://localize.example.test/download/latest.po")
    handler = _SameOriginHttpsRedirectHandler(request.full_url)

    with pytest.raises(TranslationRepositoryConfigError, match="original HTTPS origin"):
        handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://attacker.example.test/redirected.po",
        )


def test_pull_localize_po_uses_configured_rolling_download_url(
    workspace: Path,
) -> None:
    """Verify Localize pulls use the rolling project URL from config."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path, version="2.8.0")
    requested_urls: list[str] = []

    result = pull_localize_po(
        config_path=config_path,
        repo_root=workspace,
        downloader=lambda url: requested_urls.append(url) or b"new po",
    )

    expected_url = (
        "https://localize.ds-wizard.org/download/knowledge-models/"
        "common-dsw-knowledge-model/zh_Hant/"
    )
    assert requested_urls == [expected_url]
    assert result.url == expected_url


def test_pull_localize_po_replaces_previous_latest(workspace: Path) -> None:
    """Verify changed pulls replace the checked-in Weblate snapshot."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    latest_path = workspace / "sources/localize/zh_Hant/latest.po"
    latest_path.parent.mkdir(parents=True)
    latest_path.write_bytes(b"old latest")

    result = pull_localize_po(
        config_path=config_path,
        repo_root=workspace,
        downloader=lambda _url: b"new latest",
    )

    assert result.changed is True
    assert result.initialized is False
    assert latest_path.read_bytes() == b"new latest"


def test_pull_localize_po_noops_when_latest_is_unchanged(workspace: Path) -> None:
    """Verify unchanged pulls leave the checked-in snapshot untouched."""

    config_path = workspace / "translation-config.yml"
    write_config(config_path)
    latest_path = workspace / "sources/localize/zh_Hant/latest.po"
    latest_path.parent.mkdir(parents=True)
    latest_path.write_bytes(b"same")

    result = pull_localize_po(
        config_path=config_path,
        repo_root=workspace,
        downloader=lambda _url: b"same",
    )

    assert result.changed is False
    assert result.initialized is False
    assert latest_path.read_bytes() == b"same"


def test_sync_from_localize_runs_pull_refresh_and_commit(
    monkeypatch,
    workspace: Path,
) -> None:
    """Verify the Localize sync CLI wires its three explicit phases."""

    host_repo = workspace / "translation-repo"
    tooling_repo = workspace / "tooling-repo"
    host_repo.mkdir()
    tooling_repo.mkdir()
    write_config(host_repo / "translation-config.yml")
    recorded_config: dict[str, object] = {}

    def fake_pull_localize_po(**kwargs):
        assert set(kwargs) == {"config_path", "repo_root"}
        return LocalizePullResult(
            version="2.7.0",
            url="https://example.test/localize.po",
            latest_po_path=host_repo / "sources/localize/zh_Hant/latest.po",
            changed=False,
            initialized=False,
            bytes_downloaded=0,
        )

    def fake_build_repository_ci_sync_config(**kwargs):
        recorded_config.update(kwargs)
        return object()

    def fake_refresh_tree_from_localize(**_kwargs):
        return SimpleNamespace(
            version="2.7.0",
            tree_dir=host_repo / "tree",
            folder_count=0,
            root_count=0,
            shared_block_file_count=0,
        )

    monkeypatch.setattr(sync_from_localize, "pull_localize_po", fake_pull_localize_po)
    monkeypatch.setattr(
        sync_from_localize,
        "build_repository_ci_sync_config",
        fake_build_repository_ci_sync_config,
    )
    monkeypatch.setattr(
        sync_from_localize,
        "refresh_tree_from_localize",
        fake_refresh_tree_from_localize,
    )
    monkeypatch.setattr(sync_from_localize, "run_ci_sync_commit", lambda _config: False)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "dsw-km-sync-localize",
            "--host-repo",
            str(host_repo),
            "--tooling-repo",
            str(tooling_repo),
            "--mode",
            "pull_request",
        ],
    )

    sync_from_localize.main()

    assert recorded_config["host_repo_path"] == host_repo
    assert recorded_config["mode"] == "pull_request"
