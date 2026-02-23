"""Integration tests for key workflows.

These tests verify that multiple components work together correctly.
LLM calls are mocked, but the rest of the pipeline runs end-to-end.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import asdict

from pullnotes.config import load_config, validate_config
from pullnotes.domain.models import Commit
from pullnotes.domain.schemas import CommitGroupSummary, DiffAnchors
from pullnotes.domain.services.aggregation import (
    classify_commit,
    compute_importance,
    group_commits_by_type,
    build_convention_report,
    summarize_all_groups,
)
from pullnotes.domain.services.composition import (
    render_changes_by_type_from_summaries,
    render_from_parsed_template,
    build_fields_from_template,
    _ensure_changes_section,
)
from pullnotes.domain.services.data_collection import (
    parse_git_log,
    extract_diff_anchors,
)
from pullnotes.domain.services.template_parser import parse_template
from pullnotes.domain.services.export import (
    create_output_structure,
    export_commits,
    export_convention_report,
    export_pr,
    export_release,
)
from pullnotes.domain.services.dynamic_fields import (
    build_dynamic_schema,
    build_dynamic_prompt,
)
from pullnotes.adapters.domain_definition import (
    build_repository_index,
    extract_anchors,
    build_context_snippets,
)
from pullnotes.adapters.domain_profile import _anchors_to_pydantic

from helpers import make_commit


# ---------------------------------------------------------------------------
# Integration: Config load + validate
# ---------------------------------------------------------------------------

class TestConfigIntegration:
    def test_load_and_validate_default_config(self):
        """Load the actual default config and validate it."""
        config_path = Path(__file__).parent.parent / "config.default.json"
        config = load_config(str(config_path))
        validate_config(config, generate="both")

    def test_load_and_validate_for_pr_only(self):
        config_path = Path(__file__).parent.parent / "config.default.json"
        config = load_config(str(config_path))
        validate_config(config, generate="pr")


# ---------------------------------------------------------------------------
# Integration: Git log parsing → classification → scoring → grouping
# ---------------------------------------------------------------------------

class TestCommitPipelineIntegration:
    @pytest.fixture
    def git_log_output(self):
        return (
            "__COMMIT__\n"
            "aaa1111\x1fJohn\x1fjohn@test.com\x1f2024-06-01\x1ffeat: add user registration\n"
            "50\t10\tsrc/auth.py\n"
            "20\t5\tsrc/models.py\n"
            "__COMMIT__\n"
            "bbb2222\x1fJane\x1fjane@test.com\x1f2024-06-02\x1ffix: correct validation bug\n"
            "5\t3\tsrc/validators.py\n"
            "__COMMIT__\n"
            "ccc3333\x1fBob\x1fbob@test.com\x1f2024-06-03\x1fdocs: update API docs\n"
            "30\t10\tdocs/api.md\n"
            "__COMMIT__\n"
            "ddd4444\x1fAlice\x1falice@test.com\x1f2024-06-04\x1fupdated something\n"
            "3\t1\tmisc.txt\n"
        )

    def test_full_commit_pipeline(self, git_log_output, sample_config):
        # 1. Parse
        commits = parse_git_log(git_log_output)
        assert len(commits) == 4

        # 2. Classify
        for c in commits:
            c.change_type, c.is_conventional = classify_commit(c.subject, sample_config["commit_types"])
        assert commits[0].change_type == "feat"
        assert commits[1].change_type == "fix"
        assert commits[2].change_type == "docs"
        assert commits[3].change_type == "other"
        assert commits[3].is_conventional is False

        # 3. Score
        for c in commits:
            c.importance_score, c.importance_band = compute_importance(c, sample_config)
        assert commits[0].importance_score > commits[3].importance_score

        # 4. Group
        groups = group_commits_by_type(commits, sample_config)
        group_dict = {t: cs for t, cs in groups}
        assert "feat" in group_dict
        assert "fix" in group_dict
        assert "docs" in group_dict
        assert "other" in group_dict

        # 5. Convention report
        report = build_convention_report(commits)
        assert "Total commits: 4" in report
        assert "Others: 1" in report


# ---------------------------------------------------------------------------
# Integration: Template parsing → field generation → rendering
# ---------------------------------------------------------------------------

class TestTemplateRenderIntegration:
    def test_pr_template_full_pipeline(self):
        """Parse actual PR template, create fields, render."""
        template_path = Path(__file__).parent.parent / "src" / "pullnotes" / "templates" / "pr.md"
        template_text = template_path.read_text(encoding="utf-8")

        # Parse
        parsed = parse_template(template_text)
        assert parsed.title_instruction != ""
        assert len(parsed.sections) > 0

        # Create fields manually
        fields = {}
        for s in parsed.dynamic_sections:
            fields[s.key] = f"Content for {s.heading}"

        # Render
        result = render_from_parsed_template(parsed, fields, title="Test PR Title")
        assert "# Test PR Title" in result
        for s in parsed.dynamic_sections:
            assert f"## {s.heading}" in result

    def test_release_template_full_pipeline(self):
        """Parse actual release template, create fields, render."""
        template_path = Path(__file__).parent.parent / "src" / "pullnotes" / "templates" / "release.md"
        template_text = template_path.read_text(encoding="utf-8")

        parsed = parse_template(template_text)
        assert len(parsed.sections) > 0

        fields = {}
        for s in parsed.dynamic_sections:
            fields[s.key] = f"Content for {s.heading}"

        result = render_from_parsed_template(
            parsed, fields,
            title="Notas de Versao — v1.0.0",
            subtitle="**Data de lancamento**: 2024-06-15",
        )
        assert "v1.0.0" in result
        assert "Data de lancamento" in result


# ---------------------------------------------------------------------------
# Integration: Dynamic schema + prompt generation
# ---------------------------------------------------------------------------

class TestDynamicFieldsIntegration:
    def test_schema_from_real_template(self):
        """Build dynamic schema from actual PR template."""
        template_path = Path(__file__).parent.parent / "src" / "pullnotes" / "templates" / "pr.md"
        template_text = template_path.read_text(encoding="utf-8")
        parsed = parse_template(template_text)

        schema = build_dynamic_schema(parsed.dynamic_sections, "PrFields", include_title=True)
        assert "title" in schema.model_fields
        # Dynamic sections should be fields
        for s in parsed.dynamic_sections:
            assert s.key in schema.model_fields

    def test_prompt_from_real_template(self):
        """Build prompt from actual PR template."""
        template_path = Path(__file__).parent.parent / "src" / "pullnotes" / "templates" / "pr.md"
        template_text = template_path.read_text(encoding="utf-8")
        parsed = parse_template(template_text)

        prompt = build_dynamic_prompt(
            parsed.sections, "pt-BR",
            "- Added login feature\n- Fixed auth bug",
            "### Funcionalidades\n- Login\n### Ajustes\n- Auth bug fix",
            template_type="pr",
            title_instruction=parsed.title_instruction,
        )
        assert "pt-BR" in prompt
        assert len(prompt) > 100


# ---------------------------------------------------------------------------
# Integration: Export pipeline
# ---------------------------------------------------------------------------

class TestExportIntegration:
    def test_full_export_pipeline(self, tmp_path, sample_commits, sample_config):
        """Create structure, export commits, convention report, PR, and release."""
        paths = create_output_structure(tmp_path, "test-repo")

        # Export commits
        commits_path = export_commits(sample_commits, paths["utils"])
        assert commits_path.exists()
        data = json.loads(commits_path.read_text(encoding="utf-8"))
        assert len(data) == 5

        # Export convention report
        report = build_convention_report(sample_commits)
        report_path = export_convention_report(report, paths["utils"])
        assert report_path.exists()

        # Export PR
        pr_path = export_pr("# PR Content", paths["prs"], "Test PR")
        assert pr_path.exists()

        # Export release
        release_path = export_release("# Release Notes", paths["releases"], "v1.0.0")
        assert release_path.exists()


# ---------------------------------------------------------------------------
# Integration: Diff anchors extraction pipeline
# ---------------------------------------------------------------------------

class TestDiffAnchorsIntegration:
    def test_complex_diff_extraction(self):
        """Test extraction from a realistic multi-file diff."""
        diff = (
            "diff --git a/src/auth/handler.py b/src/auth/handler.py\n"
            "--- a/src/auth/handler.py\n"
            "+++ b/src/auth/handler.py\n"
            "@@ -1,5 +1,10 @@\n"
            "+class AuthenticationService:\n"
            "+    def login(self, username, password):\n"
            "+        POST /api/v1/auth/login\n"
            "+        return token\n"
            "-class OldHandler:\n"
            "-    pass\n"
            "diff --git a/src/events.py b/src/events.py\n"
            "--- a/src/events.py\n"
            "+++ b/src/events.py\n"
            "@@ -1 +1,3 @@\n"
            "+class UserLoggedInEvent:\n"
            "+    pass\n"
            "diff --git a/.env b/.env\n"
            "--- a/.env\n"
            "+++ b/.env\n"
            "@@ -1 +1 @@\n"
            "+SECRET=new_value\n"
        )
        anchors = extract_diff_anchors(diff)

        # Files
        assert "src/auth/handler.py" in anchors.files_changed
        assert "src/events.py" in anchors.files_changed
        assert ".env" not in anchors.files_changed  # Sensitive

        # Artifacts
        artifact_names = [a.name for a in anchors.artifacts]
        assert "AuthenticationService" in artifact_names
        assert "UserLoggedInEvent" in artifact_names

        # Keywords should not contain sensitive data
        kw_texts = [k.text for k in anchors.keywords]
        assert "secret" not in kw_texts


# ---------------------------------------------------------------------------
# Integration: Repository indexing → anchor extraction
# ---------------------------------------------------------------------------

class TestRepositoryIndexIntegration:
    def test_index_and_extract(self, tmp_path):
        """Build index from temp repo and extract anchors."""
        (tmp_path / "README.md").write_text(
            "# My Project\nAuthentication and authorization module for user management.",
            encoding="utf-8",
        )
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "app.py").write_text(
            "class UserService:\n    POST /api/users\n    def create(self): pass",
            encoding="utf-8",
        )
        (tmp_path / "src" / "events.py").write_text(
            "class UserCreatedEvent:\n    pass",
            encoding="utf-8",
        )

        index = build_repository_index(tmp_path)
        assert len(index) >= 2

        anchors = extract_anchors(index)
        assert len(anchors["keywords"]) > 0

        snippets = build_context_snippets(index)
        assert "README.md" in snippets

    def test_anchors_to_pydantic(self, tmp_path):
        """Convert raw anchors to pydantic model."""
        (tmp_path / "file.py").write_text(
            "class PaymentService:\n    POST /api/payments",
            encoding="utf-8",
        )
        index = build_repository_index(tmp_path)
        raw_anchors = extract_anchors(index)
        pydantic_anchors = _anchors_to_pydantic(raw_anchors)
        assert len(pydantic_anchors.keywords) > 0


# ---------------------------------------------------------------------------
# Integration: Summarize with mocked LLM
# ---------------------------------------------------------------------------

class TestSummarizeIntegration:
    def test_summarize_all_groups_with_mock(self, sample_config):
        """Test parallel summarization with mocked LLM client."""
        commits = [
            make_commit(sha="a1", subject="feat: add login", change_type="feat"),
            make_commit(sha="a2", subject="fix: password bug", change_type="fix"),
        ]
        for c in commits:
            c.change_type, c.is_conventional = classify_commit(c.subject, sample_config["commit_types"])
            c.importance_score, c.importance_band = compute_importance(c, sample_config)

        grouped = group_commits_by_type(commits, sample_config)

        mock_client = MagicMock()
        mock_client.model = "test"
        mock_client.invoke_structured.return_value = CommitGroupSummary(
            summary_points=["- Added new login feature", "- Improved authentication flow"]
        )

        summaries = summarize_all_groups(grouped, sample_config, mock_client, "pr")
        assert "feat" in summaries
        assert "Added new login" in summaries["feat"]

    def test_no_llm_fallback(self, sample_config):
        """When --no-llm is used, commit subjects are used directly."""
        commits = [make_commit(sha="a1", subject="feat: add login", change_type="feat")]
        for c in commits:
            c.change_type, _ = classify_commit(c.subject, sample_config["commit_types"])
            c.importance_score, c.importance_band = compute_importance(c, sample_config)

        grouped = group_commits_by_type(commits, sample_config)

        # Simulate --no-llm behavior
        summaries = {}
        for change_type, group in grouped:
            if group:
                bullets = [f"- {commit.subject}" for commit in group]
                summaries[change_type] = "\n".join(bullets)

        changes_md = render_changes_by_type_from_summaries(grouped, summaries, sample_config)
        assert "feat: add login" in changes_md


# ---------------------------------------------------------------------------
# Integration: build_fields_from_template with mocked LLM
# ---------------------------------------------------------------------------

class TestBuildFieldsIntegration:
    def test_build_fields_pr(self, sample_config):
        """Test field generation for PR with mocked LLM."""
        template_path = Path(__file__).parent.parent / "src" / "pullnotes" / "templates" / "pr.md"
        template_text = template_path.read_text(encoding="utf-8")
        parsed = parse_template(template_text)

        mock_client = MagicMock()
        mock_client.model = "test"

        # The schema is dynamic, so we need to return a mock that has model_dump
        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "title": "Test PR Title",
            "descricao": "Test description",
            "riscos_e_impactos": "No risks",
            "testes": "Unit tests added",
            "observacoes": "",
        }
        mock_result.model_dump_json.return_value = "{}"
        mock_client.invoke_structured.return_value = mock_result

        summaries = {"feat": "- Added login"}
        changes_md = "### Funcionalidades\n- Added login"

        fields = build_fields_from_template(
            parsed, summaries, changes_md, sample_config, mock_client,
            template_type="pr", alerts="",
        )
        assert "title" in fields or "descricao" in fields
