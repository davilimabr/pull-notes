"""Performance tests for PullNotes.

These tests measure execution time of key operations to ensure
the tool performs within acceptable limits. They do NOT require
LLM services - all external calls are mocked.
"""

import time
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from pullnotes.config import load_config, validate_config
from pullnotes.domain.models import Commit, COMMIT_MARKER
from pullnotes.domain.schemas import CommitGroupSummary, DiffAnchors
from pullnotes.domain.services.aggregation import (
    classify_commit,
    compute_importance,
    group_commits_by_type,
    build_convention_report,
)
from pullnotes.domain.services.composition import (
    render_changes_by_type_from_summaries,
    render_from_parsed_template,
)
from pullnotes.domain.services.data_collection import (
    parse_git_log,
    extract_diff_anchors,
)
from pullnotes.domain.services.template_parser import parse_template
from pullnotes.domain.services.export import (
    create_output_structure,
    export_commits,
)
from pullnotes.domain.services.dynamic_fields import (
    build_dynamic_schema,
    build_dynamic_prompt,
)
from pullnotes.adapters.domain_definition import (
    build_repository_index,
    extract_anchors,
    build_context_snippets,
    top_keywords,
)

from helpers import make_commit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def generate_git_log(n_commits: int) -> str:
    """Generate a synthetic git log with n commits."""
    lines = []
    for i in range(n_commits):
        commit_type = ["feat", "fix", "docs", "refactor", "chore"][i % 5]
        lines.append(COMMIT_MARKER)
        lines.append(f"sha{i:06d}\x1fAuthor{i}\x1fauthor{i}@test.com\x1f2024-06-{(i%28)+1:02d}\x1f{commit_type}: change {i}")
        n_files = (i % 5) + 1
        for f in range(n_files):
            lines.append(f"{(i*3+f)%100}\t{(i*2+f)%50}\tsrc/module{f}/file{i}.py")
    return "\n".join(lines)


def generate_diff(n_files: int, lines_per_file: int = 20) -> str:
    """Generate a synthetic diff with n files."""
    parts = []
    for i in range(n_files):
        parts.append(f"diff --git a/src/file{i}.py b/src/file{i}.py")
        parts.append(f"--- a/src/file{i}.py")
        parts.append(f"+++ b/src/file{i}.py")
        parts.append(f"@@ -1,{lines_per_file} +1,{lines_per_file} @@")
        for j in range(lines_per_file):
            if j % 2 == 0:
                parts.append(f"+added_line_{i}_{j} authentication service handler")
            else:
                parts.append(f"-removed_line_{i}_{j} old_function deprecated")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Performance: Git log parsing
# ---------------------------------------------------------------------------

class TestParseGitLogPerformance:
    @pytest.mark.parametrize("n_commits", [100, 500, 1000])
    def test_parse_speed(self, n_commits):
        """Parse n commits within acceptable time."""
        log = generate_git_log(n_commits)
        start = time.perf_counter()
        commits = parse_git_log(log)
        elapsed = time.perf_counter() - start

        assert len(commits) == n_commits
        # Should parse 1000 commits in under 1 second
        assert elapsed < 2.0, f"Parsing {n_commits} commits took {elapsed:.3f}s (limit: 2.0s)"

    def test_parse_1000_commits_under_1s(self):
        log = generate_git_log(1000)
        start = time.perf_counter()
        parse_git_log(log)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Parsing 1000 commits took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Performance: Commit classification
# ---------------------------------------------------------------------------

class TestClassificationPerformance:
    def test_classify_1000_commits(self, sample_config):
        """Classify 1000 commits quickly."""
        commits = [make_commit(subject=f"feat: change {i}") for i in range(1000)]
        start = time.perf_counter()
        for c in commits:
            classify_commit(c.subject, sample_config["commit_types"])
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Classifying 1000 commits took {elapsed:.3f}s"

    def test_classify_mixed_types(self, sample_config):
        """Classify commits with different types."""
        types = ["feat", "fix", "docs", "refactor", "chore", "test", "build", "ci"]
        commits = [make_commit(subject=f"{t}: change {i}") for i, t in enumerate(types * 125)]
        start = time.perf_counter()
        for c in commits:
            classify_commit(c.subject, sample_config["commit_types"])
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Classifying 1000 mixed commits took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Performance: Importance scoring
# ---------------------------------------------------------------------------

class TestImportancePerformance:
    def test_score_1000_commits(self, sample_config):
        commits = [
            make_commit(
                additions=i * 10,
                deletions=i * 5,
                files=[f"file{j}.py" for j in range(i % 10)],
                subject=f"feat: change {i}",
            )
            for i in range(1000)
        ]
        start = time.perf_counter()
        for c in commits:
            compute_importance(c, sample_config)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Scoring 1000 commits took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Performance: Diff anchor extraction
# ---------------------------------------------------------------------------

class TestDiffAnchorPerformance:
    def test_extract_from_large_diff(self):
        """Extract anchors from a diff with 50 files."""
        diff = generate_diff(50, lines_per_file=50)
        start = time.perf_counter()
        anchors = extract_diff_anchors(diff)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Extracting anchors from 50-file diff took {elapsed:.3f}s"
        assert len(anchors.files_changed) > 0

    def test_extract_from_100_file_diff(self):
        diff = generate_diff(100, lines_per_file=30)
        start = time.perf_counter()
        extract_diff_anchors(diff)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"Extracting from 100-file diff took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Performance: Template parsing and rendering
# ---------------------------------------------------------------------------

class TestTemplatePerformance:
    def test_parse_template_speed(self):
        """Parse template quickly."""
        template_path = Path(__file__).parent.parent / "src" / "pullnotes" / "templates" / "pr.md"
        template_text = template_path.read_text(encoding="utf-8")

        start = time.perf_counter()
        for _ in range(1000):
            parse_template(template_text)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Parsing template 1000 times took {elapsed:.3f}s"

    def test_render_template_speed(self):
        """Render template quickly."""
        template_path = Path(__file__).parent.parent / "src" / "pullnotes" / "templates" / "pr.md"
        parsed = parse_template(template_path.read_text(encoding="utf-8"))
        fields = {s.key: f"Content for {s.heading}" * 10 for s in parsed.dynamic_sections}

        start = time.perf_counter()
        for _ in range(1000):
            render_from_parsed_template(parsed, fields, title="Test Title")
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Rendering template 1000 times took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Performance: Convention report generation
# ---------------------------------------------------------------------------

class TestConventionReportPerformance:
    def test_report_1000_commits(self):
        commits = [make_commit(subject=f"feat: change {i}") for i in range(1000)]
        start = time.perf_counter()
        report = build_convention_report(commits)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Convention report for 1000 commits took {elapsed:.3f}s"
        assert "1000" in report


# ---------------------------------------------------------------------------
# Performance: Grouping commits
# ---------------------------------------------------------------------------

class TestGroupingPerformance:
    def test_group_1000_commits(self, sample_config):
        types = list(sample_config["commit_types"].keys())
        commits = []
        for i in range(1000):
            t = types[i % len(types)]
            commits.append(make_commit(
                sha=f"sha{i:06d}",
                change_type=t,
                importance_score=float(i % 10),
            ))

        start = time.perf_counter()
        groups = group_commits_by_type(commits, sample_config)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0, f"Grouping 1000 commits took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Performance: Keyword extraction
# ---------------------------------------------------------------------------

class TestKeywordPerformance:
    def test_extract_from_large_text(self):
        """Extract keywords from a large text block."""
        words = ["authentication", "authorization", "middleware", "handler", "service", "controller"]
        text = " ".join(words * 5000)

        start = time.perf_counter()
        kws = top_keywords(text, top_n=20)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Keyword extraction from large text took {elapsed:.3f}s"
        assert len(kws) > 0


# ---------------------------------------------------------------------------
# Performance: Dynamic schema generation
# ---------------------------------------------------------------------------

class TestDynamicSchemaPerformance:
    def test_schema_generation_speed(self):
        from pullnotes.domain.services.template_parser import TemplateSection

        sections = [
            TemplateSection(heading=f"Section {i}", key=f"section_{i}", body=f"Instruction {i}", is_static=False)
            for i in range(20)
        ]

        start = time.perf_counter()
        for _ in range(100):
            build_dynamic_schema(sections)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Generating schema 100 times took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Performance: Export operations
# ---------------------------------------------------------------------------

class TestExportPerformance:
    def test_export_1000_commits(self, tmp_path):
        """Export 1000 commits to JSON quickly."""
        commits = [
            make_commit(
                sha=f"sha{i:06d}",
                files=[f"file{j}.py" for j in range(5)],
            )
            for i in range(1000)
        ]

        start = time.perf_counter()
        path = export_commits(commits, tmp_path)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"Exporting 1000 commits took {elapsed:.3f}s"
        assert path.exists()

        data = json.loads(path.read_text(encoding="utf-8"))
        assert len(data) == 1000


# ---------------------------------------------------------------------------
# Performance: Repository indexing
# ---------------------------------------------------------------------------

class TestRepositoryIndexPerformance:
    def test_index_100_files(self, tmp_path):
        """Index 100 files quickly."""
        src = tmp_path / "src"
        src.mkdir()
        for i in range(100):
            (src / f"file{i}.py").write_text(f"# Module {i}\nclass Module{i}:\n    pass\n" * 50, encoding="utf-8")

        start = time.perf_counter()
        index = build_repository_index(tmp_path)
        elapsed = time.perf_counter() - start
        assert elapsed < 3.0, f"Indexing 100 files took {elapsed:.3f}s"
        assert len(index) == 100


# ---------------------------------------------------------------------------
# Performance: Changes rendering
# ---------------------------------------------------------------------------

class TestChangesRenderPerformance:
    def test_render_changes_many_groups(self, sample_config):
        """Render changes for many commit groups."""
        types = list(sample_config["commit_types"].keys())
        grouped = []
        summaries = {}
        for t in types:
            commits = [make_commit(change_type=t, subject=f"{t}: change {i}") for i in range(20)]
            grouped.append((t, commits))
            summaries[t] = "\n".join(f"- {t} change {i}" for i in range(20))

        start = time.perf_counter()
        for _ in range(100):
            render_changes_by_type_from_summaries(grouped, summaries, sample_config)
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Rendering changes 100 times took {elapsed:.3f}s"


# ---------------------------------------------------------------------------
# Performance: Config loading and validation
# ---------------------------------------------------------------------------

class TestConfigPerformance:
    def test_load_and_validate_speed(self):
        """Load and validate config many times."""
        config_path = Path(__file__).parent.parent / "config.default.json"

        start = time.perf_counter()
        for _ in range(100):
            config = load_config(str(config_path))
            validate_config(config, generate="both")
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0, f"Loading/validating config 100 times took {elapsed:.3f}s"
