"""Additional quality-track tests for dharma_swarm.agent_runner."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock
import pytest

import dharma_swarm.agent_runner as ar
from dharma_swarm.models import (
    AgentConfig,
    AgentRole,
    AgentStatus,
    LLMResponse,
    ProviderType,
    Task,
    TaskPriority,
)


def test_build_system_prompt_non_claude_explicit_is_final(monkeypatch):
    cfg = AgentConfig(
        name="a",
        role=AgentRole.CODER,
        provider=ProviderType.OPENAI,
        system_prompt="EXPLICIT",
    )
    monkeypatch.setattr(
        "dharma_swarm.context.build_agent_context",
        lambda **_: "CTX-IGNORED",
        raising=True,
    )
    assert ar._build_system_prompt(cfg) == "EXPLICIT"


def test_build_system_prompt_claude_explicit_appends_context(monkeypatch):
    cfg = AgentConfig(
        name="a",
        role=AgentRole.ARCHITECT,
        provider=ProviderType.CLAUDE_CODE,
        system_prompt="BASE",
        thread="mechanistic",
    )
    monkeypatch.setattr(
        "dharma_swarm.context.build_agent_context",
        lambda **_: "CTX",
        raising=True,
    )
    out = ar._build_system_prompt(cfg)
    assert "BASE" in out
    assert "CTX" in out
    assert "SHAKTI PERCEPTION" in out


def test_build_system_prompt_claude_without_explicit_uses_v7_and_role(monkeypatch):
    cfg = AgentConfig(
        name="a",
        role=AgentRole.SURGEON,
        provider=ProviderType.CLAUDE_CODE,
        system_prompt="",
    )
    monkeypatch.setattr(
        "dharma_swarm.context.build_agent_context",
        lambda **_: "CTX",
        raising=True,
    )
    out = ar._build_system_prompt(cfg)
    assert "seven non-negotiable rules" in out
    assert "CTX" in out
    assert "SHAKTI PERCEPTION" in out


def test_build_prompt_formats_title_and_description(monkeypatch):
    cfg = AgentConfig(name="a", role=AgentRole.CODER)
    task = Task(title="Title", description="Desc")
    monkeypatch.setattr(ar, "_build_system_prompt", lambda _cfg: "SYS")
    req = ar._build_prompt(task, cfg)
    assert req.system == "SYS"
    assert "## Task: Title" in req.messages[0]["content"]
    assert "Desc" in req.messages[0]["content"]


def test_looks_like_provider_failure_prefixes_and_empty():
    assert ar._looks_like_provider_failure("") is True
    assert ar._looks_like_provider_failure("ERROR: bad") is True
    assert ar._looks_like_provider_failure("api error: bad") is True
    assert ar._looks_like_provider_failure("not logged in · please run /login") is True
    assert ar._looks_like_provider_failure("all good") is False


def test_task_file_path_prefers_metadata_and_falls_back():
    t_with_path = Task(
        title="t",
        metadata={"file_path": "dharma_swarm/pulse.py"},
    )
    assert ar._task_file_path(t_with_path) == "dharma_swarm/pulse.py"

    t_fallback = Task(title="x")
    assert ar._task_file_path(t_fallback).startswith("task:")


@pytest.mark.asyncio
async def test_leave_task_mark_best_effort(monkeypatch):
    captured = {}

    class _FakeStore:
        async def leave_mark(self, mark):
            captured["mark"] = mark
            return "id"

    monkeypatch.setattr("dharma_swarm.stigmergy.StigmergyStore", _FakeStore, raising=True)

    task = Task(
        title="Write patch",
        priority=TaskPriority.HIGH,
        metadata={"path": "x.py", "modified": True},
    )
    await ar._leave_task_mark(
        agent_name="agent-x",
        task=task,
        result_text="done",
        success=True,
    )
    mark = captured["mark"]
    assert mark.agent == "agent-x"
    assert mark.file_path == "x.py"
    assert mark.action == "write"
    assert mark.salience >= 0.7


@pytest.mark.asyncio
async def test_run_task_provider_success_increments_counters():
    cfg = AgentConfig(name="ok-agent", role=AgentRole.CODER)
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="done", model="m"))

    runner = ar.AgentRunner(cfg, provider=provider)
    await runner.start()
    out = await runner.run_task(Task(title="t"))

    assert out == "done"
    assert runner.state.tasks_completed == 1
    assert runner.state.turns_used == 1
    assert runner.state.status == AgentStatus.IDLE


@pytest.mark.asyncio
async def test_run_task_calls_leave_mark_on_success(monkeypatch):
    cfg = AgentConfig(name="mark-agent", role=AgentRole.CODER)
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="ok", model="m"))
    leave = AsyncMock()
    monkeypatch.setattr(ar, "_leave_task_mark", leave)

    runner = ar.AgentRunner(cfg, provider=provider)
    await runner.start()
    await runner.run_task(Task(title="t"))

    assert leave.await_count == 1
    assert leave.await_args.kwargs["success"] is True


@pytest.mark.asyncio
async def test_run_task_calls_leave_mark_on_failure(monkeypatch):
    cfg = AgentConfig(name="mark-agent", role=AgentRole.CODER)
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="", model="m"))
    leave = AsyncMock()
    monkeypatch.setattr(ar, "_leave_task_mark", leave)

    runner = ar.AgentRunner(cfg, provider=provider)
    await runner.start()
    with pytest.raises(RuntimeError):
        await runner.run_task(Task(title="t"))

    assert leave.await_count == 1
    assert leave.await_args.kwargs["success"] is False


@pytest.mark.asyncio
async def test_run_task_provider_empty_content_is_failure():
    cfg = AgentConfig(name="bad-agent", role=AgentRole.CODER)
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="", model="m"))

    runner = ar.AgentRunner(cfg, provider=provider)
    await runner.start()
    with pytest.raises(RuntimeError):
        await runner.run_task(Task(title="t"))
    assert runner.state.tasks_completed == 0
    assert runner.state.error


@pytest.mark.asyncio
async def test_health_check_false_before_start():
    runner = ar.AgentRunner(AgentConfig(name="h", role=AgentRole.GENERAL))
    assert await runner.health_check() is False


@pytest.mark.asyncio
async def test_health_check_false_when_heartbeat_stale():
    runner = ar.AgentRunner(AgentConfig(name="h", role=AgentRole.GENERAL))
    await runner.start()
    async with runner._lock:
        runner._state.last_heartbeat = ar._utc_now() - timedelta(minutes=5)
    assert await runner.health_check() is False


@pytest.mark.asyncio
async def test_pool_assign_release_and_get_idle_agents():
    pool = ar.AgentPool()
    cfg = AgentConfig(name="worker", role=AgentRole.GENERAL)
    runner = await pool.spawn(cfg)

    await pool.assign(cfg.id, "task-1")
    assert runner.state.current_task == "task-1"

    await pool.release(cfg.id)
    assert runner.state.current_task is None
    assert runner.state.status == AgentStatus.IDLE

    idle_states = await pool.get_idle_agents()
    assert len(idle_states) == 1
    assert idle_states[0].id == cfg.id


@pytest.mark.asyncio
async def test_pool_get_result_contract_returns_none():
    pool = ar.AgentPool()
    cfg = AgentConfig(name="r", role=AgentRole.GENERAL)
    await pool.spawn(cfg)
    assert await pool.get_result(cfg.id) is None


@pytest.mark.asyncio
async def test_pool_spawn_passes_provider_and_sandbox_references():
    provider = AsyncMock()
    sandbox = AsyncMock()
    cfg = AgentConfig(name="p", role=AgentRole.CODER)
    pool = ar.AgentPool()

    runner = await pool.spawn(cfg, provider=provider, sandbox=sandbox)
    assert runner._provider is provider
    assert runner._sandbox is sandbox
