"""Services for composing final texts and templates."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Tuple, TYPE_CHECKING

from ...adapters.prompt_debug import save_prompt
from ...prompts import load_prompt
from ..models import Commit
from .aggregation import build_language_hint, group_commits_by_type

if TYPE_CHECKING:
    from ..schemas import PRFields, ReleaseFields


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


def _format_grouped_summaries(grouped_summaries: Dict[str, str], config: Dict) -> str:
    """Format grouped summaries for LLM prompt."""
    summaries_lines = []
    for change_type in config["commit_types"]:
        if change_type in grouped_summaries:
            label = config["commit_types"][change_type]["label"]
            summaries_lines.append(f"### {label}")
            summaries_lines.append(grouped_summaries[change_type])
            summaries_lines.append("")

    if "other" in grouped_summaries:
        summaries_lines.append(f"### {config['other_label']}")
        summaries_lines.append(grouped_summaries["other"])
        summaries_lines.append("")

    return "\n".join(summaries_lines).strip()


def build_pr_fields(grouped_summaries: Dict[str, str], config: Dict, model: str) -> "PRFields":
    """Build PR fields using grouped commit summaries.

    Args:
        grouped_summaries: Dictionary mapping change_type to formatted summary text (bullet points)
        config: Configuration dictionary
        model: LLM model to use

    Returns:
        PRFields with validated PR data
    """
    from ..schemas import PRFields
    from ...adapters.llm_structured import StructuredLLMClient

    client = StructuredLLMClient(
        model=model,
        timeout_seconds=config.get("llm_timeout_seconds", 600.0),
        max_retries=config.get("llm_max_retries", 3),
    )

    formatted_summaries = _format_grouped_summaries(grouped_summaries, config)

    prompt = load_prompt(
        "pr_fields",
        {
            "language_hint": build_language_hint(config["language"]),
            "commit_summaries": formatted_summaries,
        },
    )

    result = client.invoke_structured(prompt, PRFields)
    save_prompt(prompt, "pr_fields", result.model_dump_json(indent=2))
    return result


def build_release_fields(
    grouped_summaries: Dict[str, str], domain_context: str, config: Dict, model: str, version: str
) -> "ReleaseFields":
    """Build release fields using grouped commit summaries and domain context.

    Args:
        grouped_summaries: Dictionary mapping change_type to formatted summary text (bullet points)
        domain_context: Domain context (XML string or JSON string)
        config: Configuration dictionary
        model: LLM model to use
        version: Release version label

    Returns:
        ReleaseFields with validated release data
    """
    from ..schemas import ReleaseFields
    from ...adapters.llm_structured import StructuredLLMClient

    client = StructuredLLMClient(
        model=model,
        timeout_seconds=config.get("llm_timeout_seconds", 600.0),
        max_retries=config.get("llm_max_retries", 3),
    )

    formatted_summaries = _format_grouped_summaries(grouped_summaries, config)

    prompt = load_prompt(
        "release_fields",
        {
            "language_hint": build_language_hint(config["language"]),
            "release_version": version,
            "domain_context": domain_context[:6000],  # Limit size
            "commit_summaries": formatted_summaries,
        },
    )

    result = client.invoke_structured(prompt, ReleaseFields)
    save_prompt(prompt, "release_fields", result.model_dump_json(indent=2))
    return result


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
