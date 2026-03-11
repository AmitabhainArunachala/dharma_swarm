from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.thinkodynamic_director import (
    ThinkodynamicDirector,
    WorkflowPlan,
    WorkflowTaskPlan,
    _director_provider_timeout_seconds,
    _vision_via_provider,
)


class _SlowProvider:
    async def complete(self, request):
        await asyncio.sleep(0.2)
        raise AssertionError("wait_for should time out before the provider returns")


class _ErrorStringProvider:
    async def complete(self, request):
        from dharma_swarm.models import LLMResponse

        return LLMResponse(content="ERROR: upstream unavailable", model="fake")


class _SuccessProvider:
    def __init__(self, content: str = "usable result") -> None:
        self._content = content

    async def complete(self, request):
        from dharma_swarm.models import LLMResponse

        return LLMResponse(content=self._content, model="fake")


@pytest.mark.asyncio
async def test_vision_via_provider_times_out_fast(monkeypatch):
    monkeypatch.setattr("dharma_swarm.providers.OpenRouterProvider", _SlowProvider)
    monkeypatch.setattr("dharma_swarm.providers.OpenRouterFreeProvider", _SlowProvider)
    monkeypatch.setattr("dharma_swarm.providers.AnthropicProvider", _SlowProvider)

    start = time.monotonic()
    output, success = await _vision_via_provider("prompt", timeout_seconds=0.09)
    elapsed = time.monotonic() - start

    assert success is False
    assert "timed out" in output
    assert elapsed < 0.4


@pytest.mark.asyncio
async def test_vision_via_provider_ignores_error_string_and_uses_next_provider(monkeypatch):
    monkeypatch.setattr("dharma_swarm.providers.OpenRouterProvider", _ErrorStringProvider)
    monkeypatch.setattr("dharma_swarm.providers.OpenRouterFreeProvider", _SuccessProvider)
    monkeypatch.setattr("dharma_swarm.providers.AnthropicProvider", _SuccessProvider)

    output, success = await _vision_via_provider("prompt", timeout_seconds=0.3)

    assert success is True
    assert output == "usable result"


def test_director_provider_timeout_uses_env_override(monkeypatch):
    monkeypatch.setenv("DGC_THINKODYNAMIC_PROVIDER_TIMEOUT", "1.5")

    assert _director_provider_timeout_seconds(600) == 1.5


@pytest.mark.asyncio
async def test_spawn_agent_passes_bounded_provider_timeout(tmp_path: Path):
    director = ThinkodynamicDirector(
        repo_root=tmp_path,
        state_dir=tmp_path / ".dharma",
        external_roots=(),
    )
    workflow = WorkflowPlan(
        cycle_id="1",
        workflow_id="wf-1",
        opportunity_id="opp-1",
        opportunity_title="Stabilize fallback lane",
        theme="autonomy",
        thesis="Fallback should fail fast.",
        why_now="Nested sessions are real.",
        expected_duration_min=5,
        tasks=[],
    )
    task = WorkflowTaskPlan(
        key="t1",
        title="Probe fallback",
        description="Check provider fallback propagation.",
        priority="high",
        role_hint="general",
        acceptance=["No hang"],
    )

    async def _fake_provider(prompt: str, *, timeout_seconds: float = 0.0):
        return f"timeout={timeout_seconds}", True

    with patch("dharma_swarm.thinkodynamic_director.subprocess.run", side_effect=FileNotFoundError):
        with patch("dharma_swarm.thinkodynamic_director._vision_via_provider", side_effect=_fake_provider):
            result = await director.spawn_agent(task, workflow, timeout=24)

    assert result["success"] is True
    assert result["provider"] == "openrouter-fallback"
    assert result["output"] == "timeout=5.0"
