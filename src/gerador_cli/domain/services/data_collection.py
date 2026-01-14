"""Services for the repository data collection stage."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from ...adapters.subprocess import run_git
from ..models import COMMIT_MARKER, GIT_FORMAT, Commit


def _prefix_origin_range(revision_range: str) -> str:
    """Prefix refs in a revision range with origin/ for fallback."""

    def add_origin(ref: str) -> str:
        if not ref or ref == "HEAD" or ref.startswith("origin/"):
            return ref
        return f"origin/{ref}"

    if "..." in revision_range:
        sep = "..."
    elif ".." in revision_range:
        sep = ".."
    else:
        return add_origin(revision_range)

    left, right = revision_range.split(sep, 1)
    return f"{add_origin(left)}{sep}{add_origin(right)}"


def parse_git_log(log_text: str) -> List[Commit]:
    """Parse git log output into Commit objects."""
    commits: List[Commit] = []
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i] != COMMIT_MARKER:
            i += 1
            continue
        if i + 1 >= len(lines):
            break
        header = lines[i + 1]
        i += 2
        parts = header.split("\x1f")
        if len(parts) < 5:
            continue
        sha, author_name, author_email, date, subject = parts[:5]
        additions = 0
        deletions = 0
        files: List[str] = []
        while i < len(lines) and lines[i] != COMMIT_MARKER:
            line = lines[i]
            i += 1
            if not line.strip():
                continue
            if "\t" in line:
                cols = line.split("\t")
                if len(cols) >= 3:
                    add, delete, path = cols[:3]
                    files.append(path)
                    if add.isdigit():
                        additions += int(add)
                    if delete.isdigit():
                        deletions += int(delete)
            else:
                files.append(line.strip())
        commits.append(
            Commit(
                sha=sha,
                author_name=author_name,
                author_email=author_email,
                date=date,
                subject=subject,
                files=files,
                additions=additions,
                deletions=deletions,
            )
        )
    return commits


def get_commits(repo_dir: Path, revision_range: Optional[str], since: Optional[str], until: Optional[str]) -> List[Commit]:
    """Fetch commits within a git range and attach body/diff."""
    args_base = ["log", "--date=iso-strict", f"--pretty=format:{GIT_FORMAT}", "--numstat"]
    if since:
        args_base.append(f"--since={since}")
    if until:
        args_base.append(f"--until={until}")

    range_to_use = revision_range
    args = args_base + ([range_to_use] if range_to_use else [])
    try:
        log_text = run_git(repo_dir, args)
    except RuntimeError as exc:
        if not revision_range:
            raise
        origin_range = _prefix_origin_range(revision_range)
        if origin_range == revision_range:
            raise
        retry_args = args_base + [origin_range]
        try:
            log_text = run_git(repo_dir, retry_args)
        except RuntimeError as retry_exc:
            raise RuntimeError(f"{exc} ; fallback with '{origin_range}' failed: {retry_exc}") from retry_exc

    commits = parse_git_log(log_text)
    for commit in commits:
        commit.body = run_git(repo_dir, ["show", "-s", "--format=%B", commit.sha]).strip()
        commit.diff = run_git(repo_dir, ["show", "--pretty=format:", "--unified=3", "--no-color", commit.sha])
    return commits


def trim_diff(diff_text: str, max_lines: int, max_bytes: int) -> str:
    """Trim diff content by lines and bytes."""
    lines = diff_text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    trimmed = "\n".join(lines)
    if len(trimmed.encode("utf-8")) > max_bytes:
        trimmed = trimmed.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
    return trimmed
