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
    CerebrasProvider,
    ClaudeCodeProvider,
    CodexProvider,
    ModelRouter,
    NVIDIANIMProvider,
    OllamaProvider,
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


def _mk_resp(
    content: str | None = "ok",
    *,
    reasoning: str | None = None,
    reasoning_details: list[object] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        model="m",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        choices=[SimpleNamespace(
            message=SimpleNamespace(
                content=content,
                reasoning=reasoning,
                reasoning_details=reasoning_details,
                tool_calls=None,
            ),
            finish_reason="stop",
        )],
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
async def test_openrouter_provider_uses_reasoning_when_content_empty(monkeypatch):
    p = OpenRouterProvider(api_key="k")
    req = LLMRequest(model="openrouter-test", messages=[{"role": "user", "content": "hi"}])

    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_mk_resp(content=None, reasoning="OK"))
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    out = await p.complete(req)
    assert out.content == "OK"


@pytest.mark.asyncio
async def test_openrouter_provider_forwards_tools_and_parses_tool_calls(monkeypatch):
    p = OpenRouterProvider(api_key="k")
    req = LLMRequest(
        model="openrouter-test",
        messages=[{"role": "user", "content": "hi"}],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "shell_exec",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ],
    )

    client = AsyncMock()
    tool_call = SimpleNamespace(
        id="tc1",
        function=SimpleNamespace(name="shell_exec", arguments='{"command":"pwd"}'),
    )
    client.chat.completions.create = AsyncMock(
        return_value=_mk_resp(content="", reasoning=None)
    )
    client.chat.completions.create.return_value.choices[0].message.tool_calls = [tool_call]
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    out = await p.complete(req)

    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["tools"] == req.tools
    assert out.tool_calls == [{"id": "tc1", "name": "shell_exec", "parameters": {"command": "pwd"}}]


@pytest.mark.asyncio
async def test_openrouter_free_provider_uses_reasoning_details_when_content_empty(monkeypatch):
    p = OpenRouterFreeProvider(api_key="k", model="m/m:free")
    req = LLMRequest(model="ignored", messages=[{"role": "user", "content": "hi"}])

    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_mk_resp(
        content=None,
        reasoning=None,
        reasoning_details=[SimpleNamespace(text="OK")],
    ))
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    async def _fake_get_free_models(cls):
        return ["m/m:free"]

    monkeypatch.setattr(type(p), "get_free_models", classmethod(_fake_get_free_models))

    out = await p.complete(req)
    assert out.content == "OK"


@pytest.mark.asyncio
async def test_openrouter_free_all_models_fail_returns_error(monkeypatch):
    p = OpenRouterFreeProvider(api_key="k")
    req = LLMRequest(model="ignored", messages=[{"role": "user", "content": "hi"}])

    client = AsyncMock()
    client.chat.completions.create = AsyncMock(side_effect=RuntimeError("all failed"))
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    out = await p.complete(req)
    assert "All" in out.content and "free models failed" in out.content


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


@pytest.mark.asyncio
async def test_openai_provider_uses_max_completion_tokens_for_gpt5_models(monkeypatch):
    p = OpenAIProvider(api_key="k")
    req = LLMRequest(
        model="gpt-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=32,
    )

    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_mk_resp(content="OK"))
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    out = await p.complete(req)

    assert out.content == "OK"
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["max_completion_tokens"] == 256
    assert "max_tokens" not in kwargs
    assert "temperature" not in kwargs


@pytest.mark.asyncio
async def test_openai_provider_uses_max_tokens_for_non_gpt5_models(monkeypatch):
    p = OpenAIProvider(api_key="k")
    req = LLMRequest(
        model="gpt-4o",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=32,
    )

    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_mk_resp(content="OK"))
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    out = await p.complete(req)

    assert out.content == "OK"
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["max_tokens"] == 32
    assert "max_completion_tokens" not in kwargs
    assert kwargs["temperature"] == req.temperature


@pytest.mark.asyncio
async def test_openai_provider_stream_uses_max_completion_tokens_for_gpt5_models(monkeypatch):
    p = OpenAIProvider(api_key="k")
    req = LLMRequest(
        model="gpt-5",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=48,
    )

    async def gen():
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="A"))])
        yield SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="B"))])

    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=gen())
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    chunks = [chunk async for chunk in p.stream(req)]

    assert chunks == ["A", "B"]
    kwargs = client.chat.completions.create.await_args.kwargs
    assert kwargs["max_completion_tokens"] == 256
    assert "max_tokens" not in kwargs
    assert "temperature" not in kwargs


@pytest.mark.asyncio
async def test_cerebras_provider_uses_reasoning_when_content_empty(monkeypatch):
    p = CerebrasProvider(api_key="k")
    req = LLMRequest(model="gpt-oss-120b", messages=[{"role": "user", "content": "hi"}])

    client = AsyncMock()
    client.chat.completions.create = AsyncMock(return_value=_mk_resp(content=None, reasoning="OK"))
    monkeypatch.setattr(p, "_client_or_raise", lambda: client)

    out = await p.complete(req)

    assert out.content == "OK"


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
        ProviderType.GROQ,
        ProviderType.CEREBRAS,
        ProviderType.SILICONFLOW,
        ProviderType.TOGETHER,
        ProviderType.FIREWORKS,
        ProviderType.GOOGLE_AI,
        ProviderType.SAMBANOVA,
        ProviderType.MISTRAL,
        ProviderType.CHUTES,
        ProviderType.NVIDIA_NIM,
        ProviderType.OLLAMA,
    }
    assert set(router._providers.keys()) == expected


@pytest.mark.asyncio
async def test_nvidia_nim_complete_uses_httpx(monkeypatch):
    provider = NVIDIANIMProvider(api_key="k", base_url="https://nim.example/v1")
    req = LLMRequest(
        model="meta/llama-3.3-70b-instruct",
        system="sys",
        messages=[{"role": "user", "content": "hello"}],
    )

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "model": "nim-model",
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }

    captured = {}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Resp()

    monkeypatch.setattr("dharma_swarm.providers.httpx.AsyncClient", lambda timeout: _Client())
    out = await provider.complete(req)
    assert out.content == "ok"
    assert out.model == "nim-model"
    assert captured["url"].endswith("/chat/completions")
    assert captured["json"]["messages"][0]["role"] == "system"


@pytest.mark.asyncio
async def test_nvidia_nim_error_status_raises(monkeypatch):
    provider = NVIDIANIMProvider(api_key="k", base_url="https://nim.example/v1")
    req = LLMRequest(model="x", messages=[{"role": "user", "content": "hello"}])

    class _Resp:
        status_code = 500
        text = "boom"

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json, headers):
            return _Resp()

    monkeypatch.setattr("dharma_swarm.providers.httpx.AsyncClient", lambda timeout: _Client())
    with pytest.raises(RuntimeError, match="NVIDIA NIM error 500"):
        await provider.complete(req)


@pytest.mark.asyncio
async def test_ollama_complete_uses_chat_api(monkeypatch):
    provider = OllamaProvider(base_url="http://ollama.local", model="llama3.2")
    req = LLMRequest(
        model="llama3.2",
        system="sys",
        messages=[{"role": "user", "content": "hello"}],
    )
    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "message": {"content": "hi there"},
                "prompt_eval_count": 3,
                "eval_count": 4,
                "done_reason": "stop",
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            captured["url"] = url
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr("dharma_swarm.providers.httpx.AsyncClient", lambda timeout: _Client())
    out = await provider.complete(req)
    assert out.content == "hi there"
    assert out.usage["total_tokens"] == 7
    assert captured["url"].endswith("/api/chat")
    assert captured["json"]["messages"][0]["role"] == "system"


@pytest.mark.asyncio
async def test_ollama_cloud_complete_uses_auth_headers(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-cloud-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    provider = OllamaProvider()
    req = LLMRequest(
        model="kimi-k2.5:cloud",
        messages=[{"role": "user", "content": "hello"}],
    )
    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            # Cloud path uses OpenAI-compatible format
            return {
                "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                "model": "kimi-k2.5:cloud",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class _Client:
        async def post(self, url, json, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Resp()

    monkeypatch.setattr(provider, "_get_client", lambda: _Client())
    out = await provider.complete(req)
    assert out.content == "OK"
    assert provider.base_url == "https://ollama.com"
    assert provider.transport_mode == "cloud_api"
    assert captured["url"] == "https://ollama.com/v1/chat/completions"
    assert "Authorization" in captured["headers"]
    assert captured["headers"]["Authorization"] == "Bearer ollama-cloud-key"


@pytest.mark.asyncio
async def test_ollama_cloud_glm5_applies_completion_token_floor(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-cloud-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    provider = OllamaProvider()
    req = LLMRequest(
        model="glm-5:cloud",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=16,
    )
    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                "model": "glm-5:cloud",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class _Client:
        async def post(self, url, json, headers=None):
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return _Resp()

    monkeypatch.setattr(provider, "_get_client", lambda: _Client())
    out = await provider.complete(req)
    assert out.content == "OK"
    assert captured["json"]["model"] == "glm-5"
    assert captured["json"]["max_tokens"] >= 384


@pytest.mark.asyncio
async def test_ollama_cloud_kimi_strips_cloud_suffix_and_applies_token_floor(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-cloud-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    provider = OllamaProvider()
    req = LLMRequest(
        model="kimi-k2.5:cloud",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=16,
    )
    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                "model": "kimi-k2.5",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class _Client:
        async def post(self, url, json, headers=None):
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr(provider, "_get_client", lambda: _Client())
    out = await provider.complete(req)
    assert out.content == "OK"
    assert captured["json"]["model"] == "kimi-k2.5"
    assert captured["json"]["max_tokens"] >= 256


@pytest.mark.asyncio
async def test_ollama_cloud_minimax_strips_cloud_suffix_and_applies_token_floor(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-cloud-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    provider = OllamaProvider()
    req = LLMRequest(
        model="minimax-m2.7:cloud",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=16,
    )
    captured = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": "OK"}, "finish_reason": "stop"}],
                "model": "minimax-m2.7",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class _Client:
        async def post(self, url, json, headers=None):
            captured["json"] = json
            return _Resp()

    monkeypatch.setattr(provider, "_get_client", lambda: _Client())
    out = await provider.complete(req)
    assert out.content == "OK"
    assert captured["json"]["model"] == "minimax-m2.7"
    assert captured["json"]["max_tokens"] >= 256


@pytest.mark.asyncio
async def test_ollama_cloud_falls_through_frontier_chain_on_error(monkeypatch):
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-cloud-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
    provider = OllamaProvider()
    req = LLMRequest(
        model="glm-5:cloud",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=32,
    )
    attempts: list[str] = []

    class _RespFail:
        status_code = 500
        text = "glm unavailable"

        @staticmethod
        def json():
            return {}

    class _RespOk:
        status_code = 200

        @staticmethod
        def json():
            return {
                "choices": [{"message": {"content": "fallback ok"}, "finish_reason": "stop"}],
                "model": "deepseek-v3.2",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class _Client:
        async def post(self, url, json, headers=None):
            attempts.append(json["model"])
            if len(attempts) == 1:
                return _RespFail()
            return _RespOk()

    monkeypatch.setattr(provider, "_get_client", lambda: _Client())

    out = await provider.complete(req)

    assert out.content == "fallback ok"
    assert out.model == "deepseek-v3.2"
    assert attempts[:2] == ["glm-5", "deepseek-v3.2"]


@pytest.mark.asyncio
async def test_ollama_complete_falls_back_to_generate(monkeypatch):
    provider = OllamaProvider(base_url="http://ollama.local", model="llama3.2")
    req = LLMRequest(
        model="llama3.2",
        messages=[{"role": "user", "content": "hello"}],
    )
    calls = {"n": 0}

    class _Resp404:
        status_code = 404
        text = "not found"

        @staticmethod
        def json():
            return {}

    class _Resp200:
        status_code = 200

        @staticmethod
        def json():
            return {
                "response": "legacy path",
                "prompt_eval_count": 2,
                "eval_count": 2,
            }

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, json):
            calls["n"] += 1
            if calls["n"] == 1:
                assert url.endswith("/api/chat")
                return _Resp404()
            assert url.endswith("/api/generate")
            return _Resp200()

    monkeypatch.setattr("dharma_swarm.providers.httpx.AsyncClient", lambda timeout: _Client())
    out = await provider.complete(req)
    assert out.content == "legacy path"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_ollama_stream_yields_chunks(monkeypatch):
    provider = OllamaProvider(base_url="http://ollama.local", model="llama3.2")
    req = LLMRequest(model="llama3.2", messages=[{"role": "user", "content": "hello"}])

    class _StreamResp:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def aiter_lines(self):
            yield '{"message":{"content":"A"}}'
            yield '{"message":{"content":"B"}}'
            yield '{"done":true}'

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, json):
            assert method == "POST"
            assert url.endswith("/api/chat")
            return _StreamResp()

    monkeypatch.setattr("dharma_swarm.providers.httpx.AsyncClient", lambda timeout: _Client())
    chunks = [chunk async for chunk in provider.stream(req)]
    assert chunks == ["A", "B"]
