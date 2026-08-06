"""Detect and prepare GitHub-originated translation contributions."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from .command import CommandRunner, default_command_runner, make_checked_runner
from .constants import MANIFEST_NAME, TRANSLATION_FILENAME, UUID_FILENAME
from .po_support.render import PoSectionRenderer
from .po_support.state import PoEntryState, parse_po_entry_states
from .shared_block_consistency import (
    SharedBlockConsistencyIssue,
    find_shared_block_consistency_issues,
)
from .translation_format import compare_markdown_format
from .tree_support.document import TranslationMarkdownDocument

PoKey = tuple[str, str]

HEADER_UUID_RE = re.compile(r"^- UUID: `(?P<uuid>[^`]+)`$", re.MULTILINE)
IMPORT_DECISION = "import-to-weblate"
ALREADY_IMPORTED_DECISION = "already-in-weblate"
CONFLICT_DECISION = "conflict"
MISSING_WEBLATE_DECISION = "missing-weblate-entry"
SOURCE_MISMATCH_DECISION = "source-mismatch"
REMOVED_DECISION = "removed-in-git"


class GitHubTranslationContributionError(RuntimeError):
    """Raised when GitHub translation contribution analysis cannot complete."""


_run_checked = make_checked_runner(
    GitHubTranslationContributionError,
    include_command=True,
)


@dataclass(frozen=True)
class TreeTranslationEntry:
    """One translation field read from a Git translation tree."""

    uuid: str
    field: str
    source: str
    target: str
    path: str

    @property
    def key(self) -> PoKey:
        """Return the PO key for this tree translation."""

        return (self.uuid, self.field)


@dataclass(frozen=True)
class GitHubTranslationDecision:
    """Decision for one GitHub-originated translation change."""

    uuid: str
    field: str
    path: str
    decision: str
    source: str
    base: str
    github: str
    weblate: str
    format_issues: tuple[str, ...]

    @property
    def key(self) -> PoKey:
        """Return the PO key for this decision."""

        return (self.uuid, self.field)

    @property
    def has_format_errors(self) -> bool:
        """Return whether the GitHub translation lost Markdown structure."""

        return bool(self.format_issues)


@dataclass(frozen=True)
class GitHubTranslationReport:
    """Summary of GitHub translation changes against current Weblate state."""

    base_ref: str
    head_ref: str
    latest_po_path: Path
    changed_entries: int
    importable_entries: int
    already_imported_entries: int
    conflict_entries: int
    format_error_entries: int
    shared_block_issues: tuple[SharedBlockConsistencyIssue, ...]
    decisions: tuple[GitHubTranslationDecision, ...]

    @property
    def has_translation_changes(self) -> bool:
        """Return whether GitHub changed any translation entry."""

        return self.changed_entries > 0

    @property
    def has_conflicts(self) -> bool:
        """Return whether any GitHub translation change needs human review."""

        return self.conflict_entries > 0

    @property
    def has_format_errors(self) -> bool:
        """Return whether changed translations contain Markdown format errors."""

        return self.format_error_entries > 0

    @property
    def has_shared_block_errors(self) -> bool:
        """Return whether canonical shared translations disagree with the tree."""

        return bool(self.shared_block_issues)

    @property
    def importable_decisions(self) -> tuple[GitHubTranslationDecision, ...]:
        """Return decisions that should be uploaded to Weblate."""

        return tuple(
            decision
            for decision in self.decisions
            if decision.decision == IMPORT_DECISION and not decision.has_format_errors
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation."""

        data = asdict(self)
        data["latest_po_path"] = str(self.latest_po_path)
        data["has_translation_changes"] = self.has_translation_changes
        data["has_conflicts"] = self.has_conflicts
        data["has_format_errors"] = self.has_format_errors
        data["has_shared_block_errors"] = self.has_shared_block_errors
        return data


def build_github_translation_report(
    *,
    repo_root: Path,
    base_ref: str,
    head_ref: str,
    latest_po_path: Path,
    tree_path: Path = Path("tree"),
    source_lang: str = "en",
    target_lang: str = "zh_Hant",
    runner: CommandRunner = default_command_runner,
) -> GitHubTranslationReport:
    """Compare GitHub translation changes with the current Weblate PO.

    Args:
        repo_root: Translation repository checkout root.
        base_ref: Git ref representing the accepted base state.
        head_ref: Git ref containing the candidate GitHub translation changes.
        latest_po_path: Current Weblate PO snapshot.
        tree_path: Translation tree path relative to ``repo_root``.
        source_lang: Source language code used in translation markdown headings.
        target_lang: Target language code used in translation markdown headings.
        runner: Injectable command runner.

    Returns:
        Structured report with one decision per changed translation entry.
    """

    base_entries = read_tree_entries_from_git_ref(
        repo_root=repo_root,
        ref=base_ref,
        tree_path=tree_path,
        source_lang=source_lang,
        target_lang=target_lang,
        runner=runner,
    )
    head_entries = read_tree_entries_from_git_ref(
        repo_root=repo_root,
        ref=head_ref,
        tree_path=tree_path,
        source_lang=source_lang,
        target_lang=target_lang,
        runner=runner,
    )
    weblate_entries = parse_po_entry_states(latest_po_path)
    decisions = tuple(
        _build_decision(
            key=key,
            base_entry=base_entries.get(key),
            head_entry=head_entries.get(key),
            weblate_entry=weblate_entries.get(key),
        )
        for key in sorted(set(base_entries) | set(head_entries))
        if _target_text(base_entries.get(key)) != _target_text(head_entries.get(key))
    )
    shared_block_issues = find_shared_block_consistency_issues(
        repo_root=repo_root,
        base_ref=base_ref,
        head_ref=head_ref,
        head_targets={key: entry.target for key, entry in head_entries.items()},
        tree_path=tree_path,
        target_lang=target_lang,
        runner=runner,
    )
    return _build_report(
        base_ref=base_ref,
        head_ref=head_ref,
        latest_po_path=latest_po_path,
        decisions=decisions,
        shared_block_issues=shared_block_issues,
    )


def read_tree_entries_from_git_ref(
    *,
    repo_root: Path,
    ref: str,
    tree_path: Path = Path("tree"),
    source_lang: str = "en",
    target_lang: str = "zh_Hant",
    runner: CommandRunner = default_command_runner,
) -> dict[PoKey, TreeTranslationEntry]:
    """Read translation entries from ``translation.md`` files at a Git ref."""

    relative_tree = tree_path.as_posix()
    result = _run_checked(
        runner,
        ["git", "ls-tree", "-r", "--name-only", ref, "--", relative_tree],
        cwd=repo_root,
        description=f"list translation files in {ref}",
    )
    manifest_path = (tree_path / MANIFEST_NAME).as_posix()
    manifest = _load_tree_manifest(
        repo_root=repo_root,
        ref=ref,
        path=manifest_path,
        runner=runner,
    )
    canonical_paths = _canonical_translation_paths(manifest, relative_tree, manifest_path)
    entries: dict[PoKey, TreeTranslationEntry] = {}
    for path_text in result.stdout.splitlines():
        if not path_text.endswith(f"/{TRANSLATION_FILENAME}"):
            continue
        entity_uuid = canonical_paths.get(path_text)
        if entity_uuid is None:
            raise GitHubTranslationContributionError(
                f"Translation file is not a canonical manifest node in {ref}: {path_text}"
            )
        uuid_path = str(PurePosixPath(path_text).with_name(UUID_FILENAME))
        stored_uuid = _git_show_text(
            repo_root=repo_root,
            ref=ref,
            path=uuid_path,
            runner=runner,
        ).strip()
        if stored_uuid != entity_uuid:
            raise GitHubTranslationContributionError(
                f"UUID metadata mismatch in {ref}: {uuid_path} contains {stored_uuid!r}, "
                f"expected {entity_uuid!r}"
            )
        document_text = _git_show_text(
            repo_root=repo_root,
            ref=ref,
            path=path_text,
            runner=runner,
        )
        parsed_entries = parse_translation_markdown_text(
            document_text,
            path_text,
            source_lang=source_lang,
            target_lang=target_lang,
        )
        if any(entry.uuid != entity_uuid for entry in parsed_entries):
            raise GitHubTranslationContributionError(
                f"UUID header mismatch in {ref}: {path_text} does not represent "
                f"manifest node {entity_uuid}"
            )
        for entry in parsed_entries:
            if entry.key in entries:
                previous = entries[entry.key]
                raise GitHubTranslationContributionError(
                    f"Duplicate translation key {entry.uuid}:{entry.field} in {ref}: "
                    f"{previous.path} and {entry.path}"
                )
            entries[entry.key] = entry
    return entries


def _load_tree_manifest(
    *, repo_root: Path, ref: str, path: str, runner: CommandRunner
) -> dict[str, object]:
    """Load the canonical translation-tree manifest at a Git ref."""

    text = _git_show_text(repo_root=repo_root, ref=ref, path=path, runner=runner)
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GitHubTranslationContributionError(
            f"Invalid translation tree manifest in {ref}: {path}: {exc}"
        ) from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("nodes"), dict):
        raise GitHubTranslationContributionError(
            f"Invalid translation tree manifest in {ref}: {path} must contain a nodes object"
        )
    return manifest


def _canonical_translation_paths(
    manifest: dict[str, object], relative_tree: str, manifest_path: str
) -> dict[str, str]:
    """Map manifest-authorized translation paths to their node UUIDs."""

    paths: dict[str, str] = {}
    nodes = manifest["nodes"]
    assert isinstance(nodes, dict)
    for entity_uuid, node in nodes.items():
        if not isinstance(entity_uuid, str) or not isinstance(node, dict):
            raise GitHubTranslationContributionError(
                f"Invalid node entry in translation tree manifest: {manifest_path}"
            )
        node_path = node.get("path")
        if not isinstance(node_path, str) or not node_path:
            raise GitHubTranslationContributionError(
                f"Invalid path for manifest node {entity_uuid}: {manifest_path}"
            )
        relative_path = PurePosixPath(node_path)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise GitHubTranslationContributionError(
                f"Unsafe path for manifest node {entity_uuid}: {node_path}"
            )
        translation_path = str(PurePosixPath(relative_tree) / relative_path / TRANSLATION_FILENAME)
        if translation_path in paths:
            raise GitHubTranslationContributionError(
                f"Duplicate node path in translation tree manifest: {node_path}"
            )
        paths[translation_path] = entity_uuid
    return paths


def parse_translation_markdown_text(
    markdown_text: str,
    path: str,
    *,
    source_lang: str = "en",
    target_lang: str = "zh_Hant",
) -> tuple[TreeTranslationEntry, ...]:
    """Parse one ``translation.md`` document into field-level entries."""

    uuid_match = HEADER_UUID_RE.search(markdown_text)
    if uuid_match is None:
        raise GitHubTranslationContributionError(
            f"Missing UUID metadata header in translation markdown: {path}"
        )
    entity_uuid = uuid_match.group("uuid")
    fields = TranslationMarkdownDocument(
        source_lang=source_lang,
        target_lang=target_lang,
    ).parse_text(markdown_text, path)
    return tuple(
        TreeTranslationEntry(
            uuid=entity_uuid,
            field=field,
            source=state.source_text,
            target=state.target_text,
            path=path,
        )
        for field, state in fields.items()
    )


def write_github_translation_json(
    report: GitHubTranslationReport,
    output_path: Path | str,
) -> None:
    """Write a GitHub translation report to JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_github_translation_markdown(
    report: GitHubTranslationReport,
    output_path: Path | str,
    *,
    limit: int | None = 50,
) -> None:
    """Write a GitHub translation report to Markdown."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_github_translation_markdown(report, limit=limit),
        encoding="utf-8",
    )


def render_github_translation_markdown(
    report: GitHubTranslationReport,
    *,
    limit: int | None = 50,
) -> str:
    """Render a GitHub translation contribution report as Markdown."""

    lines = [
        "## GitHub Translation Contributions",
        "",
        f"Base ref: `{report.base_ref}`",
        f"Head ref: `{report.head_ref}`",
        f"Latest Weblate PO: `{report.latest_po_path}`",
        f"Changed entries: **{report.changed_entries}**",
        f"Importable entries: **{report.importable_entries}**",
        f"Already in Weblate: **{report.already_imported_entries}**",
        f"Conflicts: **{report.conflict_entries}**",
        f"Markdown format errors: **{report.format_error_entries}**",
        f"Shared-block consistency errors: **{len(report.shared_block_issues)}**",
        "",
    ]
    if not report.decisions:
        lines.append("No GitHub-originated translation changes were detected.")
    else:
        visible = report.decisions if limit is None else report.decisions[:limit]
        lines.extend(
            [
                "| Decision | Format | UUID | Field | GitHub Translation | Weblate Translation | Path |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
        )
        for decision in visible:
            lines.append(
                "| "
                f"{decision.decision} | "
                f"{_markdown_cell('; '.join(decision.format_issues) or 'valid')} | "
                f"`{decision.uuid}` | "
                f"`{decision.field}` | "
                f"{_markdown_cell(decision.github)} | "
                f"{_markdown_cell(decision.weblate)} | "
                f"`{decision.path}` |"
            )
        hidden_count = len(report.decisions) - len(visible)
        if hidden_count > 0:
            lines.extend(["", f"... and {hidden_count} more entries."])
    if report.shared_block_issues:
        lines.extend(["", "### Shared-Block Consistency Errors", ""])
        lines.extend(f"- `{issue.path}`: {issue.message}" for issue in report.shared_block_issues)
    return "\n".join(lines) + "\n"


def write_import_po(
    *,
    report: GitHubTranslationReport,
    output_path: Path | str,
    language: str,
) -> Path:
    """Write a partial PO containing only safe GitHub translation imports."""

    importable = report.importable_decisions
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        'msgid ""\n',
        'msgstr ""\n',
        '"Project-Id-Version: GitHub translation import\\n"\n',
        f'"Language: {language}\\n"\n',
        '"Content-Type: text/plain; charset=utf-8\\n"\n',
        "\n",
    ]
    for decision in importable:
        lines.append(f"#: github:{decision.uuid}:{decision.field}\n")
        lines.extend(PoSectionRenderer.format_po_string_block("msgid", decision.source))
        lines.extend(PoSectionRenderer.format_po_string_block("msgstr", decision.github))
        lines.append("\n")
    path.write_text("".join(lines), encoding="utf-8")
    return path


def find_unapplied_weblate_imports(
    *,
    report: GitHubTranslationReport,
    latest_po_path: Path,
) -> tuple[GitHubTranslationDecision, ...]:
    """Return importable decisions not reflected in a fresh Weblate PO."""

    weblate_entries = parse_po_entry_states(latest_po_path)
    return tuple(
        decision
        for decision in report.importable_decisions
        if (entry := weblate_entries.get(decision.key)) is None
        or entry.msgid != decision.source
        or entry.msgstr != decision.github
    )


def _build_decision(
    *,
    key: PoKey,
    base_entry: TreeTranslationEntry | None,
    head_entry: TreeTranslationEntry | None,
    weblate_entry: PoEntryState | None,
) -> GitHubTranslationDecision:
    uuid, field = key
    base_text = _target_text(base_entry)
    github_text = _target_text(head_entry)
    weblate_text = weblate_entry.msgstr if weblate_entry is not None else ""
    source = (
        head_entry.source if head_entry is not None else base_entry.source if base_entry else ""
    )
    path = head_entry.path if head_entry is not None else base_entry.path if base_entry else ""
    if head_entry is None:
        decision = REMOVED_DECISION
    elif weblate_entry is None:
        decision = MISSING_WEBLATE_DECISION
    elif weblate_entry.msgid != head_entry.source:
        decision = SOURCE_MISMATCH_DECISION
    elif github_text == weblate_text:
        decision = ALREADY_IMPORTED_DECISION
    elif weblate_text == base_text:
        decision = IMPORT_DECISION
    else:
        decision = CONFLICT_DECISION
    return GitHubTranslationDecision(
        uuid=uuid,
        field=field,
        path=path,
        decision=decision,
        source=source,
        base=base_text,
        github=github_text,
        weblate=weblate_text,
        format_issues=(
            compare_markdown_format(source, github_text) if head_entry is not None else ()
        ),
    )


def _build_report(
    *,
    base_ref: str,
    head_ref: str,
    latest_po_path: Path,
    decisions: tuple[GitHubTranslationDecision, ...],
    shared_block_issues: tuple[SharedBlockConsistencyIssue, ...],
) -> GitHubTranslationReport:
    counts: dict[str, int] = {}
    for decision in decisions:
        counts[decision.decision] = counts.get(decision.decision, 0) + 1
    conflict_entries = sum(
        count
        for decision, count in counts.items()
        if decision
        not in {
            IMPORT_DECISION,
            ALREADY_IMPORTED_DECISION,
        }
    )
    format_error_entries = sum(decision.has_format_errors for decision in decisions)
    importable_entries = sum(
        decision.decision == IMPORT_DECISION and not decision.has_format_errors
        for decision in decisions
    )
    return GitHubTranslationReport(
        base_ref=base_ref,
        head_ref=head_ref,
        latest_po_path=latest_po_path,
        changed_entries=len(decisions),
        importable_entries=importable_entries,
        already_imported_entries=counts.get(ALREADY_IMPORTED_DECISION, 0),
        conflict_entries=conflict_entries,
        format_error_entries=format_error_entries,
        shared_block_issues=shared_block_issues,
        decisions=decisions,
    )


def _git_show_text(
    *,
    repo_root: Path,
    ref: str,
    path: str,
    runner: CommandRunner,
) -> str:
    result = _run_checked(
        runner,
        ["git", "show", f"{ref}:{path}"],
        cwd=repo_root,
        description=f"read {path} from {ref}",
    )
    return result.stdout


def _target_text(entry: TreeTranslationEntry | None) -> str:
    return entry.target if entry is not None else ""


def _markdown_cell(value: str, limit: int = 100) -> str:
    sanitized = value.replace("\n", "<br>").replace("|", "\\|")
    if len(sanitized) <= limit:
        return sanitized
    return sanitized[: limit - 1] + "…"
