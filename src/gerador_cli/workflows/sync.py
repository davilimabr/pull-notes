"""Main workflow orchestration."""

from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..adapters.filesystem import ensure_dir, resolve_repo_path
from ..config import load_config, validate_config
from ..domain.domain_profile import build_domain_profile
from ..domain.errors import DomainBuildError
from ..domain.services.aggregation import (
    build_convention_report,
    classify_commit,
    compute_importance,
    summarize_commit,
)
from ..domain.services.composition import (
    build_pr_fields,
    build_release_fields,
    build_version_label,
    render_changes_by_type,
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


def _summarize_commits(commits, config, llm_model: str, no_llm: bool) -> None:
    if no_llm:
        for commit in commits:
            commit.summary = commit.subject
    else:
        for commit in commits:
            commit.summary = summarize_commit(commit, config, llm_model)


def _warn_on_non_conventional(commits) -> None:
    non_conventional = [c for c in commits if not c.is_conventional]
    if not non_conventional:
        return
    print("WARNING: Commits fora do padrao definido foram encontrados:", file=sys.stderr)
    for commit in non_conventional:
        print(f"- {commit.short_sha}: {commit.subject}", file=sys.stderr)


def _prepare_domain_text(repo_dir: Path, domain_cfg, no_llm: bool) -> str:
    domain_out = resolve_repo_path(repo_dir, domain_cfg["output_path"])
    if domain_out.exists():
        return domain_out.read_text(encoding="utf-8")
    if no_llm:
        return ""
    try:
        result = build_domain_profile(
            repo_dir=repo_dir,
            template_path=resolve_repo_path(repo_dir, domain_cfg["template_path"]),
            xsd_path=resolve_repo_path(repo_dir, domain_cfg["xsd_path"]),
            model_name=domain_cfg["model"],
            output_path=domain_out,
            max_total_bytes=domain_cfg["max_total_bytes"],
            max_file_bytes=domain_cfg["max_file_bytes"],
        )
        return result.xml_text
    except DomainBuildError as exc:
        raise SystemExit(f"Domain build failed: {exc}") from exc


def run_workflow(args) -> int:
    repo_dir = Path(args.repo).resolve()
    if not repo_dir.is_dir():
        raise SystemExit(f"Repo dir not found: {repo_dir}")

    config = load_config(args.config)
    validate_config(config, generate=args.generate, no_llm=args.no_llm)
    llm_model = ""
    if not args.no_llm:
        llm_model = args.model or config["llm_model"]

    output_dir = resolve_repo_path(repo_dir, args.output_dir or config["output"]["dir"])

    domain_text = ""
    with ThreadPoolExecutor(max_workers=2) as executor:
        commits_future = executor.submit(get_commits, repo_dir, args.revision_range, args.since, args.until)
        domain_future = None
        if args.generate in {"release", "both"} and not args.refresh_domain:
            domain_future = executor.submit(_prepare_domain_text, repo_dir, config["domain"], args.no_llm)

        commits = commits_future.result()
        if domain_future:
            domain_text = domain_future.result()

    if not commits:
        raise SystemExit("No commits found for the selected range.")

    _classify_commits(commits, config)
    _warn_on_non_conventional(commits)

    ensure_dir(output_dir)

    convention_report = build_convention_report(commits)
    export_convention_report(convention_report, output_dir)

    _score_commits(commits, config)
    _summarize_commits(commits, config, llm_model, args.no_llm)

    export_commits(commits, output_dir)

    changes_md = render_changes_by_type(commits, config)

    if args.generate in {"pr", "both"}:
        alerts = [c.subject for c in commits if not c.is_conventional]
        alerts_md = "\n".join(f"- {a}" for a in alerts) if alerts else config["alerts"]["none_text"]
        pr_template_path = resolve_repo_path(repo_dir, config["templates"]["pr"])
        pr_template = pr_template_path.read_text(encoding="utf-8")
        if args.no_llm:
            pr_fields = dict(config["no_llm"]["pr"])
        else:
            pr_fields = build_pr_fields(commits, config, llm_model)
        pr_fields.update(
            {
                "changes_by_type": changes_md,
                "alerts": alerts_md,
            }
        )
        pr_text = render_template(pr_template, pr_fields)
        export_text_document(pr_text, output_dir, "pr.md")

    if args.generate in {"release", "both"}:
        domain_cfg = config["domain"]
        if not domain_text and not args.refresh_domain:
            domain_out = resolve_repo_path(repo_dir, domain_cfg["output_path"])
            if domain_out.exists():
                domain_text = domain_out.read_text(encoding="utf-8")

        release_template_path = resolve_repo_path(repo_dir, config["templates"]["release"])
        release_template = release_template_path.read_text(encoding="utf-8")
        version_label = build_version_label(args.version, args.revision_range, config["release"])
        domain_trimmed = domain_text[:6000]
        if args.no_llm:
            release_fields = dict(config["no_llm"]["release"])
        else:
            release_fields = build_release_fields(commits, domain_trimmed, config, llm_model, version_label)
        release_fields.update(
            {
                "version": version_label,
                "changes_by_type": changes_md,
            }
        )
        release_text = render_template(release_template, release_fields)
        export_text_document(release_text, output_dir, "release.md")

    return 0
