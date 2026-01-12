"""Prompt loading and templating helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict

PROMPTS_DIR = Path(__file__).parent
PLACEHOLDER_RE = re.compile(r"{{\s*([\w_]+)\s*}}")


def _strip_description(raw: str) -> str:
    """Remove leading comment/description lines from a prompt file."""
    lines = raw.splitlines()
    idx = 0
    while idx < len(lines) and lines[idx].lstrip().startswith("#"):
        idx += 1
    return "\n".join(lines[idx:]).lstrip("\n")


def render_prompt_template(template: str, values: Dict[str, str]) -> str:
    """Replace {{placeholders}} with values and drop unused placeholders."""
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        return values.get(key, "")

    rendered = PLACEHOLDER_RE.sub(repl, template)
    return rendered.strip()


def load_prompt(name: str, values: Dict[str, str]) -> str:
    """Load a prompt by name from the prompts directory and render it."""
    path = PROMPTS_DIR / f"{name}.txt"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    raw = path.read_text(encoding="utf-8")
    template = _strip_description(raw)
    return render_prompt_template(template, values)
