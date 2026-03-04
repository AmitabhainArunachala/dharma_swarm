"""Tests for dharma_swarm.swarm — integration tests."""

import pytest

from dharma_swarm.models import AgentRole, TaskPriority, TaskStatus
from dharma_swarm.swarm import SwarmManager


@pytest.fixture
async def swarm(tmp_path):
    s = SwarmManager(state_dir=tmp_path / ".dharma")
    await s.init()
    yield s
    await s.shutdown()


@pytest.mark.asyncio
async def test_init(swarm):
    state = await swarm.status()
    assert state.tasks_pending == 0
    assert len(state.agents) == 0


@pytest.mark.asyncio
async def test_spawn_agent(swarm):
    agent = await swarm.spawn_agent("worker-1", role=AgentRole.CODER)
    assert agent.name == "worker-1"
    assert agent.role == AgentRole.CODER

    agents = await swarm.list_agents()
    assert len(agents) == 1


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
    assert len(tasks) == 2


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
    assert len(state.agents) == 1
    assert state.tasks_pending == 1
    assert state.uptime_seconds > 0
