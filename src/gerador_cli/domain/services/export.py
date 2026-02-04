"""Services for exporting generated artifacts."""

from __future__ import annotations

import json
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


def export_commits(commits: Iterable[Commit], output_dir: Path) -> Path:
    """Persist commits.json with the collected commit data."""
    ensure_dir(output_dir)
    commit_data = [asdict(c) for c in commits]
    path = output_dir / "commits.json"
    path.write_text(json.dumps(commit_data, indent=2, cls=_PydanticEncoder), encoding="utf-8")
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
