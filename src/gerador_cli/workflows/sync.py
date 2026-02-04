"""Main workflow orchestration."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict

from ..adapters.filesystem import ensure_dir, get_repository_name, resolve_cli_or_absolute, resolve_repo_path
from ..adapters.domain_profile import generate_domain_profile, save_domain_profile, load_domain_profile
from ..adapters.prompt_debug import set_prompt_output_dir
from ..config import load_config, validate_config
from ..domain.errors import DomainBuildError
from ..domain.schemas import ProjectProfile
from ..domain.services.aggregation import (
    build_convention_report,
    classify_commit,
    compute_importance,
    group_commits_by_type,
    summarize_all_groups,
)
from ..domain.services.composition import (
    build_pr_fields,
    build_release_fields,
    build_version_label,
    render_changes_by_type_from_summaries,
    render_template,
)
from ..domain.services.data_collection import get_commits
from ..domain.services.export import export_commits, export_convention_report, export_text_document


def _classify_commits(commits, config):
    for commit in commits:
        commit.change_type, commit.is_conventional = classify_commit(commit.subject, config["commit_types"])


def _score_commits(commits, config):
    for commit in commits:
        commit.importance_score, commit.importance_band = compute_importance(commit, config)


def _generate_summaries_for_output(grouped_commits, config, llm_model: str, output_type: str, no_llm: bool) -> Dict[str, str]:
    """Generate summaries for each group of commits based on output type.

    Args:
        grouped_commits: List of (type, commits) tuples
        config: Configuration dictionary
        llm_model: LLM model to use
        output_type: Either "pr" (technical) or "release" (user-facing)
        no_llm: If True, use commit subjects as fallback

    Returns:
        Dictionary mapping change_type to formatted summary text (bullet points)
    """
    if no_llm:
        # Generate simple bullet list from subjects
        summaries = {}
        for change_type, commits in grouped_commits:
            if commits:
                bullets = [f"- {commit.subject}" for commit in commits]
                summaries[change_type] = "\n".join(bullets)
        return summaries

    return summarize_all_groups(grouped_commits, config, llm_model, output_type)


def _warn_on_non_conventional(commits) -> None:
    non_conventional = [c for c in commits if not c.is_conventional]
    if not non_conventional:
        return
    print("⚠️ WARNING: Commits fora do padrao definido foram encontrados, busque seguir a convenção definida ou altere no arquivo de configuração, para melhor funcionamento da ferramenta.", file=sys.stderr)


def _prepare_domain_profile(
    repo_dir: Path, output_dir: Path, domain_cfg, config: Dict
) -> ProjectProfile:
    """Prepare domain profile, loading from cache or generating new one."""
    # Get repository name to include in domain filename
    repo_name = get_repository_name(repo_dir)

    # Build domain filename with repository name (now JSON instead of XML)
    base_output_path = Path(domain_cfg.get("output_path", "domain_profile.json"))
    if base_output_path.suffix in {".xml", ".json"}:
        domain_filename = f"{base_output_path.stem}_{repo_name}.json"
    else:
        domain_filename = f"{base_output_path}_{repo_name}.json"

    # Save domain file in output directory
    domain_out = output_dir / domain_filename

    # Try to load existing profile
    if domain_out.exists():
        try:
            return load_domain_profile(domain_out)
        except Exception:
            pass  # Fall through to regenerate

    # Generate new profile
    try:
        profile = generate_domain_profile(
            repo_dir=repo_dir,
            model_name=domain_cfg["model"],
            max_total_bytes=domain_cfg["max_total_bytes"],
            max_file_bytes=domain_cfg["max_file_bytes"],
            timeout_seconds=config.get("llm_timeout_seconds", 600.0),
            max_retries=config.get("llm_max_retries", 3),
            language=config.get("language", "en"),
        )
        save_domain_profile(profile, domain_out)
        return profile
    except DomainBuildError as exc:
        raise SystemExit(f"Domain build failed: {exc}") from exc
    except Exception as exc:  # pragma: no cover - network/LLM failures
        raise SystemExit(f"Unexpected failure while generating domain profile with LLM: {exc}") from exc


def run_workflow(args) -> int:
    repo_dir = Path(args.repo).resolve()
    if not repo_dir.is_dir():
        raise SystemExit(f"Repo dir not found: {repo_dir}")

    config = load_config(args.config)
    validate_config(config, generate=args.generate)
    llm_model = args.model or config["llm_model"]

    output_dir = resolve_repo_path(repo_dir, args.output_dir or config["output"]["dir"])

    # Ensure output directory exists before starting threads that may write to it
    ensure_dir(output_dir)

    # Configure prompt debug output directory
    set_prompt_output_dir(output_dir)

    domain_profile = None
    with ThreadPoolExecutor(max_workers=2) as executor:
        commits_future = executor.submit(get_commits, repo_dir, args.revision_range, args.since, args.until)
        domain_future = None
        if args.generate in {"release", "both"} and not args.refresh_domain:
            domain_future = executor.submit(
                _prepare_domain_profile, repo_dir, output_dir, config["domain"], config
            )

        commits = commits_future.result()
        if domain_future:
            domain_profile = domain_future.result()

    if not commits:
        raise SystemExit("No commits found for the selected range.")

    _classify_commits(commits, config)
    _warn_on_non_conventional(commits)

    convention_report = build_convention_report(commits)
    export_convention_report(convention_report, output_dir)

    _score_commits(commits, config)
    grouped_commits = group_commits_by_type(commits, config)

    export_commits(commits, output_dir)

    # Generate summaries based on what output types we need
    pr_summaries = {}
    release_summaries = {}

    if args.generate in {"pr", "both"}:
        pr_summaries = _generate_summaries_for_output(grouped_commits, config, llm_model, "pr", args.no_llm)

    if args.generate in {"release", "both"}:
        release_summaries = _generate_summaries_for_output(grouped_commits, config, llm_model, "release", args.no_llm)

    if args.generate in {"pr", "both"}:
        # Generate PR-specific changes (technical details)
        pr_changes_md = render_changes_by_type_from_summaries(grouped_commits, pr_summaries, config)

        alerts = [c.subject for c in commits if not c.is_conventional]
        alerts_md = "\n".join(f"- {a}" for a in alerts) if alerts else config["alerts"]["none_text"]
        pr_template_path = resolve_cli_or_absolute(config["templates"]["pr"])
        pr_template = pr_template_path.read_text(encoding="utf-8")
        try:
            pr_fields = build_pr_fields(pr_summaries, config, llm_model)
        except Exception as exc:
            raise SystemExit(f"Falha ao gerar campos de PR com LLM: {exc}") from exc
        # Convert Pydantic model to dict and add extra fields
        pr_fields_dict = pr_fields.model_dump()
        pr_fields_dict.update(
            {
                "changes_by_type": pr_changes_md,
                "alerts": alerts_md,
            }
        )
        pr_text = render_template(pr_template, pr_fields_dict)
        export_text_document(pr_text, output_dir, "pr.md")

    if args.generate in {"release", "both"}:
        # Generate Release-specific changes (user-facing functionality)
        release_changes_md = render_changes_by_type_from_summaries(grouped_commits, release_summaries, config)

        domain_cfg = config["domain"]
        if domain_profile is None and not args.refresh_domain:
            # Try to load existing domain profile
            repo_name = get_repository_name(repo_dir)
            base_output_path = Path(domain_cfg.get("output_path", "domain_profile.json"))
            if base_output_path.suffix in {".xml", ".json"}:
                domain_filename = f"{base_output_path.stem}_{repo_name}.json"
            else:
                domain_filename = f"{base_output_path}_{repo_name}.json"
            domain_out = output_dir / domain_filename
            if domain_out.exists():
                try:
                    domain_profile = load_domain_profile(domain_out)
                except Exception:
                    pass  # Will use empty context

        # Convert domain profile to JSON string for the prompt
        domain_context = domain_profile.model_dump_json(indent=2) if domain_profile else ""

        release_template_path = resolve_cli_or_absolute(config["templates"]["release"])
        release_template = release_template_path.read_text(encoding="utf-8")
        version_label = build_version_label(args.version, args.revision_range, config["release"])
        try:
            release_fields = build_release_fields(release_summaries, domain_context, config, llm_model, version_label)
        except Exception as exc:
            raise SystemExit(f"Falha ao gerar campos de release com LLM: {exc}") from exc
        # Convert Pydantic model to dict and add extra fields
        release_fields_dict = release_fields.model_dump()
        release_fields_dict.update(
            {
                "version": version_label,
                "changes_by_type": release_changes_md,
            }
        )
        release_text = render_template(release_template, release_fields_dict)
        export_text_document(release_text, output_dir, "release.md")

    return 0
