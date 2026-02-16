"""HTTP/LLM adapters."""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

try:
    import httpx
    from ollama import Client as OllamaClient
except Exception:  # pragma: no cover - optional import handling
    httpx = None
    OllamaClient = None


def call_ollama(model: str, prompt: str, timeout_seconds: float | int | None = None) -> str:
    """Call Ollama chat API and return content."""
    if OllamaClient is None or httpx is None:
        raise RuntimeError("ollama package not available")

    effective_timeout = 10.0
    if timeout_seconds is not None:
        try:
            candidate = float(timeout_seconds)
            if candidate > 0:
                effective_timeout = candidate
        except (TypeError, ValueError):
            pass

    logger.debug("Calling Ollama (model=%s, timeout=%.1fs, prompt_len=%d)", model, effective_timeout, len(prompt))

    try:
        client = OllamaClient(timeout=httpx.Timeout(effective_timeout))
    except Exception as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Ollama client init failed: {exc}") from exc

    try:
        resp: Dict[str, Any] | Any = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2},
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise RuntimeError(f"Ollama request failed: {exc}") from exc

    if hasattr(resp, "message"):
        content = resp.message.content.strip()
    else:
        content = resp.get("message", {}).get("content", "").strip()

    logger.debug("Ollama response received (%d chars)", len(content))
    return content
