"""Main workflow orchestration."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict

from ..adapters.filesystem import get_repository_name, resolve_cli_or_absolute, resolve_repo_path
from ..adapters.subprocess import PackfileTooLargeError
from ..adapters.domain_profile import generate_domain_profile, save_domain_profile, load_domain_profile
from ..adapters.llm_structured import StructuredLLMClient
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
    build_fields_from_template,
    build_version_label,
    render_changes_by_type_from_summaries,
    render_from_parsed_template,
)
from ..domain.services.template_parser import parse_template
from ..domain.services.data_collection import get_commits
from ..domain.services.export import (
    create_output_structure,
    export_commits,
    export_convention_report,
    export_pr,
    export_release,
)

logger = logging.getLogger(__name__)


def _classify_commits(commits, config):
    for commit in commits:
        commit.change_type, commit.is_conventional = classify_commit(commit.subject, config["commit_types"])
    logger.debug("Classified %d commits", len(commits))


def _score_commits(commits, config):
    for commit in commits:
        commit.importance_score, commit.importance_band = compute_importance(commit, config)
    logger.debug("Scored %d commits", len(commits))


def _generate_summaries_for_output(grouped_commits, config, client: StructuredLLMClient, output_type: str, no_llm: bool) -> Dict[str, str]:
    """Generate summaries for each group of commits based on output type."""
    if no_llm:
        logger.debug("Skipping LLM summaries (--no-llm), using commit subjects for %s", output_type)
        summaries = {}
        for change_type, commits in grouped_commits:
            if commits:
                bullets = [f"- {commit.subject}" for commit in commits]
                summaries[change_type] = "\n".join(bullets)
        return summaries

    logger.debug("Generating LLM summaries for %s (model=%s)", output_type, client.model)
    return summarize_all_groups(grouped_commits, config, client, output_type)


def _warn_on_non_conventional(commits) -> None:
    non_conventional = [c for c in commits if not c.is_conventional]
    if not non_conventional:
        return
    logger.warning(
        "Commits fora do padrao definido foram encontrados (%d), busque seguir a convencao definida "
        "ou altere no arquivo de configuracao, para melhor funcionamento da ferramenta.",
        len(non_conventional),
    )
    for c in non_conventional:
        logger.debug("  Non-conventional commit: %s %s", c.short_sha, c.subject)


def _prepare_domain_profile(
    repo_dir: Path, utils_dir: Path, domain_cfg, config: Dict
) -> ProjectProfile:
    """Prepare domain profile, loading from cache or generating new one."""
    repo_name = get_repository_name(repo_dir)
    domain_filename = f"domain_profile_{repo_name}.json"
    domain_out = utils_dir / domain_filename

    if domain_out.exists():
        try:
            profile = load_domain_profile(domain_out)
            logger.debug("Loaded cached domain profile from %s", domain_out)
            return profile
        except Exception as exc:
            logger.debug("Failed to load cached domain profile: %s", exc)

    logger.debug("Generating new domain profile for %s", repo_name)
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
        logger.debug("Domain profile saved to %s", domain_out)
        return profile
    except DomainBuildError as exc:
        raise SystemExit(f"Domain build failed: {exc}") from exc
    except Exception as exc:  # pragma: no cover - network/LLM failures
        raise SystemExit(f"Unexpected failure while generating domain profile with LLM: {exc}") from exc


def run_workflow(args) -> int:
    repo_dir = Path(args.repo).resolve()
    if not repo_dir.is_dir():
        raise SystemExit(f"Repo dir not found: {repo_dir}")

    logger.debug("Starting workflow for repo: %s", repo_dir)

    config = load_config(args.config)
    validate_config(config, generate=args.generate)
    llm_model = args.model or config["llm_model"]
    logger.debug("Config loaded. LLM model: %s, generate: %s", llm_model, args.generate)

    base_output_dir = resolve_repo_path(repo_dir, args.output_dir or config["output"]["dir"])
    repo_name = get_repository_name(repo_dir)
    logger.debug("Output dir: %s, repo name: %s", base_output_dir, repo_name)

    output_paths = create_output_structure(base_output_dir, repo_name)
    if args.debug:
        set_prompt_output_dir(output_paths['utils'])

    domain_profile = None
    logger.debug("Fetching commits and domain profile in parallel...")
    with ThreadPoolExecutor(max_workers=2) as executor:
        commits_future = executor.submit(get_commits, repo_dir, args.revision_range, args.since, args.until)
        domain_future = None
        if args.generate in {"release", "both"} and not args.refresh_domain:
            domain_future = executor.submit(
                _prepare_domain_profile, repo_dir, output_paths['utils'], config["domain"], config
            )

        try:
            commits = commits_future.result()
        except PackfileTooLargeError as exc:
            raise SystemExit(f"Git packfile error: {exc}")
        except RuntimeError as exc:
            raise SystemExit(str(exc))
        logger.debug("Fetched %d commits", len(commits))
        if domain_future:
            domain_profile = domain_future.result()

    if not commits:
        raise SystemExit("No commits found for the selected range.")

    _classify_commits(commits, config)
    _warn_on_non_conventional(commits)

    convention_report = build_convention_report(commits)
    export_convention_report(convention_report, output_paths['utils'])

    _score_commits(commits, config)
    grouped_commits = group_commits_by_type(commits, config)
    logger.debug("Grouped commits into %d type groups", len(grouped_commits))

    if args.debug:
        export_commits(commits, output_paths['utils'])

    client = StructuredLLMClient(
        model=llm_model,
        timeout_seconds=config.get("llm_timeout_seconds", 600.0),
        max_retries=config.get("llm_max_retries", 3),
    )
    _ = client.llm  # Force lazy initialization before parallel use

    if args.generate == "both":
        # Fase A: Generate summaries in parallel
        logger.debug("Generating PR and release summaries in parallel...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            pr_future = executor.submit(_generate_summaries_for_output, grouped_commits, config, client, "pr", args.no_llm)
            release_future = executor.submit(_generate_summaries_for_output, grouped_commits, config, client, "release", args.no_llm)
            pr_summaries = pr_future.result()
            release_summaries = release_future.result()

        # Fase B: Prepare intermediate data (fast, no LLM)
        pr_changes_md = render_changes_by_type_from_summaries(grouped_commits, pr_summaries, config)
        release_changes_md = render_changes_by_type_from_summaries(grouped_commits, release_summaries, config)

        alerts = [c.subject for c in commits if not c.is_conventional]
        alerts_md = "\n".join(f"- {a}" for a in alerts) if alerts else ""

        pr_template_path = resolve_cli_or_absolute(config["templates"]["pr"])
        logger.debug("PR template: %s", pr_template_path)
        parsed_pr = parse_template(pr_template_path.read_text(encoding="utf-8"))

        if domain_profile is None and not args.refresh_domain:
            domain_filename = f"domain_profile_{repo_name}.json"
            domain_out = output_paths['utils'] / domain_filename
            if domain_out.exists():
                try:
                    domain_profile = load_domain_profile(domain_out)
                    logger.debug("Loaded domain profile from %s", domain_out)
                except Exception:
                    pass

        domain_context = domain_profile.model_dump_json(indent=2) if domain_profile else ""

        release_template_path = resolve_cli_or_absolute(config["templates"]["release"])
        logger.debug("Release template: %s", release_template_path)
        parsed_release = parse_template(release_template_path.read_text(encoding="utf-8"))

        version_label = build_version_label(args.version, args.revision_range, config["release"])
        logger.debug("Release version: %s", version_label)

        # Fase C: Generate fields in parallel
        logger.debug("Generating PR and release fields in parallel...")
        with ThreadPoolExecutor(max_workers=2) as executor:
            pr_fields_future = executor.submit(
                build_fields_from_template,
                parsed_pr, pr_summaries, pr_changes_md, config, client,
                template_type="pr",
                alerts=alerts_md,
            )
            release_fields_future = executor.submit(
                build_fields_from_template,
                parsed_release, release_summaries, release_changes_md, config, client,
                template_type="release",
                domain_context=domain_context,
                version=version_label,
            )
            try:
                pr_fields = pr_fields_future.result()
            except Exception as exc:
                raise SystemExit(f"Falha ao gerar campos de PR com LLM: {exc}") from exc
            try:
                release_fields = release_fields_future.result()
            except Exception as exc:
                raise SystemExit(f"Falha ao gerar campos de release com LLM: {exc}") from exc

        # Fase D: Render and export (fast, no LLM)
        pr_title = pr_fields.get("title", "untitled")
        pr_text = render_from_parsed_template(parsed_pr, pr_fields, title=pr_title)
        path = export_pr(pr_text, output_paths['prs'], pr_title)
        logger.debug("PR exported to %s", path)

        release_date = datetime.now().strftime(config["release"]["date_format"])
        release_text = render_from_parsed_template(
            parsed_release, release_fields,
            title=f"Notas de Versao \u2014 {version_label}",
            subtitle=f"**Data de lancamento**: {release_date}",
        )
        path = export_release(release_text, output_paths['releases'], version_label)
        logger.debug("Release exported to %s", path)

    elif args.generate == "pr":
        logger.debug("Generating PR summaries...")
        pr_summaries = _generate_summaries_for_output(grouped_commits, config, client, "pr", args.no_llm)

        logger.debug("Building PR output...")
        pr_changes_md = render_changes_by_type_from_summaries(grouped_commits, pr_summaries, config)

        alerts = [c.subject for c in commits if not c.is_conventional]
        alerts_md = "\n".join(f"- {a}" for a in alerts) if alerts else ""

        pr_template_path = resolve_cli_or_absolute(config["templates"]["pr"])
        logger.debug("PR template: %s", pr_template_path)
        parsed_pr = parse_template(pr_template_path.read_text(encoding="utf-8"))

        try:
            pr_fields = build_fields_from_template(
                parsed_pr, pr_summaries, pr_changes_md, config, client,
                template_type="pr",
                alerts=alerts_md,
            )
        except Exception as exc:
            raise SystemExit(f"Falha ao gerar campos de PR com LLM: {exc}") from exc

        pr_title = pr_fields.get("title", "untitled")
        pr_text = render_from_parsed_template(parsed_pr, pr_fields, title=pr_title)
        path = export_pr(pr_text, output_paths['prs'], pr_title)
        logger.debug("PR exported to %s", path)

    elif args.generate == "release":
        logger.debug("Generating release summaries...")
        release_summaries = _generate_summaries_for_output(grouped_commits, config, client, "release", args.no_llm)

        logger.debug("Building release output...")
        release_changes_md = render_changes_by_type_from_summaries(grouped_commits, release_summaries, config)

        if domain_profile is None and not args.refresh_domain:
            domain_filename = f"domain_profile_{repo_name}.json"
            domain_out = output_paths['utils'] / domain_filename
            if domain_out.exists():
                try:
                    domain_profile = load_domain_profile(domain_out)
                    logger.debug("Loaded domain profile from %s", domain_out)
                except Exception:
                    pass

        domain_context = domain_profile.model_dump_json(indent=2) if domain_profile else ""

        release_template_path = resolve_cli_or_absolute(config["templates"]["release"])
        logger.debug("Release template: %s", release_template_path)
        parsed_release = parse_template(release_template_path.read_text(encoding="utf-8"))

        version_label = build_version_label(args.version, args.revision_range, config["release"])
        logger.debug("Release version: %s", version_label)
        try:
            release_fields = build_fields_from_template(
                parsed_release, release_summaries, release_changes_md, config, client,
                template_type="release",
                domain_context=domain_context,
                version=version_label,
            )
        except Exception as exc:
            raise SystemExit(f"Falha ao gerar campos de release com LLM: {exc}") from exc

        release_date = datetime.now().strftime(config["release"]["date_format"])
        release_text = render_from_parsed_template(
            parsed_release, release_fields,
            title=f"Notas de Versao \u2014 {version_label}",
            subtitle=f"**Data de lancamento**: {release_date}",
        )
        path = export_release(release_text, output_paths['releases'], version_label)
        logger.debug("Release exported to %s", path)

    logger.debug("Workflow completed successfully")
    return 0
