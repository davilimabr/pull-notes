"""Pydantic schemas for structured LLM outputs."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# === Enums ===

class ProjectKind(str, Enum):
    """Valid project types."""
    FRAMEWORK = "framework"
    WEB_SERVICE = "web_service"
    WEB_APP = "web_app"
    MOBILE_APP = "mobile_app"
    DESKTOP_APP = "desktop_app"
    DATA_PIPELINE = "data_pipeline"
    INFRASTRUCTURE = "infrastructure"
    CLI = "cli"
    LIBRARY = "library"
    PACKAGE = "package"
    OTHER = "other"


class ArtifactKind(str, Enum):
    """Valid artifact types."""
    DB_TABLE = "db_table"
    TOPIC = "topic"
    QUEUE = "queue"
    API_ENDPOINT = "api_endpoint"
    EVENT = "event"
    SERVICE = "service"
    FILE = "file"
    CONFIG = "config"


# === Schemas para Composicao (PR/Release) ===

class PRFields(BaseModel):
    """Schema for PR description fields."""

    title: str = Field(
        ...,
        description="Concise PR title summarizing the changes",
        min_length=5,
        max_length=100
    )
    summary: str = Field(
        ...,
        description="Brief description of what was changed and why"
    )
    risks: str = Field(
        default="",
        description="Potential risks or impacts of the changes"
    )
    testing: str = Field(
        default="",
        description="Testing performed or recommended"
    )


class ReleaseFields(BaseModel):
    """Schema for Release notes fields."""

    executive_summary: str = Field(
        ...,
        description="Brief overview of this release for stakeholders"
    )
    highlights: str = Field(
        ...,
        description="Key features and improvements in bullet points"
    )
    migration_notes: str = Field(
        default="",
        description="Steps needed to upgrade from previous version"
    )
    known_issues: str = Field(
        default="",
        description="Any known problems or limitations"
    )
    internal_notes: str = Field(
        default="",
        description="Technical details for the development team"
    )


class CommitGroupSummary(BaseModel):
    """Schema for commit group summaries."""

    summary_points: List[str] = Field(
        ...,
        description="List of bullet points summarizing the commits",
        min_length=1
    )


# === Schemas para Domain Profile (substitui XML) ===

class Keyword(BaseModel):
    """A domain keyword with its source."""
    text: str = Field(..., min_length=1, description="The keyword text")
    source: str = Field(..., min_length=1, description="File path where keyword was found")


class Artifact(BaseModel):
    """A detected artifact in the codebase."""
    kind: ArtifactKind = Field(..., description="Type of artifact")
    name: str = Field(..., min_length=1, description="Name of the artifact")


class DomainAnchors(BaseModel):
    """Observable terms and artifacts from the repository."""
    keywords: List[Keyword] = Field(..., min_length=2, description="At least 2 domain keywords")
    artifacts: List[Artifact] = Field(default_factory=list, description="Detected artifacts")


class DomainLabel(BaseModel):
    """A controlled domain label with weight."""
    name: str = Field(..., min_length=1)
    weight: float = Field(..., ge=0.0, le=1.0)


class DomainOther(BaseModel):
    """Free-form domain category when labels don't fit."""
    name: Optional[str] = Field(default=None, max_length=50)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source_terms: List[str] = Field(default_factory=list)
    rationale: Optional[str] = Field(default=None)


class Domain(BaseModel):
    """Domain information with anchors and classification."""
    domain_anchors: DomainAnchors = Field(..., description="Observable anchors from repo")
    labels: List[DomainLabel] = Field(default_factory=list, max_length=3)
    other: Optional[DomainOther] = Field(default=None)
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(..., description="Justification based on anchors")


class DomainDetails(BaseModel):
    """Detailed domain information."""
    summary: str = Field(..., min_length=10, max_length=600, description="1-3 sentences about the project")
    entities: List[str] = Field(..., min_length=1, description="Domain entities")
    core_tasks: List[str] = Field(..., min_length=1, description="Main tasks/features")
    actors: List[str] = Field(default_factory=list, description="User profiles or consumer systems")
    integrations: List[str] = Field(default_factory=list, description="External integrations")
    non_functional: List[str] = Field(default_factory=list, description="Non-functional requirements")
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: str = Field(...)


class EvidenceItem(BaseModel):
    """Evidence supporting a field."""
    field: str = Field(...)
    source: Optional[str] = Field(default=None)
    snippet: Optional[str] = Field(default=None)


class ProjectType(BaseModel):
    """Project classification."""
    kind: ProjectKind = Field(...)
    label: str = Field(..., min_length=1, description="Human-readable label")
    confidence: float = Field(..., ge=0.0, le=1.0)
    rationale: Optional[str] = Field(default=None)


class ProjectProfile(BaseModel):
    """Complete project profile (replaces XML domain definition)."""
    version: str = Field(default="1.0")
    project_type: ProjectType = Field(...)
    domain: Domain = Field(...)
    domain_details: DomainDetails = Field(...)
    evidence: List[EvidenceItem] = Field(default_factory=list)
