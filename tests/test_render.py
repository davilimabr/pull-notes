"""Tests for render_from_parsed_template."""

import pytest

from pullnotes.domain.services.template_parser import TemplateSection, ParsedTemplate
from pullnotes.domain.services.composition import render_from_parsed_template


@pytest.fixture
def parsed_template_with_mixed():
    """Template with dynamic and static sections."""
    return ParsedTemplate(
        title_instruction="Titulo do PR",
        sections=[
            TemplateSection(
                heading="Descricao",
                key="descricao",
                body="Descreva o que foi alterado.",
                is_static=False,
            ),
            TemplateSection(
                heading="Tipo de Alteracao",
                key="tipo_de_alteracao",
                body="- [ ] Bug fix\n- [ ] Feature",
                is_static=True,
            ),
            TemplateSection(
                heading="Riscos",
                key="riscos",
                body="Descreva riscos.",
                is_static=False,
            ),
            TemplateSection(
                heading="Checklist",
                key="checklist",
                body="- [ ] Tests\n- [ ] Docs",
                is_static=True,
            ),
        ],
    )


class TestRenderFromParsedTemplate:
    def test_uses_provided_title(self, parsed_template_with_mixed):
        result = render_from_parsed_template(
            parsed_template_with_mixed,
            {"descricao": "Some desc", "riscos": "Some risk"},
            title="My PR Title",
        )
        assert result.startswith("# My PR Title\n")

    def test_includes_subtitle(self, parsed_template_with_mixed):
        result = render_from_parsed_template(
            parsed_template_with_mixed,
            {"descricao": "Some desc"},
            title="Title",
            subtitle="**Date**: 2026-02-16",
        )
        assert "**Date**: 2026-02-16" in result

    def test_omits_empty_dynamic_sections(self, parsed_template_with_mixed):
        result = render_from_parsed_template(
            parsed_template_with_mixed,
            {"descricao": "Some desc", "riscos": ""},
            title="Title",
        )
        assert "## Descricao" in result
        assert "## Riscos" not in result

    def test_preserves_static_sections(self, parsed_template_with_mixed):
        result = render_from_parsed_template(
            parsed_template_with_mixed,
            {"descricao": "Some desc"},
            title="Title",
        )
        assert "## Tipo de Alteracao" in result
        assert "- [ ] Bug fix" in result
        assert "## Checklist" in result
        assert "- [ ] Tests" in result

    def test_dynamic_section_content_included(self, parsed_template_with_mixed):
        result = render_from_parsed_template(
            parsed_template_with_mixed,
            {"descricao": "Changed the auth module", "riscos": "May break login"},
            title="Title",
        )
        assert "Changed the auth module" in result
        assert "May break login" in result

    def test_all_empty_dynamic_only_shows_static(self, parsed_template_with_mixed):
        result = render_from_parsed_template(
            parsed_template_with_mixed,
            {},
            title="Title",
        )
        assert "## Tipo de Alteracao" in result
        assert "## Checklist" in result
        assert "## Descricao" not in result
        assert "## Riscos" not in result

    def test_ends_with_newline(self, parsed_template_with_mixed):
        result = render_from_parsed_template(
            parsed_template_with_mixed,
            {"descricao": "Desc"},
            title="Title",
        )
        assert result.endswith("\n")

    def test_section_ordering_preserved(self, parsed_template_with_mixed):
        result = render_from_parsed_template(
            parsed_template_with_mixed,
            {"descricao": "Desc", "riscos": "Risk"},
            title="Title",
        )
        desc_pos = result.index("## Descricao")
        tipo_pos = result.index("## Tipo de Alteracao")
        riscos_pos = result.index("## Riscos")
        checklist_pos = result.index("## Checklist")
        assert desc_pos < tipo_pos < riscos_pos < checklist_pos

    def test_release_with_subtitle(self):
        parsed = ParsedTemplate(
            title_instruction="",
            sections=[
                TemplateSection(
                    heading="Resumo", key="resumo",
                    body="Descricao geral.", is_static=False,
                ),
            ],
        )
        result = render_from_parsed_template(
            parsed,
            {"resumo": "Big update"},
            title="Notas de Versao — v1.0.0",
            subtitle="**Data de lancamento**: 2026-02-16",
        )
        assert "# Notas de Versao — v1.0.0" in result
        assert "**Data de lancamento**: 2026-02-16" in result
        assert "## Resumo" in result
        assert "Big update" in result
