"""Tests for the Phase 2 hybrid retriever."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dharma_swarm.engine.event_memory import EventMemoryStore
from dharma_swarm.engine.hybrid_retriever import HybridRetriever, infer_temporal_query
from dharma_swarm.engine.retrieval_feedback import RetrievalFeedbackStore
from dharma_swarm.engine.unified_index import UnifiedIndex
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType


@pytest.mark.asyncio
async def test_hybrid_retriever_fuses_note_and_event_results(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = EventMemoryStore(db_path)
    await store.init_db()
    index = UnifiedIndex(db_path)
    retriever = HybridRetriever(index)

    index.index_document(
        "note",
        "notes/retrieval.md",
        "# Hybrid Retrieval\n\nBGE M3 hybrid retrieval uses BM25 and reranking for memory recall.",
        {"topic": "memory"},
    )
    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="orchestrator.lifecycle",
        agent_id="agent-1",
        session_id="sess-hybrid",
        trace_id="trace-hybrid",
        payload={
            "action_name": "retrieval_refresh",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    await store.ingest_envelope(event)

    hits = retriever.search("hybrid retrieval bm25", limit=5)

    assert hits
    assert hits[0].record.metadata["source_kind"] == "note"
    assert "lexical" in hits[0].evidence["lane_scores"]
    assert "semantic" in hits[0].evidence["lane_scores"]
    assert {hit.record.metadata["source_kind"] for hit in hits} >= {"note", "runtime_event"}


def test_hybrid_retriever_respects_filters(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    index = UnifiedIndex(db_path)
    retriever = HybridRetriever(index)

    index.index_document(
        "note",
        "notes/research.md",
        "# Memory\n\nSemantic retrieval for research notes.",
        {"topic": "research"},
    )
    index.index_document(
        "note",
        "notes/code.md",
        "# Memory\n\nSemantic retrieval for code notes.",
        {"topic": "engineering"},
    )

    hits = retriever.search("semantic retrieval", filters={"topic": "engineering"})

    assert len(hits) == 1
    assert hits[0].record.metadata["topic"] == "engineering"


def test_hybrid_retriever_boosts_title_terms(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    index = UnifiedIndex(db_path)
    retriever = HybridRetriever(index)

    index.index_document(
        "note",
        "notes/architecture.md",
        "# Memory Palace\n\nBrief generic body text.",
        {"topic": "memory"},
    )
    index.index_document(
        "note",
        "notes/noisy.md",
        "# Notes\n\nMemory palace memory palace memory palace.",
        {"topic": "memory"},
    )

    hits = retriever.search("memory palace", limit=2)

    assert len(hits) == 2
    assert hits[0].record.metadata["source_path"].endswith("architecture.md")


def test_infer_temporal_query_parses_relative_windows() -> None:
    now = datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc)

    temporal = infer_temporal_query("latest memory shift from yesterday", now=now)

    assert temporal.since == datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc)
    assert temporal.until == datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc)
    assert temporal.recency_bias > 0
    assert "yesterday" in temporal.matched_phrases


@pytest.mark.asyncio
async def test_hybrid_retriever_honors_yesterday_window(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = EventMemoryStore(db_path)
    await store.init_db()
    retriever = HybridRetriever(UnifiedIndex(db_path))

    older = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="orchestrator.lifecycle",
        agent_id="agent-1",
        session_id="sess-temporal",
        trace_id="trace-temporal",
        event_id="evt-older",
        emitted_at="2026-03-07T08:00:00+00:00",
        payload={
            "action_name": "memory_shift",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    yesterday = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="orchestrator.lifecycle",
        agent_id="agent-1",
        session_id="sess-temporal",
        trace_id="trace-temporal",
        event_id="evt-yesterday",
        emitted_at="2026-03-08T09:00:00+00:00",
        payload={
            "action_name": "memory_shift",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    await store.ingest_envelope(older)
    await store.ingest_envelope(yesterday)

    hits = retriever.search_with_temporal_query(
        "memory shift from yesterday",
        limit=5,
        now=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )

    assert len(hits) == 1
    assert hits[0].record.record_id == "evt-yesterday"
    assert "yesterday" in hits[0].evidence["temporal_query"]


@pytest.mark.asyncio
async def test_hybrid_retriever_biases_latest_toward_newer_records(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = EventMemoryStore(db_path)
    await store.init_db()
    retriever = HybridRetriever(UnifiedIndex(db_path))

    older = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="orchestrator.lifecycle",
        agent_id="agent-1",
        session_id="sess-latest",
        trace_id="trace-latest",
        event_id="evt-latest-old",
        emitted_at="2026-03-08T01:00:00+00:00",
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
        session_id="sess-latest",
        trace_id="trace-latest",
        event_id="evt-latest-new",
        emitted_at="2026-03-09T11:00:00+00:00",
        payload={
            "action_name": "memory_shift",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    await store.ingest_envelope(older)
    await store.ingest_envelope(latest)

    hits = retriever.search_with_temporal_query(
        "latest memory shift",
        limit=5,
        now=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
    )

    assert len(hits) >= 2
    assert hits[0].record.record_id == "evt-latest-new"
    assert hits[0].evidence["temporal_boost"] >= hits[1].evidence["temporal_boost"]


def test_hybrid_retriever_applies_feedback_bias_for_consumer(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    index = UnifiedIndex(db_path)
    retriever = HybridRetriever(index)
    feedback = RetrievalFeedbackStore(db_path)

    index.index_document(
        "note",
        "notes/a.md",
        "# Memory Recall\n\nStable recall content for agent prompts.",
        {"topic": "memory"},
    )
    index.index_document(
        "note",
        "notes/b.md",
        "# Memory Recall\n\nStable recall content for agent prompts.",
        {"topic": "memory"},
    )

    hits = retriever.search("memory recall stable", limit=2)
    by_path = {hit.record.metadata["source_path"]: hit for hit in hits}
    feedback.log_hits(
        "memory recall stable",
        [by_path["notes/a.md"]],
        consumer="agent_runner.prompt",
        task_id="task-success",
    )
    feedback.log_hits(
        "memory recall stable",
        [by_path["notes/b.md"]],
        consumer="agent_runner.prompt",
        task_id="task-failure",
    )
    feedback.record_outcome(
        "task-success",
        outcome="success",
        consumer="agent_runner.prompt",
    )
    feedback.record_outcome(
        "task-failure",
        outcome="failure",
        consumer="agent_runner.prompt",
    )

    reranked = retriever.search(
        "memory recall stable",
        limit=2,
        consumer="agent_runner.prompt",
    )

    assert len(reranked) == 2
    assert reranked[0].record.metadata["source_path"] == "notes/a.md"
    assert reranked[0].evidence["feedback_boost"] > 0
    assert reranked[1].evidence["feedback_boost"] < 0


def test_hybrid_retriever_feedback_bias_is_query_aware(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    index = UnifiedIndex(db_path)
    retriever = HybridRetriever(index)
    feedback = RetrievalFeedbackStore(db_path)

    index.index_document(
        "note",
        "notes/memory.md",
        "# Memory Recall\n\nStable recall content for agent prompts.",
        {"topic": "memory"},
    )
    index.index_document(
        "note",
        "notes/compiler.md",
        "# Memory Recall\n\nStable recall content for agent prompts.",
        {"topic": "memory"},
    )

    baseline = retriever.search("memory recall stable", limit=2)
    by_path = {hit.record.metadata["source_path"]: hit for hit in baseline}
    feedback.log_hits(
        "memory recall stable",
        [by_path["notes/memory.md"]],
        consumer="agent_runner.prompt",
        task_id="task-memory-success",
    )
    feedback.log_hits(
        "compiler routing fallback",
        [by_path["notes/compiler.md"]],
        consumer="agent_runner.prompt",
        task_id="task-compiler-success",
    )
    feedback.record_outcome(
        "task-memory-success",
        outcome="success",
        consumer="agent_runner.prompt",
    )
    feedback.record_outcome(
        "task-compiler-success",
        outcome="success",
        consumer="agent_runner.prompt",
    )

    reranked = retriever.search(
        "memory recall stable",
        limit=2,
        consumer="agent_runner.prompt",
    )

    assert len(reranked) == 2
    assert reranked[0].record.metadata["source_path"] == "notes/memory.md"
