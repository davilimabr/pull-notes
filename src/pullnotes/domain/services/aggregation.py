"""Services for grouping and summarizing repository changes."""

from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, TYPE_CHECKING

from ...adapters.prompt_debug import save_prompt
from ...prompts import load_prompt
from ..models import Commit

if TYPE_CHECKING:
    from ...adapters.llm_structured import StructuredLLMClient

logger = logging.getLogger(__name__)

_JS_REGEX_RE = re.compile(r"^/(.+)/([a-zA-Z]*)$")


def _compile_config_pattern(pattern_spec) -> re.Pattern:
    """Allow JS-style /.../flags patterns or plain regex strings."""
    if isinstance(pattern_spec, re.Pattern):
        return pattern_spec
    if not isinstance(pattern_spec, str):
        raise ValueError(f"Commit pattern must be string or regex, got {type(pattern_spec)!r}")

    flags = re.IGNORECASE
    body = pattern_spec.strip()
    js_match = _JS_REGEX_RE.match(body)
    if js_match:
        body = js_match.group(1)
        flag_text = js_match.group(2).lower()
        flags = 0
        for char in flag_text:
            if char == "i":
                flags |= re.IGNORECASE
            elif char == "m":
                flags |= re.MULTILINE
            elif char == "s":
                flags |= re.DOTALL
        if not flags:
            flags = re.IGNORECASE

    # Config JSON often swallows backslashes like \b; restore common escapes.
    body = body.replace("\x08", r"\b")

    try:
        return re.compile(body, flags)
    except re.error as exc:
        raise ValueError(f"Invalid commit type pattern '{pattern_spec}': {exc}") from exc


def classify_commit(subject: str, commit_types: Dict[str, Dict]) -> Tuple[str, bool]:
    """Classify commit message using configured patterns."""
    clean_subject = subject.strip()
    for type_name, data in commit_types.items():
        compiled = data.get("_compiled_patterns")
        if compiled is None:
            compiled = [_compile_config_pattern(pattern) for pattern in data["patterns"]]
            data["_compiled_patterns"] = compiled
        for regex in compiled:
            if regex.search(clean_subject):
                return type_name, True
    return "other", False


def compute_importance(commit: Commit, config: Dict) -> Tuple[float, str]:
    """Compute importance score and band for a commit."""
    imp = config["importance"]
    score = (commit.additions + commit.deletions) * imp["weight_lines"]
    score += len(commit.files) * imp["weight_files"]
    lowered = (commit.subject + "\n" + commit.body).lower()
    
    for keyword, bonus in imp["keyword_bonus"].items():
        if keyword in lowered:
            score += float(bonus)
            
    bands = sorted(config["importance_bands"], key=lambda x: x["min"])
    band = bands[0]["name"]
    for item in bands:
        if score >= item["min"]:
            band = item["name"]
    logger.debug("Commit %s importance: score=%.2f band=%s", commit.short_sha, score, band)
    return score, band


def group_commits_by_type(commits: List[Commit], config: Dict) -> List[Tuple[str, List[Commit]]]:
    """Group commits by configured type and sort each group by importance."""
    grouped: List[Tuple[str, List[Commit]]] = []
    commit_types = config["commit_types"]
    for type_name in commit_types:
        typed_commits = sorted(
            (c for c in commits if c.change_type == type_name), key=lambda c: c.importance_score, reverse=True
        )
        grouped.append((type_name, typed_commits))

    other_commits = sorted(
        (c for c in commits if c.change_type not in commit_types), key=lambda c: c.importance_score, reverse=True
    )
    if other_commits:
        grouped.append(("other", other_commits))

    for type_name, group in grouped:
        if group:
            logger.debug("Group '%s': %d commits", type_name, len(group))
    return grouped


_LANGUAGE_NAMES = {
    "pt": "português brasileiro (pt-BR)",
    "en": "English (en)",
    "es": "español (es)",
}


def _resolve_language_name(language: str) -> str:
    prefix = language.split("-")[0].lower() if language else "en"
    return _LANGUAGE_NAMES.get(prefix, language)


def build_language_hint(language: str) -> str:
    name = _resolve_language_name(language)
    return (
        f"MANDATORY: All generated text MUST be written in {name}. "
        f"Do NOT write in any other language.\n"
        f"OBRIGATÓRIO: Todo o texto gerado DEVE ser escrito em {name}. "
        f"NÃO escreva em nenhum outro idioma."
    )


def build_language_reminder(language: str) -> str:
    """Short reminder to append at the end of prompts (recency effect)."""
    name = _resolve_language_name(language)
    return f"REMINDER: Your ENTIRE response must be in {name}. No exceptions."


def _format_diff_anchors_for_prompt(commit: Commit) -> str:
    """Format diff anchors as text for prompt insertion."""
    if not commit.diff_anchors:
        return "(diff analysis unavailable)"

    anchors = commit.diff_anchors
    sections = []

    # Files changed
    if anchors.files_changed:
        files_section = "\n".join(f"- {f}" for f in anchors.files_changed[:15])
        sections.append(f"Files Changed:\n{files_section}")

    # Keywords
    added_kws = [k.text for k in anchors.keywords if k.change_type == "added"][:5]
    removed_kws = [k.text for k in anchors.keywords if k.change_type == "removed"][:5]
    if added_kws or removed_kws:
        kw_parts = []
        if added_kws:
            kw_parts.append(f"Added: {', '.join(added_kws)}")
        if removed_kws:
            kw_parts.append(f"Removed: {', '.join(removed_kws)}")
        sections.append(f"Keywords:\n" + "\n".join(kw_parts))

    # Artifacts
    if anchors.artifacts:
        artifacts_list = [
            f"[{a.change_type}] {a.kind}: {a.name}"
            for a in anchors.artifacts[:5]
        ]
        artifacts_section = "\n".join(f"- {a}" for a in artifacts_list)
        sections.append(f"Artifacts:\n{artifacts_section}")

    return "\n\n".join(sections) if sections else "(no changes detected)"


def _build_commit_blocks(commits: List[Commit], diff_cfg: Dict) -> str:
    """Build text blocks for each commit using semantic anchors."""
    blocks: List[str] = []
    for commit in commits:
        files = "\n".join(f"- {f}" for f in commit.files[:30]) or "- (no files listed)"
        body_text = commit.body.strip() or "(sem corpo)"

        # Build anchors section
        if commit.diff_anchors:
            anchors = commit.diff_anchors

            # Files changed
            files_section = "\n".join(f"- {f}" for f in anchors.files_changed[:15]) or "- (no files)"

            # Keywords
            added_kws = [k.text for k in anchors.keywords if k.change_type == "added"][:5]
            removed_kws = [k.text for k in anchors.keywords if k.change_type == "removed"][:5]
            keywords_section = ""
            if added_kws:
                keywords_section += f"Added: {', '.join(added_kws)}\n"
            if removed_kws:
                keywords_section += f"Removed: {', '.join(removed_kws)}"
            keywords_section = keywords_section.strip() or "(no keywords)"

            # Artifacts
            artifacts_list = [
                f"[{a.change_type}] {a.kind}: {a.name}"
                for a in anchors.artifacts[:5]
            ]
            artifacts_section = "\n".join(f"- {a}" for a in artifacts_list) or "- (no artifacts)"

            change_summary = "\n".join([
                "Files Changed:",
                files_section,
                "Keywords:",
                keywords_section,
                "Artifacts:",
                artifacts_section,
            ])
        else:
            change_summary = "(diff analysis unavailable)"

        blocks.append(
            "\n".join([
                f"Commit: {commit.short_sha}",
                f"Subject: {commit.subject}",
                f"Body: {body_text}",
                "Change Summary:",
                change_summary,
            ])
        )
    return "\n\n".join(blocks)


def summarize_commit_group(
    commit_type: str, commits: List[Commit], config: Dict, client: "StructuredLLMClient", output_type: str = "pr"
) -> str:
    """Summarize a list of commits of the same type using structured output.

    Args:
        commit_type: Type of commits (feat, fix, etc.)
        commits: List of commits to summarize
        config: Configuration dictionary
        client: Shared StructuredLLMClient instance
        output_type: Either "pr" (technical details) or "release" (user-facing)

    Returns:
        Formatted bullet points as string (for backward compatibility with templates)
    """
    from ..schemas import CommitGroupSummary

    commit_types = config.get("commit_types", {})
    label = commit_types.get(commit_type, {}).get("label") or config.get("other_label", commit_type)
    diff_cfg = config["diff"]

    prompt_name = f"commit_group_summary_{output_type}"
    logger.debug("Summarizing group '%s' (%d commits) for %s", label, len(commits), output_type)

    prompt = load_prompt(
        prompt_name,
        {
            "language_hint": build_language_hint(config["language"]),
            "language_reminder": build_language_reminder(config["language"]),
            "change_type_label": label,
            "commit_blocks": _build_commit_blocks(commits, diff_cfg),
        },
    )

    result = client.invoke_structured(prompt, CommitGroupSummary)

    # Save prompt for debugging
    response_text = "\n".join(
        f"- {point.lstrip('- ')}" for point in result.summary_points
    )
    save_prompt(prompt, f"commit_group_{commit_type}_{output_type}", response_text)

    logger.debug("Group '%s' summarized: %d bullet points", label, len(result.summary_points))
    return response_text


def summarize_all_groups(
    grouped_commits: List[Tuple[str, List[Commit]]], config: Dict, client: "StructuredLLMClient", output_type: str = "pr"
) -> Dict[str, str]:
    """Summarize all commit groups in parallel LLM calls.

    Args:
        grouped_commits: List of (type, commits) tuples
        config: Configuration dictionary
        client: Shared StructuredLLMClient instance
        output_type: Either "pr" (technical) or "release" (user-facing)

    Returns:
        Dictionary mapping change_type to formatted summary text
    """
    summaries: Dict[str, str] = {}

    active_groups = [(ct, cs) for ct, cs in grouped_commits if cs]
    if not active_groups:
        return summaries

    def _summarize_one(change_type, commits):
        return change_type, summarize_commit_group(change_type, commits, config, client, output_type)

    with ThreadPoolExecutor(max_workers=len(active_groups)) as executor:
        futures = {
            executor.submit(_summarize_one, ct, cs): ct
            for ct, cs in active_groups
        }
        for future in as_completed(futures):
            change_type = futures[future]
            try:
                _, summary_text = future.result()
                summaries[change_type] = summary_text
            except Exception as exc:
                type_label = config["commit_types"].get(change_type, {}).get("label") or config.get(
                    "other_label", change_type
                )
                logger.warning(
                    "Falha ao resumir grupo %s: %s. Usando assuntos como fallback.",
                    type_label, exc,
                )
                group_commits = [cs for ct, cs in grouped_commits if ct == change_type]
                if group_commits:
                    bullets = [f"- {c.subject}" for c in group_commits[0]]
                    summaries[change_type] = "\n".join(bullets)

    return summaries


def build_convention_report(commits: List[Commit]) -> str:
    """Build markdown report about conventional commits usage."""
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
    logger.debug("Convention report: %d/%d conventional", classified, total)
    return "\n".join(lines)
