"""Services for exporting generated artifacts."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel

from ...adapters.filesystem import ensure_dir
from ..models import Commit


class _PydanticEncoder(json.JSONEncoder):
    """JSON encoder that handles Pydantic models."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, BaseModel):
            return obj.model_dump()
        return super().default(obj)


def _sanitize_filename(name: str) -> str:
    """Sanitize a string to be used as a filename."""
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', name)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = sanitized.strip('_')
    return sanitized[:100] if sanitized else "unnamed"


def create_output_structure(base_output_dir: Path, repo_name: str) -> dict[str, Path]:
    """Create the output directory structure and return paths.

    Structure:
        {base_output_dir}/{repo_name}/
        ├── utils/
        ├── releases/
        └── prs/

    Returns:
        Dictionary with keys: 'root', 'utils', 'releases', 'prs'
    """
    root = base_output_dir / repo_name
    paths = {
        'root': root,
        'utils': root / 'utils',
        'releases': root / 'releases',
        'prs': root / 'prs',
    }
    for path in paths.values():
        ensure_dir(path)
    return paths


def export_commits(commits: Iterable[Commit], utils_dir: Path) -> Path:
    """Persist commit.json with the collected commit data to utils directory."""
    ensure_dir(utils_dir)
    commit_data = [asdict(c) for c in commits]
    path = utils_dir / "commit.json"
    path.write_text(json.dumps(commit_data, indent=2, cls=_PydanticEncoder), encoding="utf-8")
    return path


def export_convention_report(report: str, utils_dir: Path) -> Path:
    """Persist the convention report markdown to utils directory."""
    ensure_dir(utils_dir)
    path = utils_dir / "conventions.md"
    path.write_text(report, encoding="utf-8")
    return path


def export_release(content: str, releases_dir: Path, version: str) -> Path:
    """Persist release notes to releases directory with version in filename."""
    ensure_dir(releases_dir)
    sanitized_version = _sanitize_filename(version)
    filename = f"release_{sanitized_version}.md"
    path = releases_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def export_pr(content: str, prs_dir: Path, title: str) -> Path:
    """Persist PR description to prs directory with title in filename."""
    ensure_dir(prs_dir)
    sanitized_title = _sanitize_filename(title)
    filename = f"pr_{sanitized_title}.md"
    path = prs_dir / filename
    path.write_text(content, encoding="utf-8")
    return path


def export_text_document(content: str, output_dir: Path, filename: str) -> Path:
    """Persist a markdown/text artifact to the output directory."""
    ensure_dir(output_dir)
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    return path
