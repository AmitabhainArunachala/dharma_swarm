"""Tests for async safety — graceful shutdown & cleanup (Phase 4).

Verifies that orchestrator.graceful_stop() cancels in-flight tasks,
SwarmManager supports async context manager, and shutdown is ordered.
"""

from __future__ import annotations

import asyncio

import pytest

from dharma_swarm.orchestrator import Orchestrator


@pytest.mark.asyncio
async def test_orchestrator_graceful_stop_empty() -> None:
    """graceful_stop on an idle orchestrator returns zeros."""
    orch = Orchestrator()
    result = await orch.graceful_stop(timeout=1.0)
    assert result == {"cancelled": 0, "completed": 0}
    assert orch._running is False


@pytest.mark.asyncio
async def test_orchestrator_graceful_stop_cancels_tasks() -> None:
    """graceful_stop cancels pending asyncio.Tasks."""
    orch = Orchestrator()

    async def slow_work() -> str:
        await asyncio.sleep(999)
        return "done"

    # Simulate a running task
    atask = asyncio.create_task(slow_work())
    orch._running_tasks["fake-task-id"] = atask

    result = await orch.graceful_stop(timeout=2.0)
    assert result["cancelled"] == 1
    assert len(orch._running_tasks) == 0
    assert len(orch._active_dispatches) == 0


@pytest.mark.asyncio
async def test_orchestrator_graceful_stop_already_done() -> None:
    """Tasks that finished before stop are counted as completed."""
    orch = Orchestrator()

    async def instant() -> str:
        return "ok"

    atask = asyncio.create_task(instant())
    await atask  # let it finish
    orch._running_tasks["done-task"] = atask

    result = await orch.graceful_stop(timeout=1.0)
    assert result["completed"] == 1


@pytest.mark.asyncio
async def test_orchestrator_context_manager() -> None:
    """Orchestrator supports async with."""
    async with Orchestrator() as orch:
        assert isinstance(orch, Orchestrator)
    assert orch._running is False


@pytest.mark.asyncio
async def test_swarm_manager_has_context_manager() -> None:
    """SwarmManager has __aenter__ and __aexit__."""
    from dharma_swarm.swarm import SwarmManager
    assert hasattr(SwarmManager, "__aenter__")
    assert hasattr(SwarmManager, "__aexit__")


@pytest.mark.asyncio
async def test_swarm_shutdown_clears_initialized() -> None:
    """shutdown() clears the _initialized tracking set."""
    from dharma_swarm.swarm import SwarmManager
    sm = SwarmManager(state_dir="/tmp/test_swarm_shutdown")
    sm._initialized.add("test_subsystem")
    await sm.shutdown(drain_timeout=1.0)
    assert len(sm._initialized) == 0
    assert sm._running is False
