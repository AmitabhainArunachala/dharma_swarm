"""Tests for dharma_swarm.swarm — integration tests."""

import asyncio

import pytest

from dharma_swarm.engine.conversation_memory import ConversationMemoryStore
from dharma_swarm.models import AgentRole, TaskPriority, TaskStatus
from dharma_swarm.swarm import SwarmManager


# startup_crew auto-spawns 7 agents (3 claude_code + 1 codex + 3 free) and 5 seed tasks on init
_AUTO_AGENTS = 7
_AUTO_TASKS = 5


@pytest.fixture
async def swarm(tmp_path):
    s = SwarmManager(state_dir=tmp_path / ".dharma")
    await s.init()
    yield s
    await s.shutdown()


@pytest.mark.asyncio
async def test_init(swarm):
    state = await swarm.status()
    assert state.tasks_pending == _AUTO_TASKS
    assert len(state.agents) == _AUTO_AGENTS


@pytest.mark.asyncio
async def test_spawn_agent(swarm):
    agent = await swarm.spawn_agent("worker-1", role=AgentRole.CODER)
    assert agent.name == "worker-1"
    assert agent.role == AgentRole.CODER

    agents = await swarm.list_agents()
    assert len(agents) == _AUTO_AGENTS + 1


@pytest.mark.asyncio
async def test_create_task(swarm):
    task = await swarm.create_task("Build module", priority=TaskPriority.HIGH)
    assert task.title == "Build module"
    assert task.priority == TaskPriority.HIGH
    assert task.metadata.get("trace_id", "").startswith("trc_")
    assert task.metadata.get("created_via") == "swarm.create_task"


@pytest.mark.asyncio
async def test_create_task_blocked(swarm):
    with pytest.raises(ValueError, match="Telos gate blocked"):
        await swarm.create_task("rm -rf /everything")


@pytest.mark.asyncio
async def test_create_task_blocks_self_referential_heartbeat_task(swarm):
    with pytest.raises(ValueError, match="Self-referential heartbeat task blocked"):
        await swarm.create_task(
            "Parse heartbeat.md",
            description="Create a task about heartbeat.md and summarize heartbeat loops",
            metadata={"source": "heartbeat"},
        )


@pytest.mark.asyncio
async def test_list_tasks(swarm):
    await swarm.create_task("Task 1")
    await swarm.create_task("Task 2")
    tasks = await swarm.list_tasks()
    assert len(tasks) == _AUTO_TASKS + 2


@pytest.mark.asyncio
async def test_get_task(swarm):
    task = await swarm.create_task("Findable")
    found = await swarm.get_task(task.id)
    assert found is not None
    assert found.title == "Findable"


@pytest.mark.asyncio
async def test_memory(swarm):
    await swarm.remember("test memory entry")
    entries = await swarm.recall(limit=5)
    assert len(entries) >= 1


@pytest.mark.asyncio
async def test_spawn_latent_gold_tasks_reopens_orphaned_branches(swarm):
    store = ConversationMemoryStore(swarm.state_dir / "db" / "memory_plane.db")
    store.record_turn(
        session_id="sess-latent",
        task_id="task-source",
        role="user",
        content=(
            "We could build a memory palace index for task recall.\n"
            "Maybe preserve abandoned branches from the conversation."
        ),
        turn_index=1,
    )
    store.mark_task_outcome("task-source", outcome="success")

    created = await swarm.spawn_latent_gold_tasks(
        limit=2,
        max_pending=100,
        min_salience=0.0,
    )

    assert created
    assert created[0].metadata["latent_gold_reopened"] is True
    assert created[0].metadata["latent_gold_shard_id"].startswith("shd_")

    second = await swarm.spawn_latent_gold_tasks(
        limit=2,
        max_pending=100,
        min_salience=0.0,
    )
    assert second == []


@pytest.mark.asyncio
async def test_run_dispatches_pending_work_even_when_generation_rate_limited(
    swarm,
    monkeypatch,
):
    calls = {"spawn": 0, "tick": 0}

    async def fake_spawn(*args, **kwargs):
        calls["spawn"] += 1
        return []

    async def fake_tick():
        calls["tick"] += 1
        swarm._running = False
        return {"dispatched": 1, "settled": 0, "recovered": 0}

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(swarm, "spawn_latent_gold_tasks", fake_spawn)
    monkeypatch.setattr(swarm, "_contribution_allowed", lambda: False)
    monkeypatch.setattr(swarm, "_in_quiet_hours", lambda: True)
    monkeypatch.setattr(swarm._orchestrator, "tick", fake_tick)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    swarm._running = True
    await swarm.run(interval=0.0)

    assert calls["spawn"] == 0
    assert calls["tick"] == 1
    assert swarm._daily_contributions == 1


@pytest.mark.asyncio
async def test_run_does_not_consume_contribution_budget_without_work(
    swarm,
    monkeypatch,
):
    calls = {"spawn": 0, "tick": 0}

    async def fake_spawn(*args, **kwargs):
        calls["spawn"] += 1
        return []

    async def fake_tick():
        calls["tick"] += 1
        swarm._running = False
        return {"dispatched": 0, "settled": 0, "recovered": 0}

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(swarm, "spawn_latent_gold_tasks", fake_spawn)
    monkeypatch.setattr(swarm, "_contribution_allowed", lambda: True)
    monkeypatch.setattr(swarm, "_in_quiet_hours", lambda: False)
    monkeypatch.setattr(swarm._orchestrator, "tick", fake_tick)
    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    swarm._running = True
    swarm._daily_contributions = 0
    swarm._last_contribution = None
    await swarm.run(interval=0.0)

    assert calls["spawn"] == 1
    assert calls["tick"] == 1
    assert swarm._daily_contributions == 0
    assert swarm._last_contribution is None


@pytest.mark.asyncio
async def test_status(swarm):
    await swarm.spawn_agent("a1")
    await swarm.create_task("t1")
    state = await swarm.status()
    assert len(state.agents) == _AUTO_AGENTS + 1
    assert state.tasks_pending == _AUTO_TASKS + 1
    assert state.uptime_seconds > 0


# --- Gödel Claw v0.3.0 tests ---


@pytest.mark.asyncio
async def test_dharma_status(swarm):
    """dharma_status returns subsystem state."""
    status = await swarm.dharma_status()
    assert status["kernel"] is True
    assert status["kernel_axioms"] == 10
    assert status["kernel_integrity"] is True
    assert status["corpus"] is True
    assert status["compiler"] is True
    assert status["canary"] is True


@pytest.mark.asyncio
async def test_propose_claim(swarm):
    """propose_claim creates a claim with DC-ID."""
    result = await swarm.propose_claim("Test safety claim", category="safety")
    assert result["id"].startswith("DC-")
    assert result["status"] == "proposed"


@pytest.mark.asyncio
async def test_review_claim(swarm):
    """review_claim adds a review record."""
    claim = await swarm.propose_claim("Review test claim", category="operational")
    result = await swarm.review_claim(
        claim["id"], reviewer="test", action="review", comment="looks good"
    )
    assert result["status"] == "under_review"
    assert result["reviews"] == 1


@pytest.mark.asyncio
async def test_promote_claim(swarm):
    """promote_claim changes status to accepted."""
    claim = await swarm.propose_claim("Promote test", category="ethics")
    result = await swarm.promote_claim(claim["id"])
    assert result["status"] == "accepted"


@pytest.mark.asyncio
async def test_compile_policy(swarm):
    """compile_policy produces rules from kernel."""
    result = await swarm.compile_policy(context="test")
    assert result["immutable"] == 10  # kernel axioms
    assert result["context"] == "test"


@pytest.mark.asyncio
async def test_compile_policy_with_claims(swarm):
    """compile_policy includes accepted claims."""
    claim = await swarm.propose_claim(
        "Policy test claim", category="safety", confidence=0.8
    )
    await swarm.promote_claim(claim["id"])
    result = await swarm.compile_policy()
    assert result["mutable"] >= 1


@pytest.mark.asyncio
async def test_kernel_integrity_on_init(swarm):
    """Kernel should be valid after init."""
    status = await swarm.dharma_status()
    assert status["kernel_integrity"] is True


@pytest.mark.asyncio
async def test_corpus_claims_count(swarm):
    """Corpus claim count tracks proposals."""
    s1 = await swarm.dharma_status()
    initial = s1.get("corpus_claims", 0)
    await swarm.propose_claim("Counting test", category="operational")
    s2 = await swarm.dharma_status()
    assert s2["corpus_claims"] == initial + 1
