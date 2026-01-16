"""Domain extraction helpers and CLI wrapper for building the domain XML."""

from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from lxml import etree

from .filesystem import resolve_repo_path
from .http import call_ollama
from ..config import load_config, validate_config
from ..domain.errors import DomainBuildError
from ..prompts import load_prompt

DEFAULT_MAX_TOTAL_BYTES = 400_000
DEFAULT_MAX_FILE_BYTES = 40_000

TEXT_EXTS = {
    ".md",
    ".txt",
    ".rst",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".cs",
    ".go",
    ".rb",
    ".php",
    ".sh",
    ".yml",
    ".yaml",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
    ".sql",
    ".gradle",
    ".groovy",
}

IGNORE_DIRS = {".git", ".svn", ".hg", "node_modules", "dist", "build", "target", ".venv", "venv", "__pycache__"}

KW_STOPWORDS = {
    # pt
    "de",
    "da",
    "do",
    "das",
    "dos",
    "em",
    "para",
    "por",
    "com",
    "sem",
    "ao",
    "a",
    "o",
    "e",
    "ou",
    "um",
    "uma",
    "se",
    "que",
    "os",
    "as",
    "no",
    "na",
    "nos",
    "nas",
    "como",
    "mais",
    "menos",
    "ser",
    "ter",
    "ha",
    "sao",
    # en
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "without",
    "is",
    "are",
    "be",
    "this",
    "that",
    "it",
    "as",
    "by",
    "from",
    "at",
    "not",
    "can",
    "if",
    "else",
    "when",
    "do",
    "does",
    "did",
    "will",
    "would",
    "should",
    "into",
    "out",
    "about",
    "over",
    "under",
    "between",
    "within",
    "we",
    "you",
    "they",
    "he",
    "she",
    "i",
    "my",
    "your",
    "our",
    "their",
    "was",
    "were",
    "been",
    "being",
}

API_METHOD_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[A-Za-z0-9_\-/{}/:]+)", re.IGNORECASE)
SQL_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\s+`?([A-Za-z0-9_]+)`?", re.IGNORECASE)
EVENT_NAME_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+Event)\b")
SERVICE_NAME_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+Service)\b")
QUEUE_TOPIC_RE = re.compile(r"\b(topic|queue)s?[:=]\s*([A-Za-z0-9._\-]+)", re.IGNORECASE)

README_CANDIDATES = ("README.md", "readme.md", "README", "Readme.md")
PACKAGE_CANDIDATES = ("package.json", "requirements.txt", "pyproject.toml", "pom.xml", "build.gradle", "Cargo.toml")
WORD_RE = re.compile(r"[\w\-]{3,}", flags=re.UNICODE)


@dataclass
class IndexedFile:
    """Small representation of a repository file."""

    relative_path: str
    content: str


def _normalize_token(token: str) -> str:
    normalized = unicodedata.normalize("NFD", token)
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return without_accents.casefold()


def is_text_file(path: Path) -> bool:
    """Check if a path should be treated as text based on extension or filename."""
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return True
    return path.name.lower() in {name.lower() for name in README_CANDIDATES}


def iter_repo_files(repo_dir: Path) -> Iterable[Path]:
    """Yield text files under a repository respecting ignore rules."""
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for file_name in files:
            if file_name.startswith("."):
                continue
            path = Path(root, file_name)
            if is_text_file(path):
                yield path


def safe_read(path: Path, max_bytes: int = DEFAULT_MAX_FILE_BYTES) -> str:
    """Read a file defensively, truncating at max_bytes and replacing decode errors."""
    try:
        with path.open("rb") as fh:
            data = fh.read(max_bytes + 1)
        if len(data) > max_bytes:
            data = data[:max_bytes]
        return data.decode("utf-8", errors="replace")
    except Exception as exc:  # pragma: no cover - defensive path
        return f"<<ERROR READING {path}: {exc}>>"


def build_repository_index(
    repo_dir: Path, max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES
) -> List[IndexedFile]:
    """Create an index of text files limited by total bytes."""
    index: List[IndexedFile] = []
    total_bytes = 0
    for file_path in iter_repo_files(repo_dir):
        content = safe_read(file_path, max_file_bytes)
        size_b = len(content.encode("utf-8", errors="replace"))
        if total_bytes + size_b > max_total_bytes:
            break
        rel = file_path.relative_to(repo_dir).as_posix()
        index.append(IndexedFile(relative_path=rel, content=content))
        total_bytes += size_b
    return index


def top_keywords(text: str, top_n: int = 30) -> List[str]:
    tokens = WORD_RE.findall(text)
    filtered: List[str] = []
    for token in tokens:
        if _normalize_token(token) in KW_STOPWORDS:
            continue
        filtered.append(token.lower())
    freq = {}
    for token in filtered:
        freq[token] = freq.get(token, 0) + 1
    return [word for word, _ in sorted(freq.items(), key=lambda item: item[1], reverse=True)[:top_n]]


def extract_anchors(index: Sequence[IndexedFile]) -> Dict[str, List[Tuple[str, str]]]:
    """Extract keywords and artifacts used as anchors for the domain XML."""
    kw_scores: Dict[str, int] = {}
    kw_sources: Dict[str, List[str]] = {}
    artifacts: List[Tuple[str, str]] = []

    prioritized: List[IndexedFile] = []
    others: List[IndexedFile] = []
    for entry in index:
        base = Path(entry.relative_path).name
        if base in README_CANDIDATES or base in PACKAGE_CANDIDATES:
            prioritized.append(entry)
        else:
            others.append(entry)
    ordered = prioritized + others

    for entry in ordered:
        keywords = top_keywords(entry.content, top_n=15 if Path(entry.relative_path).name in README_CANDIDATES else 8)
        for kw in keywords:
            kw_scores[kw] = kw_scores.get(kw, 0) + 1
            kw_sources.setdefault(kw, [])
            if len(kw_sources[kw]) < 3:
                kw_sources[kw].append(entry.relative_path)

        for match in API_METHOD_RE.finditer(entry.content):
            artifacts.append(("api_endpoint", f"{match.group(1).upper()} {match.group(2)}"))
        for match in SQL_TABLE_RE.finditer(entry.content):
            artifacts.append(("db_table", match.group(1)))
        for match in EVENT_NAME_RE.finditer(entry.content):
            artifacts.append(("event", match.group(1)))
        for match in SERVICE_NAME_RE.finditer(entry.content):
            artifacts.append(("service", match.group(1)))
        for match in QUEUE_TOPIC_RE.finditer(entry.content):
            artifacts.append((match.group(1).lower(), match.group(2)))

    top_kws = [kw for kw, _ in sorted(kw_scores.items(), key=lambda item: item[1], reverse=True)[:20]]
    kw_items: List[Tuple[str, str]] = []
    for kw in top_kws[:12]:
        sources = kw_sources.get(kw, [])
        source = sources[0] if sources else "UNKNOWN"
        kw_items.append((kw, source))

    seen = set()
    art_items: List[Tuple[str, str]] = []
    for kind, name in artifacts:
        key = (kind, name)
        if key in seen:
            continue
        seen.add(key)
        art_items.append((kind, name))
        if len(art_items) >= 12:
            break

    return {"keywords": kw_items, "artifacts": art_items}


def build_context_snippets(index: Sequence[IndexedFile], budget: int = DEFAULT_MAX_TOTAL_BYTES) -> str:
    """Produce small snippets of repository files for LLM context."""
    parts: List[str] = []
    total = 0
    for entry in index:
        header = f"\n----- FILE: {entry.relative_path} -----\n"
        snippet = entry.content[:2000]
        chunk = header + snippet
        size_b = len(chunk.encode("utf-8", errors="replace"))
        if total + size_b > budget:
            break
        parts.append(chunk)
        total += size_b
    return "".join(parts)


def load_xml(path: Path) -> etree._ElementTree:
    return etree.parse(str(path))


def validate_xml(xml_tree: etree._ElementTree, xsd_path: Path) -> Tuple[bool, str]:
    schema_doc = etree.parse(str(xsd_path))
    schema = etree.XMLSchema(schema_doc)
    try:
        schema.assertValid(xml_tree)
        return True, "OK"
    except etree.DocumentInvalid as exc:
        return False, str(exc)


def fill_domain_anchors(xml_tree: etree._ElementTree, anchors: Dict[str, List[Tuple[str, str]]]) -> None:
    """Fill <domainAnchors> in the template while keeping other content intact."""
    root = xml_tree.getroot()
    domain = root.find(".//domain")
    if domain is None:
        raise DomainBuildError("Tag <domain> not found in XML template.")

    anchors_node = domain.find("domainAnchors")
    if anchors_node is None:
        anchors_node = etree.SubElement(domain, "domainAnchors")

    keywords_node = anchors_node.find("keywords")
    if keywords_node is not None:
        anchors_node.remove(keywords_node)
    keywords_node = etree.SubElement(anchors_node, "keywords")
    for kw, source in anchors.get("keywords", []):
        kw_el = etree.SubElement(keywords_node, "kw")
        kw_el.text = kw
        kw_el.set("source", source)

    artifacts_node = anchors_node.find("artifacts")
    if artifacts_node is not None:
        anchors_node.remove(artifacts_node)
    artifacts_node = etree.SubElement(anchors_node, "artifacts")
    for kind, name in anchors.get("artifacts", []):
        art_el = etree.SubElement(artifacts_node, "artifact")
        art_el.set("kind", kind)
        art_el.set("name", name)


def build_prompt(repo_context: str, xml_for_llm: str) -> str:
    return load_prompt(
        "domain_xml",
        {
            "repo_context": repo_context,
            "xml_template": xml_for_llm,
        },
    )


def call_llm_for_xml(model: str, prompt: str, timeout_seconds: float | int | None = None) -> str:
    content = call_ollama(model, prompt, timeout_seconds)
    if not content:
        raise DomainBuildError("Empty response from LLM.")
    return content.strip()


def _save_debug_output(path: Path, xml_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(xml_text, encoding="utf-8")


def generate_domain_xml(
    repo_dir: Path,
    template_path: Path,
    xsd_path: Path,
    model_name: str,
    *,
    max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
    llm_timeout_seconds: float | int | None = None,
    debug_output_path: Path | None = None,
) -> str:
    """Build and validate the domain XML using repository context and an LLM."""
    repo_dir = repo_dir.resolve()
    template_path = template_path.resolve()
    xsd_path = xsd_path.resolve()

    index = build_repository_index(repo_dir, max_total_bytes, max_file_bytes)
    if not index:
        raise DomainBuildError("No eligible text files found in repository.")

    anchors = extract_anchors(index)
    xml_tree = load_xml(template_path)
    fill_domain_anchors(xml_tree, anchors)

    repo_context = build_context_snippets(index, budget=max_total_bytes)
    xml_bytes = etree.tostring(xml_tree, encoding="utf-8", xml_declaration=True, pretty_print=True)
    xml_for_llm = xml_bytes.decode("utf-8", errors="replace")
    prompt = build_prompt(repo_context, xml_for_llm)

    raw_output = call_llm_for_xml(model_name, prompt, llm_timeout_seconds)
    try:
        final_tree = etree.fromstring(raw_output.encode("utf-8", errors="replace"))
        final_doc = etree.ElementTree(final_tree)
    except Exception as exc:
        if debug_output_path:
            _save_debug_output(debug_output_path, raw_output)
        raise DomainBuildError("LLM output is not valid XML.") from exc

    ok, msg = validate_xml(final_doc, xsd_path)
    xml_text = etree.tostring(final_doc, encoding="utf-8", xml_declaration=True, pretty_print=True).decode("utf-8")
    if not ok:
        if debug_output_path:
            _save_debug_output(debug_output_path, raw_output)
        raise DomainBuildError(f"LLM XML does not validate against XSD: {msg}")

    return xml_text


def run_cli(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate domain XML using repository context and LLM.")
    parser.add_argument("repo", help="Path to the repository directory")
    parser.add_argument("--config", default="config.default.json", help="Path to the JSON config file")
    parser.add_argument("--output", default="", help="Override output path for the generated XML")
    parser.add_argument("--model", default="", help="Override LLM model name")
    parser.add_argument("--max-total-bytes", type=int, default=None, help="Total byte budget for repository context")
    parser.add_argument("--max-file-bytes", type=int, default=None, help="Per-file byte limit when indexing")
    args = parser.parse_args(argv)

    repo_dir = Path(args.repo).resolve()
    if not repo_dir.is_dir():
        raise SystemExit(f"Repo dir not found: {repo_dir}")

    config = load_config(args.config)
    validate_config(config, generate="release", no_llm=False)
    domain_cfg = config["domain"]

    template_path = resolve_repo_path(repo_dir, domain_cfg["template_path"])
    xsd_path = resolve_repo_path(repo_dir, domain_cfg["xsd_path"])
    output_path = resolve_repo_path(repo_dir, args.output or domain_cfg["output_path"])
    model_name = args.model or domain_cfg["model"]
    max_total_bytes = args.max_total_bytes or domain_cfg["max_total_bytes"]
    max_file_bytes = args.max_file_bytes or domain_cfg["max_file_bytes"]
    llm_timeout_seconds = config.get("llm_timeout_seconds")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        xml_text = generate_domain_xml(
            repo_dir=repo_dir,
            template_path=template_path,
            xsd_path=xsd_path,
            model_name=model_name,
            max_total_bytes=max_total_bytes,
            max_file_bytes=max_file_bytes,
            llm_timeout_seconds=llm_timeout_seconds,
            debug_output_path=output_path,
        )
    except DomainBuildError as exc:
        print(f"[ERRO] {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive catch
        print(f"[ERRO] Unexpected error: {exc}", file=sys.stderr)
        return 1

    output_path.write_text(xml_text, encoding="utf-8")
    print(f"[OK] Domain XML generated at: {output_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(run_cli())
