"""Scaffold a Git repository for an append-only source KM lineage."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


class KmSourceRepositoryScaffoldError(RuntimeError):
    """Raised when source-repository templates cannot be rendered."""


@dataclass(frozen=True)
class KmSourceRepositoryScaffoldResult:
    """Files written by source repository initialization."""

    repo_root: Path
    written_files: tuple[Path, ...]
    skipped_files: tuple[Path, ...]


TEMPLATE_ROOT = Path("examples") / "km-source-repository"
TOKEN_RE = re.compile(r"(?<!\$)\{\{(?P<name>[^{}]+)\}\}")


def scaffold_km_source_repository(
    *,
    repo_root: Path,
    tooling_repo: Path,
    organization_id: str,
    km_id: str,
    name: str,
    initial_parent_package_id: str,
    tooling_repository: str,
    tooling_ref: str,
    overwrite: bool = False,
) -> KmSourceRepositoryScaffoldResult:
    """Render the managed first version of a source KM repository."""

    target_root = repo_root.resolve()
    source_root = tooling_repo.resolve() / TEMPLATE_ROOT
    if not source_root.is_dir():
        raise KmSourceRepositoryScaffoldError(f"Missing template directory: {source_root}")
    values = {
        "ORGANIZATION_ID": _required(organization_id, "organization ID"),
        "KM_ID": _required(km_id, "KM ID"),
        "KM_NAME": _required(name, "KM name"),
        "ASSET_STEM": (
            f"{_required(organization_id, 'organization ID')}-{_required(km_id, 'KM ID')}"
        ),
        "INITIAL_PARENT_PACKAGE_ID": _required(
            initial_parent_package_id,
            "initial parent package ID",
        ),
        "TOOLING_REPOSITORY": _required(tooling_repository, "tooling repository"),
        "TOOLING_REF": _required(tooling_ref, "tooling ref"),
    }
    written: list[Path] = []
    skipped: list[Path] = []
    for source in sorted(source_root.rglob("*")):
        if not source.is_file():
            continue
        relative = source.relative_to(source_root)
        target = target_root / relative
        text = source.read_text(encoding="utf-8")
        tokens = set(TOKEN_RE.findall(text))
        unknown = sorted(tokens - values.keys())
        if unknown:
            raise KmSourceRepositoryScaffoldError(
                f"Unknown template token(s) in {source}: {', '.join(unknown)}"
            )
        rendered = TOKEN_RE.sub(lambda match: values[match.group("name")], text)
        if target.exists() and not overwrite:
            skipped.append(target)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        written.append(target)
    return KmSourceRepositoryScaffoldResult(
        repo_root=target_root,
        written_files=tuple(written),
        skipped_files=tuple(skipped),
    )


def _required(value: str, label: str) -> str:
    if not value.strip():
        raise KmSourceRepositoryScaffoldError(f"{label} must not be empty")
    return value.strip()
