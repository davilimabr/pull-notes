"""Domain models and constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from pullnotes.domain.schemas import DiffAnchors


COMMIT_MARKER = "__COMMIT__"
GIT_FORMAT = f"{COMMIT_MARKER}%n%H%x1f%an%x1f%ae%x1f%ad%x1f%s"


@dataclass
class Commit:
    sha: str
    author_name: str
    author_email: str
    date: str
    subject: str
    body: str = ""
    files: List[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    diff: str = ""
    diff_anchors: Optional["DiffAnchors"] = None
    change_type: str = ""
    is_conventional: bool = True
    importance_score: float = 0.0
    importance_band: str = "low"
    summary: str = ""

    @property
    def short_sha(self) -> str:
        return self.sha[:7]
