"""Tests for export service."""

import json
import pytest
from pathlib import Path

from pullnotes.domain.services.export import (
    _sanitize_filename,
    create_output_structure,
    export_commits,
    export_convention_report,
    export_release,
    export_pr,
    export_text_document,
    _PydanticEncoder,
)
from pullnotes.domain.models import Commit
from pydantic import BaseModel

from helpers import make_commit


# ---------------------------------------------------------------------------
# _sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    def test_removes_unsafe_chars(self):
        assert _sanitize_filename('file<>:"/\\|?*name') == "file_________name"

    def test_replaces_spaces(self):
        assert _sanitize_filename("my file name") == "my_file_name"

    def test_strips_underscores(self):
        assert _sanitize_filename("_hello_") == "hello"

    def test_truncates_long_names(self):
        long_name = "a" * 200
        assert len(_sanitize_filename(long_name)) == 100

    def test_empty_returns_unnamed(self):
        assert _sanitize_filename("") == "unnamed"

    def test_only_special_chars(self):
        assert _sanitize_filename("***") == "unnamed"


# ---------------------------------------------------------------------------
# _PydanticEncoder
# ---------------------------------------------------------------------------

class TestPydanticEncoder:
    def test_encodes_pydantic_model(self):
        class MyModel(BaseModel):
            name: str = "test"

        result = json.dumps(MyModel(), cls=_PydanticEncoder)
        assert '"name"' in result
        assert '"test"' in result

    def test_raises_on_unknown_type(self):
        class Custom:
            pass

        with pytest.raises(TypeError):
            json.dumps(Custom(), cls=_PydanticEncoder)


# ---------------------------------------------------------------------------
# create_output_structure
# ---------------------------------------------------------------------------

class TestCreateOutputStructure:
    def test_creates_all_dirs(self, tmp_path):
        paths = create_output_structure(tmp_path, "my-repo")
        assert paths["root"].exists()
        assert paths["utils"].exists()
        assert paths["releases"].exists()
        assert paths["prs"].exists()

    def test_structure_names(self, tmp_path):
        paths = create_output_structure(tmp_path, "test-repo")
        assert paths["root"].name == "test-repo"
        assert paths["utils"].name == "utils"

    def test_idempotent(self, tmp_path):
        create_output_structure(tmp_path, "repo")
        paths = create_output_structure(tmp_path, "repo")
        assert paths["root"].exists()


# ---------------------------------------------------------------------------
# export_commits
# ---------------------------------------------------------------------------

class TestExportCommits:
    def test_exports_json(self, tmp_path):
        commits = [make_commit(sha="abc123")]
        path = export_commits(commits, tmp_path)
        assert path.exists()
        assert path.name == "commit.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1
        assert data[0]["sha"] == "abc123"

    def test_empty_commits(self, tmp_path):
        path = export_commits([], tmp_path)
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data == []

    def test_creates_dir_if_missing(self, tmp_path):
        utils_dir = tmp_path / "new_dir"
        path = export_commits([make_commit()], utils_dir)
        assert path.exists()


# ---------------------------------------------------------------------------
# export_convention_report
# ---------------------------------------------------------------------------

class TestExportConventionReport:
    def test_exports_markdown(self, tmp_path):
        path = export_convention_report("# Report\n- test", tmp_path)
        assert path.exists()
        assert path.name == "conventions.md"
        assert "# Report" in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# export_release
# ---------------------------------------------------------------------------

class TestExportRelease:
    def test_exports_with_version(self, tmp_path):
        path = export_release("# Release v1.0", tmp_path, "v1.0.0")
        assert path.exists()
        assert "v1.0.0" in path.name
        assert path.read_text(encoding="utf-8") == "# Release v1.0"

    def test_sanitizes_version(self, tmp_path):
        path = export_release("content", tmp_path, "v1.0/beta<1>")
        assert "<" not in path.name
        assert ">" not in path.name


# ---------------------------------------------------------------------------
# export_pr
# ---------------------------------------------------------------------------

class TestExportPr:
    def test_exports_with_title(self, tmp_path):
        path = export_pr("# PR Content", tmp_path, "Add Login Feature")
        assert path.exists()
        assert "Add_Login_Feature" in path.name

    def test_sanitizes_title(self, tmp_path):
        path = export_pr("content", tmp_path, 'title:with"special')
        assert '"' not in path.name


# ---------------------------------------------------------------------------
# export_text_document
# ---------------------------------------------------------------------------

class TestExportTextDocument:
    def test_exports_generic(self, tmp_path):
        path = export_text_document("hello world", tmp_path, "output.txt")
        assert path.exists()
        assert path.read_text(encoding="utf-8") == "hello world"

    def test_creates_dir(self, tmp_path):
        new_dir = tmp_path / "subdir"
        path = export_text_document("content", new_dir, "file.md")
        assert path.exists()
