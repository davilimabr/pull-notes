"""Filesystem helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path


def ensure_dir(path: Path) -> None:
    """Ensure directory exists."""
    path.mkdir(parents=True, exist_ok=True)


def resolve_repo_path(repo_dir: Path, path_str: str) -> Path:
    """Resolve a possibly relative path against repo directory."""
    path = Path(path_str)
    return path if path.is_absolute() else repo_dir / path


_CLI_ROOT = Path(__file__).resolve().parent.parent


def resolve_cli_path(path_str: str) -> Path:
    """Resolve a path against the CLI package root (for bundled assets)."""
    path = Path(path_str)
    parts = path.parts

    if "pullnotes" in parts:
        idx = parts.index("pullnotes")
        rel_parts = parts[idx + 1 :]
    elif path.is_absolute():
        rel_parts = parts[1:]
    else:
        rel_parts = parts

    return _CLI_ROOT.joinpath(*rel_parts)


def resolve_cli_or_absolute(path_str: str) -> Path:
    """Resolve a path preferring CLI root for relative paths, keep absolute intact."""
    path = Path(path_str)
    if path.is_absolute():
        return path

    parts = path.parts
    if "pullnotes" in parts:
        idx = parts.index("pullnotes")
        rel_parts = parts[idx + 1 :]
    else:
        rel_parts = parts

    return _CLI_ROOT.joinpath(*rel_parts)


def get_repository_name(repo_dir: Path) -> str:
    """Get repository name from git remote URL or directory name.

    Args:
        repo_dir: Path to the repository directory

    Returns:
        Repository name (sanitized for use in filenames)
    """
    try:
        # Try to get repo name from git remote URL
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            remote_url = result.stdout.strip()
            # Extract repo name from URL (handles both SSH and HTTPS)
            # Examples:
            # https://github.com/user/repo.git -> repo
            # git@github.com:user/repo.git -> repo
            repo_name = remote_url.rstrip("/").split("/")[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            return _sanitize_filename(repo_name)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass

    # Fallback to directory name
    return _sanitize_filename(repo_dir.name)


def _sanitize_filename(name: str) -> str:
    """Sanitize a string to be safe for use in filenames."""
    # Replace unsafe characters with underscores
    unsafe_chars = '<>:"/\\|?*'
    sanitized = name
    for char in unsafe_chars:
        sanitized = sanitized.replace(char, "_")
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(". ")
    # Ensure we have a valid name
    return sanitized if sanitized else "unknown_repo"
