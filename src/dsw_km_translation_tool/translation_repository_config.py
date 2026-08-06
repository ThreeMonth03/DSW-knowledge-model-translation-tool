"""Configuration contract for dedicated KM translation repositories.

The tooling repository is reusable, while each production translation
repository provides a ``translation-config.yml`` file. This module validates
that file and derives conventional artifact paths used by sync, report, and KM
update commands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .data_models import KnowledgeModelPackageIdentityMapping


class TranslationRepositoryConfigError(ValueError):
    """Raised when a translation repository config is invalid."""


@dataclass(frozen=True)
class KnowledgeModelRepositoryConfig:
    """Source KM coordinates and the currently tracked package version."""

    organization_id: str
    km_id: str
    upstream_repository: str
    upstream_ref: str | None
    upstream_bundle_path: Path | None
    bundle_path: Path | None
    version: str


@dataclass(frozen=True)
class TranslationLanguageConfig:
    """Target-language metadata for translated KM packages."""

    source_language: str
    target_language: str
    target_language_label: str
    translated_organization_id: str
    translated_km_id: str
    translated_name: str
    catalog_path: Path | None
    supplemental_directory: Path | None
    package_identity_mappings: tuple[KnowledgeModelPackageIdentityMapping, ...]


@dataclass(frozen=True)
class BranchConfig:
    """Translation branch naming policy."""

    tracking_branch: str


@dataclass(frozen=True)
class ToolingConfig:
    """Tooling repository reference used by downstream automation."""

    repository: str
    ref: str


@dataclass(frozen=True)
class LocalizeConfig:
    """Localize/Weblate source metadata for PO synchronization."""

    download_url: str
    repository: str | None


@dataclass(frozen=True)
class WorkflowConfig:
    """Select the translation repository authority and automation profile."""

    mode: str
    source: str


@dataclass(frozen=True)
class RegistryConfig:
    """DSW Registry endpoint used for KM version discovery."""

    api_url: str


@dataclass(frozen=True)
class KmVersionWorkspacePaths:
    """Conventional workspace paths for the configured KM package."""

    version: str
    package_id: str
    source_slug: str
    source_km_path: Path
    source_po_path: Path
    localize_latest_po_path: Path
    translation_tree_dir: Path
    final_po_path: Path
    final_km_path: Path
    review_diff_path: Path
    validation_report_path: Path
    conflicts_report_path: Path


@dataclass(frozen=True)
class TranslationRepositoryConfig:
    """Parsed translation repository configuration."""

    schema_version: int
    knowledge_model: KnowledgeModelRepositoryConfig
    translation: TranslationLanguageConfig
    branches: BranchConfig
    tooling: ToolingConfig
    workflow: WorkflowConfig
    localize: LocalizeConfig | None
    registry: RegistryConfig


VERSION_RE = re.compile(r"^v?(?P<number>\d+(?:\.\d+){1,3})$")
DEFAULT_REGISTRY_API_URL = "https://api.registry.ds-wizard.org"
WORKFLOW_MODES = frozenset({"weblate", "github"})
GITHUB_SOURCE_MODES = frozenset({"release", "git"})
GIT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
TRUSTED_TOOLING_REPOSITORY = "ThreeMonth03/dsw-km-translation-tool"
GIT_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def load_translation_repository_config(path: str | Path) -> TranslationRepositoryConfig:
    """Load and validate a KM translation repository config.

    Args:
        path: Path to ``translation-config.yml``.

    Returns:
        Parsed config with normalized bare semantic versions such as ``2.7.0``.
    """

    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TranslationRepositoryConfigError("translation-config.yml must contain a mapping")

    schema_version = _optional_int(payload, "schema_version", default=1)
    if schema_version != 1:
        raise TranslationRepositoryConfigError(
            f"Unsupported translation-config.yml schema_version {schema_version!r}"
        )

    knowledge_model = _load_knowledge_model_config(_require_dict(payload, "knowledge_model"))
    translation = _load_translation_config(_require_dict(payload, "translation"))
    _validate_package_identity_mappings(
        knowledge_model=knowledge_model,
        translation=translation,
    )
    branches = _load_branch_config(_require_dict(payload, "branches"))
    tooling = _load_tooling_config(_require_dict(payload, "tooling"))
    workflow = _load_workflow_config(_optional_dict(payload, "workflow"))
    _validate_source_mode(knowledge_model=knowledge_model, workflow=workflow)
    localize_payload = payload.get("localize")
    if localize_payload is None:
        if workflow.mode == "weblate":
            raise TranslationRepositoryConfigError(
                "`localize` is required when workflow.mode is `weblate`"
            )
        localize = None
    elif isinstance(localize_payload, dict):
        localize = _load_localize_config(localize_payload)
    else:
        raise TranslationRepositoryConfigError("Expected mapping at `localize`")
    registry = _load_registry_config(_optional_dict(payload, "registry"))

    return TranslationRepositoryConfig(
        schema_version=schema_version,
        knowledge_model=knowledge_model,
        translation=translation,
        branches=branches,
        tooling=tooling,
        workflow=workflow,
        localize=localize,
        registry=registry,
    )


def _load_knowledge_model_config(
    payload: dict[str, Any],
) -> KnowledgeModelRepositoryConfig:
    bundle_path_raw = _optional_str(payload, "bundle_path")
    return KnowledgeModelRepositoryConfig(
        organization_id=_require_str(payload, "organization_id"),
        km_id=_require_str(payload, "km_id"),
        upstream_repository=_require_str(payload, "upstream_repository"),
        upstream_ref=_optional_str(payload, "upstream_ref"),
        upstream_bundle_path=_optional_safe_path(payload, "upstream_bundle_path"),
        bundle_path=Path(bundle_path_raw) if bundle_path_raw else None,
        version=normalize_version(_require_str(payload, "version")),
    )


def _load_translation_config(payload: dict[str, Any]) -> TranslationLanguageConfig:
    return TranslationLanguageConfig(
        source_language=_require_str(payload, "source_language"),
        target_language=_require_str(payload, "target_language"),
        target_language_label=_require_str(payload, "target_language_label"),
        translated_organization_id=_require_str(payload, "translated_organization_id"),
        translated_km_id=_require_str(payload, "translated_km_id"),
        translated_name=_require_str(payload, "translated_name"),
        catalog_path=(Path(value) if (value := _optional_str(payload, "catalog_path")) else None),
        supplemental_directory=(
            Path(value) if (value := _optional_str(payload, "supplemental_directory")) else None
        ),
        package_identity_mappings=_load_package_identity_mappings(payload),
    )


def _load_package_identity_mappings(
    payload: dict[str, Any],
) -> tuple[KnowledgeModelPackageIdentityMapping, ...]:
    raw_mappings = payload.get("package_identity_mappings", [])
    if not isinstance(raw_mappings, list):
        raise TranslationRepositoryConfigError(
            "Expected list at `translation.package_identity_mappings`"
        )

    mappings: list[KnowledgeModelPackageIdentityMapping] = []
    for index, raw_mapping in enumerate(raw_mappings):
        if not isinstance(raw_mapping, dict):
            raise TranslationRepositoryConfigError(
                f"Expected mapping at `translation.package_identity_mappings[{index}]`"
            )
        mappings.append(
            KnowledgeModelPackageIdentityMapping(
                source_organization_id=_require_str(
                    raw_mapping,
                    "source_organization_id",
                ),
                source_km_id=_require_str(raw_mapping, "source_km_id"),
                translated_organization_id=_require_str(
                    raw_mapping,
                    "translated_organization_id",
                ),
                translated_km_id=_require_str(raw_mapping, "translated_km_id"),
                translated_name=_require_str(raw_mapping, "translated_name"),
            )
        )
    return tuple(mappings)


def _validate_package_identity_mappings(
    *,
    knowledge_model: KnowledgeModelRepositoryConfig,
    translation: TranslationLanguageConfig,
) -> None:
    primary_source = (knowledge_model.organization_id, knowledge_model.km_id)
    primary_target = (
        translation.translated_organization_id,
        translation.translated_km_id,
    )
    source_coordinates = {primary_source}
    target_coordinates = {primary_target}
    for mapping in translation.package_identity_mappings:
        if mapping.source_coordinate in source_coordinates:
            source = ":".join(mapping.source_coordinate)
            raise TranslationRepositoryConfigError(
                f"Duplicate translated package source coordinate: {source}"
            )
        if mapping.translated_coordinate in target_coordinates:
            target = ":".join(mapping.translated_coordinate)
            raise TranslationRepositoryConfigError(
                f"Translated package coordinates must remain distinct; duplicate target: {target}"
            )
        source_coordinates.add(mapping.source_coordinate)
        target_coordinates.add(mapping.translated_coordinate)


def _load_branch_config(payload: dict[str, Any]) -> BranchConfig:
    tracking = _optional_str(payload, "tracking_branch")
    if not tracking:
        raise TranslationRepositoryConfigError("branches.tracking_branch is required")
    return BranchConfig(tracking_branch=_validate_git_ref(tracking, "branches.tracking_branch"))


def _load_tooling_config(payload: dict[str, Any]) -> ToolingConfig:
    repository = _require_str(payload, "repository")
    if repository != TRUSTED_TOOLING_REPOSITORY:
        raise TranslationRepositoryConfigError(
            f"tooling.repository must be the trusted repository `{TRUSTED_TOOLING_REPOSITORY}`"
        )
    return ToolingConfig(
        repository=repository,
        ref=_validate_git_ref(_require_str(payload, "ref"), "tooling.ref"),
    )


def _validate_git_ref(value: str, field: str) -> str:
    """Reject ref names that are unsafe in generated YAML, shells, or Git."""

    invalid = (
        not GIT_REF_RE.fullmatch(value)
        or ".." in value
        or "//" in value
        or "@{" in value
        or value.endswith(("/", "."))
        or any(part.startswith(".") or part.endswith(".lock") for part in value.split("/"))
    )
    if invalid:
        raise TranslationRepositoryConfigError(f"{field} must be a safe Git ref name")
    return value


def _load_localize_config(payload: dict[str, Any]) -> LocalizeConfig:
    return LocalizeConfig(
        download_url=_require_str(payload, "download_url"),
        repository=_optional_str(payload, "repository"),
    )


def _load_workflow_config(payload: dict[str, Any]) -> WorkflowConfig:
    mode = (_optional_str(payload, "mode") or "weblate").lower()
    if mode not in WORKFLOW_MODES:
        choices = ", ".join(sorted(WORKFLOW_MODES))
        raise TranslationRepositoryConfigError(
            f"workflow.mode must be one of: {choices}; got {mode!r}"
        )
    source = (_optional_str(payload, "source") or "release").lower()
    if source not in GITHUB_SOURCE_MODES:
        choices = ", ".join(sorted(GITHUB_SOURCE_MODES))
        raise TranslationRepositoryConfigError(
            f"workflow.source must be one of: {choices}; got {source!r}"
        )
    if mode != "github" and source != "release":
        raise TranslationRepositoryConfigError(
            "workflow.source `git` requires workflow.mode `github`"
        )
    return WorkflowConfig(mode=mode, source=source)


def _load_registry_config(payload: dict[str, Any]) -> RegistryConfig:
    return RegistryConfig(
        api_url=_optional_str(payload, "api_url") or DEFAULT_REGISTRY_API_URL,
    )


def _validate_source_mode(
    *,
    knowledge_model: KnowledgeModelRepositoryConfig,
    workflow: WorkflowConfig,
) -> None:
    if workflow.source != "git":
        return
    if not knowledge_model.upstream_ref or not GIT_COMMIT_RE.fullmatch(
        knowledge_model.upstream_ref
    ):
        raise TranslationRepositoryConfigError(
            "knowledge_model.upstream_ref must be a full lowercase Git commit "
            "SHA when workflow.source is `git`"
        )
    if knowledge_model.upstream_bundle_path is None:
        raise TranslationRepositoryConfigError(
            "knowledge_model.upstream_bundle_path is required when workflow.source is `git`"
        )


def tracking_branch(config: TranslationRepositoryConfig) -> str:
    """Return the branch that should track the configured KM."""

    return config.branches.tracking_branch


def require_localize_config(config: TranslationRepositoryConfig) -> LocalizeConfig:
    """Return Weblate metadata or fail clearly for a GitHub-only repository."""

    if config.localize is None:
        raise TranslationRepositoryConfigError(
            "This command requires workflow.mode `weblate` and a `localize` mapping"
        )
    return config.localize


def version_paths(config: TranslationRepositoryConfig) -> KmVersionWorkspacePaths:
    """Return conventional workspace paths for the configured KM package."""

    normalized = config.knowledge_model.version
    package_id = format_package_id(
        organization_id=config.knowledge_model.organization_id,
        km_id=config.knowledge_model.km_id,
        version=normalized,
    )
    source_slug = (
        f"{config.knowledge_model.organization_id}-{config.knowledge_model.km_id}-{normalized}"
    )
    target_lang = config.translation.target_language
    weblate_po_path = Path("sources") / "localize" / target_lang / "latest.po"
    source_po_path = config.translation.catalog_path or weblate_po_path
    return KmVersionWorkspacePaths(
        version=normalized,
        package_id=package_id,
        source_slug=source_slug,
        source_km_path=Path("sources") / "knowledge-models" / source_slug / f"{source_slug}.km",
        source_po_path=source_po_path,
        localize_latest_po_path=weblate_po_path,
        translation_tree_dir=Path("tree"),
        final_po_path=Path("builds") / "final_translated.po",
        final_km_path=Path("builds") / "final_translated.km",
        review_diff_path=Path("reviews") / "final_translated.diff",
        validation_report_path=Path("reports") / "final_report.json",
        conflicts_report_path=Path("reviews") / "conflicts.json",
    )


def normalize_version(version: str) -> str:
    """Normalize a KM version to a bare semantic version string."""

    match = VERSION_RE.fullmatch(version.strip())
    if not match:
        raise TranslationRepositoryConfigError(f"Invalid semantic version: {version!r}")
    return match.group("number")


def version_sort_key(version: str) -> tuple[int, ...]:
    """Return a semantic-version sort key."""

    normalized = normalize_version(version)
    return tuple(int(part) for part in normalized.split("."))


def format_package_id(organization_id: str, km_id: str, version: str) -> str:
    """Format a DSW knowledge-model package ID."""

    return f"{organization_id}:{km_id}:{normalize_version(version)}"


def _require_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise TranslationRepositoryConfigError(f"Expected mapping at `{key}`")
    return value


def _optional_dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key, {})
    if not isinstance(value, dict):
        raise TranslationRepositoryConfigError(f"Expected mapping at `{key}`")
    return value


def _require_str(parent: dict[str, Any], key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TranslationRepositoryConfigError(f"Expected non-empty string at `{key}`")
    return value.strip()


def _optional_str(parent: dict[str, Any], key: str) -> str | None:
    value = parent.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TranslationRepositoryConfigError(f"Expected string at `{key}`")
    return value.strip()


def _optional_safe_path(parent: dict[str, Any], key: str) -> Path | None:
    raw_value = _optional_str(parent, key)
    if raw_value is None:
        return None
    path = Path(raw_value)
    if path.is_absolute() or ".." in path.parts or raw_value != path.as_posix():
        raise TranslationRepositoryConfigError(f"Expected safe relative POSIX path at `{key}`")
    return path


def _optional_int(parent: dict[str, Any], key: str, default: int) -> int:
    value = parent.get(key, default)
    if not isinstance(value, int):
        raise TranslationRepositoryConfigError(f"Expected integer at `{key}`")
    return value
