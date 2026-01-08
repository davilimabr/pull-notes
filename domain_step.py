from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from lxml import etree

import preencher_dominio as poc


@dataclass
class DomainResult:
    output_path: Path
    xml_text: str


class DomainBuildError(RuntimeError):
    pass


def build_domain_profile(
    repo_dir: Path,
    template_path: Path,
    xsd_path: Path,
    model_name: str,
    output_path: Path,
    max_total_bytes: Optional[int] = None,
) -> DomainResult:
    repo_dir = repo_dir.resolve()
    if not repo_dir.is_dir():
        raise DomainBuildError(f"Repo dir not found: {repo_dir}")

    template_path = template_path.resolve()
    xsd_path = xsd_path.resolve()
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    index = []
    total_bytes = 0
    budget = max_total_bytes or poc.MAX_TOTAL_BYTES
    for fpath in poc.iter_repo_files(str(repo_dir)):
        rel = Path(fpath).relative_to(repo_dir).as_posix()
        content = poc.safe_read(fpath, poc.MAX_FILE_BYTES)
        size_b = len(content.encode("utf-8", errors="replace"))
        if total_bytes + size_b > budget:
            break
        index.append((rel, content))
        total_bytes += size_b

    if not index:
        raise DomainBuildError("No eligible text files found in repo.")

    anchors = poc.extract_anchors(index)
    xml_tree = poc.load_xml(str(template_path))
    poc.fill_domain_anchors(xml_tree, anchors)

    ok, msg = poc.validate_xml(xml_tree, str(xsd_path))
    if not ok:
        raise DomainBuildError(f"Template+anchors invalid for XSD: {msg}")

    repo_context = poc.build_context_snippets(index, budget=budget)
    xml_bytes = etree.tostring(xml_tree, encoding="utf-8", xml_declaration=True, pretty_print=True)
    xml_for_llm = xml_bytes.decode("utf-8", errors="replace")

    prompt = (
        "Repository context (snippets):\n"
        f"{repo_context}\n\n"
        "INSTRUCTION:\n"
        f"{poc.build_llm_prompt_from_template(xml_for_llm)}"
    ).strip()

    llm_xml = poc.call_ollama_and_get_xml(model_name, prompt)
    try:
        final_tree = etree.fromstring(llm_xml.encode("utf-8", errors="replace"))
        final_doc = etree.ElementTree(final_tree)
    except Exception as exc:
        output_path.write_text(llm_xml, encoding="utf-8")
        raise DomainBuildError(f"LLM output is not valid XML. Saved to: {output_path}") from exc

    ok, msg = poc.validate_xml(final_doc, str(xsd_path))
    output_path.write_text(
        etree.tostring(final_doc, encoding="utf-8", xml_declaration=True, pretty_print=True).decode("utf-8"),
        encoding="utf-8",
    )
    if not ok:
        raise DomainBuildError(f"LLM XML does not validate against XSD: {msg}")

    return DomainResult(output_path=output_path, xml_text=output_path.read_text(encoding="utf-8"))
