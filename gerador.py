from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from ollama import chat as ollama_chat
except Exception:  # pragma: no cover - optional import for --no-llm
    ollama_chat = None

from domain_step import DomainBuildError, build_domain_profile


COMMIT_MARKER = "__COMMIT__"
GIT_FORMAT = f"{COMMIT_MARKER}%n%H%x1f%an%x1f%ae%x1f%ad%x1f%s"


DEFAULT_CONFIG = {
    "commit_types": {
        "feat": {"label": "Features", "patterns": [r"^feat(\(|:|$)", r"^feature(\(|:|$)"]},
        "fix": {"label": "Fixes", "patterns": [r"^fix(\(|:|$)", r"^bugfix(\(|:|$)"]},
        "docs": {"label": "Docs", "patterns": [r"^docs(\(|:|$)"]},
        "refactor": {"label": "Refactors", "patterns": [r"^refactor(\(|:|$)"]},
        "perf": {"label": "Performance", "patterns": [r"^perf(\(|:|$)"]},
        "test": {"label": "Tests", "patterns": [r"^test(\(|:|$)"]},
        "build": {"label": "Build", "patterns": [r"^build(\(|:|$)"]},
        "ci": {"label": "CI", "patterns": [r"^ci(\(|:|$)"]},
        "style": {"label": "Style", "patterns": [r"^style(\(|:|$)"]},
        "chore": {"label": "Chores", "patterns": [r"^chore(\(|:|$)"]},
        "revert": {"label": "Reverts", "patterns": [r"^revert(\(|:|$)"]},
    },
    "other_label": "Other",
    "importance": {
        "weight_lines": 0.02,
        "weight_files": 0.6,
        "keyword_bonus": {"breaking": 3.0, "security": 2.0, "perf": 1.0, "hotfix": 2.0},
    },
    "importance_bands": [
        {"name": "low", "min": 0.0},
        {"name": "medium", "min": 3.0},
        {"name": "high", "min": 6.0},
        {"name": "critical", "min": 9.0},
    ],
    "diff": {"max_bytes": 12000, "max_lines": 200},
    "domain": {
        "template_path": "xml/dominio.xml",
        "xsd_path": "xml/XSD_dominio.xml",
        "output_path": ".gerador/domain.xml",
        "model": "gpt-oss:20b",
        "max_total_bytes": 400000,
    },
    "templates": {"pr": "templates/pr.md", "release": "templates/release.md"},
    "output": {"dir": "out"},
    "language": "pt-BR",
    "llm_model": "gpt-oss:20b",
}


@dataclass
class Commit:
    sha: str
    author_name: str
    author_email: str
    date: str
    subject: str
    body: str = ""
    files: List[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    diff: str = ""
    change_type: str = ""
    is_conventional: bool = True
    importance_score: float = 0.0
    importance_band: str = "low"
    summary: str = ""

    @property
    def short_sha(self) -> str:
        return self.sha[:7]


def deep_merge(base: Dict, override: Dict) -> Dict:
    result = dict(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: Optional[str]) -> Dict:
    if not path:
        return DEFAULT_CONFIG
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    return deep_merge(DEFAULT_CONFIG, raw)


def run_git(repo_dir: Path, args: List[str]) -> str:
    cmd = ["git", "-C", str(repo_dir)] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Git command failed")
    return result.stdout


def parse_git_log(log_text: str) -> List[Commit]:
    commits = []
    lines = log_text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i] != COMMIT_MARKER:
            i += 1
            continue
        if i + 1 >= len(lines):
            break
        header = lines[i + 1]
        i += 2
        parts = header.split("\x1f")
        if len(parts) < 5:
            continue
        sha, author_name, author_email, date, subject = parts[:5]
        additions = 0
        deletions = 0
        files = []
        while i < len(lines) and lines[i] != COMMIT_MARKER:
            line = lines[i]
            i += 1
            if not line.strip():
                continue
            if "\t" in line:
                cols = line.split("\t")
                if len(cols) >= 3:
                    add, delete, path = cols[:3]
                    files.append(path)
                    if add.isdigit():
                        additions += int(add)
                    if delete.isdigit():
                        deletions += int(delete)
            else:
                files.append(line.strip())
        commits.append(
            Commit(
                sha=sha,
                author_name=author_name,
                author_email=author_email,
                date=date,
                subject=subject,
                files=files,
                additions=additions,
                deletions=deletions,
            )
        )
    return commits


def get_commits(repo_dir: Path, revision_range: Optional[str], since: Optional[str], until: Optional[str]) -> List[Commit]:
    args = ["log", "--date=iso-strict", f"--pretty=format:{GIT_FORMAT}", "--numstat"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    if revision_range:
        args.append(revision_range)
    log_text = run_git(repo_dir, args)
    commits = parse_git_log(log_text)
    for commit in commits:
        commit.body = run_git(repo_dir, ["show", "-s", "--format=%B", commit.sha]).strip()
        commit.diff = run_git(repo_dir, ["show", "--pretty=format:", "--unified=3", "--no-color", commit.sha])
    return commits


def trim_diff(diff_text: str, max_lines: int, max_bytes: int) -> str:
    lines = diff_text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    trimmed = "\n".join(lines)
    if len(trimmed.encode("utf-8")) > max_bytes:
        trimmed = trimmed.encode("utf-8")[:max_bytes].decode("utf-8", errors="ignore")
    return trimmed


def classify_commit(subject: str, commit_types: Dict[str, Dict]) -> Tuple[str, bool]:
    clean_subject = subject.strip()
    for type_name, data in commit_types.items():
        for pattern in data.get("patterns", []):
            if re.search(pattern, clean_subject, flags=re.IGNORECASE):
                return type_name, True
    return "other", False


def compute_importance(commit: Commit, config: Dict) -> Tuple[float, str]:
    imp = config["importance"]
    score = (commit.additions + commit.deletions) * imp["weight_lines"]
    score += len(commit.files) * imp["weight_files"]
    lowered = (commit.subject + "\n" + commit.body).lower()
    for keyword, bonus in imp.get("keyword_bonus", {}).items():
        if keyword in lowered:
            score += float(bonus)
    bands = sorted(config["importance_bands"], key=lambda x: x["min"])
    band = bands[0]["name"]
    for item in bands:
        if score >= item["min"]:
            band = item["name"]
    return score, band


def call_ollama(model: str, prompt: str) -> str:
    if ollama_chat is None:
        raise RuntimeError("ollama package not available")
    resp = ollama_chat(model=model, messages=[{"role": "user", "content": prompt}], options={"temperature": 0.2})
    if hasattr(resp, "message"):
        return resp.message.content.strip()
    return resp.get("message", {}).get("content", "").strip()


def build_language_hint(language: str) -> str:
    if language:
        return f"Write the response in {language}."
    return "Write the response in the same language as the input."


def summarize_commit(commit: Commit, config: Dict, model: str) -> str:
    diff_cfg = config["diff"]
    diff = trim_diff(commit.diff, diff_cfg["max_lines"], diff_cfg["max_bytes"])
    prompt = (
        "You are a careful assistant. Summarize the commit in 1-2 sentences.\n"
        "Use only facts present in the message, files, and diff.\n"
        "If unsure, answer with: Contexto insuficiente para resumir.\n"
        f"{build_language_hint(config.get('language', 'pt-BR'))}\n\n"
        "Commit message:\n"
        f"{commit.subject}\n{commit.body}\n\n"
        "Files:\n"
        + "\n".join(f"- {f}" for f in commit.files[:30])
        + "\n\nDiff (truncated):\n"
        f"{diff}\n\n"
        "Return only the summary text."
    )
    return call_ollama(model, prompt)


def extract_json(text: str) -> Dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found")
    return json.loads(text[start : end + 1])


def build_pr_fields(commits: List[Commit], config: Dict, model: str) -> Dict[str, str]:
    prompt = (
        "You are a careful assistant. Produce JSON with keys: title, summary, risks, testing.\n"
        "Use only the facts present in commit summaries and messages.\n"
        "If unsure about risks/testing, return empty string for those fields.\n"
        f"{build_language_hint(config.get('language', 'pt-BR'))}\n\n"
        "Commit summaries:\n"
        + "\n".join(f"- {c.summary or c.subject}" for c in commits)
        + "\n\nReturn only JSON."
    )
    raw = call_ollama(model, prompt)
    return extract_json(raw)


def build_release_fields(
    commits: List[Commit], domain_xml: str, config: Dict, model: str, version: str
) -> Dict[str, str]:
    prompt = (
        "You are a careful assistant. Produce JSON with keys: executive_summary, highlights, "
        "migration_notes, known_issues, internal_notes.\n"
        "Use only facts present in commit summaries, messages, and the domain XML context.\n"
        f"{build_language_hint(config.get('language', 'pt-BR'))}\n\n"
        f"Release version: {version}\n\n"
        "Domain XML (truncated):\n"
        f"{domain_xml}\n\n"
        "Commit summaries:\n"
        + "\n".join(f"- {c.summary or c.subject}" for c in commits)
        + "\n\nReturn only JSON."
    )
    raw = call_ollama(model, prompt)
    return extract_json(raw)


def render_template(template_text: str, values: Dict[str, str]) -> str:
    out = template_text
    for key, value in values.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    out = re.sub(r"{{\s*[\w_]+\s*}}", "", out)
    return out.strip() + "\n"


def render_changes_by_type(commits: List[Commit], config: Dict) -> str:
    by_type: Dict[str, List[Commit]] = {}
    for commit in commits:
        by_type.setdefault(commit.change_type, []).append(commit)
    lines = []
    for type_name, data in config["commit_types"].items():
        group = by_type.get(type_name, [])
        if not group:
            continue
        lines.append(f"### {data['label']}")
        for commit in sorted(group, key=lambda c: c.importance_score, reverse=True):
            summary = commit.summary or commit.subject
            lines.append(f"- {summary} ({commit.short_sha}, {commit.importance_band})")
        lines.append("")
    other_group = by_type.get("other", [])
    if other_group:
        lines.append(f"### {config.get('other_label', 'Other')}")
        for commit in sorted(other_group, key=lambda c: c.importance_score, reverse=True):
            summary = commit.summary or commit.subject
            lines.append(f"- {summary} ({commit.short_sha}, {commit.importance_band})")
        lines.append("")
    return "\n".join(lines).strip()


def build_convention_report(commits: List[Commit]) -> str:
    total = len(commits)
    classified = sum(1 for c in commits if c.is_conventional)
    other = total - classified
    examples_good = [c.subject for c in commits if c.is_conventional][:3]
    examples_bad = [c.subject for c in commits if not c.is_conventional][:3]
    lines = [
        "# Convention Report",
        f"- Total commits: {total}",
        f"- Conventional: {classified}",
        f"- Others: {other}",
        "",
        "## Good Examples",
    ]
    lines += [f"- {s}" for s in examples_good] if examples_good else ["- (none)"]
    lines += ["", "## Bad Examples"]
    lines += [f"- {s}" for s in examples_bad] if examples_bad else ["- (none)"]
    lines.append("")
    return "\n".join(lines)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def resolve_repo_path(repo_dir: Path, path_str: str) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else repo_dir / path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PR descriptions and release notes from a Git repo.")
    parser.add_argument("repo", nargs="?", default=".", help="Path to the git repository")
    parser.add_argument("--range", dest="revision_range", help="Git revision range (e.g. v1.0..v1.1)")
    parser.add_argument("--since", help="Git since date (e.g. 2024-01-01)")
    parser.add_argument("--until", help="Git until date (e.g. 2024-01-31)")
    parser.add_argument("--config", help="Path to JSON config file")
    parser.add_argument("--generate", choices=["pr", "release", "both"], default="both")
    parser.add_argument("--version", default="", help="Release version label")
    parser.add_argument("--output-dir", default="", help="Override output directory")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM calls and use fallback text")
    parser.add_argument("--refresh-domain", action="store_true", help="Rebuild domain profile")
    parser.add_argument("--model", default="", help="Override LLM model for summaries")
    args = parser.parse_args()

    repo_dir = Path(args.repo).resolve()
    if not repo_dir.is_dir():
        raise SystemExit(f"Repo dir not found: {repo_dir}")

    config = load_config(args.config)
    llm_model = args.model or config.get("llm_model", "gpt-oss:20b")

    //pega commits
    commits = get_commits(repo_dir, args.revision_range, args.since, args.until)
    if not commits:
        raise SystemExit("No commits found for the selected range.")

    for commit in commits:
        commit.change_type, commit.is_conventional = classify_commit(commit.subject, config["commit_types"])
        commit.importance_score, commit.importance_band = compute_importance(commit, config)

    if args.no_llm:
        for commit in commits:
            commit.summary = commit.subject
    else:
        for commit in commits:
            commit.summary = summarize_commit(commit, config, llm_model)

    output_dir = resolve_repo_path(repo_dir, args.output_dir or config["output"]["dir"])
    ensure_dir(output_dir)

    commit_data = [asdict(c) for c in commits]
    (output_dir / "commits.json").write_text(json.dumps(commit_data, indent=2), encoding="utf-8")

    convention_report = build_convention_report(commits)
    (output_dir / "conventions.md").write_text(convention_report, encoding="utf-8")

    changes_md = render_changes_by_type(commits, config)
    alerts = [c.subject for c in commits if not c.is_conventional]
    alerts_md = "\n".join(f"- {a}" for a in alerts) if alerts else "None."

    if args.generate in {"pr", "both"}:
        pr_template_path = resolve_repo_path(repo_dir, config["templates"]["pr"])
        pr_template = pr_template_path.read_text(encoding="utf-8")
        if args.no_llm:
            pr_fields = {
                "title": "Pull Request",
                "summary": "Automated summary based on commits.",
                "risks": "",
                "testing": "",
            }
        else:
            pr_fields = build_pr_fields(commits, config, llm_model)
        pr_fields.update(
            {
                "changes_by_type": changes_md,
                "alerts": alerts_md,
            }
        )
        pr_text = render_template(pr_template, pr_fields)
        (output_dir / "pr.md").write_text(pr_text, encoding="utf-8")

    if args.generate in {"release", "both"}:
        domain_cfg = config["domain"]
        domain_out = resolve_repo_path(repo_dir, domain_cfg["output_path"])
        domain_text = ""
        if not domain_out.exists() or args.refresh_domain:
            if args.no_llm:
                domain_text = ""
            else:
                try:
                    result = build_domain_profile(
                        repo_dir=repo_dir,
                        template_path=resolve_repo_path(repo_dir, domain_cfg["template_path"]),
                        xsd_path=resolve_repo_path(repo_dir, domain_cfg["xsd_path"]),
                        model_name=domain_cfg["model"],
                        output_path=domain_out,
                        max_total_bytes=domain_cfg.get("max_total_bytes"),
                    )
                    domain_text = result.xml_text
                except DomainBuildError as exc:
                    raise SystemExit(f"Domain build failed: {exc}")
        else:
            domain_text = domain_out.read_text(encoding="utf-8")

        release_template_path = resolve_repo_path(repo_dir, config["templates"]["release"])
        release_template = release_template_path.read_text(encoding="utf-8")
        version_label = args.version or args.revision_range or datetime.now().strftime("%Y-%m-%d")
        domain_trimmed = domain_text[:6000]
        if args.no_llm:
            release_fields = {
                "executive_summary": "Automated release summary based on commits.",
                "highlights": "",
                "migration_notes": "",
                "known_issues": "",
                "internal_notes": "",
            }
        else:
            release_fields = build_release_fields(commits, domain_trimmed, config, llm_model, version_label)
        release_fields.update(
            {
                "version": version_label,
                "changes_by_type": changes_md,
            }
        )
        release_text = render_template(release_template, release_fields)
        (output_dir / "release.md").write_text(release_text, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
