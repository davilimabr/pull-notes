"""Services for composing final texts and templates."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Tuple, TYPE_CHECKING

from ...adapters.prompt_debug import save_prompt
from ..models import Commit
from .aggregation import build_language_hint, group_commits_by_type

if TYPE_CHECKING:
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

    # Fallback: ensure changes_by_type is present in at least one section
    if changes_by_type.strip():
        _ensure_changes_included(fields, dynamic_sections, changes_by_type)

    return fields


def _ensure_changes_included(
    fields: Dict[str, str],
    dynamic_sections: list,
    changes_by_type: str,
) -> None:
    """Ensure changes_by_type content is present in the fields.

    If no dynamic field contains substantial content from changes_by_type,
    inject it into the first dynamic section (most relevant for changes).
    """
    # Check if any field already has substantial content (more than just a summary)
    non_empty_fields = {k: v for k, v in fields.items() if v.strip() and k != "title"}
    if not non_empty_fields:
        # All fields empty — inject changes into first dynamic section
        if dynamic_sections:
            target_key = dynamic_sections[0].key
            fields[target_key] = changes_by_type
        return

    # Check if changes are distributed: count fields with content >= 3 lines
    fields_with_content = sum(
        1 for v in non_empty_fields.values()
        if len(v.strip().splitlines()) >= 3
    )
    if fields_with_content >= 2:
        # LLM distributed content across multiple fields — trust it
        return

    # Only one field has substantial content — the LLM probably put everything
    # in one place. Check if the first dynamic section has the grouped changes.
    first_key = dynamic_sections[0].key
    first_content = fields.get(first_key, "")
    if "###" not in first_content and changes_by_type.strip():
        # Missing type headers — append changes_by_type to preserve grouping
        if first_content.strip():
            fields[first_key] = first_content.strip() + "\n\n" + changes_by_type
        else:
            fields[first_key] = changes_by_type


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
