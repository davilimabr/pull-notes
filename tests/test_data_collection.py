"""Tests for data_collection service."""

import pytest
from unittest.mock import patch, MagicMock

from pullnotes.domain.services.data_collection import (
    _prefix_origin_range,
    _strip_sensitive_hunks,
    parse_git_log,
    extract_diff_anchors,
)
from pullnotes.domain.models import COMMIT_MARKER


# ---------------------------------------------------------------------------
# _prefix_origin_range
# ---------------------------------------------------------------------------

class TestPrefixOriginRange:
    def test_double_dot(self):
        result = _prefix_origin_range("v1.0..v2.0")
        assert result == "origin/v1.0..origin/v2.0"

    def test_triple_dot(self):
        result = _prefix_origin_range("v1.0...v2.0")
        assert result == "origin/v1.0...origin/v2.0"

    def test_single_ref(self):
        result = _prefix_origin_range("main")
        assert result == "origin/main"

    def test_head_unchanged(self):
        result = _prefix_origin_range("HEAD")
        assert result == "HEAD"

    def test_already_origin_prefix(self):
        result = _prefix_origin_range("origin/main..origin/develop")
        assert result == "origin/main..origin/develop"

    def test_mixed_head_and_ref(self):
        result = _prefix_origin_range("HEAD..v2.0")
        assert result == "HEAD..origin/v2.0"

    def test_empty_left(self):
        result = _prefix_origin_range("..v2.0")
        assert result == "..origin/v2.0"


# ---------------------------------------------------------------------------
# _strip_sensitive_hunks
# ---------------------------------------------------------------------------

class TestStripSensitiveHunks:
    def test_removes_env_section(self):
        diff = (
            "diff --git a/.env b/.env\n"
            "+SECRET=value\n"
            "diff --git a/src/app.py b/src/app.py\n"
            "+print('ok')\n"
        )
        result = _strip_sensitive_hunks(diff)
        assert "SECRET" not in result
        assert "print('ok')" in result

    def test_preserves_safe_files(self):
        diff = "diff --git a/src/app.py b/src/app.py\n+code\n"
        assert _strip_sensitive_hunks(diff) == diff

    def test_removes_env_local(self):
        diff = "diff --git a/.env.local b/.env.local\n+DB_PASS=x\n"
        assert _strip_sensitive_hunks(diff).strip() == ""

    def test_empty_diff(self):
        assert _strip_sensitive_hunks("") == ""


# ---------------------------------------------------------------------------
# parse_git_log
# ---------------------------------------------------------------------------

class TestParseGitLog:
    def test_single_commit(self):
        log = (
            f"{COMMIT_MARKER}\n"
            "abc1234\x1fJohn\x1fjohn@test.com\x1f2024-01-01\x1ffeat: add feature\n"
            "10\t2\tsrc/main.py\n"
        )
        commits = parse_git_log(log)
        assert len(commits) == 1
        assert commits[0].sha == "abc1234"
        assert commits[0].author_name == "John"
        assert commits[0].subject == "feat: add feature"
        assert commits[0].additions == 10
        assert commits[0].deletions == 2
        assert "src/main.py" in commits[0].files

    def test_multiple_commits(self):
        log = (
            f"{COMMIT_MARKER}\n"
            "aaa\x1fA\x1fa@t.c\x1f2024-01-01\x1ffeat: one\n"
            "5\t1\tfile1.py\n"
            f"{COMMIT_MARKER}\n"
            "bbb\x1fB\x1fb@t.c\x1f2024-01-02\x1ffix: two\n"
            "3\t2\tfile2.py\n"
        )
        commits = parse_git_log(log)
        assert len(commits) == 2
        assert commits[0].subject == "feat: one"
        assert commits[1].subject == "fix: two"

    def test_sensitive_files_excluded(self):
        log = (
            f"{COMMIT_MARKER}\n"
            "abc\x1fA\x1fa@t.c\x1f2024-01-01\x1ffeat: config\n"
            "5\t0\t.env\n"
            "3\t1\tsrc/app.py\n"
        )
        commits = parse_git_log(log)
        assert ".env" not in commits[0].files
        assert "src/app.py" in commits[0].files
        assert commits[0].additions == 3
        assert commits[0].deletions == 1

    def test_empty_log(self):
        assert parse_git_log("") == []

    def test_incomplete_header(self):
        log = f"{COMMIT_MARKER}\nbad header without separators\n"
        commits = parse_git_log(log)
        assert len(commits) == 0

    def test_non_numeric_stats(self):
        log = (
            f"{COMMIT_MARKER}\n"
            "abc\x1fA\x1fa@t.c\x1f2024-01-01\x1ffeat: binary\n"
            "-\t-\timage.png\n"
        )
        commits = parse_git_log(log)
        assert commits[0].additions == 0
        assert commits[0].deletions == 0
        assert "image.png" in commits[0].files

    def test_blank_lines_skipped(self):
        log = (
            f"{COMMIT_MARKER}\n"
            "abc\x1fA\x1fa@t.c\x1f2024-01-01\x1ffeat: test\n"
            "\n"
            "5\t1\tfile.py\n"
            "\n"
        )
        commits = parse_git_log(log)
        assert len(commits) == 1
        assert commits[0].files == ["file.py"]


# ---------------------------------------------------------------------------
# extract_diff_anchors
# ---------------------------------------------------------------------------

class TestExtractDiffAnchors:
    def test_empty_diff(self):
        anchors = extract_diff_anchors("")
        assert anchors.files_changed == []
        assert anchors.keywords == []
        assert anchors.artifacts == []

    def test_extracts_files(self):
        diff = (
            "diff --git a/src/auth.py b/src/auth.py\n"
            "+new code\n"
            "diff --git a/src/login.py b/src/login.py\n"
            "+more code\n"
        )
        anchors = extract_diff_anchors(diff)
        assert "src/auth.py" in anchors.files_changed
        assert "src/login.py" in anchors.files_changed

    def test_extracts_keywords(self):
        diff = (
            "diff --git a/src/app.py b/src/app.py\n"
            "+authentication module initialized\n"
            "+password validation added\n"
            "-old handler removed\n"
        )
        anchors = extract_diff_anchors(diff)
        kw_texts = [k.text for k in anchors.keywords]
        assert len(kw_texts) > 0

    def test_extracts_api_artifacts(self):
        diff = (
            "diff --git a/routes.py b/routes.py\n"
            "+POST /api/v1/users\n"
            "+GET /api/v1/users/{id}\n"
        )
        anchors = extract_diff_anchors(diff)
        artifact_names = [a.name for a in anchors.artifacts]
        assert any("POST" in n for n in artifact_names)

    def test_extracts_event_artifacts(self):
        diff = (
            "diff --git a/events.py b/events.py\n"
            "+class UserCreatedEvent:\n"
        )
        anchors = extract_diff_anchors(diff)
        artifact_names = [a.name for a in anchors.artifacts]
        assert "UserCreatedEvent" in artifact_names

    def test_extracts_service_artifacts(self):
        diff = (
            "diff --git a/svc.py b/svc.py\n"
            "+class PaymentService:\n"
        )
        anchors = extract_diff_anchors(diff)
        artifact_names = [a.name for a in anchors.artifacts]
        assert "PaymentService" in artifact_names

    def test_sensitive_files_stripped(self):
        diff = (
            "diff --git a/.env b/.env\n"
            "+SECRET_KEY=abc123\n"
            "diff --git a/src/app.py b/src/app.py\n"
            "+print('hello')\n"
        )
        anchors = extract_diff_anchors(diff)
        assert ".env" not in anchors.files_changed
        kw_texts = [k.text for k in anchors.keywords]
        assert "secret_key" not in kw_texts

    def test_limits_files(self):
        lines = []
        for i in range(50):
            lines.append(f"diff --git a/file{i}.py b/file{i}.py\n+code\n")
        diff = "".join(lines)
        anchors = extract_diff_anchors(diff)
        assert len(anchors.files_changed) <= 30

    def test_added_and_removed_keywords(self):
        diff = (
            "diff --git a/app.py b/app.py\n"
            "+new_feature_handler\n"
            "-old_deprecated_function\n"
        )
        anchors = extract_diff_anchors(diff)
        added = [k for k in anchors.keywords if k.change_type == "added"]
        removed = [k for k in anchors.keywords if k.change_type == "removed"]
        assert len(added) > 0 or len(removed) > 0
