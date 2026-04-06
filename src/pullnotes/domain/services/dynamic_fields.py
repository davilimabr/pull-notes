"""Geracao dinamica de schema e prompt a partir de secoes do template."""
from __future__ import annotations

import logging
from typing import List, Type

from pydantic import BaseModel, Field, create_model

from .template_parser import TemplateSection
from .aggregation import build_language_hint, build_language_reminder
from ...prompts import load_prompt

logger = logging.getLogger(__name__)


def build_dynamic_schema(
    sections: List[TemplateSection],
    schema_name: str = "DynamicFields",
    *,
    include_title: bool = False,
) -> Type[BaseModel]:
    """Gera um Pydantic model dinamico a partir das secoes do template.

    Cada secao dinamica vira um campo opcional (str, default="").
    Secoes estaticas NAO viram campos (sao preservadas como estao).
    """
    field_definitions = {}
    if include_title:
        field_definitions["title"] = (
            str,
            Field(..., description="Titulo conciso", min_length=5, max_length=100),
        )
    for section in sections:
        if section.is_static:
            continue
        field_definitions[section.key] = (
            str,
            Field(default="", description=section.body[:200]),
        )

    logger.debug("Dynamic schema '%s' created with %d fields: %s", schema_name, len(field_definitions), list(field_definitions.keys()))
    return create_model(schema_name, **field_definitions)


def build_dynamic_prompt(
    sections: List[TemplateSection],
    language: str,
    commit_summaries: str,
    changes_by_type: str,
    *,
    template_type: str = "pr",
    domain_context: str = "",
    version: str = "",
    title_instruction: str = "",
    alerts: str = "",
    changes_key: str = "",
) -> str:
    """Monta o prompt dinamicamente a partir das secoes do template.

    Inclui:
    - Instrucoes gerais (anti-alucinacao, idioma)
    - Descricao de cada secao dinamica com sua instrucao
    - Commits sumarizados e changes_by_type como contexto
    - Formato de saida esperado (JSON com as keys)

    The ``changes_key`` section is excluded from the fields to generate because
    its content is injected directly from ``changes_by_type``.
    """
    language_hint = build_language_hint(language)

    # Monta descricao das secoes
    sections_desc = []
    dynamic_keys = []

    # Inclui title como campo especial para PR
    if template_type == "pr" and title_instruction:
        dynamic_keys.append("title")
        sections_desc.append(
            f'- **title** (titulo do documento): {title_instruction}'
        )

    for section in sections:
        if section.is_static:
            continue
        # Skip changes section — filled directly, not by LLM
        if changes_key and section.key == changes_key:
            continue
        dynamic_keys.append(section.key)
        sections_desc.append(
            f'- **{section.key}** (secao "{section.heading}"): {section.body}'
        )

    sections_block = "\n".join(sections_desc)

    # JSON de exemplo para o formato de saida
    json_example_lines = []
    for key in dynamic_keys:
        json_example_lines.append(f'  "{key}": "conteudo gerado"')
    json_example = "{\n" + ",\n".join(json_example_lines) + "\n}"

    # Contexto extra para release
    extra_context = ""
    if template_type == "release" and domain_context:
        extra_context = f"\nDomain context (for understanding the project):\n{domain_context}\n"
    if version:
        extra_context += f"\nRelease version: {version}\n"

    # Bloco de alertas (commits fora do padrao)
    alerts_block = ""
    if alerts:
        alerts_block = f"### Commits fora do padrao convencional:\n{alerts}"

    prompt = load_prompt("dynamic_fields", {
        "template_type": template_type,
        "language_hint": language_hint,
        "language_reminder": build_language_reminder(language),
        "sections_block": sections_block,
        "extra_context": extra_context,
        "commit_summaries": commit_summaries,
        "changes_by_type": changes_by_type,
        "alerts_block": alerts_block,
        "json_example": json_example,
    })

    logger.debug("Dynamic prompt built for %s (%d keys, %d chars)", template_type, len(dynamic_keys), len(prompt))
    return prompt
