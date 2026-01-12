"""Filesystem helpers."""

from __future__ import annotations

from pathlib import Path


def ensure_dir(path: Path) -> None:
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)


def resolve_repo_path(repo_dir: Path, path_str: str) -> Path:
    """Resolve a possibly relative path against repo directory."""
    path = Path(path_str)
    return path if path.is_absolute() else repo_dir / path
