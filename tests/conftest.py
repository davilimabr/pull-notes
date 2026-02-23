"""Shared test fixtures and helpers."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from pullnotes.domain.schemas import (
    DiffAnchors,
    DiffKeyword,
    DiffArtifact,
    ProjectProfile,
    ProjectType,
    ProjectKind,
    Domain,
    DomainAnchors,
    DomainDetails,
    Keyword,
)
from pullnotes.domain.services.template_parser import TemplateSection, ParsedTemplate

from helpers import make_commit


@pytest.fixture
def sample_commit():
    return make_commit()


@pytest.fixture
def sample_commits():
    return [
        make_commit(sha="aaa1111", subject="feat: add login", change_type="feat", additions=50, deletions=10, files=["src/auth.py", "src/login.py"]),
        make_commit(sha="bbb2222", subject="fix: correct password validation", change_type="fix", additions=5, deletions=3, files=["src/auth.py"]),
        make_commit(sha="ccc3333", subject="docs: update README", change_type="docs", additions=20, deletions=5, files=["README.md"]),
        make_commit(sha="ddd4444", subject="refactor: clean up utils", change_type="refactor", additions=15, deletions=20, files=["src/utils.py", "src/helpers.py"]),
        make_commit(sha="eee5555", subject="chore: update deps", change_type="chore", additions=2, deletions=2, files=["requirements.txt"]),
    ]


@pytest.fixture
def non_conventional_commit():
    return make_commit(
        sha="fff6666",
        subject="updated some stuff",
        change_type="other",
        is_conventional=False,
    )


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_config():
    return {
        "commit_types": {
            "feat": {"label": "Funcionalidades", "patterns": ["\\bfeat\\b", "\\bfeature\\b"]},
            "fix": {"label": "Ajustes", "patterns": ["\\bfix\\b", "\\bbugfix\\b"]},
            "docs": {"label": "Documentação", "patterns": ["\\bdocs\\b"]},
            "refactor": {"label": "Refatoração", "patterns": ["\\brefactor\\b"]},
            "perf": {"label": "Performance", "patterns": ["\\bperf\\b"]},
            "test": {"label": "Testes", "patterns": ["\\btest\\b"]},
            "build": {"label": "Build", "patterns": ["\\bbuild\\b"]},
            "ci": {"label": "CI", "patterns": ["\\bci\\b"]},
            "style": {"label": "Estilo", "patterns": ["\\bstyle\\b"]},
            "chore": {"label": "chore", "patterns": ["\\bchore\\b"]},
            "revert": {"label": "revert", "patterns": ["\\brevert\\b"]},
        },
        "other_label": "Other",
        "importance": {
            "weight_lines": 0.02,
            "weight_files": 0.6,
            "keyword_bonus": {"breaking": 3.0, "security": 2.0, "perf": 1.0, "hotfix": 2.0},
        },
        "importance_bands": [
            {"name": "low", "min": 0.0},
            {"name": "medium", "min": 3.0},
            {"name": "high", "min": 6.0},
            {"name": "critical", "min": 9.0},
        ],
        "diff": {"max_anchors_keywords": 10, "max_anchors_artifacts": 10},
        "domain": {
            "output_path": "domain_profile.json",
            "model": "qwen2.5:7b",
            "max_total_bytes": 400000,
            "max_file_bytes": 40000,
        },
        "templates": {"pr": "templates/pr.md", "release": "templates/release.md"},
        "output": {"dir": "output"},
        "language": "pt-BR",
        "llm_model": "qwen2.5:7b",
        "llm_timeout_seconds": 600,
        "llm_max_retries": 3,
        "alerts": {"none_text": "None."},
        "release": {
            "version_template": "{revision_range}",
            "date_format": "%Y-%m-%d",
        },
    }


@pytest.fixture
def config_file(tmp_path, sample_config):
    """Write sample config to a temp file and return the path."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps(sample_config), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Template fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_parsed_template():
    return ParsedTemplate(
        title_instruction="Titulo do PR",
        sections=[
            TemplateSection(heading="Descricao", key="descricao", body="Descreva o que foi alterado.", is_static=False),
            TemplateSection(heading="Alterações", key="alteracoes", body="Liste as alteracoes.", is_static=False),
            TemplateSection(heading="Riscos", key="riscos", body="Descreva riscos.", is_static=False),
        ],
    )


# ---------------------------------------------------------------------------
# DiffAnchors fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_diff_anchors():
    return DiffAnchors(
        files_changed=["src/auth.py", "src/login.py"],
        keywords=[
            DiffKeyword(text="authentication", change_type="added"),
            DiffKeyword(text="password", change_type="removed"),
        ],
        artifacts=[
            DiffArtifact(kind="api_endpoint", name="POST /api/login", change_type="added"),
        ],
    )


# ---------------------------------------------------------------------------
# ProjectProfile fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_project_profile():
    return ProjectProfile(
        project_type=ProjectType(kind=ProjectKind.CLI, label="CLI tool", confidence=0.9),
        domain=Domain(
            domain_anchors=DomainAnchors(
                keywords=[Keyword(text="commit", source="README.md"), Keyword(text="git", source="README.md")],
                artifacts=[],
            ),
            confidence=0.8,
            rationale="Test rationale",
        ),
        domain_details=DomainDetails(
            summary="A tool for generating PR descriptions",
            entities=["Commit", "PR"],
            core_tasks=["Parse commits", "Generate text"],
            confidence=0.85,
            rationale="Inferred from code",
        ),
    )


# ---------------------------------------------------------------------------
# Mock LLM client
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.model = "test-model"
    return client
