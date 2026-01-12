"""Domain services for commit processing and text generation."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..adapters.http import call_ollama
from ..adapters.subprocess import run_git
from .models import COMMIT_MARKER, GIT_FORMAT, Commit


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
    args = ["log", "--date=iso-strict", f"--pretty=format:{GIT_FORMAT}", "--numstat"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    if revision_range:
        args.append(revision_range)
    log_text = run_git(repo_dir, args)
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


def classify_commit(subject: str, commit_types: Dict[str, Dict]) -> Tuple[str, bool]:
    """Classify commit message using configured patterns."""
    clean_subject = subject.strip()
    for type_name, data in commit_types.items():
        for pattern in data["patterns"]:
            if re.search(pattern, clean_subject, flags=re.IGNORECASE):
                return type_name, True
    return "other", False


def compute_importance(commit: Commit, config: Dict) -> Tuple[float, str]:
    """Compute importance score and band for a commit."""
    imp = config["importance"]
    score = (commit.additions + commit.deletions) * imp["weight_lines"]
    score += len(commit.files) * imp["weight_files"]
    lowered = (commit.subject + "\n" + commit.body).lower()
    for keyword, bonus in imp["keyword_bonus"].items():
        if keyword in lowered:
            score += float(bonus)
    bands = sorted(config["importance_bands"], key=lambda x: x["min"])
    band = bands[0]["name"]
    for item in bands:
        if score >= item["min"]:
            band = item["name"]
    return score, band


def build_language_hint(language: str) -> str:
    return f"Write the response in {language}."


def build_version_label(version_override: str, revision_range: Optional[str], release_cfg: Dict) -> str:
    """Build version label from override or template/date."""
    if version_override:
        return version_override
    date_label = datetime.now().strftime(release_cfg["date_format"])
    try:
        label = release_cfg["version_template"].format(
            revision_range=revision_range or "",
            date=date_label,
        ).strip()
    except KeyError as exc:
        raise SystemExit(f"Invalid release.version_template placeholder: {exc}") from exc
    if not label:
        raise SystemExit("Release version label is empty. Provide --version or set release.version_template.")
    return label


def summarize_commit(commit: Commit, config: Dict, model: str) -> str:
    """Summarize commit using LLM."""
    diff_cfg = config["diff"]
    diff = trim_diff(commit.diff, diff_cfg["max_lines"], diff_cfg["max_bytes"])
    prompt = (
        "You are a careful assistant. Summarize the commit in 1-2 sentences.\n"
        "Use only facts present in the message, files, and diff.\n"
        "If unsure, answer with: Contexto insuficiente para resumir.\n"
        f"{build_language_hint(config['language'])}\n\n"
        "Commit message:\n"
        f"{commit.subject}\n{commit.body}\n\n"
        "Files:\n"
        + "\n".join(f"- {f}" for f in commit.files[:30])
        + "\n\nDiff (truncated):\n"
        f"{diff}\n\n"
        "Return only the summary text."
    )
    return call_ollama(model, prompt)


def extract_json(text: str) -> Dict:
    """Extract JSON object from a string."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return json.loads(text[start : end + 1])


def build_pr_fields(commits: List[Commit], config: Dict, model: str) -> Dict[str, str]:
    """Build PR fields using commit summaries."""
    prompt = (
        "You are a careful assistant. Produce JSON with keys: title, summary, risks, testing.\n"
        "Use only the facts present in commit summaries and messages.\n"
        "If unsure about risks/testing, return empty string for those fields.\n"
        f"{build_language_hint(config['language'])}\n\n"
        "Commit summaries:\n"
        + "\n".join(f"- {c.summary or c.subject}" for c in commits)
        + "\n\nReturn only JSON."
    )
    raw = call_ollama(model, prompt)
    return extract_json(raw)


def build_release_fields(
    commits: List[Commit], domain_xml: str, config: Dict, model: str, version: str
) -> Dict[str, str]:
    """Build release fields using commit summaries and domain context."""
    prompt = (
        "You are a careful assistant. Produce JSON with keys: executive_summary, highlights, "
        "migration_notes, known_issues, internal_notes.\n"
        "Use only facts present in commit summaries, messages, and the domain XML context.\n"
        f"{build_language_hint(config['language'])}\n\n"
        f"Release version: {version}\n\n"
        "Domain XML (truncated):\n"
        f"{domain_xml}\n\n"
        "Commit summaries:\n"
        + "\n".join(f"- {c.summary or c.subject}" for c in commits)
        + "\n\nReturn only JSON."
    )
    raw = call_ollama(model, prompt)
    return extract_json(raw)


def render_template(template_text: str, values: Dict[str, str]) -> str:
    """Render simple placeholder template."""
    out = template_text
    for key, value in values.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    out = re.sub(r"{{\s*[\w_]+\s*}}", "", out)
    return out.strip() + "\n"


def render_changes_by_type(commits: List[Commit], config: Dict) -> str:
    """Render changes grouped by commit type."""
    by_type: Dict[str, List[Commit]] = {}
    for commit in commits:
        by_type.setdefault(commit.change_type, []).append(commit)
    lines = []
    for type_name, data in config["commit_types"].items():
        group = by_type.get(type_name, [])
        if not group:
            continue
        lines.append(f"### {data['label']}")
        for commit in sorted(group, key=lambda c: c.importance_score, reverse=True):
            summary = commit.summary or commit.subject
            lines.append(f"- {summary} ({commit.short_sha}, {commit.importance_band})")
        lines.append("")
    other_group = by_type.get("other", [])
    if other_group:
        lines.append(f"### {config['other_label']}")
        for commit in sorted(other_group, key=lambda c: c.importance_score, reverse=True):
            summary = commit.summary or commit.subject
            lines.append(f"- {summary} ({commit.short_sha}, {commit.importance_band})")
        lines.append("")
    return "\n".join(lines).strip()


def build_convention_report(commits: List[Commit]) -> str:
    """Build markdown report about conventional commits usage."""
    total = len(commits)
    classified = sum(1 for c in commits if c.is_conventional)
    other = total - classified
    examples_good = [c.subject for c in commits if c.is_conventional][:3]
    examples_bad = [c.subject for c in commits if not c.is_conventional][:3]
    lines = [
        "# Convention Report",
        f"- Total commits: {total}",
        f"- Conventional: {classified}",
        f"- Others: {other}",
        "",
        "## Good Examples",
    ]
    lines += [f"- {s}" for s in examples_good] if examples_good else ["- (none)"]
    lines += ["", "## Bad Examples"]
    lines += [f"- {s}" for s in examples_bad] if examples_bad else ["- (none)"]
    lines.append("")
    return "\n".join(lines)
