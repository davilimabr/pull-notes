"""Tests for aggregation service."""

import pytest
from unittest.mock import MagicMock, patch

from pullnotes.domain.services.aggregation import (
    classify_commit,
    compute_importance,
    group_commits_by_type,
    build_language_hint,
    build_convention_report,
    _compile_config_pattern,
    _format_diff_anchors_for_prompt,
    _build_commit_blocks,
)
from pullnotes.domain.models import Commit
from pullnotes.domain.schemas import DiffAnchors, DiffKeyword, DiffArtifact

from helpers import make_commit


# ---------------------------------------------------------------------------
# _compile_config_pattern
# ---------------------------------------------------------------------------

class TestCompileConfigPattern:
    def test_plain_regex(self):
        pattern = _compile_config_pattern(r"\bfeat\b")
        assert pattern.search("feat: add login")
        assert not pattern.search("feature: add login")

    def test_js_style_with_flags(self):
        pattern = _compile_config_pattern("/^feat/i")
        assert pattern.search("Feat: something")

    def test_js_style_multiline(self):
        pattern = _compile_config_pattern("/^test/m")
        assert pattern.search("line1\ntest: line2")

    def test_js_style_no_flags_defaults_ignorecase(self):
        pattern = _compile_config_pattern("/feat/")
        assert pattern.search("FEAT: something")

    def test_already_compiled_passthrough(self):
        import re
        compiled = re.compile(r"\bfeat\b")
        assert _compile_config_pattern(compiled) is compiled

    def test_invalid_pattern_raises(self):
        with pytest.raises(ValueError, match="Invalid commit type pattern"):
            _compile_config_pattern("[invalid")

    def test_non_string_raises(self):
        with pytest.raises(ValueError, match="must be string or regex"):
            _compile_config_pattern(123)

    def test_backspace_byte_restored(self):
        # JSON can turn \b into backspace byte 0x08
        pattern = _compile_config_pattern("\x08feat\x08")
        assert pattern.search("feat: test")


# ---------------------------------------------------------------------------
# classify_commit
# ---------------------------------------------------------------------------

class TestClassifyCommit:
    def test_feat_classified(self, sample_config):
        type_name, is_conv = classify_commit("feat: add login", sample_config["commit_types"])
        assert type_name == "feat"
        assert is_conv is True

    def test_fix_classified(self, sample_config):
        type_name, is_conv = classify_commit("fix: correct bug", sample_config["commit_types"])
        assert type_name == "fix"
        assert is_conv is True

    def test_docs_classified(self, sample_config):
        type_name, _ = classify_commit("docs: update readme", sample_config["commit_types"])
        assert type_name == "docs"

    def test_unrecognized_is_other(self, sample_config):
        type_name, is_conv = classify_commit("updated something", sample_config["commit_types"])
        assert type_name == "other"
        assert is_conv is False

    def test_whitespace_stripped(self, sample_config):
        type_name, _ = classify_commit("  feat: add login  ", sample_config["commit_types"])
        assert type_name == "feat"

    def test_case_insensitive(self, sample_config):
        type_name, _ = classify_commit("FEAT: big change", sample_config["commit_types"])
        assert type_name == "feat"

    def test_chore_classified(self, sample_config):
        type_name, _ = classify_commit("chore: update deps", sample_config["commit_types"])
        assert type_name == "chore"

    def test_patterns_are_cached(self, sample_config):
        classify_commit("feat: first call", sample_config["commit_types"])
        assert "_compiled_patterns" in sample_config["commit_types"]["feat"]
        classify_commit("feat: second call", sample_config["commit_types"])


# ---------------------------------------------------------------------------
# compute_importance
# ---------------------------------------------------------------------------

class TestComputeImportance:
    def test_basic_score(self, sample_config):
        commit = make_commit(additions=10, deletions=5, files=["a.py"])
        score, band = compute_importance(commit, sample_config)
        # (10+5)*0.02 + 1*0.6 = 0.3 + 0.6 = 0.9
        assert abs(score - 0.9) < 0.01
        assert band == "low"

    def test_medium_band(self, sample_config):
        commit = make_commit(additions=50, deletions=50, files=["a.py", "b.py", "c.py", "d.py"])
        score, band = compute_importance(commit, sample_config)
        # (100)*0.02 + 4*0.6 = 2.0 + 2.4 = 4.4
        assert band == "medium"

    def test_high_band(self, sample_config):
        commit = make_commit(additions=100, deletions=100, files=["a.py"] * 5)
        score, band = compute_importance(commit, sample_config)
        # (200)*0.02 + 5*0.6 = 4.0 + 3.0 = 7.0
        assert band == "high"

    def test_critical_with_keyword(self, sample_config):
        commit = make_commit(
            additions=100, deletions=100,
            files=["a.py"] * 5,
            subject="fix: breaking change in auth",
        )
        score, band = compute_importance(commit, sample_config)
        # 7.0 + 3.0 (breaking) = 10.0
        assert band == "critical"

    def test_security_keyword_bonus(self, sample_config):
        commit = make_commit(additions=0, deletions=0, files=[], subject="fix: security vulnerability")
        score, _ = compute_importance(commit, sample_config)
        assert score >= 2.0  # security bonus

    def test_multiple_keywords_stack(self, sample_config):
        commit = make_commit(
            additions=0, deletions=0, files=[],
            subject="fix: breaking security hotfix",
        )
        score, _ = compute_importance(commit, sample_config)
        # breaking=3.0 + security=2.0 + hotfix=2.0 = 7.0
        assert score >= 7.0

    def test_body_keywords_count(self, sample_config):
        commit = make_commit(additions=0, deletions=0, files=[], subject="fix: update", body="this is a breaking change")
        score, _ = compute_importance(commit, sample_config)
        assert score >= 3.0


# ---------------------------------------------------------------------------
# group_commits_by_type
# ---------------------------------------------------------------------------

class TestGroupCommitsByType:
    def test_groups_by_type(self, sample_commits, sample_config):
        groups = group_commits_by_type(sample_commits, sample_config)
        group_dict = {t: cs for t, cs in groups}
        assert len(group_dict["feat"]) == 1
        assert len(group_dict["fix"]) == 1
        assert len(group_dict["docs"]) == 1

    def test_other_group_created(self, sample_config):
        commits = [make_commit(change_type="unknown_type")]
        groups = group_commits_by_type(commits, sample_config)
        group_dict = {t: cs for t, cs in groups}
        assert "other" in group_dict
        assert len(group_dict["other"]) == 1

    def test_empty_commits(self, sample_config):
        groups = group_commits_by_type([], sample_config)
        for _, cs in groups:
            assert cs == []

    def test_sorted_by_importance(self, sample_config):
        c1 = make_commit(sha="aaa", change_type="feat", importance_score=1.0)
        c2 = make_commit(sha="bbb", change_type="feat", importance_score=5.0)
        groups = group_commits_by_type([c1, c2], sample_config)
        feat_group = [cs for t, cs in groups if t == "feat"][0]
        assert feat_group[0].importance_score > feat_group[1].importance_score


# ---------------------------------------------------------------------------
# build_language_hint
# ---------------------------------------------------------------------------

class TestBuildLanguageHint:
    def test_portuguese(self):
        assert "pt-BR" in build_language_hint("pt-BR")

    def test_english(self):
        assert "en" in build_language_hint("en")


# ---------------------------------------------------------------------------
# build_convention_report
# ---------------------------------------------------------------------------

class TestBuildConventionReport:
    def test_report_structure(self, sample_commits):
        report = build_convention_report(sample_commits)
        assert "# Convention Report" in report
        assert "Total commits: 5" in report
        assert "## Good Examples" in report
        assert "## Bad Examples" in report

    def test_empty_commits(self):
        report = build_convention_report([])
        assert "Total commits: 0" in report

    def test_non_conventional_examples(self):
        commits = [
            make_commit(subject="feat: good", is_conventional=True),
            make_commit(subject="bad commit", is_conventional=False),
        ]
        report = build_convention_report(commits)
        assert "feat: good" in report
        assert "bad commit" in report

    def test_all_conventional(self, sample_commits):
        report = build_convention_report(sample_commits)
        assert "Others: 0" in report


# ---------------------------------------------------------------------------
# _format_diff_anchors_for_prompt
# ---------------------------------------------------------------------------

class TestFormatDiffAnchorsForPrompt:
    def test_no_anchors(self):
        commit = make_commit(diff_anchors=None)
        result = _format_diff_anchors_for_prompt(commit)
        assert "unavailable" in result

    def test_with_anchors(self, sample_diff_anchors):
        commit = make_commit(diff_anchors=sample_diff_anchors)
        result = _format_diff_anchors_for_prompt(commit)
        assert "src/auth.py" in result
        assert "authentication" in result
        assert "POST /api/login" in result

    def test_empty_anchors(self):
        commit = make_commit(diff_anchors=DiffAnchors())
        result = _format_diff_anchors_for_prompt(commit)
        assert "no changes detected" in result


# ---------------------------------------------------------------------------
# _build_commit_blocks
# ---------------------------------------------------------------------------

class TestBuildCommitBlocks:
    def test_basic_block(self):
        commit = make_commit(subject="feat: add auth")
        result = _build_commit_blocks([commit], {"max_anchors_keywords": 10, "max_anchors_artifacts": 10})
        assert "feat: add auth" in result
        assert "abc1234" in result

    def test_commit_without_anchors(self):
        commit = make_commit(diff_anchors=None)
        result = _build_commit_blocks([commit], {"max_anchors_keywords": 10, "max_anchors_artifacts": 10})
        assert "unavailable" in result

    def test_multiple_commits(self):
        commits = [make_commit(sha="aaa1111", subject="feat: a"), make_commit(sha="bbb2222", subject="fix: b")]
        result = _build_commit_blocks(commits, {"max_anchors_keywords": 10, "max_anchors_artifacts": 10})
        assert "feat: a" in result
        assert "fix: b" in result
