"""Debug utilities for saving LLM prompts to output directory."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

# Global output directory for prompts - set by workflow
_output_dir: Optional[Path] = None
_prompt_counter: int = 0


def set_prompt_output_dir(output_dir: Path) -> None:
    """Set the output directory for saving prompts."""
    global _output_dir, _prompt_counter
    _output_dir = output_dir
    _prompt_counter = 0


def save_prompt(prompt: str, name: str, response: Optional[str] = None) -> Optional[Path]:
    """Save a prompt to the output directory for debugging.

    Args:
        prompt: The prompt text sent to the LLM
        name: A descriptive name for the prompt (e.g., "commit_summary", "pr_fields")
        response: Optional LLM response to save alongside the prompt

    Returns:
        Path to saved file, or None if output dir not set
    """
    global _prompt_counter

    if _output_dir is None:
        return None

    prompts_dir = _output_dir / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    _prompt_counter += 1
    timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{_prompt_counter:03d}_{timestamp}_{name}.txt"

    content = f"=== PROMPT: {name} ===\n"
    content += f"Timestamp: {datetime.now().isoformat()}\n"
    content += "=" * 50 + "\n\n"
    content += prompt

    if response is not None:
        content += "\n\n" + "=" * 50 + "\n"
        content += "=== RESPONSE ===\n"
        content += "=" * 50 + "\n\n"
        content += response

    path = prompts_dir / filename
    path.write_text(content, encoding="utf-8")
    return path
