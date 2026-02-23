"""Tests for domain models."""

import pytest

from pullnotes.domain.models import Commit, is_sensitive_file, COMMIT_MARKER, GIT_FORMAT


class TestCommit:
    def test_short_sha(self, sample_commit):
        assert sample_commit.short_sha == "abc1234"
        assert len(sample_commit.short_sha) == 7

    def test_default_values(self):
        c = Commit(sha="abc", author_name="A", author_email="a@b.c", date="2024-01-01", subject="test")
        assert c.body == ""
        assert c.files == []
        assert c.additions == 0
        assert c.deletions == 0
        assert c.diff == ""
        assert c.diff_anchors is None
        assert c.change_type == ""
        assert c.is_conventional is True
        assert c.importance_score == 0.0
        assert c.importance_band == "low"
        assert c.summary == ""

    def test_commit_fields(self, sample_commit):
        assert sample_commit.sha == "abc1234567890"
        assert sample_commit.author_name == "Test Author"
        assert sample_commit.author_email == "test@example.com"
        assert sample_commit.date == "2024-06-15T10:00:00-03:00"
        assert sample_commit.subject == "feat: add new feature"


class TestCommitMarker:
    def test_marker_value(self):
        assert COMMIT_MARKER == "__COMMIT__"

    def test_git_format_contains_marker(self):
        assert "__COMMIT__" in GIT_FORMAT


class TestIsSensitiveFile:
    @pytest.mark.parametrize("path", [
        ".env",
        ".env.local",
        ".env.production",
        "deploy/.env",
        "config/.env.staging",
    ])
    def test_sensitive_detected(self, path):
        assert is_sensitive_file(path) is True

    @pytest.mark.parametrize("path", [
        "src/main.py",
        "README.md",
        "environment.py",
        ".envrc",
        "src/env.py",
        ".gitignore",
        "config.json",
    ])
    def test_safe_not_flagged(self, path):
        assert is_sensitive_file(path) is False

    def test_backslash_paths(self):
        assert is_sensitive_file("config\\.env") is True
        assert is_sensitive_file("src\\main.py") is False
