"""Tests for base_provider.py — provider algebra.

Verifies tool call normalization, message handling, response building,
and provider capabilities declarations.
"""

from __future__ import annotations

import pytest

from dharma_swarm.base_provider import BaseProvider, ProviderCapabilities
from dharma_swarm.models import LLMResponse
from dharma_swarm.providers import (
    AnthropicProvider,
    ClaudeCodeProvider,
    LLMProvider,
    NVIDIANIMProvider,
    OllamaProvider,
    OpenAIProvider,
    OpenRouterFreeProvider,
    OpenRouterProvider,
)


class TestProviderCapabilities:
    def test_anthropic_caps(self) -> None:
        assert AnthropicProvider.capabilities.supports_tools is True
        assert AnthropicProvider.capabilities.supports_thinking is True
        assert AnthropicProvider.capabilities.provider_family == "anthropic"
        assert AnthropicProvider.capabilities.max_context_tokens == 200_000

    def test_openai_caps(self) -> None:
        assert OpenAIProvider.capabilities.supports_tools is True
        assert OpenAIProvider.capabilities.provider_family == "openai"

    def test_openrouter_caps(self) -> None:
        assert OpenRouterProvider.capabilities.supports_tools is False
        assert OpenRouterProvider.capabilities.provider_family == "openrouter"

    def test_nvidia_caps(self) -> None:
        assert NVIDIANIMProvider.capabilities.can_close is True
        assert NVIDIANIMProvider.capabilities.provider_family == "nvidia"

    def test_ollama_caps(self) -> None:
        assert OllamaProvider.capabilities.requires_api_key is False
        assert OllamaProvider.capabilities.can_close is True

    def test_subprocess_caps(self) -> None:
        assert ClaudeCodeProvider.capabilities.requires_api_key is False
        assert ClaudeCodeProvider.capabilities.provider_family == "subprocess"

    def test_free_caps(self) -> None:
        assert OpenRouterFreeProvider.capabilities.max_context_tokens == 32_000

    def test_frozen(self) -> None:
        with pytest.raises(AttributeError):
            AnthropicProvider.capabilities.supports_tools = False  # type: ignore[misc]


class TestNormalizeToolCalls:
    def test_anthropic_style(self) -> None:
        raw = [{"id": "tc1", "name": "search", "input": {"query": "test"}}]
        result = BaseProvider.normalize_tool_calls(raw)
        assert len(result) == 1
        assert result[0]["name"] == "search"
        assert result[0]["parameters"] == {"query": "test"}
        assert "input" not in result[0]

    def test_openai_style_nested(self) -> None:
        raw = [{"id": "tc2", "function": {"name": "run", "arguments": '{"cmd": "ls"}'}}]
        result = BaseProvider.normalize_tool_calls(raw)
        assert result[0]["name"] == "run"
        assert result[0]["parameters"] == {"cmd": "ls"}

    def test_openai_style_dict_arguments(self) -> None:
        raw = [{"id": "tc3", "function": {"name": "fn", "arguments": {"x": 1}}}]
        result = BaseProvider.normalize_tool_calls(raw)
        assert result[0]["parameters"] == {"x": 1}

    def test_arguments_key_at_top_level(self) -> None:
        raw = [{"id": "tc4", "name": "act", "arguments": '{"k": "v"}'}]
        result = BaseProvider.normalize_tool_calls(raw)
        assert result[0]["parameters"] == {"k": "v"}

    def test_empty_list(self) -> None:
        assert BaseProvider.normalize_tool_calls([]) == []

    def test_passthrough_unknown_format(self) -> None:
        raw = [{"weird": "format"}]
        result = BaseProvider.normalize_tool_calls(raw)
        assert result == [{"weird": "format"}]

    def test_malformed_json_string(self) -> None:
        raw = [{"id": "tc5", "name": "fn", "arguments": "not json"}]
        result = BaseProvider.normalize_tool_calls(raw)
        assert result[0]["parameters"] == {"raw": "not json"}


class TestNormalizeMessages:
    def test_openai_prepends_system(self) -> None:
        msgs = [{"role": "user", "content": "hello"}]
        result = BaseProvider.normalize_messages_openai(msgs, "You are helpful")
        assert len(result) == 2
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are helpful"

    def test_openai_no_system(self) -> None:
        msgs = [{"role": "user", "content": "hi"}]
        result = BaseProvider.normalize_messages_openai(msgs, "")
        assert len(result) == 1

    def test_strip_system(self) -> None:
        msgs = [
            {"role": "system", "content": "ignored"},
            {"role": "user", "content": "hello"},
        ]
        result = BaseProvider.strip_system_messages(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "user"


class TestBuildResponse:
    def test_basic(self) -> None:
        resp = BaseProvider.build_response(
            content="hello", model="test-model",
        )
        assert isinstance(resp, LLMResponse)
        assert resp.content == "hello"
        assert resp.model == "test-model"
        assert resp.tool_calls == []
        assert resp.usage == {}

    def test_with_tool_calls_normalized(self) -> None:
        raw_calls = [{"id": "t1", "name": "fn", "input": {"a": 1}}]
        resp = BaseProvider.build_response(
            content="", model="m", tool_calls=raw_calls,
        )
        assert resp.tool_calls[0]["parameters"] == {"a": 1}
        assert "input" not in resp.tool_calls[0]

    def test_skip_normalization(self) -> None:
        raw_calls = [{"id": "t1", "name": "fn", "input": {"a": 1}}]
        resp = BaseProvider.build_response(
            content="", model="m", tool_calls=raw_calls,
            normalize_tools=False,
        )
        assert "input" in resp.tool_calls[0]


class TestInheritance:
    def test_llmprovider_is_baseprovider(self) -> None:
        assert issubclass(LLMProvider, BaseProvider)

    def test_all_providers_are_baseprovider(self) -> None:
        for cls in (AnthropicProvider, OpenAIProvider, OpenRouterProvider,
                    NVIDIANIMProvider, OllamaProvider, ClaudeCodeProvider,
                    OpenRouterFreeProvider):
            assert issubclass(cls, BaseProvider), f"{cls.__name__} not a BaseProvider"
