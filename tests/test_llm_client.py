"""Tests for StructuredLLMClient."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pydantic import BaseModel, ValidationError

from pullnotes.adapters.llm_structured import StructuredLLMClient


class SimpleSchema(BaseModel):
    name: str
    value: int


class TestStructuredLLMClientInit:
    def test_default_values(self):
        client = StructuredLLMClient(model="test-model")
        assert client.model == "test-model"
        assert client.temperature == 0.2
        assert client.timeout_seconds == 600.0
        assert client.max_retries == 3

    def test_custom_values(self):
        client = StructuredLLMClient(model="m", temperature=0.5, timeout_seconds=30.0, max_retries=1)
        assert client.temperature == 0.5
        assert client.timeout_seconds == 30.0
        assert client.max_retries == 1

    def test_llm_not_initialized(self):
        client = StructuredLLMClient(model="test")
        assert client._llm is None


class TestInvokeStructured:
    @patch("pullnotes.adapters.llm_structured.ChatOllama")
    def test_native_structured_success(self, mock_ollama_cls):
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        expected = SimpleSchema(name="test", value=42)
        mock_structured = MagicMock()
        mock_structured.invoke.return_value = expected
        mock_llm.with_structured_output.return_value = mock_structured

        client = StructuredLLMClient(model="test")
        result = client.invoke_structured("prompt", SimpleSchema)
        assert result.name == "test"
        assert result.value == 42

    @patch("pullnotes.adapters.llm_structured.ChatOllama")
    def test_fallback_to_parser(self, mock_ollama_cls):
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        # Native structured output fails
        mock_llm.with_structured_output.side_effect = Exception("not supported")

        # Parser-based approach succeeds
        mock_response = MagicMock()
        mock_response.content = '{"name": "parsed", "value": 99}'
        mock_llm.invoke.return_value = mock_response

        client = StructuredLLMClient(model="test")
        result = client.invoke_structured("prompt", SimpleSchema)
        assert result.name == "parsed"
        assert result.value == 99

    @patch("pullnotes.adapters.llm_structured.ChatOllama")
    def test_native_returns_none_falls_back(self, mock_ollama_cls):
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        mock_structured = MagicMock()
        mock_structured.invoke.return_value = None
        mock_llm.with_structured_output.return_value = mock_structured

        mock_response = MagicMock()
        mock_response.content = '{"name": "fallback", "value": 1}'
        mock_llm.invoke.return_value = mock_response

        client = StructuredLLMClient(model="test")
        result = client.invoke_structured("prompt", SimpleSchema)
        assert result.name == "fallback"

    @patch("pullnotes.adapters.llm_structured.ChatOllama")
    def test_skip_native_structured(self, mock_ollama_cls):
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        mock_response = MagicMock()
        mock_response.content = '{"name": "direct", "value": 5}'
        mock_llm.invoke.return_value = mock_response

        client = StructuredLLMClient(model="test")
        result = client.invoke_structured("prompt", SimpleSchema, use_native_structured=False)
        assert result.name == "direct"
        mock_llm.with_structured_output.assert_not_called()


class TestInvokeWithParserRetry:
    @patch("pullnotes.adapters.llm_structured.ChatOllama")
    def test_retry_on_parse_failure(self, mock_ollama_cls):
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        # First call returns bad JSON, second returns good JSON
        bad_response = MagicMock()
        bad_response.content = "not json at all"
        good_response = MagicMock()
        good_response.content = '{"name": "retry", "value": 7}'
        mock_llm.invoke.side_effect = [bad_response, good_response]

        client = StructuredLLMClient(model="test", max_retries=3)
        result = client._invoke_with_parser_retry("prompt", SimpleSchema)
        assert result.name == "retry"
        assert mock_llm.invoke.call_count == 2

    @patch("pullnotes.adapters.llm_structured.ChatOllama")
    def test_raises_after_max_retries(self, mock_ollama_cls):
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        bad_response = MagicMock()
        bad_response.content = "bad"
        mock_llm.invoke.return_value = bad_response

        client = StructuredLLMClient(model="test", max_retries=2)
        with pytest.raises(ValueError, match="Failed to parse"):
            client._invoke_with_parser_retry("prompt", SimpleSchema)
        assert mock_llm.invoke.call_count == 2

    @patch("pullnotes.adapters.llm_structured.ChatOllama")
    def test_retry_uses_same_prompt(self, mock_ollama_cls):
        mock_llm = MagicMock()
        mock_ollama_cls.return_value = mock_llm

        bad_response = MagicMock()
        bad_response.content = "invalid"
        good_response = MagicMock()
        good_response.content = '{"name": "ok", "value": 1}'
        mock_llm.invoke.side_effect = [bad_response, good_response]

        client = StructuredLLMClient(model="test", max_retries=3)
        client._invoke_with_parser_retry("prompt", SimpleSchema)

        # Retries should use the same prompt (no bloat from error feedback)
        first_call_prompt = mock_llm.invoke.call_args_list[0][0][0]
        second_call_prompt = mock_llm.invoke.call_args_list[1][0][0]
        assert first_call_prompt == second_call_prompt


class TestLLMProperty:
    @patch("pullnotes.adapters.llm_structured.ChatOllama")
    def test_lazy_init(self, mock_ollama_cls):
        client = StructuredLLMClient(model="test")
        assert client._llm is None
        _ = client.llm
        mock_ollama_cls.assert_called_once()

    @patch("pullnotes.adapters.llm_structured.ChatOllama")
    def test_reuses_instance(self, mock_ollama_cls):
        client = StructuredLLMClient(model="test")
        _ = client.llm
        _ = client.llm
        mock_ollama_cls.assert_called_once()
