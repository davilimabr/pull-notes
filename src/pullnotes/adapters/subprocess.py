"""Subprocess helpers."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)


def run_git(repo_dir: Path, args: List[str]) -> str:
    """Run a git command and return stdout."""
    cmd = ["git", "-C", str(repo_dir)] + args
    logger.debug("Running: %s", " ".join(cmd))
    # Force UTF-8 decoding to avoid Windows locale decode errors (e.g. cp1252).
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        logger.debug("Git command failed (rc=%d): %s", result.returncode, result.stderr.strip()[:200])
        raise RuntimeError(result.stderr.strip() or "Git command failed")
    logger.debug("Git command succeeded (%d bytes output)", len(result.stdout))
    return result.stdout
