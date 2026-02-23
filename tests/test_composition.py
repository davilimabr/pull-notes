"""Tests for composition service."""

import pytest
from unittest.mock import MagicMock

from pullnotes.domain.services.composition import (
    build_version_label,
    render_changes_by_type_from_summaries,
    _detect_changes_key,
    _changes_heading_for_language,
    _format_grouped_summaries,
    _ensure_changes_section,
    render_from_parsed_template,
)
from pullnotes.domain.services.template_parser import TemplateSection, ParsedTemplate

from helpers import make_commit


# ---------------------------------------------------------------------------
# _detect_changes_key
# ---------------------------------------------------------------------------

class TestDetectChangesKey:
    def test_finds_alteracoes(self):
        sections = [
            TemplateSection(heading="Desc", key="desc", body="", is_static=False),
            TemplateSection(heading="Alterações", key="alteracoes", body="", is_static=False),
        ]
        assert _detect_changes_key(sections) == "alteracoes"

    def test_finds_changes(self):
        sections = [
            TemplateSection(heading="Changes", key="changes", body="", is_static=False),
        ]
        assert _detect_changes_key(sections) == "changes"

    def test_returns_none_when_absent(self):
        sections = [
            TemplateSection(heading="Desc", key="desc", body="", is_static=False),
        ]
        assert _detect_changes_key(sections) is None


# ---------------------------------------------------------------------------
# _changes_heading_for_language
# ---------------------------------------------------------------------------

class TestChangesHeadingForLanguage:
    def test_portuguese(self):
        assert _changes_heading_for_language("pt-BR") == "Alterações"

    def test_english(self):
        assert _changes_heading_for_language("en") == "Changes"

    def test_unknown_defaults_english(self):
        assert _changes_heading_for_language("fr") == "Changes"

    def test_empty_defaults_english(self):
        assert _changes_heading_for_language("") == "Changes"


# ---------------------------------------------------------------------------
# build_version_label
# ---------------------------------------------------------------------------

class TestBuildVersionLabel:
    def test_override_takes_precedence(self):
        label = build_version_label("v2.0.0", "v1.0..v2.0", {"version_template": "{revision_range}", "date_format": "%Y-%m-%d"})
        assert label == "v2.0.0"

    def test_template_with_range(self):
        label = build_version_label("", "v1.0..v2.0", {"version_template": "{revision_range}", "date_format": "%Y-%m-%d"})
        assert label == "v1.0..v2.0"

    def test_template_with_date(self):
        label = build_version_label("", None, {"version_template": "release-{date}", "date_format": "%Y-%m-%d"})
        assert label.startswith("release-")

    def test_invalid_placeholder_raises(self):
        with pytest.raises(SystemExit, match="Invalid"):
            build_version_label("", None, {"version_template": "{bad_key}", "date_format": "%Y-%m-%d"})

    def test_empty_label_raises(self):
        with pytest.raises(SystemExit, match="empty"):
            build_version_label("", "", {"version_template": "{revision_range}", "date_format": "%Y-%m-%d"})


# ---------------------------------------------------------------------------
# _format_grouped_summaries
# ---------------------------------------------------------------------------

class TestFormatGroupedSummaries:
    def test_formats_known_types(self, sample_config):
        summaries = {"feat": "- Added login", "fix": "- Fixed bug"}
        result = _format_grouped_summaries(summaries, sample_config)
        assert "### Funcionalidades" in result
        assert "- Added login" in result
        assert "### Ajustes" in result

    def test_includes_other(self, sample_config):
        summaries = {"other": "- misc change"}
        result = _format_grouped_summaries(summaries, sample_config)
        assert "### Other" in result

    def test_empty_summaries(self, sample_config):
        result = _format_grouped_summaries({}, sample_config)
        assert result == ""


# ---------------------------------------------------------------------------
# render_changes_by_type_from_summaries
# ---------------------------------------------------------------------------

class TestRenderChangesByType:
    def test_renders_with_summaries(self, sample_config):
        grouped = [
            ("feat", [make_commit(change_type="feat")]),
            ("fix", [make_commit(change_type="fix")]),
        ]
        summaries = {"feat": "- Added login", "fix": "- Fixed bug"}
        result = render_changes_by_type_from_summaries(grouped, summaries, sample_config)
        assert "### Funcionalidades" in result
        assert "- Added login" in result
        assert "### Ajustes" in result

    def test_fallback_to_subjects(self, sample_config):
        grouped = [("feat", [make_commit(subject="feat: add login", change_type="feat")])]
        result = render_changes_by_type_from_summaries(grouped, {}, sample_config)
        assert "feat: add login" in result

    def test_empty_groups(self, sample_config):
        grouped = [("feat", [])]
        result = render_changes_by_type_from_summaries(grouped, {}, sample_config)
        assert result == ""

    def test_other_group_rendered(self, sample_config):
        grouped = [("other", [make_commit(subject="misc", change_type="other")])]
        summaries = {"other": "- misc update"}
        result = render_changes_by_type_from_summaries(grouped, summaries, sample_config)
        assert "### Other" in result


# ---------------------------------------------------------------------------
# _ensure_changes_section
# ---------------------------------------------------------------------------

class TestEnsureChangesSection:
    def test_existing_key_returned(self, simple_parsed_template):
        key = _ensure_changes_section(simple_parsed_template, "pt-BR")
        assert key == "alteracoes"

    def test_creates_section_when_missing(self):
        parsed = ParsedTemplate(
            title_instruction="Title",
            sections=[
                TemplateSection(heading="Desc", key="desc", body="", is_static=False),
            ],
        )
        key = _ensure_changes_section(parsed, "pt-BR")
        assert key == "alteracoes"
        assert len(parsed.sections) == 2

    def test_creates_english_section(self):
        parsed = ParsedTemplate(title_instruction="Title", sections=[])
        key = _ensure_changes_section(parsed, "en")
        assert key == "changes"
