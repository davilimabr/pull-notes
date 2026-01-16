"""Services for grouping and summarizing repository changes."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ...adapters.http import call_ollama
from ...prompts import load_prompt
from ..models import Commit
from .data_collection import trim_diff

_GROUP_LINE_RE = re.compile(r"^(?:[-*]\s*)?(?P<sha>[0-9a-fA-F]{7,})\s*[:\-]\s*(?P<summary>.+)$")
_JS_REGEX_RE = re.compile(r"^/(.+)/([a-zA-Z]*)$")


def _compile_config_pattern(pattern_spec) -> re.Pattern:
    """Allow JS-style /.../flags patterns or plain regex strings."""
    if isinstance(pattern_spec, re.Pattern):
        return pattern_spec
    if not isinstance(pattern_spec, str):
        raise ValueError(f"Commit pattern must be string or regex, got {type(pattern_spec)!r}")

    flags = re.IGNORECASE
    body = pattern_spec.strip()
    js_match = _JS_REGEX_RE.match(body)
    if js_match:
        body = js_match.group(1)
        flag_text = js_match.group(2).lower()
        flags = 0
        for char in flag_text:
            if char == "i":
                flags |= re.IGNORECASE
            elif char == "m":
                flags |= re.MULTILINE
            elif char == "s":
                flags |= re.DOTALL
        if not flags:
            flags = re.IGNORECASE

    # Config JSON often swallows backslashes like \b; restore common escapes.
    body = body.replace("\x08", r"\b")

    try:
        return re.compile(body, flags)
    except re.error as exc:
        raise ValueError(f"Invalid commit type pattern '{pattern_spec}': {exc}") from exc


def classify_commit(subject: str, commit_types: Dict[str, Dict]) -> Tuple[str, bool]:
    """Classify commit message using configured patterns."""
    clean_subject = subject.strip()
    for type_name, data in commit_types.items():
        compiled = data.get("_compiled_patterns")
        if compiled is None:
            compiled = [_compile_config_pattern(pattern) for pattern in data["patterns"]]
            data["_compiled_patterns"] = compiled
        for regex in compiled:
            if regex.search(clean_subject):
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


def group_commits_by_type(commits: List[Commit], config: Dict) -> List[Tuple[str, List[Commit]]]:
    """Group commits by configured type and sort each group by importance."""
    grouped: List[Tuple[str, List[Commit]]] = []
    commit_types = config["commit_types"]
    for type_name in commit_types:
        typed_commits = sorted(
            (c for c in commits if c.change_type == type_name), key=lambda c: c.importance_score, reverse=True
        )
        grouped.append((type_name, typed_commits))

    other_commits = sorted(
        (c for c in commits if c.change_type not in commit_types), key=lambda c: c.importance_score, reverse=True
    )
    if other_commits:
        grouped.append(("other", other_commits))
    return grouped


def build_language_hint(language: str) -> str:
    return f"Write the response in {language}."


def summarize_commit(commit: Commit, config: Dict, model: str) -> str:
    """Summarize commit using LLM."""
    diff_cfg = config["diff"]
    diff = trim_diff(commit.diff, diff_cfg["max_lines"], diff_cfg["max_bytes"])
    prompt = load_prompt(
        "commit_summary",
        {
            "language_hint": build_language_hint(config["language"]),
            "commit_message": f"{commit.subject}\n{commit.body}",
            "files": "\n".join(f"- {f}" for f in commit.files[:30]),
            "diff": diff,
        },
    )
    return call_ollama(model, prompt, config.get("llm_timeout_seconds"))


def _build_commit_blocks(commits: List[Commit], diff_cfg: Dict) -> str:
    blocks: List[str] = []
    for commit in commits:
        files = "\n".join(f"- {f}" for f in commit.files[:30]) or "- (no files listed)"
        trimmed_diff = trim_diff(commit.diff, diff_cfg["max_lines"], diff_cfg["max_bytes"])
        diff_text = trimmed_diff if trimmed_diff.strip() else "(diff vazio ou indisponivel)"
        body_text = commit.body.strip() or "(sem corpo)"
        blocks.append(
            "\n".join(
                [
                    f"Commit: {commit.short_sha}",
                    f"Subject: {commit.subject}",
                    f"Body: {body_text}",
                    "Files:",
                    files,
                    "Diff (truncated):",
                    diff_text,
                ]
            )
        )
    return "\n\n".join(blocks)


def _parse_group_summary_output(raw: str, expected_shas: List[str]) -> Dict[str, str]:
    summaries: Dict[str, str] = {}
    expected_set = {sha.lower() for sha in expected_shas}
    for line in raw.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        match = _GROUP_LINE_RE.match(cleaned)
        if not match:
            continue
        sha = match.group("sha").lower()[:7]
        summary = match.group("summary").strip()
        if sha in expected_set and sha not in summaries and summary:
            summaries[sha] = summary
    return summaries


def summarize_commit_group(commit_type: str, commits: List[Commit], config: Dict, model: str) -> Dict[str, str]:
    """Summarize a list of commits of the same type in a single LLM call."""
    commit_types = config.get("commit_types", {})
    label = commit_types.get(commit_type, {}).get("label") or config.get("other_label", commit_type)
    diff_cfg = config["diff"]
    prompt = load_prompt(
        "commit_group_summary",
        {
            "language_hint": build_language_hint(config["language"]),
            "change_type_label": label,
            "commit_blocks": _build_commit_blocks(commits, diff_cfg),
        },
    )
    raw = call_ollama(model, prompt, config.get("llm_timeout_seconds"))
    return _parse_group_summary_output(raw, [c.short_sha for c in commits])


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
