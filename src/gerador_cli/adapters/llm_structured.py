"""Structured LLM client with validation and retry."""

from __future__ import annotations

from typing import Type, TypeVar, Optional
import logging

from pydantic import BaseModel, ValidationError

from langchain_ollama import ChatOllama
from langchain_core.output_parsers import PydanticOutputParser

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


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

    @property
    def llm(self) -> ChatOllama:
        """Lazy initialization of LLM client."""
        if self._llm is None:
            self._llm = ChatOllama(
                model=self.model,
                temperature=self.temperature,
                timeout=self.timeout_seconds,
            )
        return self._llm

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
        """Fallback strategy using parser with manual retry and error feedback."""
        parser = PydanticOutputParser(pydantic_object=output_schema)

        # Build prompt with format instructions
        format_instructions = parser.get_format_instructions()
        full_prompt = f"{prompt}\n\n{format_instructions}"

        last_error: Optional[Exception] = None
        last_response: str = ""

        for attempt in range(self.max_retries):
            try:
                # On retry, include the error feedback in the prompt
                if attempt > 0 and last_error:
                    retry_prompt = (
                        f"{full_prompt}\n\n"
                        f"PREVIOUS ATTEMPT FAILED with error: {last_error}\n"
                        f"Previous response was: {last_response[:500]}\n"
                        f"Please fix the output and try again."
                    )
                else:
                    retry_prompt = full_prompt

                # Invoke LLM
                raw_response = self.llm.invoke(retry_prompt)
                content = raw_response.content if hasattr(raw_response, 'content') else str(raw_response)
                last_response = content

                # Try to parse the response
                result = parser.parse(content)
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
