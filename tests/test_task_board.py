"""Tests for dharma_swarm.task_board."""

import pytest

import dharma_swarm.task_board as task_board_mod
from dharma_swarm.models import GateCheckResult, GateDecision
from dharma_swarm.models import TaskPriority, TaskStatus
from dharma_swarm.task_board import TaskBoard, TaskBoardError


@pytest.fixture
async def board(tmp_path):
    b = TaskBoard(tmp_path / "tasks.db")
    await b.init_db()
    return b


@pytest.mark.asyncio
async def test_create_task(board):
    task = await board.create("Build feature", description="Do the thing")
    assert task.title == "Build feature"
    assert task.status == TaskStatus.PENDING
    assert len(task.id) == 16


@pytest.mark.asyncio
async def test_get_task(board):
    task = await board.create("Test task")
    found = await board.get(task.id)
    assert found is not None
    assert found.title == "Test task"


@pytest.mark.asyncio
async def test_get_nonexistent(board):
    assert await board.get("nonexistent") is None


@pytest.mark.asyncio
async def test_list_tasks(board):
    await board.create("Task 1")
    await board.create("Task 2")
    tasks = await board.list_tasks()
    assert len(tasks) == 2


@pytest.mark.asyncio
async def test_list_tasks_by_status(board):
    t = await board.create("Task 1")
    await board.assign(t.id, "agent1")
    pending = await board.list_tasks(status=TaskStatus.PENDING)
    assigned = await board.list_tasks(status=TaskStatus.ASSIGNED)
    assert len(pending) == 0
    assert len(assigned) == 1


@pytest.mark.asyncio
async def test_full_lifecycle(board):
    task = await board.create("Lifecycle test")
    assert task.status == TaskStatus.PENDING

    task = await board.assign(task.id, "agent-1")
    assert task.status == TaskStatus.ASSIGNED
    assert task.assigned_to == "agent-1"

    task = await board.start(task.id)
    assert task.status == TaskStatus.RUNNING

    task = await board.complete(task.id, result="done!")
    assert task.status == TaskStatus.COMPLETED
    assert task.result == "done!"


@pytest.mark.asyncio
async def test_fail_and_retry(board):
    task = await board.create("Retry test")
    task = await board.assign(task.id, "agent")
    task = await board.start(task.id)
    task = await board.fail(task.id, error="timeout")
    assert task.status == TaskStatus.FAILED


@pytest.mark.asyncio
async def test_cancel(board):
    task = await board.create("Cancel test")
    task = await board.cancel(task.id)
    assert task.status == TaskStatus.CANCELLED


@pytest.mark.asyncio
async def test_invalid_transition(board):
    task = await board.create("Bad transition")
    task = await board.assign(task.id, "a")
    task = await board.start(task.id)
    task = await board.complete(task.id)
    with pytest.raises(TaskBoardError, match="Invalid transition"):
        await board.assign(task.id, "b")


@pytest.mark.asyncio
async def test_dependencies(board):
    t1 = await board.create("Dep 1")
    t2 = await board.create("Dep 2", depends_on=[t1.id])

    deps = await board.get_dependencies(t2.id)
    assert t1.id in deps


@pytest.mark.asyncio
async def test_get_ready_tasks(board):
    t1 = await board.create("Blocker")
    t2 = await board.create("Blocked", depends_on=[t1.id])
    t3 = await board.create("Independent")

    ready = await board.get_ready_tasks()
    ready_ids = [t.id for t in ready]
    assert t3.id in ready_ids
    assert t1.id in ready_ids
    assert t2.id not in ready_ids  # blocked by t1

    # Complete t1, t2 should become ready
    await board.assign(t1.id, "a")
    await board.start(t1.id)
    await board.complete(t1.id)
    ready = await board.get_ready_tasks()
    ready_ids = [t.id for t in ready]
    assert t2.id in ready_ids


@pytest.mark.asyncio
async def test_priority_ordering(board):
    await board.create("Low", priority=TaskPriority.LOW)
    await board.create("Urgent", priority=TaskPriority.URGENT)
    await board.create("Normal", priority=TaskPriority.NORMAL)

    ready = await board.get_ready_tasks()
    assert ready[0].priority == TaskPriority.URGENT


@pytest.mark.asyncio
async def test_stats(board):
    await board.create("T1")
    t2 = await board.create("T2")
    await board.assign(t2.id, "a")
    stats = await board.stats()
    assert stats["pending"] == 1
    assert stats["assigned"] == 1
    assert stats["total"] == 2


@pytest.mark.asyncio
async def test_complete_transition_block_raises(board, monkeypatch):
    class _Outcome:
        def __init__(self):
            self.result = GateCheckResult(
                decision=GateDecision.BLOCK,
                reason="forced block for test",
                gate_results={},
            )

    monkeypatch.setattr(
        task_board_mod,
        "check_with_reflective_reroute",
        lambda **_: _Outcome(),
    )

    task = await board.create("Blocked completion")
    task = await board.assign(task.id, "agent")
    task = await board.start(task.id)
    with pytest.raises(TaskBoardError, match="Telos blocked transition"):
        await board.complete(task.id, result="done")
