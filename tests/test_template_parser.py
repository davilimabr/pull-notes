"""Tests for template_parser module."""

import pytest
from pathlib import Path

from pullnotes.domain.services.template_parser import (
    ParsedTemplate,
    TemplateSection,
    _slugify,
    parse_template,
)


# ---- _slugify tests ----

class TestSlugify:
    def test_simple_text(self):
        assert _slugify("Descricao") == "descricao"

    def test_spaces_to_underscore(self):
        assert _slugify("Riscos e Impactos") == "riscos_e_impactos"

    def test_accented_chars(self):
        assert _slugify("Alterações Realizadas") == "alteracoes_realizadas"

    def test_cedilla(self):
        assert _slugify("Correções") == "correcoes"

    def test_mixed_accents(self):
        assert _slugify("Notas de Infraestrutura") == "notas_de_infraestrutura"

    def test_special_chars_removed(self):
        assert _slugify("Tipo de Alteração!") == "tipo_de_alteracao"

    def test_leading_trailing_underscores_stripped(self):
        assert _slugify("  Hello World  ") == "hello_world"

    def test_tilde_accents(self):
        assert _slugify("ã õ") == "a_o"

    def test_circumflex_accents(self):
        assert _slugify("â ê ô") == "a_e_o"


# ---- parse_template tests ----

class TestParseTemplatePR:
    """Test parsing the PR template."""

    @pytest.fixture
    def pr_template(self):
        template_path = Path(__file__).parent.parent / "src" / "pullnotes" / "templates" / "pr.md"
        return template_path.read_text(encoding="utf-8")

    def test_extracts_title(self, pr_template):
        parsed = parse_template(pr_template)
        assert parsed.title_instruction == "Titulo do Pull Request"

    def test_extracts_correct_number_of_sections(self, pr_template):
        parsed = parse_template(pr_template)
        assert len(parsed.sections) == 6

    def test_section_headings(self, pr_template):
        parsed = parse_template(pr_template)
        headings = [s.heading for s in parsed.sections]
        assert headings == [
            "Descricao",
            "Tipo de Alteracao",
            "Alteracoes Realizadas",
            "Riscos e Impactos",
            "Plano de Testes",
            "Checklist",
        ]

    def test_static_sections(self, pr_template):
        parsed = parse_template(pr_template)
        static_names = [s.heading for s in parsed.static_sections]
        assert "Tipo de Alteracao" in static_names
        assert "Plano de Testes" in static_names
        assert "Checklist" in static_names

    def test_dynamic_sections(self, pr_template):
        parsed = parse_template(pr_template)
        dynamic_names = [s.heading for s in parsed.dynamic_sections]
        assert "Descricao" in dynamic_names
        assert "Alteracoes Realizadas" in dynamic_names
        assert "Riscos e Impactos" in dynamic_names

    def test_static_count(self, pr_template):
        parsed = parse_template(pr_template)
        assert len(parsed.static_sections) == 3

    def test_dynamic_count(self, pr_template):
        parsed = parse_template(pr_template)
        assert len(parsed.dynamic_sections) == 3

    def test_section_keys_are_slugified(self, pr_template):
        parsed = parse_template(pr_template)
        keys = [s.key for s in parsed.sections]
        assert "descricao" in keys
        assert "tipo_de_alteracao" in keys
        assert "alteracoes_realizadas" in keys
        assert "riscos_e_impactos" in keys

    def test_section_body_not_empty(self, pr_template):
        parsed = parse_template(pr_template)
        for section in parsed.sections:
            assert section.body, f"Section '{section.heading}' has empty body"


class TestParseTemplateRelease:
    """Test parsing the Release template."""

    @pytest.fixture
    def release_template(self):
        template_path = Path(__file__).parent.parent / "src" / "pullnotes" / "templates" / "release.md"
        return template_path.read_text(encoding="utf-8")

    def test_extracts_title(self, release_template):
        parsed = parse_template(release_template)
        # Title contains the h1 instruction
        assert "Notas de Versao" in parsed.title_instruction

    def test_extracts_correct_number_of_sections(self, release_template):
        parsed = parse_template(release_template)
        assert len(parsed.sections) == 8

    def test_section_headings(self, release_template):
        parsed = parse_template(release_template)
        headings = [s.heading for s in parsed.sections]
        assert headings == [
            "Resumo",
            "Novidades",
            "Melhorias",
            "Correcoes",
            "Alteracoes que Quebram Compatibilidade",
            "Alteracoes de Dependencias",
            "Problemas Conhecidos",
            "Notas de Infraestrutura",
        ]

    def test_all_sections_are_dynamic(self, release_template):
        parsed = parse_template(release_template)
        assert len(parsed.static_sections) == 0
        assert len(parsed.dynamic_sections) == 8

    def test_subsection_included_in_body(self, release_template):
        """### Guia de Migracao should be part of 'Alteracoes que Quebram Compatibilidade' body."""
        parsed = parse_template(release_template)
        breaking = next(s for s in parsed.sections if s.heading == "Alteracoes que Quebram Compatibilidade")
        assert "Guia de Migracao" in breaking.body


class TestParseTemplateEdgeCases:
    """Test edge cases for the parser."""

    def test_empty_template(self):
        parsed = parse_template("")
        assert parsed.title_instruction == ""
        assert parsed.sections == []

    def test_title_only(self):
        parsed = parse_template("# My Title")
        assert parsed.title_instruction == "My Title"
        assert parsed.sections == []

    def test_no_title(self):
        template = "## Section One\n\nContent here\n\n## Section Two\n\nMore content"
        parsed = parse_template(template)
        assert parsed.title_instruction == ""
        assert len(parsed.sections) == 2

    def test_checkbox_detection(self):
        template = "## Static Section\n\n- [ ] Item one\n- [x] Item two\n\n## Dynamic Section\n\nNo checkboxes here"
        parsed = parse_template(template)
        assert parsed.sections[0].is_static is True
        assert parsed.sections[1].is_static is False

    def test_minimal_template(self):
        template = "# Title\n\n## Only Section\n\nJust some text"
        parsed = parse_template(template)
        assert parsed.title_instruction == "Title"
        assert len(parsed.sections) == 1
        assert parsed.sections[0].heading == "Only Section"
        assert parsed.sections[0].body == "Just some text"
        assert parsed.sections[0].is_static is False

    def test_all_levels_are_2(self):
        template = "## A\n\nBody A\n\n## B\n\nBody B"
        parsed = parse_template(template)
        for section in parsed.sections:
            assert section.level == 2
