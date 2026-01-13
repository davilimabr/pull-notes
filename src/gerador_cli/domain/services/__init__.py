"""Services organized by pipeline macro etapas."""

from .aggregation import build_convention_report, build_language_hint, classify_commit, compute_importance, summarize_commit
from .composition import (
    build_pr_fields,
    build_release_fields,
    build_version_label,
    render_changes_by_type,
    render_template,
)
from .data_collection import get_commits, parse_git_log, trim_diff
from .export import export_commits, export_convention_report, export_text_document

__all__ = [
    "build_convention_report",
    "build_language_hint",
    "build_pr_fields",
    "build_release_fields",
    "build_version_label",
    "classify_commit",
    "compute_importance",
    "export_commits",
    "export_convention_report",
    "export_text_document",
    "get_commits",
    "parse_git_log",
    "render_changes_by_type",
    "render_template",
    "summarize_commit",
    "trim_diff",
]
