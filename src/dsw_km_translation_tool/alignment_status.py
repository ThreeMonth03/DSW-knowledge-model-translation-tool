"""Read-only alignment checks for Localize, tree, PO, and KM artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from .localize_sync import Downloader, _download_url
from .translation_repository_config import (
    load_translation_repository_config,
    require_localize_config,
    version_paths,
)
from .workflow import TranslationWorkflowService


@dataclass(frozen=True)
class AlignmentArtifact:
    """Metadata for one compared artifact."""

    label: str
    path: str
    bytes: int
    sha256: str


@dataclass(frozen=True)
class AlignmentCheck:
    """One artifact equality check."""

    name: str
    expected: AlignmentArtifact
    actual: AlignmentArtifact
    matched: bool
    guidance: str


@dataclass(frozen=True)
class AlignmentStatusReport:
    """Summary of repository alignment with Localize/Weblate and build outputs."""

    repo_root: str
    config_path: str
    version: str
    localize_url: str
    checks: tuple[AlignmentCheck, ...]

    @property
    def aligned(self) -> bool:
        """Return whether every alignment check matched."""

        return all(check.matched for check in self.checks)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-ready representation."""

        data = asdict(self)
        data["aligned"] = self.aligned
        return data


def build_alignment_status_report(
    *,
    repo_root: Path,
    config_path: Path,
    artifact_dir: Path | None = None,
    downloader: Downloader | None = None,
) -> AlignmentStatusReport:
    """Build a read-only alignment report for one translation repository.

    The report verifies three contracts:

    - the checked-in Localize PO matches the latest Weblate download;
    - the checked-in tree rebuilds to the checked-in final PO;
    - the checked-in final PO rebuilds to the checked-in final KM.

    Args:
        repo_root: Translation repository root.
        config_path: Path to ``translation-config.yml``.
        artifact_dir: Optional directory where generated comparison artifacts
            are written for later diffing.
        downloader: Optional injectable URL downloader used by tests.

    Returns:
        Structured alignment report.
    """

    resolved_repo_root = repo_root.resolve()
    resolved_config_path = _resolve_repo_path(resolved_repo_root, config_path)
    repository_config = load_translation_repository_config(resolved_config_path)
    localize = require_localize_config(repository_config)
    version = repository_config.knowledge_model.version
    paths = version_paths(repository_config)

    checked_in_localize_po = resolved_repo_root / paths.localize_latest_po_path
    checked_in_tree_dir = resolved_repo_root / paths.translation_tree_dir
    checked_in_final_po = resolved_repo_root / paths.final_po_path
    checked_in_source_km = resolved_repo_root / paths.source_km_path
    checked_in_final_km = resolved_repo_root / paths.final_km_path

    _require_file(checked_in_localize_po)
    _require_directory(checked_in_tree_dir)
    _require_file(checked_in_final_po)
    _require_file(checked_in_source_km)
    _require_file(checked_in_final_km)

    download = downloader or _download_url
    localize_bytes = download(localize.download_url)

    workflow = TranslationWorkflowService(
        source_lang=repository_config.translation.source_language,
        target_lang=repository_config.translation.target_language,
    )

    with tempfile.TemporaryDirectory(prefix="dsw-alignment-") as tmpdir:
        generated_root = Path(tmpdir)
        downloaded_localize_po = generated_root / "weblate-latest.po"
        rebuilt_po = generated_root / "tree-rebuilt.po"
        rebuilt_km = generated_root / "final-po-rebuilt.km"

        downloaded_localize_po.write_bytes(localize_bytes)
        workflow.build_po_from_tree(
            tree_dir=str(checked_in_tree_dir),
            original_po_path=str(checked_in_localize_po),
            out_po_path=str(rebuilt_po),
        )
        workflow.build_km_from_po(
            translated_po_path=str(checked_in_final_po),
            original_model_path=str(checked_in_source_km),
            out_model_path=str(rebuilt_km),
            output_organization_id=repository_config.translation.translated_organization_id,
            output_km_id=repository_config.translation.translated_km_id,
            output_name=repository_config.translation.translated_name,
            supplemental_translations_dir=(
                str(repo_root / repository_config.translation.supplemental_directory)
                if repository_config.translation.supplemental_directory
                else None
            ),
        )

        checks = (
            _build_file_check(
                name="Weblate download matches checked-in latest PO",
                expected_label="Weblate latest PO",
                expected_path=downloaded_localize_po,
                actual_label="Repository latest PO",
                actual_path=checked_in_localize_po,
                guidance=(
                    "Run the Localize pull/sync workflow, then commit the refreshed "
                    "sources/localize snapshot, tree, final PO, and final KM."
                ),
            ),
            _build_file_check(
                name="Translation tree rebuilds checked-in final PO",
                expected_label="Tree rebuilt PO",
                expected_path=rebuilt_po,
                actual_label="Repository final PO",
                actual_path=checked_in_final_po,
                guidance=(
                    "Run the tree-to-PO sync workflow and commit builds/final_translated.po."
                ),
            ),
            _build_file_check(
                name="Final PO rebuilds checked-in final KM",
                expected_label="Final PO rebuilt KM",
                expected_path=rebuilt_km,
                actual_label="Repository final KM",
                actual_path=checked_in_final_km,
                guidance="Run PO-to-KM generation with translation-config.yml metadata.",
            ),
        )

        if artifact_dir is not None:
            _write_alignment_artifacts(
                artifact_dir=artifact_dir,
                downloaded_localize_po=downloaded_localize_po,
                rebuilt_po=rebuilt_po,
                rebuilt_km=rebuilt_km,
            )

    return AlignmentStatusReport(
        repo_root=str(resolved_repo_root),
        config_path=str(resolved_config_path),
        version=version,
        localize_url=localize.download_url,
        checks=checks,
    )


def render_alignment_status_markdown(report: AlignmentStatusReport) -> str:
    """Render an alignment report as GitHub-flavored Markdown."""

    status = "aligned" if report.aligned else "not aligned"
    lines = [
        "## Localize/Repository Alignment",
        "",
        f"Repository: `{report.repo_root}`",
        f"Config: `{report.config_path}`",
        f"KM version: `{report.version}`",
        f"Localize URL: `{report.localize_url}`",
        f"Status: **{status}**",
        "",
        "| Check | Result | Expected SHA-256 | Actual SHA-256 |",
        "| --- | --- | --- | --- |",
    ]
    for check in report.checks:
        result = "pass" if check.matched else "fail"
        lines.append(
            f"| {check.name} | {result} | `{check.expected.sha256}` | `{check.actual.sha256}` |"
        )
    failed_checks = [check for check in report.checks if not check.matched]
    if failed_checks:
        lines.extend(["", "### Follow-up", ""])
        for check in failed_checks:
            lines.append(f"- {check.name}: {check.guidance}")
    return "\n".join(lines) + "\n"


def write_alignment_status_json(
    report: AlignmentStatusReport,
    output_path: Path | str,
) -> None:
    """Write an alignment report to JSON."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report.to_dict(), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def write_alignment_status_markdown(
    report: AlignmentStatusReport,
    output_path: Path | str,
) -> None:
    """Append an alignment report to a Markdown file."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(render_alignment_status_markdown(report))


def _resolve_repo_path(repo_root: Path, path: Path) -> Path:
    """Resolve a path relative to the translation repository when needed."""

    if path.is_absolute():
        return path.resolve()
    return (repo_root / path).resolve()


def _require_file(path: Path) -> None:
    """Raise if a required file is missing."""

    if not path.is_file():
        raise FileNotFoundError(f"Required file is missing: {path}")


def _require_directory(path: Path) -> None:
    """Raise if a required directory is missing."""

    if not path.is_dir():
        raise FileNotFoundError(f"Required directory is missing: {path}")


def _build_file_check(
    *,
    name: str,
    expected_label: str,
    expected_path: Path,
    actual_label: str,
    actual_path: Path,
    guidance: str,
) -> AlignmentCheck:
    """Build one exact file equality check."""

    return AlignmentCheck(
        name=name,
        expected=_build_artifact(expected_label, expected_path),
        actual=_build_artifact(actual_label, actual_path),
        matched=expected_path.read_bytes() == actual_path.read_bytes(),
        guidance=guidance,
    )


def _build_artifact(label: str, path: Path) -> AlignmentArtifact:
    """Build metadata for one compared artifact."""

    payload = path.read_bytes()
    return AlignmentArtifact(
        label=label,
        path=str(path.resolve()),
        bytes=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def _write_alignment_artifacts(
    *,
    artifact_dir: Path,
    downloaded_localize_po: Path,
    rebuilt_po: Path,
    rebuilt_km: Path,
) -> None:
    """Copy generated comparison files into a persistent artifact directory."""

    artifact_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(downloaded_localize_po, artifact_dir / downloaded_localize_po.name)
    shutil.copyfile(rebuilt_po, artifact_dir / rebuilt_po.name)
    shutil.copyfile(rebuilt_km, artifact_dir / rebuilt_km.name)
