"""Services for composing final texts and templates."""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Dict, List, Tuple

from ...adapters.http import call_ollama
from ...prompts import load_prompt
from ..models import Commit
from .aggregation import build_language_hint, group_commits_by_type


def build_version_label(version_override: str, revision_range: str | None, release_cfg: Dict) -> str:
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


def extract_json(text: str) -> Dict:
    """Extract JSON object from a string."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found. LLM response: {text[:500]}")

    json_str = text[start : end + 1]
    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from LLM. Error: {e}. JSON string: {json_str[:500]}")


def build_pr_fields(commits: List[Commit], config: Dict, model: str) -> Dict[str, str]:
    """Build PR fields using commit summaries."""
    import sys

    prompt = load_prompt(
        "pr_fields",
        {
            "language_hint": build_language_hint(config["language"]),
            "commit_summaries": "\n".join(f"- {c.summary or c.subject}" for c in commits),
        },
    )
    print(f"\n=== DEBUG: PR Fields Prompt (first 1000 chars) ===\n{prompt[:1000]}\n", file=sys.stderr)
    raw = call_ollama(model, prompt, config.get("llm_timeout_seconds"))
    print(f"\n=== DEBUG: LLM Response (first 1000 chars) ===\n{raw[:1000]}\n", file=sys.stderr)
    return extract_json(raw)


def build_release_fields(
    commits: List[Commit], domain_xml: str, config: Dict, model: str, version: str
) -> Dict[str, str]:
    """Build release fields using commit summaries and domain context."""
    import sys

    prompt = load_prompt(
        "release_fields",
        {
            "language_hint": build_language_hint(config["language"]),
            "release_version": version,
            "domain_xml": domain_xml,
            "commit_summaries": "\n".join(f"- {c.summary or c.subject}" for c in commits),
        },
    )
    print(f"\n=== DEBUG: Release Fields Prompt (first 1000 chars) ===\n{prompt[:1000]}\n", file=sys.stderr)
    raw = call_ollama(model, prompt, config.get("llm_timeout_seconds"))
    print(f"\n=== DEBUG: LLM Response (first 1000 chars) ===\n{raw[:1000]}\n", file=sys.stderr)
    return extract_json(raw)


def render_template(template_text: str, values: Dict[str, str]) -> str:
    """Render simple placeholder template."""
    out = template_text
    for key, value in values.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    out = re.sub(r"{{\s*[\w_]+\s*}}", "", out)
    return out.strip() + "\n"


def render_changes_by_type_from_summaries(
    grouped_commits: List[Tuple[str, List[Commit]]], summaries_by_type: Dict[str, str], config: Dict
) -> str:
    """Render changes grouped by commit type using pre-generated summaries.

    Args:
        grouped_commits: List of (type, commits) tuples
        summaries_by_type: Dictionary mapping change_type to formatted summary text (bullet points)
        config: Configuration dictionary

    Returns:
        Formatted markdown with changes by type
    """
    by_type: Dict[str, List[Commit]] = {type_name: group for type_name, group in grouped_commits}
    lines = []

    for type_name, data in config["commit_types"].items():
        group = by_type.get(type_name, [])
        if not group:
            continue

        lines.append(f"### {data['label']}")
        summary_text = summaries_by_type.get(type_name, "")
        if summary_text:
            lines.append(summary_text)
        else:
            # Fallback to individual commit subjects
            for commit in group:
                lines.append(f"- {commit.subject}")
        lines.append("")

    other_group = by_type.get("other", [])
    if other_group:
        lines.append(f"### {config['other_label']}")
        summary_text = summaries_by_type.get("other", "")
        if summary_text:
            lines.append(summary_text)
        else:
            for commit in other_group:
                lines.append(f"- {commit.subject}")
        lines.append("")

    return "\n".join(lines).strip()
