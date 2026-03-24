"""Tests for SwarmManager.reap_orphaned_tasks and _propagate_dependency_failures.

Covers:
  - Orphan reaping: tasks assigned to dead agents are requeued
  - Staleness window: recently-touched tasks are skipped
  - Live agents: tasks on living agents are never reaped
  - Metadata enrichment: orphan_reaped_at / orphan_original_agent / orphan_original_status
  - Dependency propagation: permanently-failed chains cascade to pending children
  - Rescue attempts: tasks whose deps still have retries left are NOT propagated
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.models import (
    AgentConfig,
    AgentRole,
    AgentState,
    AgentStatus,
    Task,
    TaskPriority,
    TaskStatus,
)
from dharma_swarm.swarm import SwarmManager
from dharma_swarm.task_board import TaskBoard


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeAgentPool:
    """Minimal AgentPool stand-in that returns a configurable list of agents."""

    def __init__(self, agents: list[AgentState] | None = None) -> None:
        self._agents = agents or []

    async def list_agents(self) -> list[AgentState]:
        return list(self._agents)


def _agent(agent_id: str, name: str = "test-agent") -> AgentState:
    return AgentState(
        id=agent_id,
        name=name,
        role=AgentRole.GENERAL,
        status=AgentStatus.IDLE,
    )


async def _make_board(tmp_path: Path) -> TaskBoard:
    """Create and initialise a fresh TaskBoard in a temp directory."""
    db_path = tmp_path / "tasks.db"
    board = TaskBoard(db_path)
    await board.init_db()
    return board


async def _make_swarm(
    tmp_path: Path,
    board: TaskBoard,
    pool: _FakeAgentPool,
) -> SwarmManager:
    """Build a SwarmManager with only _task_board and _agent_pool wired."""
    sm = SwarmManager(state_dir=tmp_path / ".dharma")
    sm._task_board = board
    sm._agent_pool = pool  # type: ignore[assignment]
    return sm


async def _force_task_state(
    board: TaskBoard,
    task_id: str,
    status: str,
    assigned_to: str | None = None,
    updated_at: datetime | None = None,
    metadata: dict | None = None,
) -> None:
    """Directly set task columns via raw SQL (bypasses FSM for test setup)."""
    async with board._open() as db:
        sets = ["status = ?"]
        params: list = [status]
        if assigned_to is not None:
            sets.append("assigned_to = ?")
            params.append(assigned_to)
        if updated_at is not None:
            sets.append("updated_at = ?")
            params.append(updated_at.isoformat())
        if metadata is not None:
            sets.append("metadata = ?")
            params.append(json.dumps(metadata, ensure_ascii=True))
        params.append(task_id)
        await db.execute(
            f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        await db.commit()


async def _add_dependency(board: TaskBoard, child_id: str, parent_id: str) -> None:
    """Insert a task dependency row."""
    async with board._open() as db:
        await db.execute(
            "INSERT INTO task_dependencies (task_id, depends_on_id) VALUES (?, ?)",
            (child_id, parent_id),
        )
        await db.commit()


# ===================================================================
# reap_orphaned_tasks
# ===================================================================


class TestReapOrphanedTasks:
    """Verify orphan detection and requeue for tasks on dead agents."""

    @pytest.mark.asyncio
    async def test_assigned_task_on_dead_agent_is_reaped(self, tmp_path: Path) -> None:
        board = await _make_board(tmp_path)
        task = await board.create("stale assigned task")
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        await _force_task_state(
            board,
            task.id,
            status=TaskStatus.ASSIGNED.value,
            assigned_to="dead-agent-001",
            updated_at=stale_time,
        )

        pool = _FakeAgentPool([])  # no live agents
        sm = await _make_swarm(tmp_path, board, pool)

        reaped = await sm.reap_orphaned_tasks(stale_minutes=30)

        assert len(reaped) == 1
        assert reaped[0].id == task.id
        assert reaped[0].status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_running_task_on_dead_agent_is_reaped(self, tmp_path: Path) -> None:
        board = await _make_board(tmp_path)
        task = await board.create("stale running task")
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=45)
        await _force_task_state(
            board,
            task.id,
            status=TaskStatus.RUNNING.value,
            assigned_to="dead-agent-002",
            updated_at=stale_time,
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        reaped = await sm.reap_orphaned_tasks(stale_minutes=30)

        assert len(reaped) == 1
        assert reaped[0].id == task.id
        assert reaped[0].status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_task_on_live_agent_is_not_reaped(self, tmp_path: Path) -> None:
        board = await _make_board(tmp_path)
        task = await board.create("task on live agent")
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=120)
        await _force_task_state(
            board,
            task.id,
            status=TaskStatus.ASSIGNED.value,
            assigned_to="live-agent-01",
            updated_at=stale_time,
        )

        pool = _FakeAgentPool([_agent("live-agent-01")])
        sm = await _make_swarm(tmp_path, board, pool)

        reaped = await sm.reap_orphaned_tasks(stale_minutes=30)

        assert len(reaped) == 0
        refreshed = await board.get(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.ASSIGNED

    @pytest.mark.asyncio
    async def test_recently_updated_task_is_not_reaped(self, tmp_path: Path) -> None:
        board = await _make_board(tmp_path)
        task = await board.create("recently touched task")
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        await _force_task_state(
            board,
            task.id,
            status=TaskStatus.RUNNING.value,
            assigned_to="dead-agent-003",
            updated_at=recent_time,
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        reaped = await sm.reap_orphaned_tasks(stale_minutes=30)

        assert len(reaped) == 0
        refreshed = await board.get(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.RUNNING

    @pytest.mark.asyncio
    async def test_metadata_enriched_on_reap(self, tmp_path: Path) -> None:
        board = await _make_board(tmp_path)
        task = await board.create("metadata enrichment task")
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        await _force_task_state(
            board,
            task.id,
            status=TaskStatus.ASSIGNED.value,
            assigned_to="dead-agent-meta",
            updated_at=stale_time,
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        reaped = await sm.reap_orphaned_tasks(stale_minutes=30)

        assert len(reaped) == 1
        meta = reaped[0].metadata
        assert "orphan_reaped_at" in meta
        assert meta["orphan_original_agent"] == "dead-agent-meta"
        assert meta["orphan_original_status"] == "assigned"

    @pytest.mark.asyncio
    async def test_custom_stale_minutes_threshold(self, tmp_path: Path) -> None:
        board = await _make_board(tmp_path)
        task = await board.create("custom threshold task")
        # 20 min ago — stale for 10-min window, NOT stale for 30-min window
        at_20_min = datetime.now(timezone.utc) - timedelta(minutes=20)
        await _force_task_state(
            board,
            task.id,
            status=TaskStatus.ASSIGNED.value,
            assigned_to="ghost-agent",
            updated_at=at_20_min,
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        # Default 30-min window: should NOT reap
        not_reaped = await sm.reap_orphaned_tasks(stale_minutes=30)
        assert len(not_reaped) == 0

        # Tighter 10-min window: SHOULD reap
        reaped = await sm.reap_orphaned_tasks(stale_minutes=10)
        assert len(reaped) == 1
        assert reaped[0].id == task.id

    @pytest.mark.asyncio
    async def test_multiple_orphans_reaped_in_single_sweep(self, tmp_path: Path) -> None:
        board = await _make_board(tmp_path)
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=60)

        t1 = await board.create("orphan 1")
        await _force_task_state(
            board, t1.id,
            status=TaskStatus.ASSIGNED.value,
            assigned_to="dead-1",
            updated_at=stale_time,
        )
        t2 = await board.create("orphan 2")
        await _force_task_state(
            board, t2.id,
            status=TaskStatus.RUNNING.value,
            assigned_to="dead-2",
            updated_at=stale_time,
        )
        t3 = await board.create("live task")
        await _force_task_state(
            board, t3.id,
            status=TaskStatus.ASSIGNED.value,
            assigned_to="alive",
            updated_at=stale_time,
        )

        pool = _FakeAgentPool([_agent("alive")])
        sm = await _make_swarm(tmp_path, board, pool)

        reaped = await sm.reap_orphaned_tasks(stale_minutes=30)

        reaped_ids = {t.id for t in reaped}
        assert t1.id in reaped_ids
        assert t2.id in reaped_ids
        assert t3.id not in reaped_ids
        assert len(reaped) == 2

    @pytest.mark.asyncio
    async def test_orphan_metadata_keys_present_on_reap(self, tmp_path: Path) -> None:
        """Verify the three orphan-tracking keys are injected during reap."""
        board = await _make_board(tmp_path)
        task = await board.create("claimed task")
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=60)
        await _force_task_state(
            board,
            task.id,
            status=TaskStatus.RUNNING.value,
            assigned_to="dead-claimant",
            updated_at=stale_time,
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        reaped = await sm.reap_orphaned_tasks(stale_minutes=30)

        assert len(reaped) == 1
        meta = reaped[0].metadata
        assert meta["orphan_original_agent"] == "dead-claimant"
        assert meta["orphan_original_status"] == "running"
        assert "orphan_reaped_at" in meta

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_subsystems(self, tmp_path: Path) -> None:
        sm = SwarmManager(state_dir=tmp_path / ".dharma")
        # _task_board and _agent_pool are both None
        result = await sm.reap_orphaned_tasks()
        assert result == []


# ===================================================================
# _propagate_dependency_failures
# ===================================================================


class TestPropagateDependencyFailures:
    """Verify failure cascades through the dependency graph."""

    @pytest.mark.asyncio
    async def test_pending_with_permanently_failed_dep_is_propagated(
        self, tmp_path: Path,
    ) -> None:
        board = await _make_board(tmp_path)

        parent = await board.create("parent task")
        child = await board.create("child task")
        await _add_dependency(board, child.id, parent.id)

        # Parent: FAILED with auto_rescue_count >= 2 (exhausted)
        await _force_task_state(
            board,
            parent.id,
            status=TaskStatus.FAILED.value,
            metadata={"auto_rescue_count": 3},
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        propagated = await sm._propagate_dependency_failures()

        assert len(propagated) == 1
        assert propagated[0].id == child.id
        assert propagated[0].status == TaskStatus.FAILED
        assert "permanently failed" in (propagated[0].result or "").lower()

    @pytest.mark.asyncio
    async def test_pending_with_rescuable_dep_is_not_propagated(
        self, tmp_path: Path,
    ) -> None:
        board = await _make_board(tmp_path)

        parent = await board.create("rescuable parent")
        child = await board.create("waiting child")
        await _add_dependency(board, child.id, parent.id)

        # Parent: FAILED but auto_rescue_count < 2 (still has retries)
        await _force_task_state(
            board,
            parent.id,
            status=TaskStatus.FAILED.value,
            metadata={"auto_rescue_count": 1},
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        propagated = await sm._propagate_dependency_failures()

        assert len(propagated) == 0
        refreshed = await board.get(child.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_pending_with_running_dep_is_not_propagated(
        self, tmp_path: Path,
    ) -> None:
        board = await _make_board(tmp_path)

        parent = await board.create("running parent")
        child = await board.create("blocked child")
        await _add_dependency(board, child.id, parent.id)

        await _force_task_state(
            board,
            parent.id,
            status=TaskStatus.RUNNING.value,
            assigned_to="agent-x",
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        propagated = await sm._propagate_dependency_failures()

        assert len(propagated) == 0
        refreshed = await board.get(child.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_pending_with_no_dependencies_is_not_affected(
        self, tmp_path: Path,
    ) -> None:
        board = await _make_board(tmp_path)
        task = await board.create("independent task")

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        propagated = await sm._propagate_dependency_failures()

        assert len(propagated) == 0
        refreshed = await board.get(task.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_pending_with_completed_dep_is_not_propagated(
        self, tmp_path: Path,
    ) -> None:
        """A completed dependency is satisfied -- child stays pending (ready)."""
        board = await _make_board(tmp_path)

        parent = await board.create("completed parent")
        child = await board.create("ready child")
        await _add_dependency(board, child.id, parent.id)

        await _force_task_state(
            board,
            parent.id,
            status=TaskStatus.COMPLETED.value,
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        propagated = await sm._propagate_dependency_failures()

        assert len(propagated) == 0
        refreshed = await board.get(child.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_mixed_deps_one_completed_one_permanently_failed(
        self, tmp_path: Path,
    ) -> None:
        """Two deps: one completed (satisfied), one permanently failed.
        The blocking dep is permanently failed, so child is propagated."""
        board = await _make_board(tmp_path)

        parent_ok = await board.create("completed parent")
        parent_bad = await board.create("failed parent")
        child = await board.create("child with mixed deps")

        await _add_dependency(board, child.id, parent_ok.id)
        await _add_dependency(board, child.id, parent_bad.id)

        await _force_task_state(
            board,
            parent_ok.id,
            status=TaskStatus.COMPLETED.value,
        )
        await _force_task_state(
            board,
            parent_bad.id,
            status=TaskStatus.FAILED.value,
            metadata={"auto_rescue_count": 5},
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        propagated = await sm._propagate_dependency_failures()

        assert len(propagated) == 1
        assert propagated[0].id == child.id
        assert propagated[0].status == TaskStatus.FAILED

    @pytest.mark.asyncio
    async def test_mixed_deps_one_running_one_permanently_failed(
        self, tmp_path: Path,
    ) -> None:
        """Two deps: one still running, one permanently failed.
        Because one dep is still running (not completed, not failed),
        it blocks propagation -- the child should remain pending."""
        board = await _make_board(tmp_path)

        parent_running = await board.create("running parent")
        parent_failed = await board.create("failed parent")
        child = await board.create("waiting child")

        await _add_dependency(board, child.id, parent_running.id)
        await _add_dependency(board, child.id, parent_failed.id)

        await _force_task_state(
            board,
            parent_running.id,
            status=TaskStatus.RUNNING.value,
            assigned_to="agent-y",
        )
        await _force_task_state(
            board,
            parent_failed.id,
            status=TaskStatus.FAILED.value,
            metadata={"auto_rescue_count": 10},
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        propagated = await sm._propagate_dependency_failures()

        assert len(propagated) == 0
        refreshed = await board.get(child.id)
        assert refreshed is not None
        assert refreshed.status == TaskStatus.PENDING

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_task_board(self, tmp_path: Path) -> None:
        sm = SwarmManager(state_dir=tmp_path / ".dharma")
        result = await sm._propagate_dependency_failures()
        assert result == []

    @pytest.mark.asyncio
    async def test_dep_with_zero_rescue_count_is_not_propagated(
        self, tmp_path: Path,
    ) -> None:
        """auto_rescue_count=0 means the task failed but has never been retried."""
        board = await _make_board(tmp_path)

        parent = await board.create("fresh failure")
        child = await board.create("patient child")
        await _add_dependency(board, child.id, parent.id)

        await _force_task_state(
            board,
            parent.id,
            status=TaskStatus.FAILED.value,
            metadata={"auto_rescue_count": 0},
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        propagated = await sm._propagate_dependency_failures()

        assert len(propagated) == 0

    @pytest.mark.asyncio
    async def test_dep_with_no_metadata_is_not_propagated(
        self, tmp_path: Path,
    ) -> None:
        """A failed dep with no metadata at all (rescue_count defaults to 0)."""
        board = await _make_board(tmp_path)

        parent = await board.create("no-meta failure")
        child = await board.create("waiting for meta")
        await _add_dependency(board, child.id, parent.id)

        await _force_task_state(
            board,
            parent.id,
            status=TaskStatus.FAILED.value,
            metadata={},
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        propagated = await sm._propagate_dependency_failures()

        assert len(propagated) == 0


# ===================================================================
# Integration: reap_orphaned_tasks calls _propagate_dependency_failures
# ===================================================================


class TestReapAndPropagateIntegration:
    """Verify that reap_orphaned_tasks also triggers dependency propagation."""

    @pytest.mark.asyncio
    async def test_reap_triggers_propagation(self, tmp_path: Path) -> None:
        board = await _make_board(tmp_path)
        stale_time = datetime.now(timezone.utc) - timedelta(minutes=60)

        # Orphan: ASSIGNED to a dead agent (will be reaped)
        orphan = await board.create("orphaned task")
        await _force_task_state(
            board,
            orphan.id,
            status=TaskStatus.ASSIGNED.value,
            assigned_to="dead-agent",
            updated_at=stale_time,
        )

        # Dependency chain: parent permanently failed, child pending
        parent = await board.create("dead parent")
        child = await board.create("doomed child")
        await _add_dependency(board, child.id, parent.id)
        await _force_task_state(
            board,
            parent.id,
            status=TaskStatus.FAILED.value,
            metadata={"auto_rescue_count": 5},
        )

        pool = _FakeAgentPool([])
        sm = await _make_swarm(tmp_path, board, pool)

        reaped = await sm.reap_orphaned_tasks(stale_minutes=30)

        # The orphan should be reaped
        assert any(t.id == orphan.id for t in reaped)

        # The child should now be failed (propagated within reap call)
        child_refreshed = await board.get(child.id)
        assert child_refreshed is not None
        assert child_refreshed.status == TaskStatus.FAILED
