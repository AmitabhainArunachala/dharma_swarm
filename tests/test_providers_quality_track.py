"""Additional quality-track tests for dharma_swarm.providers."""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.providers import (
    AnthropicProvider,
    ClaudeCodeProvider,
    CodexProvider,
    ModelRouter,
    OpenAIProvider,
    OpenRouterFreeProvider,
    OpenRouterProvider,
    create_default_router,
)


class _DummyProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=self.content, model="dummy")

    async def stream(self, request: LLMRequest):
        yield self.content


def _mk_resp(content: str = "ok") -> SimpleNamespace:
    return SimpleNamespace(
        model="m",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=None), finish_reason="stop")],
    )


@pytest.mark.asyncio
async def test_model_router_complete_dispatches_to_selected_provider():
    router = ModelRouter({
        ProviderType.ANTHROPIC: _DummyProvider("A"),
        ProviderType.OPENAI: _DummyProvider("B"),
    })
    req = LLMRequest(model="x", messages=[{"role": "user", "content": "hi"}])
    res = await router.complete(ProviderType.OPENAI, req)
    assert res.content == "B"


def test_subprocess_provider_build_env_disables_nonessential_traffic(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    p = ClaudeCodeProvider()
    env = p._build_env()
    assert env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert "CLAUDECODE" not in env


def test_codex_provider_build_env_keeps_claudecode_var(monkeypatch):
    monkeypatch.setenv("CLAUDECODE", "1")
    p = CodexProvider()
    env = p._build_env()
    assert env.get("CLAUDECODE") == "1"


def test_subprocess_provider_prompt_includes_only_user_messages():
    req = LLMRequest(
        model="x",
        system="SYS",
        messages=[
            {"role": "assistant", "content": "ignored"},
            {"role": "user", "content": "hello"},
            {"role": "user", "content": "again"},
        ],
    )
    p = ClaudeCodeProvider()
    prompt = p._build_prompt(req)
    assert "SYS" in prompt
    assert "hello" in prompt and "again" in prompt
    assert "ignored" not in prompt


@pytest.mark.asyncio
async def test_subprocess_provider_stream_yields_complete_result(monkeypatch):
    p = ClaudeCodeProvider()
    monkeypatch.setattr(
        p,
        "complete",
        AsyncMock(return_value=LLMResponse(content="streamed", model="m")),
    )
    req = LLMRequest(model="x", messages=[{"role": "user", "content": "hi"}])
    chunks = [chunk async for chunk in p.stream(req)]
    assert chunks == ["streamed"]


def test_openrouter_provider_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    p = OpenRouterProvider(api_key=None)
    p._api_key = None
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        p._client_or_raise()


def test_openrouter_free_provider_missing_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    p = OpenRouterFreeProvider(api_key=None)
    p._api_key = None
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        p._client_or_raise()


@pytest.mark.asyncio
async def test_openrouter_free_fallback_model_success(monkeypatch):
    p = OpenRouterFreeProvider(api_key="k")
    req = LLMRequest(model="ignored", messages=[{"role": "user", "content": "hi"}])

    client = AsyncMock()
    first_exc = RuntimeError("first failed")
    second_resp = _mk_resp(content="fallback-ok")
    client.chat.completions.create = AsyncMock(side_effect=[first_exc, second_resp])
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    out = await p.complete(req)
    assert out.content == "fallback-ok"
    # one fail + one fallback success
    assert client.chat.completions.create.await_count == 2


@pytest.mark.asyncio
async def test_openrouter_free_all_models_fail_returns_error(monkeypatch):
    p = OpenRouterFreeProvider(api_key="k")
    req = LLMRequest(model="ignored", messages=[{"role": "user", "content": "hi"}])

    client = AsyncMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("all failed"))
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    out = await p.complete(req)
    assert out.content.startswith("ERROR: All free models failed")


@pytest.mark.asyncio
async def test_openrouter_free_stream_yields_delta_content(monkeypatch):
    p = OpenRouterFreeProvider(api_key="k")
    req = LLMRequest(model="ignored", messages=[{"role": "user", "content": "hi"}])

    async def gen():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="A"))])
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=None))])
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="B"))])

    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=gen())
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    chunks = [c async for c in p.stream(req)]
    assert chunks == ["A", "B"]


def test_openai_build_messages_without_system_does_not_prepend():
    msgs = [{"role": "user", "content": "x"}]
    out = OpenAIProvider._build_messages(msgs, "")
    assert out == msgs


def test_anthropic_strip_system_removes_only_system():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
    ]
    out = AnthropicProvider._strip_system(msgs)
    assert [m["role"] for m in out] == ["user", "assistant"]


def test_create_default_router_contains_expected_provider_types():
    router = create_default_router()
    expected = {
        ProviderType.ANTHROPIC,
        ProviderType.OPENAI,
        ProviderType.OPENROUTER,
        ProviderType.CLAUDE_CODE,
        ProviderType.CODEX,
        ProviderType.OPENROUTER_FREE,
    }
    assert set(router._providers.keys()) == expected
