"""Domain models and constants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from pullnotes.domain.schemas import DiffAnchors


COMMIT_MARKER = "__COMMIT__"
GIT_FORMAT = f"{COMMIT_MARKER}%n%H%x1f%an%x1f%ae%x1f%ad%x1f%s"

# --- Sensitive file patterns ---
SENSITIVE_FILENAMES: frozenset[str] = frozenset({".env"})
SENSITIVE_PREFIXES: tuple[str, ...] = (".env.",)


def is_sensitive_file(file_path: str) -> bool:
    """Return True if *file_path* refers to a sensitive file that should be
    excluded from processing (e.g. ``.env``, ``.env.local``).

    Works with both forward-slash (git) and OS-native paths.
    """
    basename = file_path.rsplit("/", 1)[-1]
    if "\\" in basename:
        basename = basename.rsplit("\\", 1)[-1]

    if basename in SENSITIVE_FILENAMES:
        return True
    return any(basename.startswith(p) for p in SENSITIVE_PREFIXES)


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
