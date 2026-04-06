"""Domain profile generation using structured LLM output."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List
import json
import logging

from ..domain.schemas import (
    ProjectProfile,
    DomainAnchors,
    Keyword,
    Artifact,
    ArtifactKind,
)
from ..domain.errors import DomainBuildError
from .llm_structured import StructuredLLMClient
from .prompt_debug import save_prompt
from ..prompts import load_prompt

logger = logging.getLogger(__name__)

# Reuse functions from domain_definition.py
from .domain_definition import (
    build_repository_index,
    extract_anchors,
    DEFAULT_MAX_TOTAL_BYTES,
    DEFAULT_MAX_FILE_BYTES,
)
from ..domain.services.aggregation import build_language_hint, build_language_reminder


def _anchors_to_pydantic(anchors: Dict[str, List[tuple]]) -> DomainAnchors:
    """Convert extracted anchors to Pydantic model."""
    keywords = [
        Keyword(text=kw, source=source)
        for kw, source in anchors.get("keywords", [])
    ]
    artifacts = []
    for kind, name in anchors.get("artifacts", []):
        # Only include artifacts with valid kinds
        valid_kinds = [e.value for e in ArtifactKind]
        if kind in valid_kinds:
            artifacts.append(Artifact(kind=ArtifactKind(kind), name=name))

    logger.debug("Anchors extracted: %d keywords, %d artifacts", len(keywords), len(artifacts))
    return DomainAnchors(keywords=keywords, artifacts=artifacts)


def generate_domain_profile(
    repo_dir: Path,
    model_name: str,
    *,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    timeout_seconds: float = 600.0,
    max_retries: int = 3,
    language: str = "en",
) -> ProjectProfile:
    """Generate domain profile using structured LLM output.

    Args:
        repo_dir: Path to repository
        model_name: LLM model to use
        max_total_bytes: Total byte budget for context
        max_file_bytes: Per-file byte limit
        timeout_seconds: LLM timeout
        max_retries: Number of retry attempts
        language: Output language hint

    Returns:
        ProjectProfile with validated domain information

    Raises:
        DomainBuildError: If profile cannot be generated
    """
    repo_dir = repo_dir.resolve()
    logger.debug("Generating domain profile for %s (model=%s)", repo_dir, model_name)

    index = build_repository_index(repo_dir, max_total_bytes, max_file_bytes)
    if not index:
        raise DomainBuildError("No eligible text files found in repository.")
    logger.debug("Repository index: %d files", len(index))

    anchors = extract_anchors(index)
    anchors_pydantic = _anchors_to_pydantic(anchors)

    # Create prompt with pre-filled anchors only (no full file content)
    prompt = load_prompt(
        "domain_profile",
        {
            "pre_filled_anchors": anchors_pydantic.model_dump_json(indent=2),
            "language_hint": build_language_hint(language),
            "language_reminder": build_language_reminder(language),
        },
    )

    # Use structured LLM client
    client = StructuredLLMClient(
        model=model_name,
        timeout_seconds=timeout_seconds,
        max_retries=max_retries,
    )

    try:
        logger.debug("Invoking LLM for domain profile...")
        profile = client.invoke_structured(prompt, ProjectProfile)
        profile.domain.domain_anchors = anchors_pydantic
        save_prompt(prompt, "domain_profile", profile.model_dump_json(indent=2))
        logger.debug("Domain profile generated successfully")
        return profile
    except ValueError as e:
        raise DomainBuildError(f"Failed to generate domain profile: {e}") from e


def save_domain_profile(profile: ProjectProfile, output_path: Path) -> None:
    """Save domain profile to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        profile.model_dump_json(indent=2),
        encoding="utf-8"
    )
    logger.debug("Domain profile saved to %s", output_path)


def load_domain_profile(path: Path) -> ProjectProfile:
    """Load domain profile from JSON file."""
    logger.debug("Loading domain profile from %s", path)
    data = json.loads(path.read_text(encoding="utf-8"))
    return ProjectProfile.model_validate(data)
