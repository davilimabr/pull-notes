"""Services for composing final texts and templates."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List, Tuple, TYPE_CHECKING

from ...adapters.prompt_debug import save_prompt
from ...prompts import load_prompt
from ..models import Commit
from .aggregation import build_language_hint, group_commits_by_type

if TYPE_CHECKING:
    from ..schemas import PRFields, ReleaseFields
    from .template_parser import ParsedTemplate

logger = logging.getLogger(__name__)


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


def build_fields_from_template(
    parsed_template: "ParsedTemplate",
    grouped_summaries: Dict[str, str],
    changes_by_type: str,
    config: Dict,
    model: str,
    *,
    template_type: str = "pr",
    domain_context: str = "",
    version: str = "",
    alerts: str = "",
) -> Dict[str, str]:
    """Gera campos dinamicamente a partir do template parseado.

    1. Gera schema Pydantic dinamico
    2. Monta prompt com instrucoes das secoes
    3. Chama LLM com structured output
    4. Retorna dict com campos preenchidos
    """
    from .dynamic_fields import build_dynamic_schema, build_dynamic_prompt
    from ...adapters.llm_structured import StructuredLLMClient

    dynamic_sections = parsed_template.dynamic_sections
    if not dynamic_sections:
        logger.debug("No dynamic sections in template, returning empty fields")
        return {}

    include_title = template_type == "pr"
    schema = build_dynamic_schema(
        dynamic_sections,
        f"{template_type.capitalize()}Fields",
        include_title=include_title,
    )

    formatted_summaries = _format_grouped_summaries(grouped_summaries, config)

    prompt = build_dynamic_prompt(
        sections=parsed_template.sections,
        language=config["language"],
        commit_summaries=formatted_summaries,
        changes_by_type=changes_by_type,
        template_type=template_type,
        domain_context=domain_context,
        version=version,
        title_instruction=parsed_template.title_instruction,
        alerts=alerts,
    )

    client = StructuredLLMClient(
        model=model,
        timeout_seconds=config.get("llm_timeout_seconds", 600.0),
        max_retries=config.get("llm_max_retries", 3),
    )

    logger.debug(
        "Generating %s fields from template (%d dynamic sections, model=%s)",
        template_type, len(dynamic_sections), model,
    )
    result = client.invoke_structured(prompt, schema)
    save_prompt(prompt, f"{template_type}_fields", result.model_dump_json(indent=2))
    fields = result.model_dump()
    logger.debug("Generated fields: %s", list(fields.keys()))
    return fields


def render_from_parsed_template(
    parsed_template: "ParsedTemplate",
    fields: Dict[str, str],
    *,
    title: str,
    subtitle: str = "",
) -> str:
    """Renderiza o documento final a partir do template parseado e campos preenchidos.

    Regras:
    - Titulo (h1) = parametro title
    - Secoes dinamicas: se campo preenchido (nao vazio), inclui heading + conteudo
    - Secoes dinamicas: se campo vazio, OMITE a secao inteira
    - Secoes estaticas: preservadas como estao no template
    """
    lines = [f"# {title}"]
    if subtitle:
        lines.append("")
        lines.append(subtitle)

    for section in parsed_template.sections:
        if section.is_static:
            lines.append("")
            lines.append(f"## {section.heading}")
            if section.body:
                lines.append("")
                lines.append(section.body)
        else:
            content = fields.get(section.key, "").strip()
            if content:
                lines.append("")
                lines.append(f"## {section.heading}")
                lines.append("")
                lines.append(content)

    rendered = "\n".join(lines).strip() + "\n"
    logger.debug("Rendered template: %d lines, title='%s'", len(rendered.splitlines()), title)
    return rendered
