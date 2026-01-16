"""Services for grouping and summarizing repository changes."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

from ...adapters.http import call_ollama
from ...prompts import load_prompt
from ..models import Commit
from .data_collection import trim_diff


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
