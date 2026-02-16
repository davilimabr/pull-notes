"""Services for the repository data collection stage."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Optional

from ...adapters.subprocess import run_git
from ...adapters.domain_definition import top_keywords, API_METHOD_RE, EVENT_NAME_RE, SERVICE_NAME_RE
from ..models import COMMIT_MARKER, GIT_FORMAT, Commit, is_sensitive_file
from ..schemas import DiffAnchors, DiffKeyword, DiffArtifact


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


def _strip_sensitive_hunks(diff_text: str) -> str:
    """Remove diff hunks that belong to sensitive files.

    Each hunk starts with ``diff --git a/... b/...``.  When the target file
    is sensitive the entire section (up to the next ``diff --git`` or EOF) is
    dropped.
    """
    lines = diff_text.splitlines(keepends=True)
    result: list[str] = []
    skip = False

    for line in lines:
        if line.startswith("diff --git"):
            parts = line.split()
            # Format: diff --git a/path b/path
            file_path = parts[3].lstrip("b/") if len(parts) >= 4 else ""
            skip = is_sensitive_file(file_path)
        if not skip:
            result.append(line)

    return "".join(result)


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
                    if is_sensitive_file(path):
                        continue
                    files.append(path)
                    if add.isdigit():
                        additions += int(add)
                    if delete.isdigit():
                        deletions += int(delete)
            else:
                stripped = line.strip()
                if not is_sensitive_file(stripped):
                    files.append(stripped)
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

    # Extrai body e diff de forma assíncrona usando ThreadPoolExecutor
    def fetch_commit_details(commit: Commit) -> tuple[Commit, str, str]:
        """Busca body e diff de um commit."""
        body = run_git(repo_dir, ["show", "-s", "--format=%B", commit.sha]).strip()
        diff = run_git(repo_dir, ["show", "--pretty=format:", "--unified=3", "--no-color", commit.sha])
        return commit, body, diff

    # Executa todas as chamadas git em paralelo
    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(fetch_commit_details, commit): commit for commit in commits}
        for future in as_completed(futures):
            commit, body, diff = future.result()
            commit.body = body
            commit.diff = diff
            commit.diff_anchors = extract_diff_anchors(diff)

    return commits


def extract_diff_anchors(
    diff_text: str,
    max_keywords: int = 10,
    max_artifacts: int = 10
) -> DiffAnchors:
    """
    Extract semantic anchors from a git diff.

    Separates added/removed lines and extracts:
    - Keywords from content (excluding stopwords)
    - Artifacts matching known patterns (API endpoints, events, services, etc.)
    """
    if not diff_text.strip():
        return DiffAnchors()

    clean_diff = _strip_sensitive_hunks(diff_text)

    added_lines: List[str] = []
    removed_lines: List[str] = []
    files_changed: List[str] = []

    for line in clean_diff.splitlines():
        # Extract file names from diff headers
        if line.startswith("diff --git"):
            # Format: diff --git a/path/file b/path/file
            parts = line.split()
            if len(parts) >= 4:
                file_path = parts[3].lstrip("b/")
                if file_path not in files_changed:
                    files_changed.append(file_path)
        elif line.startswith("+") and not line.startswith("+++"):
            added_lines.append(line[1:])  # Remove + prefix
        elif line.startswith("-") and not line.startswith("---"):
            removed_lines.append(line[1:])  # Remove - prefix

    # Extract keywords
    keywords: List[DiffKeyword] = []
    added_text = "\n".join(added_lines)
    removed_text = "\n".join(removed_lines)

    for kw in top_keywords(added_text, top_n=max_keywords):
        keywords.append(DiffKeyword(text=kw, change_type="added"))
    for kw in top_keywords(removed_text, top_n=max_keywords):
        if not any(k.text == kw for k in keywords):  # Avoid duplicates
            keywords.append(DiffKeyword(text=kw, change_type="removed"))

    # Extract artifacts using existing patterns
    artifacts: List[DiffArtifact] = []
    seen_artifacts: set = set()

    def extract_artifacts_from_text(text: str, change_type: str) -> None:
        for match in API_METHOD_RE.finditer(text):
            key = ("api_endpoint", f"{match.group(1)} {match.group(2)}")
            if key not in seen_artifacts:
                seen_artifacts.add(key)
                artifacts.append(DiffArtifact(
                    kind="api_endpoint",
                    name=f"{match.group(1)} {match.group(2)}",
                    change_type=change_type
                ))
        for match in EVENT_NAME_RE.finditer(text):
            key = ("event", match.group(1))
            if key not in seen_artifacts:
                seen_artifacts.add(key)
                artifacts.append(DiffArtifact(kind="event", name=match.group(1), change_type=change_type))
        for match in SERVICE_NAME_RE.finditer(text):
            key = ("service", match.group(1))
            if key not in seen_artifacts:
                seen_artifacts.add(key)
                artifacts.append(DiffArtifact(kind="service", name=match.group(1), change_type=change_type))

    extract_artifacts_from_text(added_text, "added")
    extract_artifacts_from_text(removed_text, "removed")

    return DiffAnchors(
        files_changed=files_changed[:30],  # Limit files
        keywords=keywords[:max_keywords * 2],  # Limit total keywords
        artifacts=artifacts[:max_artifacts]
    )
