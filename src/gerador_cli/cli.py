"""Command-line interface."""

from __future__ import annotations

import argparse

from .workflows.sync import run_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate PR descriptions and release notes from a Git repo.")
    parser.add_argument("repo", nargs="?", default=".", help="Path to the git repository")
    parser.add_argument("--range", dest="revision_range", help="Git revision range (e.g. v1.0..v1.1)")
    parser.add_argument("--since", help="Git since date (e.g. 2024-01-01)")
    parser.add_argument("--until", help="Git until date (e.g. 2024-01-31)")
    parser.add_argument("--config", required=True, help="Path to JSON config file")
    parser.add_argument("--generate", choices=["pr", "release", "both"], default="both")
    parser.add_argument("--version", default="", help="Release version label")
    parser.add_argument("--output-dir", default="", help="Override output directory")
    parser.add_argument("--refresh-domain", action="store_true", help="Rebuild domain profile")
    parser.add_argument("--model", default="", help="Override LLM model for summaries")
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run_workflow(args)
