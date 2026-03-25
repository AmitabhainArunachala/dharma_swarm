from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from dharma_swarm.thinkodynamic_director import (
    ThinkodynamicDirector,
    WorkflowPlan,
    WorkflowTaskPlan,
    _director_provider_timeout_seconds,
    _vision_via_provider,
    invoke_claude_vision,
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
    # Patch at both the source module and the import point to ensure the
    # local `from dharma_swarm.providers import ...` inside the function
    # picks up the mock.
    monkeypatch.setattr("dharma_swarm.providers.OpenRouterProvider", _SlowProvider)
    monkeypatch.setattr("dharma_swarm.providers.OpenRouterFreeProvider", _SlowProvider)
    monkeypatch.setattr("dharma_swarm.providers.AnthropicProvider", _SlowProvider)

    start = time.monotonic()
    output, success = await _vision_via_provider("prompt", timeout_seconds=0.5)
    elapsed = time.monotonic() - start

    assert success is False
    assert "timed out" in output.lower() or "no provider" in output.lower()
    assert elapsed < 3.0


@pytest.mark.asyncio
async def test_vision_via_provider_tries_nim_before_slow_openrouter(monkeypatch):
    class _FakeClock:
        def __init__(self) -> None:
            self.value = 0.0

        def monotonic(self) -> float:
            return self.value

        def advance(self, delta: float) -> None:
            self.value += delta

    clock = _FakeClock()
    calls: list[tuple[str, str | None]] = []

    class _BudgetEatingOpenRouter:
        async def complete(self, request):
            calls.append(("openrouter", request.model))
            clock.advance(10.0)
            raise RuntimeError("synthetic openrouter stall")

    class _NimSuccess:
        async def complete(self, request):
            from dharma_swarm.models import LLMResponse

            calls.append(("nim", request.model))
            return LLMResponse(content="nim result", model="fake")

    monkeypatch.setattr("dharma_swarm.thinkodynamic_director.time.monotonic", clock.monotonic)
    monkeypatch.setattr(
        "dharma_swarm.providers.NVIDIANIMProvider",
        lambda *args, **kwargs: _NimSuccess(),
    )
    monkeypatch.setattr(
        "dharma_swarm.providers.OpenRouterProvider",
        lambda *args, **kwargs: _BudgetEatingOpenRouter(),
    )
    monkeypatch.setattr("dharma_swarm.providers.OpenRouterFreeProvider", _SlowProvider)
    monkeypatch.setattr("dharma_swarm.providers.AnthropicProvider", _SlowProvider)

    output, success = await _vision_via_provider("prompt", timeout_seconds=10.0)

    assert success is True
    assert output == "nim result"
    assert calls[0][0] == "nim"


@pytest.mark.asyncio
async def test_vision_via_provider_ignores_error_string_and_uses_next_provider(monkeypatch):
    monkeypatch.setattr(
        "dharma_swarm.providers.OpenRouterProvider",
        lambda *args, **kwargs: _ErrorStringProvider(),
    )
    monkeypatch.setattr(
        "dharma_swarm.providers.OpenRouterFreeProvider",
        lambda *args, **kwargs: _SuccessProvider(),
    )
    monkeypatch.setattr(
        "dharma_swarm.providers.AnthropicProvider",
        lambda *args, **kwargs: _SuccessProvider(),
    )

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
    # timeout=24 → _director_provider_timeout_seconds(24) = max(10.0, min(120.0, 24/5)) = 10.0
    assert result["output"] == "timeout=10.0"


@pytest.mark.asyncio
async def test_spawn_agent_falls_back_when_claude_cli_returns_nonzero(tmp_path: Path):
    director = ThinkodynamicDirector(
        repo_root=tmp_path,
        state_dir=tmp_path / ".dharma",
        external_roots=(),
    )
    workflow = WorkflowPlan(
        cycle_id="1",
        workflow_id="wf-1",
        opportunity_id="opp-1",
        opportunity_title="Recover from claude CLI failure",
        theme="autonomy",
        thesis="Fallback should engage on empty/nonzero claude results.",
        why_now="CLI quota and nested-session failures happen.",
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

    class _FailedClaudeResult:
        returncode = 1
        stdout = "You're out of extra usage"
        stderr = ""

    async def _fake_provider(prompt: str, *, timeout_seconds: float = 0.0):
        return "provider fallback ok", True

    with patch("dharma_swarm.thinkodynamic_director.subprocess.run", return_value=_FailedClaudeResult()):
        with patch("dharma_swarm.thinkodynamic_director._vision_via_provider", side_effect=_fake_provider):
            result = await director.spawn_agent(task, workflow, timeout=24)

    assert result["success"] is True
    assert result["provider"] == "openrouter-fallback"
    assert result["output"] == "provider fallback ok"


@pytest.mark.asyncio
async def test_spawn_agent_prefers_codex_for_implementation_tasks(tmp_path: Path):
    director = ThinkodynamicDirector(
        repo_root=tmp_path,
        state_dir=tmp_path / ".dharma",
        external_roots=(),
    )
    workflow = WorkflowPlan(
        cycle_id="1",
        workflow_id="wf-1",
        opportunity_id="opp-1",
        opportunity_title="Implement a real coding slice",
        theme="autonomy",
        thesis="Implementation tasks should prefer a tool-backed worker.",
        why_now="This is where execution leverage lives.",
        expected_duration_min=5,
        tasks=[],
    )
    task = WorkflowTaskPlan(
        key="t1",
        title="Implement the worker telemetry",
        description="Write structured logs for each execution wave.",
        priority="high",
        role_hint="surgeon",
        acceptance=["Telemetry exists"],
    )

    def _fake_subprocess(cmd, **kwargs):
        if cmd[0] == "codex":
            output_path = Path(cmd[cmd.index("-o") + 1])
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text("codex completed the slice", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="codex stdout", stderr="")
        raise AssertionError(f"unexpected backend call: {cmd}")

    with patch("dharma_swarm.thinkodynamic_director.subprocess.run", side_effect=_fake_subprocess):
        result = await director.spawn_agent(task, workflow, timeout=24)

    assert result["success"] is True
    assert result["provider"] == "codex-cli"
    assert result["output"] == "codex completed the slice"


@pytest.mark.asyncio
async def test_invoke_claude_vision_falls_back_when_claude_cli_returns_nonzero():
    class _FailedClaudeResult:
        returncode = 1
        stdout = "You're out of extra usage"
        stderr = ""

    async def _fake_provider(prompt: str, *, timeout_seconds: float = 0.0):
        return "vision provider fallback ok", True

    with patch("dharma_swarm.thinkodynamic_director.subprocess.run", return_value=_FailedClaudeResult()):
        with patch("dharma_swarm.thinkodynamic_director._vision_via_provider", side_effect=_fake_provider):
            output, success = await invoke_claude_vision(
                [("seed text", "seed.md")],
                {"health": "ok"},
                "",
                {},
                model="sonnet",
                timeout=24,
            )

    assert success is True
    assert output == "vision provider fallback ok"
