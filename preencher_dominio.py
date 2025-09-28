#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Preenche um arquivo XML de domínio a partir da análise de um repositório,
usando Ollama (modelo local) e valida o resultado com XSD.

Uso:
  python preencher_dominio.py /caminho/para/repo

Requisitos:
  pip install lxml ollama
"""

import argparse
import os
import re
import sys
import json
import pathlib
from typing import List, Tuple, Dict, Iterable
from collections import Counter, defaultdict

from lxml import etree
from ollama import chat
from ollama import ChatResponse

# === CONFIGS FIXAS (ajuste aqui) ============================================

# Caminho fixo do template XML (modelo com placeholders)
TEMPLATE_XML_PATH = "C:\\Users\\Davi\\Desktop\\PG1\\xml\\dominio.xml"

# Caminho fixo do XSD (esquema do template)
XSD_PATH = "C:\\Users\\Davi\\Desktop\\PG1\\xml\\XSD_dominio.xml"

# Nome do modelo no Ollama (ajuste conforme instalado localmente)
# Exemplos: "gemma:2b", "llama3.1:8b", "phi3:3.8b-mini", etc.
MODEL_NAME = "gpt-oss:20b"

# Limites e filtros de leitura
MAX_TOTAL_BYTES = 400_000       # limite de bytes agregados do repo para o contexto
MAX_FILE_BYTES = 40_000         # tamanho máximo por arquivo
TEXT_EXTS = {
    ".md", ".txt", ".rst",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".cs", ".go", ".rb", ".php",
    ".sh", ".yml", ".yaml", ".json", ".toml", ".ini", ".cfg", ".conf", ".xml",
    ".sql", ".gradle", ".groovy"
}
IGNORE_DIRS = {".git", ".svn", ".hg", "node_modules", "dist", "build", "target", ".venv", "venv", "__pycache__"}

# Heurísticas para anchors
KW_STOPWORDS = {
    # pt
    "de","da","do","das","dos","em","para","por","com","sem","ao","à","a","o","e","ou","um","uma",
    "se","que","os","as","no","na","nos","nas","como","mais","menos","ser","ter","há","é","são",
    # en
    "the","a","an","and","or","to","of","in","on","for","with","without","is","are","be","this","that",
    "it","as","by","from","at","not","can","if","else","when","do","does","did","will","would","should",
    "into","out","about","over","under","between","within","we","you","they","he","she","i","my","your",
    "our","their","was","were","been","being"
}

API_METHOD_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+(/[A-Za-z0-9_\-/{}/:]+)", re.IGNORECASE)
SQL_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\s+`?([A-Za-z0-9_]+)`?", re.IGNORECASE)
EVENT_NAME_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+Event)\b")
SERVICE_NAME_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+Service)\b")
QUEUE_TOPIC_RE = re.compile(r"\b(topic|queue)s?[:=]\s*([A-Za-z0-9._\-]+)", re.IGNORECASE)

README_CANDIDATES = ("README.md", "readme.md", "README", "Readme.md")
PACKAGE_CANDIDATES = ("package.json", "requirements.txt", "pyproject.toml", "pom.xml", "build.gradle", "Cargo.toml")


# === UTILIDADES =============================================================

def is_text_file(path: str) -> bool:
    ext = pathlib.Path(path).suffix.lower()
    if ext in TEXT_EXTS:
        return True
    # alguns arquivos sem extensão ainda são texto (README)
    name = os.path.basename(path).lower()
    if name in {n.lower() for n in README_CANDIDATES}:
        return True
    return False


def iter_repo_files(repo_dir: str) -> Iterable[str]:
    for root, dirs, files in os.walk(repo_dir):
        # filtra dirs ignorados
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for f in files:
            if f.startswith("."):  # ignora ocultos
                continue
            full = os.path.join(root, f)
            if is_text_file(full):
                yield full


def safe_read(path: str, max_bytes: int = MAX_FILE_BYTES) -> str:
    try:
        with open(path, "rb") as fh:
            data = fh.read(max_bytes + 1)
        if len(data) > max_bytes:
            data = data[:max_bytes]
        return data.decode("utf-8", errors="replace")
    except Exception as e:
        return f"<<ERROR READING {path}: {e}>>"


def top_keywords(text: str, top_n: int = 30) -> List[str]:
    # tokenização simples
    toks = re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ0-9_]{3,}", text)
    toks = [t.lower() for t in toks if t.lower() not in KW_STOPWORDS]
    freq = Counter(toks)
    return [w for w, _ in freq.most_common(top_n)]


def extract_anchors(index: List[Tuple[str, str]]) -> Dict[str, List[Tuple[str, str]]]:
    """
    index: lista de (path_relativo, conteúdo)
    Retorna dict com:
      keywords: [(kw, source), ...]
      artifacts: [(kind,name), ...]
    """
    kw_scores = Counter()
    kw_sources = defaultdict(list)
    artifacts = []

    # prioriza README e arquivos de config
    prioritized = []
    others = []
    for p, c in index:
        base = os.path.basename(p)
        if base in README_CANDIDATES or base in PACKAGE_CANDIDATES:
            prioritized.append((p, c))
        else:
            others.append((p, c))
    ordered = prioritized + others

    # coleta keywords por arquivo
    for p, content in ordered:
        kws = top_keywords(content, top_n=15 if os.path.basename(p) in README_CANDIDATES else 8)
        for kw in kws:
            kw_scores[kw] += 1
            if len(kw_sources[kw]) < 3:
                kw_sources[kw].append(p)

        # artifacts
        for m in API_METHOD_RE.finditer(content):
            artifacts.append(("api_endpoint", f"{m.group(1).upper()} {m.group(2)}"))
        for m in SQL_TABLE_RE.finditer(content):
            artifacts.append(("db_table", m.group(1)))
        for m in EVENT_NAME_RE.finditer(content):
            artifacts.append(("event", m.group(1)))
        for m in SERVICE_NAME_RE.finditer(content):
            artifacts.append(("service", m.group(1)))
        for m in QUEUE_TOPIC_RE.finditer(content):
            artifacts.append((m.group(1).lower(), m.group(2)))

    # escolhe top keywords e origens
    top_kws = [kw for kw, _ in kw_scores.most_common(20)]
    kw_items = []
    for kw in top_kws[:12]:
        src = kw_sources.get(kw, [])
        source = src[0] if src else "UNKNOWN"
        kw_items.append((kw, source))

    # dedup artifacts, limita
    seen = set()
    art_items = []
    for kind, name in artifacts:
        key = (kind, name)
        if key in seen:
            continue
        seen.add(key)
        art_items.append((kind, name))
        if len(art_items) >= 12:
            break

    return {"keywords": kw_items, "artifacts": art_items}


def build_context_snippets(index: List[Tuple[str, str]], budget: int = MAX_TOTAL_BYTES) -> str:
    """
    Produz um contexto com "catálogo" dos arquivos e pequenos trechos.
    """
    parts = []
    total = 0
    for path, content in index:
        header = f"\n----- FILE: {path} -----\n"
        snippet = content[:2000]  # cabeçalho do arquivo
        chunk = header + snippet
        b = len(chunk.encode("utf-8", errors="replace"))
        if total + b > budget:
            break
        parts.append(chunk)
        total += b
    return "".join(parts)


def load_xml(path: str) -> etree._ElementTree:
    with open(path, "rb") as f:
        return etree.parse(f)


def validate_xml(xml_tree: etree._ElementTree, xsd_path: str) -> Tuple[bool, str]:
    with open(xsd_path, "rb") as f:
        schema_doc = etree.parse(f)
    schema = etree.XMLSchema(schema_doc)
    try:
        schema.assertValid(xml_tree)
        return True, "OK"
    except etree.DocumentInvalid as e:
        return False, str(e)


def fill_domain_anchors(xml_tree: etree._ElementTree, anchors: Dict[str, List[Tuple[str, str]]]) -> None:
    """
    Preenche <domain>/<domainAnchors> com <keywords>/<artifacts>.
    Mantém o restante do template intacto para a IA preencher.
    """
    root = xml_tree.getroot()
    domain = root.find(".//domain")
    if domain is None:
        raise RuntimeError("Tag <domain> não encontrada no template XML.")

    # cria/acha domainAnchors
    da = domain.find("domainAnchors")
    if da is None:
        da = etree.SubElement(domain, "domainAnchors")

    # keywords
    kws_node = da.find("keywords")
    if kws_node is not None:
        da.remove(kws_node)
    kws_node = etree.SubElement(da, "keywords")
    for kw, source in anchors.get("keywords", []):
        kw_el = etree.SubElement(kws_node, "kw")
        kw_el.text = kw
        kw_el.set("source", source)

    # artifacts
    arts_node = da.find("artifacts")
    if arts_node is not None:
        da.remove(arts_node)
    arts_node = etree.SubElement(da, "artifacts")
    for kind, name in anchors.get("artifacts", []):
        art = etree.SubElement(arts_node, "artifact")
        art.set("kind", kind)
        art.set("name", name)


def build_llm_prompt_from_template(xml_str: str) -> str:
    """
    Monta instruções para a IA preencher o XML COMPLETO.
    O template já contém anchors; peça para preencher 'projectType', 'labels/other/ontology',
    'confidence/rationale', 'domainDetails' e 'evidence'.
    """
    return f"""Você é um assistente técnico. Preencha o XML abaixo **sem alterar a estrutura**,
mantendo tags e ordem, apenas substituindo conteúdos vazios pelo melhor resumo factual,
e respeitando as seguintes regras:
- Use APENAS informações presentes no contexto do repositório.
- Priorize as ANCORAGENS já presentes em <domainAnchors> (keywords/artifacts).
- Se não houver certeza, deixe campos vazios e use baixa confiança.
- Preencha <evidence> referenciando caminhos/trechos usados.
- Retorne APENAS o XML final (sem comentários, sem explicações).
{xml_str}
"""


def call_ollama_and_get_xml(model: str, prompt: str) -> str:
    """
    Chama o modelo via Ollama e retorna a string (esperada) de XML.
    """
    resp: ChatResponse = chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    # A API do Ollama retorna um objeto com message.content
    content = resp.message.content if hasattr(resp, "message") else resp.get("message", {}).get("content", "")
    return content.strip()


def write_output(path: str, xml_text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(xml_text)


# === MAIN ===================================================================

def main():
    parser = argparse.ArgumentParser(description="Preenche XML de domínio com suporte a XSD e Ollama.")
    parser.add_argument("repo", help="Caminho do repositório (diretório)")
    args = parser.parse_args()

    repo_dir = os.path.abspath(args.repo)
    if not os.path.isdir(repo_dir):
        print(f"Erro: '{repo_dir}' não é um diretório.", file=sys.stderr)
        sys.exit(1)

    # 1) Indexar arquivos de texto do repositório
    index: List[Tuple[str, str]] = []
    total_bytes = 0
    for fpath in iter_repo_files(repo_dir):
        rel = os.path.relpath(fpath, repo_dir)
        content = safe_read(fpath, MAX_FILE_BYTES)
        size_b = len(content.encode("utf-8", errors="replace"))
        if total_bytes + size_b > MAX_TOTAL_BYTES:
            break
        index.append((rel, content))
        total_bytes += size_b

    if not index:
        print("Nenhum arquivo de texto elegível encontrado no repositório.", file=sys.stderr)
        sys.exit(2)

    # 2) Extrair anchors (keywords, artifacts)
    anchors = extract_anchors(index)

    # 3) Carregar template XML e preencher anchors
    xml_tree = load_xml(TEMPLATE_XML_PATH)
    fill_domain_anchors(xml_tree, anchors)

    # 4) (Opcional) Validar template já com anchors (garante estrutura básica)
    ok, msg = validate_xml(xml_tree, XSD_PATH)
    if not ok:
        print("Template + anchors inválido segundo XSD:")
        print(msg)
        sys.exit(3)

    # 5) Montar contexto do repositório (snippets) e prompt
    repo_context = build_context_snippets(index, budget=MAX_TOTAL_BYTES)
    # Inserir contexto como comentário no topo do XML (não afeta validação posterior,
    # pois a IA devolverá o XML SEM comentários, conforme instrução)
    xml_bytes = etree.tostring(xml_tree, encoding="utf-8", xml_declaration=True, pretty_print=True)
    xml_for_llm = xml_bytes.decode("utf-8", errors="replace")

    prompt = f"""
Contexto do repositório (trechos):
{repo_context}

INSTRUÇÃO:
{build_llm_prompt_from_template(xml_for_llm)}
""".strip()

    # 6) Chamar Ollama
    print(f"[INFO] Chamando Ollama modelo '{MODEL_NAME}'...", file=sys.stderr)
    llm_xml = call_ollama_and_get_xml(MODEL_NAME, prompt)

    # 7) Parsear o retorno e validar com XSD
    try:
        final_tree = etree.fromstring(llm_xml.encode("utf-8", errors="replace"))
        final_doc = etree.ElementTree(final_tree)
    except Exception as e:
        # salva saída crua para depuração
        bad_out = os.path.join(repo_dir, "dominio.preenchido.INVALID.xml")
        write_output(bad_out, llm_xml)
        print(f"[ERRO] A saída não é um XML parseável. Salvo em: {bad_out}\n{e}", file=sys.stderr)
        sys.exit(4)

    ok, msg = validate_xml(final_doc, XSD_PATH)
    out_path = os.path.join(repo_dir, "dominio.preenchido.xml")
    if ok:
        write_output(out_path, etree.tostring(final_doc, encoding="utf-8", xml_declaration=True, pretty_print=True).decode("utf-8"))
        print(f"[OK] XML válido gerado em: {out_path}")
    else:
        # salva ainda assim para inspeção
        bad_out = os.path.join(repo_dir, "dominio.preenchido.INVALID.xml")
        write_output(bad_out, llm_xml)
        print(f"[ERRO] XML inválido segundo XSD. Saída salva em: {bad_out}\n{msg}", file=sys.stderr)
        sys.exit(5)


if __name__ == "__main__":
    main()
