"""HTTP/LLM adapters."""

from __future__ import annotations

try:
    from ollama import chat as ollama_chat
except Exception:  # pragma: no cover - optional import for --no-llm
    ollama_chat = None


def call_ollama(model: str, prompt: str) -> str:
    """Call Ollama chat API and return content."""
    if ollama_chat is None:
        raise RuntimeError("ollama package not available")
    resp = ollama_chat(model=model, messages=[{"role": "user", "content": prompt}], options={"temperature": 0.2})
    if hasattr(resp, "message"):
        return resp.message.content.strip()
    return resp.get("message", {}).get("content", "").strip()
