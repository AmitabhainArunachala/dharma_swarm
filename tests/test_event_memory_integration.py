"""Integration tests for event memory and unified index."""

from __future__ import annotations

import sqlite3
import pytest

from dharma_swarm.engine.event_memory import EventMemoryStore
from dharma_swarm.engine.retrieval_feedback import RetrievalFeedbackStore
from dharma_swarm.engine.unified_index import UnifiedIndex
from dharma_swarm.models import AgentRole, AgentState, AgentStatus, Task, TaskDispatch
from dharma_swarm.orchestrator import Orchestrator
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType


class _Board:
    def __init__(self) -> None:
        self.tasks = [Task(id="task-1", title="Index task", description="safe")]
        self.updates: list[tuple[str, dict]] = []

    async def get_ready_tasks(self):
        return self.tasks

    async def update_task(self, task_id, **fields):
        self.updates.append((task_id, fields))

    async def get(self, task_id):
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None


class _Pool:
    def __init__(self) -> None:
        self._agents = [
            AgentState(
                id="a1",
                name="agent-1",
                role=AgentRole.GENERAL,
                status=AgentStatus.IDLE,
            )
        ]
        self._assignments: list[tuple[str, str]] = []

    async def get_idle_agents(self):
        return self._agents

    async def assign(self, agent_id, task_id):
        self._assignments.append((agent_id, task_id))

    async def release(self, agent_id):
        return None

    async def get_result(self, agent_id):
        return None

    async def get(self, agent_id):
        return None


@pytest.mark.asyncio
async def test_orchestrator_lifecycle_ingests_event_memory(tmp_path) -> None:
    store = EventMemoryStore(tmp_path / "memory_plane.db")
    await store.init_db()

    orch = Orchestrator(
        task_board=_Board(),
        agent_pool=_Pool(),
        event_memory=store,
        ledger_dir=tmp_path,
        session_id="sess-phase1",
    )

    await orch._assign_dispatch(TaskDispatch(task_id="task-1", agent_id="a1"))

    rows = await store.search_events("dispatch_assigned", limit=5)
    assigned_rows = [r for r in rows if r["payload"].get("action_name") == "dispatch_assigned"]
    assert assigned_rows, "Expected at least one dispatch_assigned event"
    assert assigned_rows[0]["session_id"] == "sess-phase1"
    assert assigned_rows[0]["payload"]["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_event_and_note_records_coexist_in_one_search_surface(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = EventMemoryStore(db_path)
    await store.init_db()
    index = UnifiedIndex(db_path)

    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="orchestrator.lifecycle",
        agent_id="agent-1",
        session_id="sess-search",
        trace_id="trace-search",
        payload={
            "action_name": "memory_shift",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    await store.ingest_envelope(event)
    index.index_document(
        "note",
        "notes/memory.md",
        "# Memory\n\nA memory shift happened in the planning loop.",
        {"topic": "memory"},
    )

    results = index.search("memory shift", limit=10)
    source_kinds = {record.metadata["source_kind"] for record, _score in results}
    assert "note" in source_kinds
    assert "runtime_event" in source_kinds


def test_read_memory_context_uses_memory_plane_when_strange_loop_absent(tmp_path) -> None:
    from dharma_swarm.context import read_memory_context

    db_dir = tmp_path / "db"
    db_dir.mkdir()
    index = UnifiedIndex(db_dir / "memory_plane.db")
    index.index_document(
        "note",
        "notes/context.md",
        "# Context\n\nMemory palace context surfaced from the unified index.",
        {"topic": "context"},
    )

    result = read_memory_context(state_dir=tmp_path)
    assert "[retrieval:note]" in result
    assert "Memory palace context" in result


@pytest.mark.asyncio
async def test_read_memory_context_query_prefers_temporal_hits(tmp_path) -> None:
    from dharma_swarm.context import read_memory_context

    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_path = db_dir / "memory_plane.db"
    store = EventMemoryStore(db_path)
    await store.init_db()

    older = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="orchestrator.lifecycle",
        agent_id="agent-1",
        session_id="sess-query",
        trace_id="trace-query",
        event_id="evt-old",
        emitted_at="2026-03-08T08:00:00+00:00",
        payload={
            "action_name": "memory_shift",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    latest = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="orchestrator.lifecycle",
        agent_id="agent-1",
        session_id="sess-query",
        trace_id="trace-query",
        event_id="evt-new",
        emitted_at="2026-03-09T11:00:00+00:00",
        payload={
            "action_name": "memory_shift",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    await store.ingest_envelope(older)
    await store.ingest_envelope(latest)

    result = read_memory_context(
        state_dir=tmp_path,
        query="latest memory shift",
        limit=1,
    )

    assert "[retrieval:runtime_event]" in result
    assert "evt-new" not in result  # rendered text, not raw ids
    assert "memory_shift" in result or "memory shift" in result
    feedback = RetrievalFeedbackStore(db_path).recent(limit=5)
    assert len(feedback) == 1
    assert feedback[0]["consumer"] == "context.read_memory_context"
    assert feedback[0]["record_id"] == "evt-new"
