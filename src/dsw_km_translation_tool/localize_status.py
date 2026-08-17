"""Status reporting for Localize/Weblate PO snapshots."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

from .data_models import PoBlock
from .po import PoCatalogParser


@dataclass(frozen=True)
class LocalizePoReferenceStatus:
    """One KM reference attached to a Localize/Weblate PO block."""

    prefix: str
    uuid: str
    field: str
    comment: str


@dataclass(frozen=True)
class LocalizePoIssue:
    """One PO block that needs maintainer attention.

    Args:
        block_number: One-based PO block number in parser order.
        msgid: Source string.
        msgstr: Target string.
        references: KM references attached to the block.
    """

    block_number: int
    msgid: str
    msgstr: str
    references: tuple[LocalizePoReferenceStatus, ...]


@dataclass(frozen=True)
class LocalizePoStatusReport:
    """Summary metrics for a Localize/Weblate PO snapshot.

    Args:
        po_path: Source PO path used for the report.
        message_blocks: Number of parsed translatable PO blocks.
        references: Number of KM references covered by those blocks.
        filled_blocks: Number of blocks with a non-empty `msgstr`.
        empty_blocks: Number of blocks with an empty `msgstr`.
        fuzzy_blocks: Number of blocks marked with the PO `fuzzy` flag.
        accepted_blocks: Number of filled blocks that are not fuzzy.
        filled_references: Number of KM references covered by filled blocks.
        empty_references: Number of KM references covered by empty blocks.
        fuzzy_references: Number of KM references covered by fuzzy blocks.
        accepted_references: Number of KM references covered by accepted blocks.
        empty_issues: Empty PO blocks that need translation.
        fuzzy_issues: Fuzzy PO blocks that need review.
    """

    po_path: str
    message_blocks: int
    references: int
    filled_blocks: int
    empty_blocks: int
    fuzzy_blocks: int
    accepted_blocks: int
    filled_references: int
    empty_references: int
    fuzzy_references: int
    accepted_references: int
    empty_issues: tuple[LocalizePoIssue, ...]
    fuzzy_issues: tuple[LocalizePoIssue, ...]

    @property
    def filled_percent(self) -> float:
        """Return the percentage of PO blocks that have a non-empty translation."""

        return _percentage(self.filled_blocks, self.message_blocks)

    @property
    def accepted_percent(self) -> float:
        """Return the percentage of PO blocks that are filled and not fuzzy."""

        return _percentage(self.accepted_blocks, self.message_blocks)

    @property
    def empty_percent(self) -> float:
        """Return the percentage of PO blocks with empty translations."""

        return _percentage(self.empty_blocks, self.message_blocks)

    @property
    def fuzzy_percent(self) -> float:
        """Return the percentage of PO blocks marked as fuzzy."""

        return _percentage(self.fuzzy_blocks, self.message_blocks)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready dictionary with counts and percentages."""

        data = asdict(self)
        data.update(
            {
                "filledPercent": self.filled_percent,
                "acceptedPercent": self.accepted_percent,
                "emptyPercent": self.empty_percent,
                "fuzzyPercent": self.fuzzy_percent,
            }
        )
        return data


def build_localize_po_status_report(po_path: Path | str) -> LocalizePoStatusReport:
    """Build status metrics from one Localize/Weblate PO snapshot.

    Args:
        po_path: Path to the PO file to inspect.
    Returns:
        Aggregated status report.
    """

    resolved_po_path = Path(po_path).resolve()
    blocks = PoCatalogParser(str(resolved_po_path)).parse_blocks()

    filled_blocks = 0
    empty_blocks = 0
    fuzzy_blocks = 0
    accepted_blocks = 0
    filled_references = 0
    empty_references = 0
    fuzzy_references = 0
    accepted_references = 0
    empty_issues: list[LocalizePoIssue] = []
    fuzzy_issues: list[LocalizePoIssue] = []

    for block_number, block in enumerate(blocks, start=1):
        reference_count = len(block.references)
        has_translation = bool(block.msgstr.strip())
        if has_translation:
            filled_blocks += 1
            filled_references += reference_count
        else:
            empty_blocks += 1
            empty_references += reference_count
            empty_issues.append(_build_issue(block_number=block_number, block=block))

        if block.is_fuzzy:
            issue = _build_issue(block_number=block_number, block=block)
            fuzzy_blocks += 1
            fuzzy_references += reference_count
            fuzzy_issues.append(issue)
        elif has_translation:
            accepted_blocks += 1
            accepted_references += reference_count

    return LocalizePoStatusReport(
        po_path=str(resolved_po_path),
        message_blocks=len(blocks),
        references=sum(len(block.references) for block in blocks),
        filled_blocks=filled_blocks,
        empty_blocks=empty_blocks,
        fuzzy_blocks=fuzzy_blocks,
        accepted_blocks=accepted_blocks,
        filled_references=filled_references,
        empty_references=empty_references,
        fuzzy_references=fuzzy_references,
        accepted_references=accepted_references,
        empty_issues=tuple(empty_issues),
        fuzzy_issues=tuple(fuzzy_issues),
    )


def render_localize_po_status_markdown(
    report: LocalizePoStatusReport,
    issue_limit: int | None = 20,
) -> str:
    """Render a Localize/Weblate PO status report as Markdown.

    Args:
        report: Report to render.
        issue_limit: Maximum issue rows to show per issue type. Use `None` for
            all issue rows.
    """

    rows = [
        ("Total parsed PO messages", report.message_blocks, report.references),
        ("Filled msgstr", report.filled_blocks, report.filled_references),
        ("Empty msgstr", report.empty_blocks, report.empty_references),
        ("Fuzzy / needs editing", report.fuzzy_blocks, report.fuzzy_references),
        ("Filled and not fuzzy", report.accepted_blocks, report.accepted_references),
    ]
    lines = [
        "## Localize/Weblate PO Status",
        "",
        f"Source PO: `{report.po_path}`",
        "",
        "| Metric | Message blocks | KM references |",
        "| --- | ---: | ---: |",
    ]
    lines.extend(
        f"| {label} | {_format_int(blocks)} | {_format_int(references)} |"
        for label, blocks, references in rows
    )
    lines.extend(
        [
            "",
            "| Rate | Value |",
            "| --- | ---: |",
            f"| Filled blocks | {_format_percent(report.filled_percent)} |",
            f"| Empty blocks | {_format_percent(report.empty_percent)} |",
            f"| Fuzzy / needs editing blocks | {_format_percent(report.fuzzy_percent)} |",
            f"| Filled and not fuzzy blocks | {_format_percent(report.accepted_percent)} |",
            "",
            (
                "Note: Weblate exports entries that need editing through the PO "
                "`fuzzy` flag, so this report treats fuzzy entries as requiring "
                "human review."
            ),
        ]
    )
    lines.extend(
        _render_issue_section(
            "Fuzzy / Needs Editing Entries",
            report.fuzzy_issues,
            issue_limit,
        )
    )
    lines.extend(
        _render_issue_section("Empty Translation Entries", report.empty_issues, issue_limit)
    )
    return "\n".join(lines) + "\n"


def write_localize_po_status_json(
    report: LocalizePoStatusReport,
    output_path: Path | str,
) -> None:
    """Write a status report to JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_localize_po_status_markdown(
    report: LocalizePoStatusReport,
    output_path: Path | str,
    issue_limit: int | None = 20,
) -> None:
    """Append a status report to a Markdown file."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    elif path.is_symlink():
        raise ValueError(f"Refusing to write Markdown report through symlink: {path}")
    descriptor = os.open(path, flags, 0o666)
    with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
        handle.write(render_localize_po_status_markdown(report, issue_limit=issue_limit))


def _build_issue(block_number: int, block: PoBlock) -> LocalizePoIssue:
    """Build an actionable status issue from one PO block."""

    return LocalizePoIssue(
        block_number=block_number,
        msgid=block.msgid,
        msgstr=block.msgstr,
        references=tuple(
            LocalizePoReferenceStatus(
                prefix=reference.prefix,
                uuid=reference.uuid,
                field=reference.field,
                comment=reference.comment,
            )
            for reference in block.references
        ),
    )


def _render_issue_section(
    title: str,
    issues: tuple[LocalizePoIssue, ...],
    issue_limit: int | None,
) -> list[str]:
    """Render one actionable issue table."""

    lines = ["", f"### {title}", ""]
    if not issues:
        lines.append("No entries.")
        return lines

    visible_issues = issues if issue_limit is None else issues[:issue_limit]
    lines.extend(
        [
            "| PO block | References | Source | Translation |",
            "| ---: | --- | --- | --- |",
        ]
    )
    for issue in visible_issues:
        lines.append(
            "| "
            f"{issue.block_number} | "
            f"{_format_references(issue.references)} | "
            f"{_format_markdown_cell(issue.msgid)} | "
            f"{_format_markdown_cell(issue.msgstr)} |"
        )
    hidden_count = len(issues) - len(visible_issues)
    if hidden_count > 0:
        lines.extend(["", f"... and {hidden_count} more entries."])
    return lines


def _percentage(part: int, total: int) -> float:
    """Return a rounded percentage, avoiding division by zero."""

    if total == 0:
        return 0.0
    return round((part / total) * 100, 2)


def _format_int(value: int) -> str:
    """Format an integer for Markdown tables."""

    return f"{value:,}"


def _format_percent(value: float) -> str:
    """Format a percentage for Markdown tables."""

    return f"{value:.2f}%"


def _format_references(references: tuple[LocalizePoReferenceStatus, ...]) -> str:
    """Format issue references for a compact Markdown table cell."""

    return "<br>".join(
        _format_markdown_cell(reference.comment, limit=80) for reference in references
    )


def _format_markdown_cell(value: str, limit: int = 120) -> str:
    """Format text for one Markdown table cell."""

    collapsed = " ".join(value.split())
    if len(collapsed) > limit:
        collapsed = f"{collapsed[: limit - 1]}..."
    return collapsed.replace("|", "\\|")
