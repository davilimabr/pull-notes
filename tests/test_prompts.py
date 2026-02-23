"""Tests for prompts module."""

import pytest

from pullnotes.prompts import (
    _strip_description,
    render_prompt_template,
    load_prompt,
)


# ---------------------------------------------------------------------------
# _strip_description
# ---------------------------------------------------------------------------

class TestStripDescription:
    def test_removes_comment_lines(self):
        raw = "# This is a comment\n# Another comment\nActual prompt text"
        result = _strip_description(raw)
        assert result == "Actual prompt text"

    def test_preserves_non_comment(self):
        raw = "No comments here\nJust text"
        result = _strip_description(raw)
        assert result == "No comments here\nJust text"

    def test_empty_string(self):
        assert _strip_description("") == ""

    def test_all_comments(self):
        raw = "# Comment 1\n# Comment 2"
        result = _strip_description(raw)
        assert result == ""

    def test_indented_comments(self):
        raw = "  # Indented comment\nContent"
        result = _strip_description(raw)
        assert result == "Content"


# ---------------------------------------------------------------------------
# render_prompt_template
# ---------------------------------------------------------------------------

class TestRenderPromptTemplate:
    def test_replaces_placeholders(self):
        template = "Hello {{name}}, welcome to {{place}}."
        result = render_prompt_template(template, {"name": "World", "place": "Earth"})
        assert result == "Hello World, welcome to Earth."

    def test_drops_unused_placeholders(self):
        template = "Hello {{name}}. {{unused}} placeholder."
        result = render_prompt_template(template, {"name": "World"})
        assert result == "Hello World.  placeholder."

    def test_handles_spaces_in_placeholders(self):
        template = "Hello {{ name }}."
        result = render_prompt_template(template, {"name": "World"})
        assert result == "Hello World."

    def test_no_placeholders(self):
        template = "Plain text without placeholders."
        result = render_prompt_template(template, {})
        assert result == "Plain text without placeholders."

    def test_empty_template(self):
        assert render_prompt_template("", {}) == ""

    def test_multiple_same_placeholder(self):
        template = "{{x}} and {{x}}"
        result = render_prompt_template(template, {"x": "hello"})
        assert result == "hello and hello"


# ---------------------------------------------------------------------------
# load_prompt
# ---------------------------------------------------------------------------

class TestLoadPrompt:
    def test_loads_existing_prompt(self):
        result = load_prompt("commit_group_summary_pr", {"language_hint": "pt", "change_type_label": "feat", "commit_blocks": "test"})
        assert len(result) > 0

    def test_raises_on_missing(self):
        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_prompt", {})

    def test_strips_comments(self):
        result = load_prompt("commit_group_summary_pr", {"language_hint": "en", "change_type_label": "fix", "commit_blocks": "data"})
        # Should not start with a comment line
        assert not result.startswith("#")

    def test_replaces_values(self):
        result = load_prompt("commit_group_summary_pr", {"language_hint": "pt-BR", "change_type_label": "Funcionalidades", "commit_blocks": "my blocks"})
        assert "pt-BR" in result
        assert "Funcionalidades" in result
        assert "my blocks" in result
