"""Tests for dharma_swarm.agent_runner."""

import re

import pytest
from unittest.mock import AsyncMock

from dharma_swarm.models import AgentConfig, AgentRole, AgentStatus, Task
from dharma_swarm.agent_runner import AgentPool, AgentRunner


@pytest.fixture
def config():
    return AgentConfig(name="test-agent", role=AgentRole.CODER)


@pytest.mark.asyncio
async def test_runner_start(config):
    runner = AgentRunner(config)
    await runner.start()
    assert runner.state.status == AgentStatus.IDLE
    assert runner.state.started_at is not None


@pytest.mark.asyncio
async def test_runner_mock_task(config):
    runner = AgentRunner(config)
    await runner.start()
    task = Task(title="Write tests")
    result = await runner.run_task(task)
    assert "test-agent" in result
    assert "Write tests" in result
    assert runner.state.status == AgentStatus.IDLE
    assert runner.state.tasks_completed == 1


@pytest.mark.asyncio
async def test_runner_provider_error_string_marks_failure(config):
    from dharma_swarm.models import LLMResponse

    for text in ("ERROR: upstream unavailable", "API Error: Unable to connect to API (ENOTFOUND)"):
        provider = AsyncMock()
        provider.complete = AsyncMock(
            return_value=LLMResponse(content=text, model="test"),
        )

        runner = AgentRunner(config, provider=provider)
        await runner.start()

        with pytest.raises(RuntimeError, match=re.escape(text)):
            await runner.run_task(Task(title="Failing task"))

        assert runner.state.status == AgentStatus.IDLE
        assert runner.state.tasks_completed == 0
        assert text in (runner.state.error or "")


@pytest.mark.asyncio
async def test_runner_blocks_harmful_task_before_provider_call(config):
    from dharma_swarm.models import LLMResponse

    provider = AsyncMock()
    provider.complete = AsyncMock(return_value=LLMResponse(content="ok", model="test"))
    runner = AgentRunner(config, provider=provider)
    await runner.start()

    with pytest.raises(RuntimeError, match="Telos block"):
        await runner.run_task(Task(title="rm -rf /important", description="delete all"))

    provider.complete.assert_not_awaited()
    assert runner.state.status == AgentStatus.IDLE
    assert runner.state.tasks_completed == 0


@pytest.mark.asyncio
async def test_runner_heartbeat(config):
    runner = AgentRunner(config)
    await runner.start()
    await runner.heartbeat()
    assert runner.state.last_heartbeat is not None


@pytest.mark.asyncio
async def test_runner_stop(config):
    runner = AgentRunner(config)
    await runner.start()
    await runner.stop()
    assert runner.state.status == AgentStatus.DEAD


@pytest.mark.asyncio
async def test_runner_health_check(config):
    runner = AgentRunner(config)
    await runner.start()
    assert await runner.health_check()
    await runner.stop()
    assert not await runner.health_check()


@pytest.mark.asyncio
async def test_pool_spawn():
    pool = AgentPool()
    config = AgentConfig(name="worker-1", role=AgentRole.GENERAL)
    runner = await pool.spawn(config)
    assert runner.state.status == AgentStatus.IDLE

    agents = await pool.list_agents()
    assert len(agents) == 1
    assert agents[0].name == "worker-1"


@pytest.mark.asyncio
async def test_pool_get_idle():
    pool = AgentPool()
    c1 = AgentConfig(name="idle-1", role=AgentRole.GENERAL)
    c2 = AgentConfig(name="idle-2", role=AgentRole.CODER)
    await pool.spawn(c1)
    await pool.spawn(c2)

    idle = await pool.get_idle()
    assert len(idle) == 2


@pytest.mark.asyncio
async def test_pool_get():
    pool = AgentPool()
    config = AgentConfig(name="findme")
    runner = await pool.spawn(config)
    found = await pool.get(config.id)
    assert found is runner
    assert await pool.get("nonexistent") is None


@pytest.mark.asyncio
async def test_pool_shutdown_all():
    pool = AgentPool()
    for i in range(3):
        await pool.spawn(AgentConfig(name=f"agent-{i}"))

    await pool.shutdown_all()
    agents = await pool.list_agents()
    assert all(a.status == AgentStatus.DEAD for a in agents)


@pytest.mark.asyncio
async def test_pool_remove_dead():
    pool = AgentPool()
    c = AgentConfig(name="doomed")
    runner = await pool.spawn(c)
    await runner.stop()

    await pool.remove_dead()
    agents = await pool.list_agents()
    assert len(agents) == 0
