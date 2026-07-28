"""CI helpers for syncing translation artifacts and committing updates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .command import (
    CommandRunner,
    configure_github_actions_git_identity,
    default_command_runner,
    make_checked_runner,
    tooling_virtualenv_command_path,
    tooling_virtualenv_python_path,
)
from .constants import SHARED_BLOCK_CONTEXT_FILENAME, TRANSLATION_FILENAME
from .data_models import KnowledgeModelPackageIdentityMapping
from .layout import (
    DEFAULT_MODEL_PATH,
    DEFAULT_PO_PATH,
    DEFAULT_SOURCE_LANG,
    DEFAULT_TARGET_LANG,
    TranslationOutputLayout,
)

DEFAULT_SYNC_COMMIT_MESSAGE = "chore(sync): refresh translation artifacts"
RESTORABLE_SYNC_FILENAMES = frozenset(
    {
        TRANSLATION_FILENAME,
        SHARED_BLOCK_CONTEXT_FILENAME,
    }
)
SYNC_FILE_LINE_RE = re.compile(r"^File: (?P<path>.+)$", re.MULTILINE)


class CiSyncError(RuntimeError):
    """Raised when CI sync-and-commit automation cannot complete."""


_run_checked = make_checked_runner(CiSyncError, include_command=True)


@dataclass(frozen=True)
class CiSyncCommitConfig:
    """Describe one CI sync-and-commit operation.

    Args:
        host_repo_path: Repository whose translation tree should be updated.
        tooling_repo_path: Repository that contains the sync CLI and tests.
        translation_root: Relative path inside the host repository that contains
            `tree/`, `builds/`, and `reviews/`.
        target_ref: Branch/ref that should receive the push.
        mode: Trigger mode, either `schedule` or `pull_request`.
        source_lang: Source language code used by the sync CLI.
        target_lang: Target language code used by the sync CLI.
        commit_message: Commit message used when sync changes are detected.
        source_po_path: Optional source PO template path. Relative paths are
            resolved inside the host repository; absolute paths are used as-is.
            Defaults to the canonical PO bundled in the tooling repository.
        source_km_path: Optional source KM bundle path. Relative paths are
            resolved inside the host repository; absolute paths are used as-is.
            Defaults to the canonical KM bundled in the tooling repository.
        output_organization_id: Optional organization ID for the generated KM.
        output_km_id: Optional KM ID for the generated KM.
        output_name: Optional display name for the generated KM.
        supplemental_translations_path: Optional directory of translator-facing
            forms for KM fields omitted from the upstream PO.
        package_identity_mappings: Explicit translated identities for
            additional package coordinates in mixed-lineage bundles.
        restore_source_ref: Git ref used when restoring a malformed
            translation source file during CI recovery.
    """

    host_repo_path: Path
    tooling_repo_path: Path
    translation_root: str
    target_ref: str
    mode: str
    source_lang: str = DEFAULT_SOURCE_LANG
    target_lang: str = DEFAULT_TARGET_LANG
    commit_message: str = DEFAULT_SYNC_COMMIT_MESSAGE
    source_po_path: Path | None = None
    source_km_path: Path | None = None
    output_organization_id: str | None = None
    output_km_id: str | None = None
    output_name: str | None = None
    supplemental_translations_path: Path | None = None
    package_identity_mappings: tuple[KnowledgeModelPackageIdentityMapping, ...] = ()
    restore_source_ref: str = "origin/master"

    @property
    def host_repo_dir(self) -> Path:
        """Return the absolute host repository path."""

        return self.host_repo_path.resolve()

    @property
    def tooling_repo_dir(self) -> Path:
        """Return the absolute tooling repository path."""

        return self.tooling_repo_path.resolve()

    @property
    def translation_root_path(self) -> Path:
        """Return the translation root as a relative path object."""

        return Path(self.translation_root)

    @property
    def translation_root_arg(self) -> str:
        """Return the normalized pathspec used by git commands."""

        normalized = self.translation_root_path.as_posix()
        return normalized or "."

    @property
    def translation_root_dir(self) -> Path:
        """Return the absolute translation root inside the host repository."""

        return (self.host_repo_dir / self.translation_root_path).resolve()

    @property
    def output_layout(self) -> TranslationOutputLayout:
        """Return the shared artifact layout rooted in the host repository."""

        return TranslationOutputLayout(
            output_root=self.translation_root_dir,
            target_lang=self.target_lang,
        )

    @property
    def tree_dir(self) -> Path:
        """Return the absolute translation tree directory."""

        return self.output_layout.tree_dir

    @property
    def final_po_path(self) -> Path:
        """Return the generated PO output path."""

        return self.output_layout.final_po_path

    @property
    def final_km_path(self) -> Path:
        """Return the generated translated KM output path."""

        return self.output_layout.final_km_path

    @property
    def final_km_git_path(self) -> str:
        """Return the generated KM path relative to the host repo."""

        return self.final_km_path.relative_to(self.host_repo_dir).as_posix()

    @property
    def diff_path(self) -> Path:
        """Return the generated review diff path."""

        return self.output_layout.diff_path

    @property
    def outline_path(self) -> Path:
        """Return the generated outline markdown path."""

        return self.output_layout.outline_path

    @property
    def shared_blocks_dir(self) -> Path:
        """Return the canonical split shared-block directory root."""

        return self.output_layout.shared_blocks_dir

    @property
    def shared_blocks_outline_path(self) -> Path:
        """Return the compact shared-block outline markdown path."""

        return self.output_layout.shared_blocks_outline_path

    @property
    def tooling_python_path(self) -> Path:
        """Return the tooling virtualenv Python path."""

        return tooling_virtualenv_python_path(self.tooling_repo_dir)

    def tooling_command_path(self, command_name: str) -> Path:
        """Return one installed console-script path from the tooling virtualenv."""

        return tooling_virtualenv_command_path(self.tooling_repo_dir, command_name)

    @property
    def original_po_path(self) -> Path:
        """Return the source PO template path for sync and validation."""

        return self._resolve_source_path(
            configured_path=self.source_po_path,
            default_path=self.tooling_repo_dir / DEFAULT_PO_PATH,
        )

    @property
    def original_model_path(self) -> Path:
        """Return the source KM bundle path for building translated KM output."""

        return self._resolve_source_path(
            configured_path=self.source_km_path,
            default_path=self.tooling_repo_dir / DEFAULT_MODEL_PATH,
        )

    @property
    def supplemental_translations_dir(self) -> Path | None:
        """Return the resolved supplemental translation directory, if configured."""

        if self.supplemental_translations_path is None:
            return None
        return self._resolve_source_path(
            configured_path=self.supplemental_translations_path,
            default_path=self.host_repo_dir,
        )

    def _resolve_source_path(self, configured_path: Path | None, default_path: Path) -> Path:
        """Resolve one optional source path for CI automation.

        Args:
            configured_path: User-provided source path, or ``None``.
            default_path: Built-in fallback path.

        Returns:
            Absolute path to the source file.
        """

        if configured_path is None:
            return default_path.resolve()
        if configured_path.is_absolute():
            return configured_path.resolve()
        return (self.host_repo_dir / configured_path).resolve()

    def validate(self) -> None:
        """Validate that the requested sync operation can run locally.

        Raises:
            CiSyncError: If the configuration points to missing or unsupported
                paths.
        """

        if self.mode not in {"schedule", "pull_request"}:
            raise CiSyncError(
                "Unsupported CI sync mode. Expected 'schedule' or "
                f"'pull_request', got {self.mode!r}."
            )
        if self.translation_root_path.is_absolute():
            raise CiSyncError("Translation root must be relative to the host repository.")
        if not self.host_repo_dir.is_dir():
            raise CiSyncError(f"Host repository does not exist: {self.host_repo_dir}")
        if not self.tooling_repo_dir.is_dir():
            raise CiSyncError(f"Tooling repository does not exist: {self.tooling_repo_dir}")
        if not self.translation_root_dir.is_dir():
            raise CiSyncError(
                "Translation root does not exist inside the host repository: "
                f"{self.translation_root_dir}"
            )
        if not self.tree_dir.is_dir():
            raise CiSyncError(f"Missing translation tree directory: {self.tree_dir}")
        if not self.tooling_python_path.exists():
            raise CiSyncError(
                "Missing tooling virtualenv Python. Run `make install-dev` first: "
                f"{self.tooling_python_path}"
            )
        if not self.restore_source_ref.strip():
            raise CiSyncError("Restore source ref must not be empty.")
        if not self.original_po_path.exists():
            raise CiSyncError(f"Missing original PO file: {self.original_po_path}")
        if not self.original_model_path.exists():
            raise CiSyncError(f"Missing original KM file: {self.original_model_path}")
        if (
            self.supplemental_translations_dir is not None
            and not self.supplemental_translations_dir.is_dir()
        ):
            raise CiSyncError(
                f"Missing supplemental translation directory: {self.supplemental_translations_dir}"
            )


def run_ci_sync_commit(
    config: CiSyncCommitConfig,
    *,
    runner: CommandRunner = default_command_runner,
) -> bool:
    """Run sync, translation validation, and optional commit/push.

    Args:
        config: Sync-and-commit configuration.
        runner: Injectable subprocess runner used by tests and production code.

    Returns:
        `True` when a commit was created and pushed, otherwise `False`.

    Raises:
        CiSyncError: If sync, validation, commit, or push fails.
    """

    config.validate()
    print(f"[ci-sync] Mode: {config.mode}")
    print(f"[ci-sync] Host repo: {config.host_repo_dir}")
    print(f"[ci-sync] Translation root: {config.translation_root_arg}")

    _run_sync_with_origin_restore(config, runner)
    _run_checked(
        runner,
        _build_po_to_km_command(config),
        cwd=config.tooling_repo_dir,
        description="build translated KM artifact",
        echo_output=True,
    )
    _run_checked(
        runner,
        _build_translation_test_command(config),
        cwd=config.tooling_repo_dir,
        env={
            "DSW_TRANSLATION_OUTPUT_ROOT": str(config.translation_root_dir),
            "DSW_SOURCE_PO_PATH": str(config.original_po_path),
            "DSW_SOURCE_KM_PATH": str(config.original_model_path),
        },
        description="run translation tests",
        echo_output=True,
    )

    _mark_generated_km_as_intent_to_add(config, runner)
    if not _translation_root_has_tracked_changes(config, runner):
        print("[ci-sync] No tracked translation changes detected after sync.")
        return False

    configure_github_actions_git_identity(
        repo_root=config.host_repo_dir,
        runner=runner,
        error_factory=CiSyncError,
        include_command=True,
    )
    _run_checked(
        runner,
        ["git", "add", "--", config.translation_root_arg],
        cwd=config.host_repo_dir,
        description="stage translation changes",
    )
    _run_checked(
        runner,
        ["git", "commit", "-m", config.commit_message],
        cwd=config.host_repo_dir,
        description="create sync commit",
    )
    _run_checked(
        runner,
        ["git", "push", "origin", f"HEAD:{config.target_ref}"],
        cwd=config.host_repo_dir,
        description="push sync commit",
    )
    print(f"[ci-sync] Pushed sync commit to {config.target_ref}.")
    return True


def _run_sync_with_origin_restore(
    config: CiSyncCommitConfig,
    runner: CommandRunner,
) -> None:
    """Run sync once, optionally restoring one broken source file from a git ref.

    Args:
        config: Sync-and-commit configuration.
        runner: Injectable subprocess runner.

    Raises:
        CiSyncError: If sync still fails after the restore attempt or if the
            failure is not eligible for aggressive restore.
    """

    try:
        _run_checked(
            runner,
            _build_sync_command(config),
            cwd=config.tooling_repo_dir,
            description="sync translation artifacts",
            echo_output=True,
        )
        return
    except CiSyncError as error:
        restore_path = _extract_origin_restore_candidate(str(error), config)
        if restore_path is None:
            raise

    print(
        "[ci-sync] WARNING: restoring malformed translation source from "
        f"{config.restore_source_ref}: {restore_path}"
    )
    _restore_file_from_configured_source(config, runner, restore_path)
    _run_checked(
        runner,
        _build_sync_command(config),
        cwd=config.tooling_repo_dir,
        description="re-run sync translation artifacts after git restore",
        echo_output=True,
    )


def _build_sync_command(config: CiSyncCommitConfig) -> list[str]:
    """Build the explicit sync CLI command for one CI operation.

    Args:
        config: Sync-and-commit configuration.

    Returns:
        Command argument vector.
    """

    return [
        str(config.tooling_command_path("dsw-km-sync-shared-strings")),
        "--tree-dir",
        str(config.tree_dir),
        "--original-po",
        str(config.original_po_path),
        "--out-po",
        str(config.final_po_path),
        "--diff-out",
        str(config.diff_path),
        "--outline-out",
        str(config.outline_path),
        "--shared-blocks-dir-out",
        str(config.shared_blocks_dir),
        "--shared-blocks-outline-out",
        str(config.shared_blocks_outline_path),
        "--source-lang",
        config.source_lang,
        "--target-lang",
        config.target_lang,
        "--group-by",
        "shared-block",
    ]


def _build_po_to_km_command(config: CiSyncCommitConfig) -> list[str]:
    """Build the explicit PO-to-KM CLI command for one CI operation.

    Args:
        config: Sync-and-commit configuration.

    Returns:
        Command argument vector.
    """

    return [
        str(config.tooling_command_path("dsw-km-po-to-km")),
        "--translated-po",
        str(config.final_po_path),
        "--original-km",
        str(config.original_model_path),
        "--out-km",
        str(config.final_km_path),
        "--source-lang",
        config.source_lang,
        "--target-lang",
        config.target_lang,
    ] + _build_optional_po_to_km_args(config)


def _build_optional_po_to_km_args(config: CiSyncCommitConfig) -> list[str]:
    """Build optional translated-KM identity and supplemental flags.

    Args:
        config: Sync-and-commit configuration.

    Returns:
        Command-line flags for identity overrides.
    """

    args: list[str] = []
    if config.output_organization_id:
        args.extend(["--output-organization-id", config.output_organization_id])
    if config.output_km_id:
        args.extend(["--output-km-id", config.output_km_id])
    if config.output_name:
        args.extend(["--output-name", config.output_name])
    if config.supplemental_translations_dir is not None:
        args.extend(
            [
                "--supplemental-translations-dir",
                str(config.supplemental_translations_dir),
            ]
        )
    for mapping in config.package_identity_mappings:
        args.extend(
            [
                "--package-identity-mapping",
                mapping.source_organization_id,
                mapping.source_km_id,
                mapping.translated_organization_id,
                mapping.translated_km_id,
                mapping.translated_name,
            ]
        )
    return args


def _build_translation_test_command(config: CiSyncCommitConfig) -> list[str]:
    """Build the explicit translation-test command for one CI operation.

    Args:
        config: Sync-and-commit configuration.

    Returns:
        Command argument vector.
    """

    return [
        str(config.tooling_python_path),
        "-m",
        "pytest",
        "tests/translation",
    ]


def _mark_generated_km_as_intent_to_add(
    config: CiSyncCommitConfig,
    runner: CommandRunner,
) -> None:
    """Make a newly generated KM visible to tracked-only status checks.

    Args:
        config: Sync-and-commit configuration.
        runner: Injectable subprocess runner.
    """

    _run_checked(
        runner,
        ["git", "add", "-N", "--", config.final_km_git_path],
        cwd=config.host_repo_dir,
        description="mark generated KM artifact for change detection",
    )


def _translation_root_has_tracked_changes(
    config: CiSyncCommitConfig,
    runner: CommandRunner,
) -> bool:
    """Return whether tracked files changed under the translation root.

    Args:
        config: Sync-and-commit configuration.
        runner: Injectable subprocess runner.

    Returns:
        `True` when tracked files changed under the translation root.

    Raises:
        CiSyncError: If git status fails.
    """

    result = _run_checked(
        runner,
        [
            "git",
            "status",
            "--porcelain",
            "--untracked-files=no",
            "--",
            config.translation_root_arg,
        ],
        cwd=config.host_repo_dir,
        description="inspect tracked translation changes",
    )
    return bool(result.stdout.strip())


def _extract_origin_restore_candidate(
    error_message: str,
    config: CiSyncCommitConfig,
) -> Path | None:
    """Return a restorable source file path from one sync failure message.

    Args:
        error_message: Raised sync failure message.
        config: Sync-and-commit configuration.

    Returns:
        Absolute path to a restorable source file, or `None` when the failure
        should not trigger aggressive restore.
    """

    for match in SYNC_FILE_LINE_RE.finditer(error_message):
        candidate_path = Path(match.group("path").strip()).resolve()
        if candidate_path.name not in RESTORABLE_SYNC_FILENAMES:
            continue
        if not _is_relative_to(candidate_path, config.host_repo_dir):
            continue
        if not _is_relative_to(candidate_path, config.translation_root_dir):
            continue
        if candidate_path.name == SHARED_BLOCK_CONTEXT_FILENAME and not _is_relative_to(
            candidate_path,
            config.shared_blocks_dir,
        ):
            continue
        return candidate_path
    return None


def _restore_file_from_configured_source(
    config: CiSyncCommitConfig,
    runner: CommandRunner,
    file_path: Path,
) -> None:
    """Restore one tracked translation source file from the configured git ref.

    Args:
        config: Sync-and-commit configuration.
        runner: Injectable subprocess runner.
        file_path: Absolute host-repository file path to restore.

    Raises:
        CiSyncError: If the git restore command fails.
    """

    relative_path = file_path.relative_to(config.host_repo_dir).as_posix()
    _run_checked(
        runner,
        [
            "git",
            "restore",
            "--source",
            config.restore_source_ref,
            "--worktree",
            "--",
            relative_path,
        ],
        cwd=config.host_repo_dir,
        description=f"restore {relative_path} from {config.restore_source_ref}",
    )


def _is_relative_to(path: Path, root: Path) -> bool:
    """Return whether one path is located under the given root.

    Args:
        path: Candidate absolute path.
        root: Candidate absolute root.

    Returns:
        `True` when `path` is inside `root`, otherwise `False`.
    """

    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
