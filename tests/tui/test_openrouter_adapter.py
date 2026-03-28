"""Tests for OpenRouter adapter canonical event flow."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from dharma_swarm.model_hierarchy import DEFAULT_MODELS
from dharma_swarm.models import ProviderType
from dharma_swarm.tui.engine.adapters.base import CompletionRequest, ProviderConfig
from dharma_swarm.tui.engine.adapters.openrouter import OpenRouterAdapter
from dharma_swarm.tui.engine.events import ErrorEvent, SessionEnd, TextComplete, UsageReport


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, headers: dict, json: dict) -> _FakeResponse:
        return self._response


async def _collect_events(adapter: OpenRouterAdapter) -> list[object]:
    request = CompletionRequest(
        messages=[{"role": "user", "content": "hello"}],
        model="openai/gpt-5-codex",
    )
    events: list[object] = []
    async for ev in adapter.stream(request, session_id="sid-1"):
        events.append(ev)
    return events


def test_openrouter_adapter_defaults_to_canonical_runtime_model() -> None:
    adapter = OpenRouterAdapter()
    profile = adapter.get_profile()

    assert profile.model_id == DEFAULT_MODELS[ProviderType.OPENROUTER]


@pytest.mark.asyncio
async def test_openrouter_missing_api_key_emits_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    adapter = OpenRouterAdapter(
        ProviderConfig(provider_id="openrouter", api_key=None)
    )

    events = await _collect_events(adapter)

    assert any(
        isinstance(ev, ErrorEvent) and ev.code == "missing_api_key" for ev in events
    )
    assert any(
        isinstance(ev, SessionEnd) and (not ev.success) for ev in events
    )


@pytest.mark.asyncio
async def test_openrouter_success_emits_text_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeResponse(
        200,
        {
            "choices": [{"message": {"content": "hi from model"}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_cost": 0.02},
        },
    )
    monkeypatch.setattr(
        "dharma_swarm.tui.engine.adapters.openrouter.httpx.AsyncClient",
        lambda timeout: _FakeClient(response),
    )
    adapter = OpenRouterAdapter(
        ProviderConfig(provider_id="openrouter", api_key="test-key")
    )

    events = await _collect_events(adapter)

    assert any(
        isinstance(ev, TextComplete) and ev.content == "hi from model"
        for ev in events
    )
    assert any(
        isinstance(ev, UsageReport) and ev.total_cost_usd == 0.02 for ev in events
    )
    assert any(isinstance(ev, SessionEnd) and ev.success for ev in events)


@pytest.mark.asyncio
async def test_openrouter_success_emits_reasoning_when_content_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _FakeResponse(
        200,
        {
            "choices": [{
                "message": {
                    "content": None,
                    "reasoning": "hi from reasoning",
                }
            }],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_cost": 0.02},
        },
    )
    monkeypatch.setattr(
        "dharma_swarm.tui.engine.adapters.openrouter.httpx.AsyncClient",
        lambda timeout: _FakeClient(response),
    )
    adapter = OpenRouterAdapter(
        ProviderConfig(provider_id="openrouter", api_key="test-key")
    )

    events = await _collect_events(adapter)

    assert any(
        isinstance(ev, TextComplete) and ev.content == "hi from reasoning"
        for ev in events
    )
    assert any(isinstance(ev, SessionEnd) and ev.success for ev in events)


@pytest.mark.asyncio
async def test_openrouter_http_429_marks_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _FakeResponse(
        429,
        {},
        text="rate limit",
    )
    monkeypatch.setattr(
        "dharma_swarm.tui.engine.adapters.openrouter.httpx.AsyncClient",
        lambda timeout: _FakeClient(response),
    )
    adapter = OpenRouterAdapter(
        ProviderConfig(provider_id="openrouter", api_key="test-key")
    )

    events = await _collect_events(adapter)

    err = next((ev for ev in events if isinstance(ev, ErrorEvent)), None)
    assert isinstance(err, ErrorEvent)
    assert err.code == "rate_limited"
    assert err.retryable is True
    assert any(
        isinstance(ev, SessionEnd) and (not ev.success) and ev.error_code == "rate_limited"
        for ev in events
    )
