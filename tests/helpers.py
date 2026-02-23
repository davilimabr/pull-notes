"""Shared test helpers (importable from test modules)."""

from pullnotes.domain.models import Commit
from pullnotes.domain.schemas import DiffAnchors


def make_commit(
    sha="abc1234567890",
    author_name="Test Author",
    author_email="test@example.com",
    date="2024-06-15T10:00:00-03:00",
    subject="feat: add new feature",
    body="",
    files=None,
    additions=10,
    deletions=5,
    diff="",
    diff_anchors=None,
    change_type="feat",
    is_conventional=True,
    importance_score=3.0,
    importance_band="medium",
    summary="",
) -> Commit:
    return Commit(
        sha=sha,
        author_name=author_name,
        author_email=author_email,
        date=date,
        subject=subject,
        body=body,
        files=files or ["src/main.py"],
        additions=additions,
        deletions=deletions,
        diff=diff,
        diff_anchors=diff_anchors,
        change_type=change_type,
        is_conventional=is_conventional,
        importance_score=importance_score,
        importance_band=importance_band,
        summary=summary,
    )
