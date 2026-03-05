"""Tests for dharma_swarm.swarm — integration tests."""

import pytest

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


@pytest.mark.asyncio
async def test_create_task_blocked(swarm):
    with pytest.raises(ValueError, match="Telos gate blocked"):
        await swarm.create_task("rm -rf /everything")


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
