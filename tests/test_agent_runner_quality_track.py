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
    monkeypatch.setattr(
        "dharma_swarm.context.read_memory_context",
        lambda **_: "",
        raising=True,
    )
    req = ar._build_prompt(task, cfg)
    assert req.system == "SYS"
    assert "## Task: Title" in req.messages[0]["content"]
    assert "Desc" in req.messages[0]["content"]


def test_build_prompt_appends_memory_recall(monkeypatch):
    cfg = AgentConfig(name="a", role=AgentRole.CODER)
    task = Task(title="Title", description="Desc")
    monkeypatch.setattr(ar, "_build_system_prompt", lambda _cfg: "SYS")
    monkeypatch.setattr(
        "dharma_swarm.context.read_memory_context",
        lambda **_: "  [retrieval:note] prior memory",
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.context.read_latent_gold_context",
        lambda **_: "",
        raising=True,
    )

    req = ar._build_prompt(task, cfg)

    assert "## Memory Recall" in req.messages[0]["content"]
    assert "prior memory" in req.messages[0]["content"]


def test_build_prompt_appends_latent_gold(monkeypatch):
    cfg = AgentConfig(name="a", role=AgentRole.CODER)
    task = Task(title="Title", description="Desc")
    monkeypatch.setattr(ar, "_build_system_prompt", lambda _cfg: "SYS")
    monkeypatch.setattr(
        "dharma_swarm.context.read_memory_context",
        lambda **_: "",
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.context.read_latent_gold_context",
        lambda **_: "  [idea:orphaned] proposal | latent branch",
        raising=True,
    )

    req = ar._build_prompt(task, cfg)

    assert "## Latent Gold" in req.messages[0]["content"]
    assert "latent branch" in req.messages[0]["content"]


@pytest.mark.asyncio
async def test_run_task_records_retrieval_success_outcome(monkeypatch, fast_gate):
    cfg = AgentConfig(name="a", role=AgentRole.CODER)
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="done", model="m"))
    monkeypatch.setattr(
        "dharma_swarm.context.read_memory_context",
        lambda **_: "  [retrieval:note] prior memory",
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.context.read_latent_gold_context",
        lambda **_: "",
        raising=True,
    )
    calls: list[tuple[str, str, str | None]] = []
    conversation_calls: list[tuple[str, str]] = []

    class _FakeStore:
        def record_citation_uptake(self, task_id, *, text, consumer=None):
            calls.append((task_id, f"uptake:{text}", consumer))
            return 1

        def record_outcome(self, task_id, *, outcome, consumer=None):
            calls.append((task_id, outcome, consumer))
            return 1

    class _FakeConversationStore:
        def record_turn(self, **kwargs):
            conversation_calls.append((kwargs["role"], kwargs["content"]))
            return "turn-x"

        def record_uptake_from_text(self, **kwargs):
            conversation_calls.append(("uptake", kwargs["text"]))
            return 1

        def record_follow_up_outcome(self, **kwargs):
            conversation_calls.append(("follow_up", kwargs["outcome"]))
            return True

        def mark_task_outcome(self, task_id, *, outcome):
            conversation_calls.append(("outcome", outcome))
            return 1

    monkeypatch.setattr(
        "dharma_swarm.engine.retrieval_feedback.RetrievalFeedbackStore",
        lambda *args, **kwargs: _FakeStore(),
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.engine.conversation_memory.ConversationMemoryStore",
        lambda *args, **kwargs: _FakeConversationStore(),
        raising=True,
    )

    runner = ar.AgentRunner(cfg, provider=provider)
    await runner.start()
    await runner.run_task(
        Task(
            id="task-1",
            title="Title",
            description="Desc",
            metadata={
                "latent_gold_shard_id": "shd-1",
                "memory_plane_db": "/tmp/test-memory-plane.db",
            },
        )
    )

    assert calls == [
        ("task-1", "uptake:done", "agent_runner.prompt"),
        ("task-1", "success", "agent_runner.prompt"),
    ]
    assert conversation_calls[0][0] == "user"
    assert conversation_calls[1][0] == "assistant"
    assert conversation_calls[2][0] == "uptake"
    assert conversation_calls[3] == ("follow_up", "success")
    assert conversation_calls[4] == ("outcome", "success")


@pytest.mark.asyncio
async def test_run_task_records_retrieval_failure_outcome(monkeypatch, fast_gate):
    cfg = AgentConfig(name="a", role=AgentRole.CODER)
    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="", model="m"))
    monkeypatch.setattr(
        "dharma_swarm.context.read_memory_context",
        lambda **_: "  [retrieval:note] prior memory",
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.context.read_latent_gold_context",
        lambda **_: "",
        raising=True,
    )
    calls: list[tuple[str, str, str | None]] = []
    conversation_calls: list[tuple[str, str]] = []

    class _FakeStore:
        def record_citation_uptake(self, task_id, *, text, consumer=None):
            calls.append((task_id, f"uptake:{text}", consumer))
            return 1

        def record_outcome(self, task_id, *, outcome, consumer=None):
            calls.append((task_id, outcome, consumer))
            return 1

    class _FakeConversationStore:
        def record_turn(self, **kwargs):
            conversation_calls.append((kwargs["role"], kwargs["content"]))
            return "turn-x"

        def record_uptake_from_text(self, **kwargs):
            conversation_calls.append(("uptake", kwargs["text"]))
            return 1

        def record_follow_up_outcome(self, **kwargs):
            conversation_calls.append(("follow_up", kwargs["outcome"]))
            return True

        def mark_task_outcome(self, task_id, *, outcome):
            conversation_calls.append(("outcome", outcome))
            return 1

    monkeypatch.setattr(
        "dharma_swarm.engine.retrieval_feedback.RetrievalFeedbackStore",
        lambda *args, **kwargs: _FakeStore(),
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.engine.conversation_memory.ConversationMemoryStore",
        lambda *args, **kwargs: _FakeConversationStore(),
        raising=True,
    )

    runner = ar.AgentRunner(cfg, provider=provider)
    await runner.start()
    with pytest.raises(RuntimeError):
        await runner.run_task(
            Task(
                id="task-2",
                title="Title",
                description="Desc",
                metadata={
                    "latent_gold_shard_id": "shd-2",
                    "memory_plane_db": "/tmp/test-memory-plane.db",
                },
            )
        )

    assert calls == [("task-2", "failure", "agent_runner.prompt")]
    assert conversation_calls[0][0] == "user"
    assert conversation_calls[1][0] == "assistant_error"
    assert conversation_calls[2] == ("follow_up", "failure")
    assert conversation_calls[3] == ("outcome", "failure")


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
async def test_run_task_provider_success_increments_counters(fast_gate):
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
async def test_run_task_calls_leave_mark_on_success(monkeypatch, fast_gate):
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
async def test_run_task_calls_leave_mark_on_failure(monkeypatch, fast_gate):
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
async def test_run_task_provider_empty_content_is_failure(fast_gate):
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
