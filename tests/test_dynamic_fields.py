"""Tests for dynamic_fields module (schema and prompt generation)."""

import pytest

from pullnotes.domain.services.template_parser import TemplateSection, ParsedTemplate
from pullnotes.domain.services.dynamic_fields import (
    build_dynamic_schema,
    build_dynamic_prompt,
)


# ---- Fixtures ----

@pytest.fixture
def sample_dynamic_sections():
    return [
        TemplateSection(
            heading="Descricao",
            key="descricao",
            body="Descreva o que foi alterado.",
            is_static=False,
        ),
        TemplateSection(
            heading="Riscos e Impactos",
            key="riscos_e_impactos",
            body="Descreva riscos conhecidos.",
            is_static=False,
        ),
    ]


@pytest.fixture
def sample_mixed_sections():
    """Sections with both dynamic and static."""
    return [
        TemplateSection(
            heading="Descricao",
            key="descricao",
            body="Descreva o que foi alterado.",
            is_static=False,
        ),
        TemplateSection(
            heading="Checklist",
            key="checklist",
            body="- [ ] Item 1\n- [ ] Item 2",
            is_static=True,
        ),
        TemplateSection(
            heading="Riscos",
            key="riscos",
            body="Descreva riscos.",
            is_static=False,
        ),
    ]


# ---- build_dynamic_schema tests ----

class TestBuildDynamicSchema:
    def test_creates_model_with_dynamic_fields(self, sample_dynamic_sections):
        schema = build_dynamic_schema(sample_dynamic_sections)
        fields = schema.model_fields
        assert "descricao" in fields
        assert "riscos_e_impactos" in fields

    def test_excludes_static_sections(self, sample_mixed_sections):
        schema = build_dynamic_schema(sample_mixed_sections)
        fields = schema.model_fields
        assert "descricao" in fields
        assert "riscos" in fields
        assert "checklist" not in fields

    def test_fields_default_to_empty_string(self, sample_dynamic_sections):
        schema = build_dynamic_schema(sample_dynamic_sections)
        instance = schema()
        assert instance.descricao == ""
        assert instance.riscos_e_impactos == ""

    def test_custom_schema_name(self, sample_dynamic_sections):
        schema = build_dynamic_schema(sample_dynamic_sections, "PrFields")
        assert schema.__name__ == "PrFields"

    def test_include_title(self, sample_dynamic_sections):
        schema = build_dynamic_schema(sample_dynamic_sections, include_title=True)
        fields = schema.model_fields
        assert "title" in fields
        assert "descricao" in fields

    def test_title_is_required(self, sample_dynamic_sections):
        schema = build_dynamic_schema(sample_dynamic_sections, include_title=True)
        with pytest.raises(Exception):
            # title is required (no default), should fail without it
            schema()

    def test_title_not_included_by_default(self, sample_dynamic_sections):
        schema = build_dynamic_schema(sample_dynamic_sections)
        fields = schema.model_fields
        assert "title" not in fields

    def test_empty_sections_creates_empty_model(self):
        schema = build_dynamic_schema([])
        instance = schema()
        assert instance.model_dump() == {}

    def test_model_can_serialize(self, sample_dynamic_sections):
        schema = build_dynamic_schema(sample_dynamic_sections)
        instance = schema(descricao="Test content", riscos_e_impactos="Some risk")
        data = instance.model_dump()
        assert data["descricao"] == "Test content"
        assert data["riscos_e_impactos"] == "Some risk"


# ---- build_dynamic_prompt tests ----

class TestBuildDynamicPrompt:
    def test_includes_language_hint(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "pt-br", "summaries", "changes"
        )
        assert "pt-br" in prompt

    def test_includes_anti_hallucination(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "pt-br", "summaries", "changes"
        )
        assert "Anti-hallucination" in prompt
        assert "Do NOT invent" in prompt

    def test_includes_all_dynamic_keys(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "pt-br", "summaries", "changes"
        )
        assert "descricao" in prompt
        assert "riscos_e_impactos" in prompt

    def test_excludes_static_sections(self, sample_mixed_sections):
        prompt = build_dynamic_prompt(
            sample_mixed_sections, "pt-br", "summaries", "changes"
        )
        assert "checklist" not in prompt.lower().split("commit summaries")[0]

    def test_includes_commit_summaries(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "en", "my commit data", "changes"
        )
        assert "my commit data" in prompt

    def test_includes_changes_by_type(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "en", "summaries", "my changes data"
        )
        assert "my changes data" in prompt

    def test_includes_json_example(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "en", "summaries", "changes"
        )
        assert '"descricao": "conteudo gerado"' in prompt
        assert '"riscos_e_impactos": "conteudo gerado"' in prompt

    def test_pr_includes_title_field(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "en", "summaries", "changes",
            template_type="pr",
            title_instruction="Titulo do PR",
        )
        assert '"title"' in prompt
        assert "Titulo do PR" in prompt

    def test_release_no_title_field(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "en", "summaries", "changes",
            template_type="release",
        )
        # title should not appear as a field in release prompts
        assert '"title": "conteudo gerado"' not in prompt

    def test_release_includes_domain_context(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "en", "summaries", "changes",
            template_type="release",
            domain_context="some domain info",
        )
        assert "some domain info" in prompt

    def test_release_includes_version(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "en", "summaries", "changes",
            template_type="release",
            version="v1.2.0",
        )
        assert "v1.2.0" in prompt

    def test_includes_alerts_when_provided(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "en", "summaries", "changes",
            alerts="- commit sem padrao",
        )
        assert "commit sem padrao" in prompt

    def test_no_alerts_section_when_empty(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "en", "summaries", "changes",
            alerts="",
        )
        assert "Commits fora do padrao" not in prompt

    def test_changes_context_only_rule(self, sample_dynamic_sections):
        prompt = build_dynamic_prompt(
            sample_dynamic_sections, "en", "summaries", "changes"
        )
        assert "CONTEXT ONLY" in prompt

    def test_excludes_changes_key_from_fields(self):
        sections = [
            TemplateSection(heading="Descricao", key="descricao", body="Desc.", is_static=False),
            TemplateSection(heading="Alterações", key="alteracoes", body="Changes.", is_static=False),
        ]
        prompt = build_dynamic_prompt(
            sections, "pt-br", "summaries", "changes", changes_key="alteracoes"
        )
        # alteracoes should not appear as a field to generate
        assert '"alteracoes": "conteudo gerado"' not in prompt
        assert '"descricao": "conteudo gerado"' in prompt
