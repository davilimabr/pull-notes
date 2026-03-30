"""Structured LLM client with validation and retry."""

from __future__ import annotations

import json
import re
from typing import Type, TypeVar, Optional
import logging

from pydantic import BaseModel, ValidationError

from langchain_ollama import ChatOllama
from langchain_core.output_parsers import PydanticOutputParser

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)


def _extract_json(text: str) -> str:
    """Extract JSON from text that may be wrapped in markdown code blocks."""
    # Try to find JSON in a markdown code block first
    match = _JSON_BLOCK_RE.search(text)
    if match:
        return match.group(1).strip()

    # Try to find a raw JSON object or array
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        # Find the matching closing bracket by scanning from the end
        end = text.rfind(end_char)
        if end > start:
            candidate = text[start:end + 1]
            try:
                json.loads(candidate)
                return candidate
            except json.JSONDecodeError:
                continue

    return text.strip()


class StructuredLLMClient:
    """Client for structured LLM outputs with validation and retry."""

    def __init__(
        self,
        model: str,
        temperature: float = 0.2,
        timeout_seconds: float = 600.0,
        max_retries: int = 3,
    ):
        self.model = model
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._llm: Optional[ChatOllama] = None
        self._llm_json: Optional[ChatOllama] = None
        logger.debug("StructuredLLMClient created (model=%s, timeout=%.1fs, retries=%d)", model, timeout_seconds, max_retries)

    @property
    def llm(self) -> ChatOllama:
        """Lazy initialization of LLM client."""
        if self._llm is None:
            self._llm = ChatOllama(
                model=self.model,
                temperature=self.temperature,
                timeout=self.timeout_seconds,
            )
            logger.debug("ChatOllama initialized (model=%s)", self.model)
        return self._llm

    @property
    def llm_json(self) -> ChatOllama:
        """Lazy initialization of LLM client with JSON mode forced."""
        if self._llm_json is None:
            self._llm_json = ChatOllama(
                model=self.model,
                temperature=self.temperature,
                timeout=self.timeout_seconds,
                format="json",
            )
            logger.debug("ChatOllama JSON-mode initialized (model=%s)", self.model)
        return self._llm_json

    def invoke_structured(
        self,
        prompt: str,
        output_schema: Type[T],
        use_native_structured: bool = True,
    ) -> T:
        """
        Invoke LLM and return structured output.

        Args:
            prompt: The prompt to send to the LLM
            output_schema: Pydantic model class for response validation
            use_native_structured: Try native structured output first

        Returns:
            Validated Pydantic model instance

        Raises:
            ValueError: If output cannot be parsed after max_retries
        """
        logger.debug("invoke_structured: schema=%s, prompt_len=%d", output_schema.__name__, len(prompt))

        # Strategy 1: Try native structured output (tool calling)
        if use_native_structured:
            try:
                structured_llm = self.llm.with_structured_output(output_schema)
                result = structured_llm.invoke(prompt)
                if result is not None:
                    logger.debug(f"Native structured output succeeded for {output_schema.__name__}")
                    return result
            except Exception as e:
                logger.debug(f"Native structured output failed: {e}, falling back to parser")

        # Strategy 2: Use PydanticOutputParser with manual retry
        return self._invoke_with_parser_retry(prompt, output_schema)

    def _invoke_with_parser_retry(
        self,
        prompt: str,
        output_schema: Type[T],
    ) -> T:
        """Fallback strategy using JSON-mode LLM with manual retry and error feedback."""
        parser = PydanticOutputParser(pydantic_object=output_schema)

        # Build prompt with format instructions
        format_instructions = parser.get_format_instructions()
        full_prompt = f"{prompt}\n\n{format_instructions}"

        prompt_chars = len(full_prompt)
        if prompt_chars > 15000:
            logger.warning(
                "Prompt is very large (%d chars) for schema %s. "
                "Small models may struggle — consider a larger model or reducing context.",
                prompt_chars, output_schema.__name__,
            )

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    logger.debug("Retry attempt %d/%d for %s", attempt + 1, self.max_retries, output_schema.__name__)

                # Use the same prompt on every attempt to avoid bloating context.
                # Appending error feedback to large prompts causes small models
                # to exceed their effective context and produce garbage.
                raw_response = self.llm_json.invoke(full_prompt)
                content = raw_response.content if hasattr(raw_response, 'content') else str(raw_response)

                # Extract JSON in case model wrapped it in markdown or text
                cleaned = _extract_json(content)

                # Try to parse the cleaned response
                result = parser.parse(cleaned)
                logger.debug(f"Parser succeeded on attempt {attempt + 1} for {output_schema.__name__}")
                return result

            except (ValidationError, Exception) as e:
                last_error = e
                logger.debug(f"Parse attempt {attempt + 1} failed for {output_schema.__name__}: {e}")
                continue

        raise ValueError(
            f"Failed to parse structured output after {self.max_retries} retries. "
            f"Schema: {output_schema.__name__}. Last error: {last_error}"
        )
