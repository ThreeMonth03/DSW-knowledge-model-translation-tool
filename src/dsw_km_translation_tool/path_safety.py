"""Filesystem safety checks for generated translation artifacts."""

from __future__ import annotations

from pathlib import Path


def reject_symlink_path(path: Path, root: Path | None = None) -> None:
    """Reject symlinks at *path* and, optionally, below a managed root.

    The check includes broken symlinks.  Callers use it immediately before
    traversing or modifying repository-controlled artifact paths.
    """

    paths = [path]
    if root is not None:
        try:
            relative_path = path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Path is outside managed root: {path}") from exc
        paths = [root]
        current = root
        for part in relative_path.parts:
            current /= part
            paths.append(current)

    for candidate in paths:
        if candidate.is_symlink():
            raise ValueError(f"Refusing to access symlinked artifact path: {candidate}")
