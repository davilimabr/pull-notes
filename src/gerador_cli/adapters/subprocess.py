"""Subprocess helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List


def run_git(repo_dir: Path, args: List[str]) -> str:
    """Run a git command and return stdout."""
    cmd = ["git", "-C", str(repo_dir)] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Git command failed")
    return result.stdout
