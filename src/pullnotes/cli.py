"""Command-line interface."""

from __future__ import annotations

import argparse
import logging

from .workflows.sync import run_workflow


def _configure_logging(debug: bool) -> None:
    """Configure root logger. DEBUG logs only appear when --debug is passed."""
    level = logging.DEBUG if debug else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate PR descriptions and release notes from a Git repo.")
    parser.add_argument("repo", nargs="?", default=".", help="Path to the git repository")
    parser.add_argument("--range", dest="revision_range", help="Git revision range (e.g. v1.0..v1.1)")
    parser.add_argument("--since", help="Git since date (e.g. 2024-01-01)")
    parser.add_argument("--until", help="Git until date (e.g. 2024-01-31)")
    parser.add_argument("--config", default="", help="Path to JSON config file (default: config.default.json from pull-notes repo)")
    parser.add_argument("--generate", choices=["pr", "release", "both"], default="both")
    parser.add_argument("--version", default="", help="Release version label")
    parser.add_argument("--output-dir", default="", help="Override output directory")
    parser.add_argument("--refresh-domain", action="store_true", help="Rebuild domain profile")
    parser.add_argument("--model", default="", help="Override LLM model for summaries")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM summaries, use commit subjects directly")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.debug)
    return run_workflow(args)
