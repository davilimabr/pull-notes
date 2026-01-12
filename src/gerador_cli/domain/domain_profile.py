"""Domain profile generation workflow."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..adapters.domain_definition import DEFAULT_MAX_FILE_BYTES, DEFAULT_MAX_TOTAL_BYTES, generate_domain_xml
from .errors import DomainBuildError


@dataclass
class DomainResult:
    output_path: Path
    xml_text: str


def build_domain_profile(
    repo_dir: Path,
    template_path: Path,
    xsd_path: Path,
    model_name: str,
    output_path: Path,
    max_total_bytes: Optional[int] = None,
    max_file_bytes: Optional[int] = None,
) -> DomainResult:
    """Build domain profile using repository context and LLM."""
    repo_dir = repo_dir.resolve()
    if not repo_dir.is_dir():
        raise DomainBuildError(f"Repo dir not found: {repo_dir}")

    template_path = template_path.resolve()
    xsd_path = xsd_path.resolve()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    budget_total = max_total_bytes or DEFAULT_MAX_TOTAL_BYTES
    budget_file = max_file_bytes or DEFAULT_MAX_FILE_BYTES

    try:
        xml_text = generate_domain_xml(
            repo_dir=repo_dir,
            template_path=template_path,
            xsd_path=xsd_path,
            model_name=model_name,
            max_total_bytes=budget_total,
            max_file_bytes=budget_file,
            debug_output_path=output_path,
        )
    except DomainBuildError:
        raise
    except Exception as exc:  # pragma: no cover - defensive catch
        raise DomainBuildError(f"Unexpected error while building domain profile: {exc}") from exc

    output_path.write_text(xml_text, encoding="utf-8")
    return DomainResult(output_path=output_path, xml_text=xml_text)
