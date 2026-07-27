"""Render and maintain files managed by a translation repository scaffold."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .translation_repository_config import (
    TranslationRepositoryConfig,
    load_translation_repository_config,
    version_paths,
)


class TranslationRepositoryScaffoldError(RuntimeError):
    """Raised when managed scaffold files cannot be rendered."""


@dataclass(frozen=True)
class RenderedScaffoldFile:
    """One rendered scaffold file and its repository-relative path."""

    path: Path
    content: str


@dataclass(frozen=True)
class TranslationRepositoryScaffoldResult:
    """Summary of a scaffold check or synchronization run."""

    repo_root: Path
    managed_files: tuple[Path, ...]
    changed_files: tuple[Path, ...]

    @property
    def aligned(self) -> bool:
        """Return whether every managed file already matched its template."""

        return not self.changed_files


WORKFLOW_TEMPLATE_SUFFIX = "_template.yml"
WORKFLOW_TARGET_SUFFIX = ".yml"
TRANSLATION_REPOSITORY_TEMPLATE_DIR = Path("examples") / "translation-repository"
GITHUB_ACTIONS_TEMPLATE_DIR = Path("examples") / "github-actions"
GITHUB_TRANSLATION_REPOSITORY_TEMPLATE_DIR = Path("examples") / "translation-repository-github"
GITHUB_TRANSLATION_ACTIONS_TEMPLATE_DIR = Path("examples") / "github-actions-github"
TEMPLATE_TOKEN_RE = re.compile(r"(?<!\$)\{\{(?P<name>[^{}]+)\}\}")


def render_translation_repository_scaffold(
    *,
    tooling_repo: Path,
    config: TranslationRepositoryConfig,
) -> tuple[RenderedScaffoldFile, ...]:
    """Render all docs and workflows managed by the tooling repository."""

    tooling_root = tooling_repo.resolve()
    values = _template_values(config)
    rendered: list[RenderedScaffoldFile] = []

    if config.workflow.mode == "github":
        repository_template_dir = GITHUB_TRANSLATION_REPOSITORY_TEMPLATE_DIR
        workflow_template_dir = GITHUB_TRANSLATION_ACTIONS_TEMPLATE_DIR
    else:
        repository_template_dir = TRANSLATION_REPOSITORY_TEMPLATE_DIR
        workflow_template_dir = GITHUB_ACTIONS_TEMPLATE_DIR

    repository_template_root = tooling_root / repository_template_dir
    _require_directory(repository_template_root, "translation repository template directory")
    for source in sorted(repository_template_root.rglob("*")):
        if source.is_file():
            rendered.append(
                _render_file(
                    source=source,
                    target=source.relative_to(repository_template_root),
                    values=values,
                )
            )

    workflow_template_root = tooling_root / workflow_template_dir
    _require_directory(workflow_template_root, "GitHub Actions template directory")
    for source in sorted(workflow_template_root.glob(f"*{WORKFLOW_TEMPLATE_SUFFIX}")):
        target_name = source.name.removesuffix(WORKFLOW_TEMPLATE_SUFFIX) + WORKFLOW_TARGET_SUFFIX
        rendered.append(
            _render_file(
                source=source,
                target=Path(".github") / "workflows" / target_name,
                values=values,
            )
        )

    return tuple(rendered)


def check_translation_repository_scaffold(
    *,
    repo_root: Path,
    tooling_repo: Path,
    config_path: Path = Path("translation-config.yml"),
) -> TranslationRepositoryScaffoldResult:
    """Report managed files that differ from their rendered templates."""

    target_root, rendered = _load_scaffold(
        repo_root=repo_root,
        tooling_repo=tooling_repo,
        config_path=config_path,
    )
    changed = tuple(
        item.path for item in rendered if not _file_matches(target_root / item.path, item.content)
    )
    return TranslationRepositoryScaffoldResult(
        repo_root=target_root,
        managed_files=tuple(item.path for item in rendered),
        changed_files=changed,
    )


def sync_translation_repository_scaffold(
    *,
    repo_root: Path,
    tooling_repo: Path,
    config_path: Path = Path("translation-config.yml"),
) -> TranslationRepositoryScaffoldResult:
    """Update managed docs and workflows without changing repository config."""

    target_root, rendered = _load_scaffold(
        repo_root=repo_root,
        tooling_repo=tooling_repo,
        config_path=config_path,
    )
    changed: list[Path] = []
    for item in rendered:
        target = target_root / item.path
        if _file_matches(target, item.content):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content, encoding="utf-8")
        changed.append(item.path)

    return TranslationRepositoryScaffoldResult(
        repo_root=target_root,
        managed_files=tuple(item.path for item in rendered),
        changed_files=tuple(changed),
    )


def _load_scaffold(
    *,
    repo_root: Path,
    tooling_repo: Path,
    config_path: Path,
) -> tuple[Path, tuple[RenderedScaffoldFile, ...]]:
    target_root = repo_root.resolve()
    resolved_config = config_path if config_path.is_absolute() else target_root / config_path
    config = load_translation_repository_config(resolved_config)
    return target_root, render_translation_repository_scaffold(
        tooling_repo=tooling_repo,
        config=config,
    )


def _render_file(
    *,
    source: Path,
    target: Path,
    values: dict[str, str],
) -> RenderedScaffoldFile:
    text = source.read_text(encoding="utf-8")
    tokens = set(TEMPLATE_TOKEN_RE.findall(text))
    unknown = sorted(tokens - values.keys())
    if unknown:
        names = ", ".join(unknown)
        raise TranslationRepositoryScaffoldError(
            f"Unknown scaffold template token(s) in {source}: {names}"
        )
    rendered = TEMPLATE_TOKEN_RE.sub(lambda match: values[match.group("name")], text)
    return RenderedScaffoldFile(path=target, content=rendered)


def _template_values(config: TranslationRepositoryConfig) -> dict[str, str]:
    return {
        "TARGET_LANGUAGE_LABEL": config.translation.target_language_label,
        "TOOLING_REPOSITORY": config.tooling.repository,
        "TOOLING_REF": config.tooling.ref,
        "TRACKING_BRANCH": config.branches.tracking_branch,
        "SOURCE_REPOSITORY": config.knowledge_model.upstream_repository,
        "SOURCE_REF": config.knowledge_model.upstream_ref or "UNRELEASED",
        "SOURCE_VERSION": config.knowledge_model.version,
        "SOURCE_KM_ID": (
            f"{config.knowledge_model.organization_id}:{config.knowledge_model.km_id}"
        ),
        "SOURCE_KM_PATH": version_paths(config).source_km_path.as_posix(),
        "SOURCE_PO_PATH": version_paths(config).source_po_path.as_posix(),
        "TARGET_LANGUAGE": config.translation.target_language,
        "TRANSLATED_KM_ID": (
            f"{config.translation.translated_organization_id}:{config.translation.translated_km_id}"
        ),
    }


def _file_matches(path: Path, expected: str) -> bool:
    try:
        return path.read_text(encoding="utf-8") == expected
    except FileNotFoundError:
        return False


def _require_directory(path: Path, label: str) -> None:
    if not path.is_dir():
        raise TranslationRepositoryScaffoldError(f"Missing {label}: {path}")
