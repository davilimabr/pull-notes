"""Subprocess helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List


def run_git(repo_dir: Path, args: List[str]) -> str:
    """Run a git command and return stdout."""
    cmd = ["git", "-C", str(repo_dir)] + args
    # Force UTF-8 decoding to avoid Windows locale decode errors (e.g. cp1252).
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Git command failed")
    return result.stdout
