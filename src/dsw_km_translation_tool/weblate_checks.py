"""Read-only Weblate check reporting helpers."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .http_auth import bearer_authorization_header
from .localize_sync import Downloader, _download_url
from .translation_repository_config import (
    load_translation_repository_config,
    require_localize_config,
)


@dataclass(frozen=True)
class WeblateCheckIssue:
    """One Weblate unit returned by a check query."""

    unit_id: int | None
    source: tuple[str, ...]
    target: tuple[str, ...]
    state: int | None
    context: str
    api_url: str


@dataclass(frozen=True)
class WeblateChecksReport:
    """Summary of Weblate units matching a check query."""

    api_url: str
    query: str
    count: int
    issues: tuple[WeblateCheckIssue, ...]
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Return whether the Weblate API query succeeded."""

        return self.error is None

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation."""

        data = asdict(self)
        data["ok"] = self.ok
        return data


def build_weblate_checks_report(
    *,
    repo_root: Path,
    config_path: Path,
    query: str = "has:check",
    page_size: int = 100,
    api_token: str = "",
    downloader: Downloader | None = None,
) -> WeblateChecksReport:
    """Query Weblate units matching a check expression.

    Args:
        repo_root: Translation repository root.
        config_path: Path to ``translation-config.yml``.
        query: Weblate unit search expression.
        page_size: API page size.
        api_token: Optional Weblate API token. Empty values use anonymous API access.
        downloader: Optional injectable downloader used by tests.

    Returns:
        Structured Weblate check report.
    """

    api_url = resolve_weblate_units_api_url(
        repo_root=repo_root,
        config_path=config_path,
        query=query,
        page_size=page_size,
    )
    download = downloader or _authenticated_downloader(api_token) or _download_url
    issues: list[WeblateCheckIssue] = []
    next_url: str | None = api_url
    total_count = 0
    while next_url:
        payload = _download_json(next_url, download)
        total_count = int(payload.get("count") or 0)
        for unit in payload.get("results", ()):
            if isinstance(unit, dict):
                issues.append(_build_issue(unit))
        next_url = payload.get("next") if isinstance(payload.get("next"), str) else None

    return WeblateChecksReport(
        api_url=api_url,
        query=query,
        count=total_count,
        issues=tuple(issues),
    )


def build_weblate_checks_error_report(
    *,
    repo_root: Path,
    config_path: Path,
    query: str,
    error: Exception,
) -> WeblateChecksReport:
    """Build a non-blocking report when Weblate check querying fails."""

    try:
        api_url = resolve_weblate_units_api_url(
            repo_root=repo_root,
            config_path=config_path,
            query=query,
        )
    except Exception:
        api_url = ""
    return WeblateChecksReport(
        api_url=api_url,
        query=query,
        count=0,
        issues=(),
        error=str(error),
    )


def resolve_weblate_units_api_url(
    *,
    repo_root: Path,
    config_path: Path,
    query: str = "has:check",
    page_size: int = 100,
) -> str:
    """Resolve the Weblate units API URL from a Localize download URL."""

    resolved_config_path = config_path if config_path.is_absolute() else repo_root / config_path
    repository_config = load_translation_repository_config(resolved_config_path)
    localize = require_localize_config(repository_config)
    parsed_url = urllib.parse.urlparse(localize.download_url)
    path_parts = [part for part in parsed_url.path.split("/") if part]
    try:
        download_index = path_parts.index("download")
        project, component, language = path_parts[download_index + 1 : download_index + 4]
    except (ValueError, IndexError) as error:
        raise ValueError(
            "Cannot derive Weblate API coordinates from localize.download_url"
        ) from error

    api_path = f"/api/translations/{project}/{component}/{language}/units/"
    query_params = urllib.parse.urlencode({"q": query, "page_size": str(page_size)})
    return urllib.parse.urlunparse(
        (
            parsed_url.scheme,
            parsed_url.netloc,
            api_path,
            "",
            query_params,
            "",
        )
    )


def render_weblate_checks_markdown(
    report: WeblateChecksReport,
    issue_limit: int | None = 20,
) -> str:
    """Render Weblate check status as Markdown."""

    lines = [
        "## Weblate Check Status",
        "",
        f"API URL: `{report.api_url}`",
        f"Query: `{report.query}`",
        f"Status: **{'ok' if report.ok else 'unavailable'}**",
        f"Matching units: **{report.count}**",
        "",
    ]
    if report.error:
        lines.extend(
            [
                "### API Error",
                "",
                _format_markdown_cell(report.error, limit=500),
                "",
                (
                    "This report is diagnostic only. Weblate API rate limits or "
                    "temporary errors should not block Git synchronization."
                ),
            ]
        )
        return "\n".join(lines) + "\n"

    if not report.issues:
        lines.append("No Weblate units currently match this query.")
        return "\n".join(lines) + "\n"

    visible_issues = report.issues if issue_limit is None else report.issues[:issue_limit]
    lines.extend(
        [
            "| Unit | State | Source | Target | API |",
            "| ---: | ---: | --- | --- | --- |",
        ]
    )
    for issue in visible_issues:
        lines.append(
            "| "
            f"{issue.unit_id or ''} | "
            f"{issue.state if issue.state is not None else ''} | "
            f"{_format_markdown_cell(' / '.join(issue.source))} | "
            f"{_format_markdown_cell(' / '.join(issue.target))} | "
            f"{_format_markdown_cell(issue.api_url, limit=80)} |"
        )
    hidden_count = len(report.issues) - len(visible_issues)
    if hidden_count > 0:
        lines.extend(["", f"... and {hidden_count} more units."])
    return "\n".join(lines) + "\n"


def write_weblate_checks_json(
    report: WeblateChecksReport,
    output_path: Path | str,
) -> None:
    """Write a Weblate checks report to JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_weblate_checks_markdown(
    report: WeblateChecksReport,
    output_path: Path | str,
    issue_limit: int | None = 20,
) -> None:
    """Append a Weblate checks report to Markdown."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(render_weblate_checks_markdown(report, issue_limit=issue_limit))


def _download_json(url: str, downloader: Downloader) -> dict[str, Any]:
    """Download and parse one JSON API response."""

    payload = json.loads(downloader(url).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object from Weblate API: {url}")
    return payload


def _authenticated_downloader(token: str) -> Downloader | None:
    """Build an authenticated downloader when a token is available."""

    if not token.strip():
        return None

    def download(url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"Authorization": bearer_authorization_header(token)},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()

    return download


def _build_issue(unit: dict[str, Any]) -> WeblateCheckIssue:
    """Build an issue from one Weblate unit payload."""

    return WeblateCheckIssue(
        unit_id=unit.get("id") if isinstance(unit.get("id"), int) else None,
        source=_string_tuple(unit.get("source")),
        target=_string_tuple(unit.get("target")),
        state=unit.get("state") if isinstance(unit.get("state"), int) else None,
        context=unit.get("context") if isinstance(unit.get("context"), str) else "",
        api_url=unit.get("url") if isinstance(unit.get("url"), str) else "",
    )


def _string_tuple(value: Any) -> tuple[str, ...]:
    """Normalize Weblate string-list fields."""

    if isinstance(value, list):
        return tuple(item for item in value if isinstance(item, str))
    if isinstance(value, str):
        return (value,)
    return ()


def _format_markdown_cell(value: str, limit: int = 120) -> str:
    """Format text for one Markdown table cell."""

    collapsed = " ".join(value.split())
    if len(collapsed) > limit:
        collapsed = f"{collapsed[: limit - 1]}..."
    return collapsed.replace("|", "\\|")
