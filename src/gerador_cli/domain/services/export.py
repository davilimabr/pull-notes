"""Services for exporting generated artifacts."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from ...adapters.filesystem import ensure_dir
from ..models import Commit


def export_commits(commits: Iterable[Commit], output_dir: Path) -> Path:
    """Persist commits.json with the collected commit data."""
    ensure_dir(output_dir)
    commit_data = [asdict(c) for c in commits]
    path = output_dir / "commits.json"
    path.write_text(json.dumps(commit_data, indent=2), encoding="utf-8")
    return path


def export_convention_report(report: str, output_dir: Path) -> Path:
    """Persist the convention report markdown."""
    return export_text_document(report, output_dir, "conventions.md")


def export_text_document(content: str, output_dir: Path, filename: str) -> Path:
    """Persist a markdown/text artifact to the output directory."""
    ensure_dir(output_dir)
    path = output_dir / filename
    path.write_text(content, encoding="utf-8")
    return path
