"""Services organized by pipeline macro etapas."""

from .aggregation import (
    build_convention_report,
    build_language_hint,
    classify_commit,
    compute_importance,
    group_commits_by_type,
    summarize_commit_group,
)
from .composition import (
    build_fields_from_template,
    build_version_label,
    render_changes_by_type_from_summaries,
    render_from_parsed_template,
)
from .template_parser import parse_template
from .data_collection import get_commits, parse_git_log, extract_diff_anchors
from .export import export_commits, export_convention_report, export_text_document

__all__ = [
    "build_convention_report",
    "build_fields_from_template",
    "build_language_hint",
    "build_version_label",
    "classify_commit",
    "compute_importance",
    "export_commits",
    "export_convention_report",
    "export_text_document",
    "get_commits",
    "group_commits_by_type",
    "parse_git_log",
    "parse_template",
    "render_changes_by_type_from_summaries",
    "render_from_parsed_template",
    "summarize_commit_group",
    "extract_diff_anchors",
]
