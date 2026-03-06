"""Tests for engine.provider_runner."""

from __future__ import annotations

import pytest

from dharma_swarm.engine.adapters.base import CompletionRequest, ModelProfile, ProviderAdapter
from dharma_swarm.engine.events import CanonicalEvent, EventType
from dharma_swarm.engine.provider_runner import ProviderRunner


class _GoodAdapter(ProviderAdapter):
    @property
    def name(self) -> str:
        return "good"

    def available_models(self) -> list[ModelProfile]:
        return [ModelProfile(model_id="good")]

    async def stream(self, request: CompletionRequest):
        yield CanonicalEvent(
            event_type=EventType.TASK_ASSIGNED,
            source_agent="director",
            target_agent="good",
            session_id=request.session_id,
        )
        yield CanonicalEvent(
            event_type=EventType.TASK_COMPLETED,
            source_agent="good",
            session_id=request.session_id,
            payload={"text": "done"},
        )


class _BadAdapter(ProviderAdapter):
    @property
    def name(self) -> str:
        return "bad"

    def available_models(self) -> list[ModelProfile]:
        return [ModelProfile(model_id="bad")]

    async def stream(self, request: CompletionRequest):
        raise RuntimeError("adapter boom")
        yield  # pragma: no cover


@pytest.mark.asyncio
async def test_provider_runner_collects_events():
    runner = ProviderRunner(_GoodAdapter())
    result = await runner.run(CompletionRequest(prompt="go", session_id="sess-a"))

    assert result.ok is True
    assert len(result.events) == 2
    assert result.events[0].event_type == EventType.TASK_ASSIGNED
    assert result.events[1].event_type == EventType.TASK_COMPLETED


@pytest.mark.asyncio
async def test_provider_runner_normalizes_adapter_exception():
    runner = ProviderRunner(_BadAdapter())
    result = await runner.run(CompletionRequest(prompt="go", session_id="sess-b"))

    assert result.ok is False
    assert len(result.events) == 1
    event = result.events[0]
    assert event.event_type == EventType.TASK_FAILED
    assert event.source_agent == "bad"
    assert "adapter boom" in event.payload["error"]
