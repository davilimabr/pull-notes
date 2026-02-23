"""Tests for CLI module."""

import pytest
from unittest.mock import patch, MagicMock

from pullnotes.cli import build_parser, run, _configure_logging


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------

class TestBuildParser:
    def test_creates_parser(self):
        parser = build_parser()
        assert parser is not None

    def test_default_repo(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "config.json"])
        assert args.repo == "."

    def test_custom_repo(self):
        parser = build_parser()
        args = parser.parse_args(["/path/to/repo", "--config", "config.json"])
        assert args.repo == "/path/to/repo"

    def test_config_required(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_generate_default(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.json"])
        assert args.generate == "both"

    def test_generate_pr(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.json", "--generate", "pr"])
        assert args.generate == "pr"

    def test_range_option(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.json", "--range", "v1.0..v2.0"])
        assert args.revision_range == "v1.0..v2.0"

    def test_since_and_until(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.json", "--since", "2024-01-01", "--until", "2024-12-31"])
        assert args.since == "2024-01-01"
        assert args.until == "2024-12-31"

    def test_version(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.json", "--version", "v1.0.0"])
        assert args.version == "v1.0.0"

    def test_no_llm_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.json", "--no-llm"])
        assert args.no_llm is True

    def test_debug_flag(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.json", "--debug"])
        assert args.debug is True

    def test_model_override(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.json", "--model", "llama3"])
        assert args.model == "llama3"

    def test_refresh_domain(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.json", "--refresh-domain"])
        assert args.refresh_domain is True

    def test_output_dir(self):
        parser = build_parser()
        args = parser.parse_args(["--config", "c.json", "--output-dir", "/tmp/out"])
        assert args.output_dir == "/tmp/out"


# ---------------------------------------------------------------------------
# _configure_logging
# ---------------------------------------------------------------------------

class TestConfigureLogging:
    def test_debug_mode(self):
        import logging
        root = logging.getLogger()
        # Clear existing handlers so basicConfig can take effect
        old_handlers = root.handlers[:]
        root.handlers.clear()
        try:
            _configure_logging(True)
            assert root.level == logging.DEBUG
        finally:
            root.handlers = old_handlers

    def test_normal_mode(self):
        import logging
        root = logging.getLogger()
        old_handlers = root.handlers[:]
        root.handlers.clear()
        try:
            _configure_logging(False)
            assert root.level == logging.WARNING
        finally:
            root.handlers = old_handlers


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

class TestRun:
    @patch("pullnotes.cli.run_workflow")
    def test_run_calls_workflow(self, mock_workflow, config_file):
        mock_workflow.return_value = 0
        result = run(["--config", str(config_file)])
        assert result == 0
        mock_workflow.assert_called_once()

    @patch("pullnotes.cli.run_workflow")
    def test_run_passes_args(self, mock_workflow, config_file):
        mock_workflow.return_value = 0
        run(["--config", str(config_file), "--generate", "pr", "--no-llm"])
        args = mock_workflow.call_args[0][0]
        assert args.generate == "pr"
        assert args.no_llm is True
