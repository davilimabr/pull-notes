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


_CLI_ROOT = Path(__file__).resolve().parent.parent


def resolve_cli_path(path_str: str) -> Path:
    """Resolve a path against the CLI package root (for bundled assets)."""
    path = Path(path_str)
    parts = path.parts

    if "gerador_cli" in parts:
        idx = parts.index("gerador_cli")
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
    if "gerador_cli" in parts:
        idx = parts.index("gerador_cli")
        rel_parts = parts[idx + 1 :]
    else:
        rel_parts = parts

    return _CLI_ROOT.joinpath(*rel_parts)
