"""Tests for Pydantic schemas."""

import pytest
from pydantic import ValidationError

from pullnotes.domain.schemas import (
    CommitGroupSummary,
    ProjectProfile,
    ProjectType,
    ProjectKind,
    Domain,
    DomainAnchors,
    DomainDetails,
    Keyword,
)


class TestCommitGroupSummary:
    def test_valid_summary(self):
        summary = CommitGroupSummary(
            summary_points=["Added new feature", "Fixed bug"]
        )
        assert len(summary.summary_points) == 2

    def test_empty_list_fails(self):
        with pytest.raises(ValidationError):
            CommitGroupSummary(summary_points=[])


class TestProjectProfile:
    def test_minimal_valid_profile(self):
        profile = ProjectProfile(
            project_type=ProjectType(
                kind=ProjectKind.CLI,
                label="CLI tool for PR generation",
                confidence=0.9
            ),
            domain=Domain(
                domain_anchors=DomainAnchors(
                    keywords=[
                        Keyword(text="commit", source="README.md"),
                        Keyword(text="git", source="README.md")
                    ],
                    artifacts=[]
                ),
                confidence=0.8,
                rationale="Based on README content"
            ),
            domain_details=DomainDetails(
                summary="Tool for generating PR descriptions from git commits",
                entities=["Commit", "PR"],
                core_tasks=["Parse commits", "Generate text"],
                confidence=0.85,
                rationale="Inferred from code structure"
            )
        )
        assert profile.project_type.kind == ProjectKind.CLI

    def test_confidence_bounds(self):
        with pytest.raises(ValidationError):
            ProjectType(
                kind=ProjectKind.CLI,
                label="Test",
                confidence=1.5  # > 1.0
            )
