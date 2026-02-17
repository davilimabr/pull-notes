"""Parser de templates markdown."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


# Heuristica: secao contem checkbox se tem linhas com "- [ ]" ou "- [x]"
_CHECKBOX_RE = re.compile(r"^\s*-\s*\[[ xX]\]", re.MULTILINE)


@dataclass
class TemplateSection:
    """Uma secao extraida do template."""
    heading: str           # Nome original do heading (ex: "Descricao")
    key: str               # Slug para uso como campo (ex: "descricao")
    body: str              # Texto sob o heading (instrucao ou conteudo estatico)
    is_static: bool        # True se contem checkboxes (preservar como esta)
    level: int = 2         # Nivel do heading (2 para ##, 3 para ###, etc)


@dataclass
class ParsedTemplate:
    """Resultado do parsing de um template."""
    title_instruction: str          # Texto sob o # (instrucao para titulo, PR only)
    sections: List[TemplateSection] = field(default_factory=list)

    @property
    def dynamic_sections(self) -> List[TemplateSection]:
        """Secoes que a LLM deve preencher."""
        return [s for s in self.sections if not s.is_static]

    @property
    def static_sections(self) -> List[TemplateSection]:
        """Secoes com checkboxes, preservadas como estao."""
        return [s for s in self.sections if s.is_static]


def _slugify(text: str) -> str:
    """Converte heading em slug para usar como key de campo."""
    # Remove acentos comuns do portugues
    replacements = {
        'a': 'a', 'e': 'e', 'i': 'i', 'o': 'o', 'u': 'u',
        'c': 'c', 'A': 'A', 'E': 'E', 'I': 'I', 'O': 'O',
        'U': 'U', 'C': 'C',
        'ã': 'a', 'õ': 'o', 'â': 'a', 'ê': 'e', 'ô': 'o',
        'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u',
        'à': 'a', 'ç': 'c',
    }
    slug = text.lower()
    for orig, repl in replacements.items():
        slug = slug.replace(orig, repl)
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug


def parse_template(template_text: str) -> ParsedTemplate:
    """Extrai estrutura de um template markdown.

    Regras:
    - # (h1) -> titulo (instrucao capturada mas heading nao vira secao)
    - ## (h2) -> secoes de nivel superior
    - ### (h3+) -> tratados como parte do body da secao ## pai
    - Secoes com checkboxes (- [ ]) -> marcadas como estaticas
    """
    lines = template_text.splitlines()
    title_instruction = ""
    sections: List[TemplateSection] = []

    current_heading = None
    current_body_lines: List[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Detecta heading ## (nivel 2)
        if line.startswith("## "):
            # Fecha secao anterior se existir
            if current_heading is not None:
                body = "\n".join(current_body_lines).strip()
                is_static = bool(_CHECKBOX_RE.search(body))
                sections.append(TemplateSection(
                    heading=current_heading,
                    key=_slugify(current_heading),
                    body=body,
                    is_static=is_static,
                    level=2,
                ))

            current_heading = line[3:].strip()
            current_body_lines = []

        # Detecta heading # (nivel 1) — titulo
        elif line.startswith("# ") and not line.startswith("## "):
            # Se ja tinhamos um heading acumulado, fecha
            if current_heading is not None:
                body = "\n".join(current_body_lines).strip()
                is_static = bool(_CHECKBOX_RE.search(body))
                sections.append(TemplateSection(
                    heading=current_heading,
                    key=_slugify(current_heading),
                    body=body,
                    is_static=is_static,
                    level=2,
                ))
                current_heading = None
                current_body_lines = []

            title_instruction = line[2:].strip()

        else:
            # Acumula no body da secao atual (incluindo ### subsecoes)
            if current_heading is not None:
                current_body_lines.append(line)
            elif title_instruction and not sections:
                # Texto apos o # e antes do primeiro ##
                # (parte da instrucao do titulo, ignora linhas vazias iniciais)
                pass

        i += 1

    # Fecha ultima secao
    if current_heading is not None:
        body = "\n".join(current_body_lines).strip()
        is_static = bool(_CHECKBOX_RE.search(body))
        sections.append(TemplateSection(
            heading=current_heading,
            key=_slugify(current_heading),
            body=body,
            is_static=is_static,
            level=2,
        ))

    static_count = sum(1 for s in sections if s.is_static)
    dynamic_count = len(sections) - static_count
    logger.debug(
        "Template parsed: %d sections (%d dynamic, %d static), title_instruction='%s'",
        len(sections), dynamic_count, static_count, title_instruction[:50],
    )

    return ParsedTemplate(
        title_instruction=title_instruction,
        sections=sections,
    )
