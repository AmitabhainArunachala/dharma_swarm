"""Tests for dharma_swarm.engine.event_memory."""

from __future__ import annotations

import pytest

from dharma_swarm.engine.event_memory import EventMemoryStore
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType


@pytest.fixture
async def store(tmp_path):
    event_store = EventMemoryStore(tmp_path / "memory_plane.db")
    await event_store.init_db()
    return event_store


@pytest.mark.asyncio
async def test_ingest_valid_runtime_envelope(store: EventMemoryStore) -> None:
    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="test.runtime",
        agent_id="agent-1",
        session_id="sess-1",
        trace_id="trace-1",
        event_id="evt-1",
        emitted_at="2026-01-01T00:00:00+00:00",
        payload={
            "action_name": "dispatch_assigned",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    inserted = await store.ingest_envelope(event)
    assert inserted is True

    rows = await store.replay_session("sess-1")
    assert len(rows) == 1
    assert rows[0]["event_id"] == "evt-1"


@pytest.mark.asyncio
async def test_duplicate_event_id_is_ignored(store: EventMemoryStore) -> None:
    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="test.runtime",
        agent_id="agent-1",
        session_id="sess-1",
        trace_id="trace-1",
        event_id="evt-dup",
        emitted_at="2026-01-01T00:00:00+00:00",
        payload={
            "action_name": "dispatch_assigned",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    assert await store.ingest_envelope(event) is True
    assert await store.ingest_envelope(event) is False

    rows = await store.replay_session("sess-1")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_replay_session_returns_ordered_events(store: EventMemoryStore) -> None:
    early = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="test.runtime",
        agent_id="agent-1",
        session_id="sess-order",
        trace_id="trace-order",
        event_id="evt-early",
        emitted_at="2026-01-01T00:00:00+00:00",
        payload={
            "action_name": "first",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    late = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="test.runtime",
        agent_id="agent-1",
        session_id="sess-order",
        trace_id="trace-order",
        event_id="evt-late",
        emitted_at="2026-01-01T00:00:05+00:00",
        payload={
            "action_name": "second",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )

    await store.ingest_envelope(late)
    await store.ingest_envelope(early)

    rows = await store.replay_session("sess-order")
    assert [row["event_id"] for row in rows] == ["evt-early", "evt-late"]


@pytest.mark.asyncio
async def test_search_events_matches_payload_and_type(store: EventMemoryStore) -> None:
    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="orchestrator.lifecycle",
        agent_id="agent-1",
        session_id="sess-search",
        trace_id="trace-search",
        payload={
            "action_name": "dispatch_assigned",
            "decision": "recorded",
            "confidence": 1.0,
            "task_id": "task-123",
        },
    )
    await store.ingest_envelope(event)

    rows = await store.search_events("dispatch_assigned", limit=5)
    assert len(rows) == 1
    assert rows[0]["source"] == "orchestrator.lifecycle"
    assert rows[0]["payload"]["task_id"] == "task-123"
