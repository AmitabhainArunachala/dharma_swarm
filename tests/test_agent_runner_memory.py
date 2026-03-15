"""Tests for agent memory integration in dharma_swarm.agent_runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from dharma_swarm.agent_memory import AgentMemoryBank
from dharma_swarm.agent_runner import AgentPool, AgentRunner
from dharma_swarm.models import (
    AgentConfig,
    AgentRole,
    AgentStatus,
    LLMResponse,
    Task,
    TaskPriority,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config() -> AgentConfig:
    return AgentConfig(name="mem-agent", role=AgentRole.CODER)


@pytest.fixture
def memory(tmp_path: Path) -> AgentMemoryBank:
    return AgentMemoryBank("mem-agent", base_path=tmp_path)


@pytest.fixture
def mock_provider() -> AsyncMock:
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value=LLMResponse(content="task done successfully", model="test"),
    )
    return provider


# ---------------------------------------------------------------------------
# 1. Constructor accepts memory parameter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_accepts_memory_parameter(
    config: AgentConfig, memory: AgentMemoryBank
) -> None:
    runner = AgentRunner(config, memory=memory)
    assert runner._memory is memory


@pytest.mark.asyncio
async def test_runner_memory_defaults_to_none(config: AgentConfig) -> None:
    runner = AgentRunner(config)
    assert runner._memory is None


# ---------------------------------------------------------------------------
# 2. Memory context injected into system prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_context_injected_into_system_prompt(
    config: AgentConfig, memory: AgentMemoryBank, mock_provider: AsyncMock, fast_gate
) -> None:
    await memory.remember("key1", "value1", category="working", importance=0.8)
    runner = AgentRunner(config, provider=mock_provider, memory=memory)
    await runner.start()

    await runner.run_task(Task(title="Test injection"))

    # The provider.complete was called; inspect the request's system field
    call_args = mock_provider.complete.call_args
    request = call_args[0][0]
    assert "Agent Memory" in request.system
    assert "key1" in request.system
    assert "value1" in request.system


# ---------------------------------------------------------------------------
# 3. Successful task stores result in working memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_successful_task_stores_result_in_working_memory(
    config: AgentConfig, memory: AgentMemoryBank, mock_provider: AsyncMock, fast_gate
) -> None:
    runner = AgentRunner(config, provider=mock_provider, memory=memory)
    await runner.start()

    task = Task(title="Build widget", id="task123")
    await runner.run_task(task)

    entry = await memory.recall("task:task123")
    assert entry is not None
    assert "task done successfully" in entry.value
    assert entry.source == "mem-agent"


# ---------------------------------------------------------------------------
# 4. Failed task learns lesson in archival memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_task_learns_lesson(
    config: AgentConfig, memory: AgentMemoryBank, fast_gate
) -> None:
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value=LLMResponse(content="error: something broke", model="test"),
    )
    runner = AgentRunner(config, provider=provider, memory=memory)
    await runner.start()

    with pytest.raises(RuntimeError):
        await runner.run_task(Task(title="Doomed task"))

    # Lesson should be in archival memory
    assert len(memory._archival) >= 1
    lesson_values = [e.value for e in memory._archival.values()]
    assert any("Failed: Doomed task" in v for v in lesson_values)


# ---------------------------------------------------------------------------
# 5. Memory consolidation runs every 5 tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consolidation_runs_every_5_tasks(
    config: AgentConfig, memory: AgentMemoryBank, mock_provider: AsyncMock, fast_gate
) -> None:
    runner = AgentRunner(config, provider=mock_provider, memory=memory)
    await runner.start()

    with patch.object(memory, "consolidate", wraps=memory.consolidate) as spy:
        # Run 5 tasks; consolidation triggers at tasks_completed % 5 == 0
        for i in range(5):
            await runner.run_task(Task(title=f"Task {i}"))

        # tasks_completed hits 5 on the 5th task -> 5 % 5 == 0 -> consolidate
        assert spy.call_count == 1

    # Run 5 more to get a second consolidation at task 10
    with patch.object(memory, "consolidate", wraps=memory.consolidate) as spy2:
        for i in range(5, 10):
            await runner.run_task(Task(title=f"Task {i}"))
        assert spy2.call_count == 1


# ---------------------------------------------------------------------------
# 6. Memory saves after operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_saves_after_successful_task(
    config: AgentConfig, memory: AgentMemoryBank, mock_provider: AsyncMock, fast_gate
) -> None:
    runner = AgentRunner(config, provider=mock_provider, memory=memory)
    await runner.start()

    with patch.object(memory, "save", wraps=memory.save) as spy:
        await runner.run_task(Task(title="Save test"))
        assert spy.call_count >= 1


@pytest.mark.asyncio
async def test_memory_saves_after_failed_task(
    config: AgentConfig, memory: AgentMemoryBank, fast_gate
) -> None:
    provider = AsyncMock()
    provider.complete = AsyncMock(
        return_value=LLMResponse(content="error: boom", model="test"),
    )
    runner = AgentRunner(config, provider=provider, memory=memory)
    await runner.start()

    with patch.object(memory, "save", wraps=memory.save) as spy:
        with pytest.raises(RuntimeError):
            await runner.run_task(Task(title="Fail save test"))
        assert spy.call_count >= 1


# ---------------------------------------------------------------------------
# 7. Backward compatibility: runner works without memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_works_without_memory(config: AgentConfig, fast_gate) -> None:
    runner = AgentRunner(config)
    await runner.start()
    result = await runner.run_task(Task(title="No memory task"))
    assert "No memory task" in result
    assert runner.state.tasks_completed == 1


# ---------------------------------------------------------------------------
# 8. Memory context respects agent name
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_context_includes_agent_name(
    tmp_path: Path, mock_provider: AsyncMock, fast_gate
) -> None:
    agent_name = "cartographer-7"
    config = AgentConfig(name=agent_name, role=AgentRole.CARTOGRAPHER)
    memory = AgentMemoryBank(agent_name, base_path=tmp_path)
    await memory.remember("finding", "vault structure mapped", importance=0.9)

    runner = AgentRunner(config, provider=mock_provider, memory=memory)
    await runner.start()
    await runner.run_task(Task(title="Map vault"))

    request = mock_provider.complete.call_args[0][0]
    assert agent_name in request.system


# ---------------------------------------------------------------------------
# 9. Task priority maps to memory importance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_task_priority_maps_to_importance(
    config: AgentConfig, memory: AgentMemoryBank, mock_provider: AsyncMock, fast_gate
) -> None:
    runner = AgentRunner(config, provider=mock_provider, memory=memory)
    await runner.start()

    # LOW priority -> 0.30 importance
    low_task = Task(title="Low prio", id="low1", priority=TaskPriority.LOW)
    await runner.run_task(low_task)
    entry_low = await memory.recall("task:low1")
    assert entry_low is not None
    assert entry_low.importance == 0.30

    # URGENT priority -> 0.90 importance
    urgent_task = Task(title="Urgent prio", id="urg1", priority=TaskPriority.URGENT)
    await runner.run_task(urgent_task)
    entry_urgent = await memory.recall("task:urg1")
    assert entry_urgent is not None
    assert entry_urgent.importance == 0.90


# ---------------------------------------------------------------------------
# 10. AgentPool.spawn passes memory through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_spawn_passes_memory(
    config: AgentConfig, memory: AgentMemoryBank
) -> None:
    pool = AgentPool()
    runner = await pool.spawn(config, memory=memory)
    assert runner._memory is memory
    assert runner.state.status == AgentStatus.IDLE
