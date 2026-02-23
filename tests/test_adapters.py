"""Tests for adapter modules (filesystem, subprocess, prompt_debug, domain_definition)."""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from pullnotes.adapters.filesystem import (
    ensure_dir,
    resolve_repo_path,
    resolve_cli_path,
    resolve_cli_or_absolute,
    get_repository_name,
    _sanitize_filename,
)
from pullnotes.adapters.prompt_debug import (
    set_prompt_output_dir,
    save_prompt,
    _output_dir,
)
from pullnotes.adapters.domain_definition import (
    _normalize_token,
    is_text_file,
    top_keywords,
    safe_read,
    build_repository_index,
    extract_anchors,
    build_context_snippets,
    IndexedFile,
    IGNORE_DIRS,
    TEXT_EXTS,
    KW_STOPWORDS,
)


# ===========================================================================
# Filesystem adapter
# ===========================================================================

class TestEnsureDir:
    def test_creates_directory(self, tmp_path):
        new_dir = tmp_path / "new" / "nested"
        ensure_dir(new_dir)
        assert new_dir.exists()

    def test_idempotent(self, tmp_path):
        ensure_dir(tmp_path)
        assert tmp_path.exists()


class TestResolveRepoPath:
    def test_relative_path(self, tmp_path):
        result = resolve_repo_path(tmp_path, "src/main.py")
        assert result == tmp_path / "src" / "main.py"

    def test_absolute_path_unchanged(self, tmp_path):
        abs_path = str(tmp_path / "file.py")
        result = resolve_repo_path(Path("/repo"), abs_path)
        assert result == Path(abs_path)


class TestSanitizeFilenameFilesystem:
    def test_removes_unsafe(self):
        assert _sanitize_filename('repo<>:name') == "repo___name"

    def test_strips_dots_and_spaces(self):
        assert _sanitize_filename("..repo..") == "repo"

    def test_empty_returns_unknown(self):
        assert _sanitize_filename("") == "unknown_repo"

    def test_preserves_valid_names(self):
        assert _sanitize_filename("my-repo_123") == "my-repo_123"


class TestGetRepositoryName:
    @patch("pullnotes.adapters.filesystem.subprocess.run")
    def test_from_https_remote(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/user/my-repo.git\n"
        )
        name = get_repository_name(tmp_path)
        assert name == "my-repo"

    @patch("pullnotes.adapters.filesystem.subprocess.run")
    def test_from_ssh_remote(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="git@github.com:user/my-repo.git\n"
        )
        name = get_repository_name(tmp_path)
        assert name == "my-repo"

    @patch("pullnotes.adapters.filesystem.subprocess.run")
    def test_fallback_to_dirname(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        name = get_repository_name(tmp_path)
        assert name == _sanitize_filename(tmp_path.name)

    @patch("pullnotes.adapters.filesystem.subprocess.run")
    def test_removes_git_suffix(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="https://github.com/user/repo-name.git\n"
        )
        name = get_repository_name(tmp_path)
        assert not name.endswith(".git")


# ===========================================================================
# Prompt debug adapter
# ===========================================================================

class TestPromptDebug:
    def test_save_without_dir_returns_none(self):
        import pullnotes.adapters.prompt_debug as pd
        pd._output_dir = None
        result = save_prompt("test prompt", "test")
        assert result is None

    def test_save_creates_file(self, tmp_path):
        set_prompt_output_dir(tmp_path)
        path = save_prompt("my prompt", "test_name")
        assert path is not None
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert "my prompt" in content

    def test_save_with_response(self, tmp_path):
        set_prompt_output_dir(tmp_path)
        path = save_prompt("prompt", "test", response="LLM response")
        content = path.read_text(encoding="utf-8")
        assert "RESPONSE" in content
        assert "LLM response" in content

    def test_counter_increments(self, tmp_path):
        set_prompt_output_dir(tmp_path)
        p1 = save_prompt("a", "first")
        p2 = save_prompt("b", "second")
        assert "001" in p1.name
        assert "002" in p2.name


# ===========================================================================
# Domain definition adapter
# ===========================================================================

class TestNormalizeToken:
    def test_lowercase(self):
        assert _normalize_token("Hello") == "hello"

    def test_removes_accents(self):
        assert _normalize_token("Alteração") == "alteracao"

    def test_cedilla(self):
        assert _normalize_token("Correções") == "correcoes"


class TestIsTextFile:
    def test_python_file(self):
        assert is_text_file(Path("src/main.py")) is True

    def test_typescript_file(self):
        assert is_text_file(Path("src/app.ts")) is True

    def test_json_file(self):
        assert is_text_file(Path("config.json")) is True

    def test_readme(self):
        assert is_text_file(Path("README.md")) is True

    def test_image_file(self):
        assert is_text_file(Path("photo.png")) is False

    def test_binary_file(self):
        assert is_text_file(Path("app.exe")) is False


class TestTopKeywords:
    def test_extracts_keywords(self):
        text = "authentication password validation authentication login password"
        kws = top_keywords(text, top_n=3)
        assert "authentication" in kws
        assert "password" in kws

    def test_excludes_stopwords(self):
        text = "the and for with this that from into"
        kws = top_keywords(text, top_n=10)
        assert len(kws) == 0

    def test_excludes_portuguese_stopwords(self):
        text = "para com sem uma dos das que"
        kws = top_keywords(text, top_n=10)
        assert len(kws) == 0

    def test_respects_top_n(self):
        text = "alpha beta gamma delta epsilon " * 5
        kws = top_keywords(text, top_n=2)
        assert len(kws) == 2

    def test_frequency_order(self):
        text = "rare common common common rare"
        kws = top_keywords(text, top_n=5)
        assert kws[0] == "common"

    def test_short_words_excluded(self):
        text = "ab cd ef"
        kws = top_keywords(text, top_n=10)
        assert len(kws) == 0


class TestSafeRead:
    def test_reads_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        assert safe_read(f) == "hello world"

    def test_truncates_large_file(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 100000, encoding="utf-8")
        result = safe_read(f, max_bytes=1000)
        assert len(result) == 1000

    def test_handles_missing_file(self):
        result = safe_read(Path("/nonexistent/file.txt"))
        assert "ERROR READING" in result


class TestBuildRepositoryIndex:
    def test_indexes_text_files(self, tmp_path):
        (tmp_path / "file.py").write_text("print('hello')", encoding="utf-8")
        (tmp_path / "file.txt").write_text("some text", encoding="utf-8")
        index = build_repository_index(tmp_path)
        paths = [f.relative_path for f in index]
        assert "file.py" in paths
        assert "file.txt" in paths

    def test_ignores_hidden_dirs(self, tmp_path):
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("data", encoding="utf-8")
        (tmp_path / "file.py").write_text("code", encoding="utf-8")
        index = build_repository_index(tmp_path)
        paths = [f.relative_path for f in index]
        assert all(".git" not in p for p in paths)

    def test_respects_byte_budget(self, tmp_path):
        for i in range(100):
            (tmp_path / f"file{i}.py").write_text("x" * 10000, encoding="utf-8")
        index = build_repository_index(tmp_path, max_total_bytes=50000)
        assert len(index) < 100

    def test_empty_directory(self, tmp_path):
        index = build_repository_index(tmp_path)
        assert len(index) == 0


class TestExtractAnchors:
    def test_extracts_keywords(self):
        index = [IndexedFile("README.md", "authentication module for user login and password management")]
        result = extract_anchors(index)
        assert len(result["keywords"]) > 0

    def test_extracts_api_artifacts(self):
        index = [IndexedFile("routes.py", "POST /api/users\nGET /api/users/{id}")]
        result = extract_anchors(index)
        assert any(kind == "api_endpoint" for kind, _ in result["artifacts"])

    def test_extracts_events(self):
        index = [IndexedFile("events.py", "class UserCreatedEvent:\n    pass")]
        result = extract_anchors(index)
        assert any(name == "UserCreatedEvent" for _, name in result["artifacts"])

    def test_extracts_services(self):
        index = [IndexedFile("svc.py", "class PaymentService:\n    pass")]
        result = extract_anchors(index)
        assert any(name == "PaymentService" for _, name in result["artifacts"])

    def test_prioritizes_readme(self):
        index = [
            IndexedFile("src/util.py", "authentication" * 10),
            IndexedFile("README.md", "unique_keyword_only_in_readme " * 5),
        ]
        result = extract_anchors(index)
        kws = [kw for kw, _ in result["keywords"]]
        assert "unique_keyword_only_in_readme" in kws


class TestBuildContextSnippets:
    def test_produces_snippets(self):
        index = [IndexedFile("file.py", "print('hello')")]
        result = build_context_snippets(index)
        assert "file.py" in result
        assert "print('hello')" in result

    def test_truncates_per_file(self):
        content = "x" * 5000
        index = [IndexedFile("big.py", content)]
        result = build_context_snippets(index)
        assert len(result) < len(content)

    def test_respects_budget(self):
        index = [IndexedFile(f"file{i}.py", "x" * 3000) for i in range(100)]
        result = build_context_snippets(index, budget=10000)
        assert len(result.encode("utf-8")) <= 10000 + 500  # small tolerance for headers
