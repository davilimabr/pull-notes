"""Subprocess helpers."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

_PACKFILE_HINT = (
    "The repository has a packfile too large for git to memory-map.\n"
    "Fix with:\n"
    "  git config core.packedGitWindowSize 512m\n"
    "  git config core.packedGitLimit 512m\n"
    "Or repack: git gc --aggressive"
)


class PackfileTooLargeError(RuntimeError):
    """Raised when git cannot map a packfile due to size limits."""


def run_git(repo_dir: Path, args: List[str]) -> str:
    """Run a git command and return stdout."""
    cmd = ["git", "-C", str(repo_dir)] + args
    logger.debug("Running: %s", " ".join(cmd))
    # Force UTF-8 decoding to avoid Windows locale decode errors (e.g. cp1252).
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        stderr = result.stderr.strip()
        logger.debug("Git command failed (rc=%d): %s", result.returncode, stderr[:200])
        if "cannot be mapped" in stderr and "File too large" in stderr:
            raise PackfileTooLargeError(f"{stderr}\n\n{_PACKFILE_HINT}")
        raise RuntimeError(stderr or "Git command failed")
    logger.debug("Git command succeeded (%d bytes output)", len(result.stdout))
    return result.stdout
