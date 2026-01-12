"""Main workflow orchestration."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ..adapters.filesystem import ensure_dir, resolve_repo_path
from ..config import load_config, validate_config
from ..domain.domain_profile import build_domain_profile
from ..domain.errors import DomainBuildError
from ..domain.services import (
    build_convention_report,
    build_pr_fields,
    build_release_fields,
    build_version_label,
    classify_commit,
    compute_importance,
    get_commits,
    render_changes_by_type,
    render_template,
    summarize_commit,
)


def _classify_and_score(commits, config):
    for commit in commits:
        commit.change_type, commit.is_conventional = classify_commit(commit.subject, config["commit_types"])
        commit.importance_score, commit.importance_band = compute_importance(commit, config)


def _summarize_commits(commits, config, llm_model: str, no_llm: bool) -> None:
    if no_llm:
        for commit in commits:
            commit.summary = commit.subject
    else:
        for commit in commits:
            commit.summary = summarize_commit(commit, config, llm_model)


def run_workflow(args) -> int:
    repo_dir = Path(args.repo).resolve()
    if not repo_dir.is_dir():
        raise SystemExit(f"Repo dir not found: {repo_dir}")

    config = load_config(args.config)
    validate_config(config, generate=args.generate, no_llm=args.no_llm)
    llm_model = ""
    if not args.no_llm:
        llm_model = args.model or config["llm_model"]

    commits = get_commits(repo_dir, args.revision_range, args.since, args.until)
    if not commits:
        raise SystemExit("No commits found for the selected range.")

    _classify_and_score(commits, config)
    _summarize_commits(commits, config, llm_model, args.no_llm)

    output_dir = resolve_repo_path(repo_dir, args.output_dir or config["output"]["dir"])
    ensure_dir(output_dir)

    commit_data = [asdict(c) for c in commits]
    (output_dir / "commits.json").write_text(json.dumps(commit_data, indent=2), encoding="utf-8")

    convention_report = build_convention_report(commits)
    (output_dir / "conventions.md").write_text(convention_report, encoding="utf-8")

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
                        max_total_bytes=domain_cfg["max_total_bytes"],
                        max_file_bytes=domain_cfg["max_file_bytes"],
                    )
                    domain_text = result.xml_text
                except DomainBuildError as exc:
                    raise SystemExit(f"Domain build failed: {exc}")
        else:
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
        (output_dir / "release.md").write_text(release_text, encoding="utf-8")

    return 0
