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
