"""Tests for engine provider adapter base contracts."""

from __future__ import annotations

import pytest

from dharma_swarm.engine.adapters.base import (
    Capability,
    CompletionRequest,
    ModelProfile,
    ProviderAdapter,
)
from dharma_swarm.engine.events import CanonicalEvent, EventType


class _FakeAdapter(ProviderAdapter):
    @property
    def name(self) -> str:
        return "fake"

    def available_models(self) -> list[ModelProfile]:
        return [ModelProfile(model_id="m1", capabilities={Capability.STREAMING, Capability.TOOLS})]

    async def stream(self, request: CompletionRequest):
        yield CanonicalEvent(
            event_type=EventType.TASK_COMPLETED,
            source_agent=self.name,
            session_id=request.session_id,
            payload={"text": "ok"},
        )


def test_supports_capability_true_and_false():
    adapter = _FakeAdapter()
    assert adapter.supports(Capability.STREAMING) is True
    assert adapter.supports(Capability.TOOLS) is True
    assert adapter.supports(Capability.SESSION_RESUME) is False


@pytest.mark.asyncio
async def test_stream_yields_canonical_events():
    adapter = _FakeAdapter()
    req = CompletionRequest(prompt="hello", session_id="s1")
    events = [event async for event in adapter.stream(req)]
    assert len(events) == 1
    assert events[0].event_type == EventType.TASK_COMPLETED
    assert events[0].payload["text"] == "ok"


# ---------------------------------------------------------------------------
# Capability enum
# ---------------------------------------------------------------------------


def test_capability_values():
    assert Capability.STREAMING == "streaming"
    assert Capability.TOOLS == "tools"
    assert Capability.THINKING == "thinking"
    assert Capability.SESSION_RESUME == "session_resume"
    assert Capability.MULTI_LINE_INPUT == "multi_line_input"


def test_capability_from_string():
    assert Capability("streaming") is Capability.STREAMING


# ---------------------------------------------------------------------------
# ModelProfile
# ---------------------------------------------------------------------------


def test_model_profile_defaults():
    mp = ModelProfile(model_id="test-model")
    assert mp.model_id == "test-model"
    assert mp.capabilities == set()
    assert mp.context_window == 0
    assert mp.metadata == {}


def test_model_profile_with_capabilities():
    mp = ModelProfile(
        model_id="claude",
        capabilities={Capability.STREAMING, Capability.TOOLS},
        context_window=200_000,
        metadata={"provider": "anthropic"},
    )
    assert Capability.STREAMING in mp.capabilities
    assert mp.context_window == 200_000
    assert mp.metadata["provider"] == "anthropic"


# ---------------------------------------------------------------------------
# CompletionRequest
# ---------------------------------------------------------------------------


def test_completion_request_defaults():
    req = CompletionRequest(prompt="hello")
    assert req.prompt == "hello"
    assert req.session_id == ""
    assert req.system == ""
    assert req.max_tokens == 4096
    assert req.temperature == 0.7
    assert req.metadata == {}


def test_completion_request_custom():
    req = CompletionRequest(
        prompt="test", session_id="s1", system="sys",
        max_tokens=1024, temperature=0.3, metadata={"k": "v"},
    )
    assert req.session_id == "s1"
    assert req.system == "sys"
    assert req.max_tokens == 1024
    assert req.temperature == 0.3
    assert req.metadata == {"k": "v"}


# ---------------------------------------------------------------------------
# ProviderAdapter.supports with empty capabilities
# ---------------------------------------------------------------------------


class _EmptyAdapter(ProviderAdapter):
    @property
    def name(self) -> str:
        return "empty"

    def available_models(self) -> list[ModelProfile]:
        return [ModelProfile(model_id="bare")]

    async def stream(self, request: CompletionRequest):
        return
        yield  # pragma: no cover


def test_supports_returns_false_for_empty_capabilities():
    adapter = _EmptyAdapter()
    assert adapter.supports(Capability.STREAMING) is False
    assert adapter.supports(Capability.TOOLS) is False
