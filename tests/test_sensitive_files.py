"""Tests for sensitive file filtering."""

import pytest

from pullnotes.domain.models import is_sensitive_file
from pullnotes.domain.services.data_collection import (
    parse_git_log,
    extract_diff_anchors,
    _strip_sensitive_hunks,
)


class TestIsSensitiveFile:
    """Tests for is_sensitive_file()."""

    @pytest.mark.parametrize("path", [
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "config/.env",
        "deploy/.env.staging",
        "path/to/.env.local",
    ])
    def test_sensitive_paths_detected(self, path: str):
        assert is_sensitive_file(path) is True

    @pytest.mark.parametrize("path", [
        "src/main.py",
        "environment.py",
        ".env_utils.py",
        "README.md",
        "config.json",
        "src/env.py",
        ".gitignore",
    ])
    def test_safe_paths_not_flagged(self, path: str):
        assert is_sensitive_file(path) is False


class TestStripSensitiveHunks:
    """Tests for _strip_sensitive_hunks()."""

    def test_removes_env_hunk(self):
        diff = (
            "diff --git a/.env b/.env\n"
            "--- a/.env\n"
            "+++ b/.env\n"
            "@@ -1,2 +1,2 @@\n"
            "-SECRET_KEY=old\n"
            "+SECRET_KEY=new\n"
            "diff --git a/src/main.py b/src/main.py\n"
            "--- a/src/main.py\n"
            "+++ b/src/main.py\n"
            "@@ -1,1 +1,2 @@\n"
            "+print('hello')\n"
        )
        result = _strip_sensitive_hunks(diff)
        assert "SECRET_KEY" not in result
        assert "src/main.py" in result
        assert "print('hello')" in result

    def test_preserves_all_when_no_sensitive(self):
        diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "+++ b/src/app.py\n"
            "+new_line\n"
        )
        assert _strip_sensitive_hunks(diff) == diff

    def test_removes_env_local_hunk(self):
        diff = (
            "diff --git a/.env.local b/.env.local\n"
            "+++ b/.env.local\n"
            "+DB_PASSWORD=secret\n"
        )
        result = _strip_sensitive_hunks(diff)
        assert result.strip() == ""


class TestParseGitLogFiltering:
    """Tests that parse_git_log excludes sensitive files."""

    def test_env_file_excluded_from_files(self):
        log = (
            "__COMMIT__\n"
            "abc1234\x1fAuthor\x1fauthor@test.com\x1f2024-01-01\x1ffeat: add config\n"
            "3\t1\tsrc/config.py\n"
            "5\t0\t.env\n"
            "2\t1\t.env.local\n"
        )
        commits = parse_git_log(log)
        assert len(commits) == 1
        commit = commits[0]
        assert "src/config.py" in commit.files
        assert ".env" not in commit.files
        assert ".env.local" not in commit.files
        # additions/deletions should only count non-sensitive files
        assert commit.additions == 3
        assert commit.deletions == 1


class TestExtractDiffAnchorsFiltering:
    """Tests that extract_diff_anchors excludes sensitive files."""

    def test_env_excluded_from_files_changed(self):
        diff = (
            "diff --git a/.env b/.env\n"
            "--- a/.env\n"
            "+++ b/.env\n"
            "@@ -1 +1 @@\n"
            "-OLD_SECRET=abc\n"
            "+NEW_SECRET=xyz\n"
            "diff --git a/src/app.py b/src/app.py\n"
            "--- a/src/app.py\n"
            "+++ b/src/app.py\n"
            "@@ -1 +1 @@\n"
            "+import os\n"
        )
        anchors = extract_diff_anchors(diff)
        assert "src/app.py" in anchors.files_changed
        assert ".env" not in anchors.files_changed
        # Keywords should not contain secret-related tokens from .env
        kw_texts = [k.text for k in anchors.keywords]
        assert "old_secret" not in kw_texts
        assert "new_secret" not in kw_texts
