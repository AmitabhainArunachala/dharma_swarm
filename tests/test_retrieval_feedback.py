"""Tests for retrieval telemetry in the memory plane."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from dharma_swarm.engine.hybrid_retriever import RetrievalHit
from dharma_swarm.engine.knowledge_store import KnowledgeRecord
from dharma_swarm.engine.retrieval_feedback import RetrievalFeedbackStore


def test_retrieval_feedback_store_logs_hits(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = RetrievalFeedbackStore(db_path)
    hit = RetrievalHit(
        record=KnowledgeRecord(
            text="Memory palace note",
            metadata={"source_kind": "note", "source_path": "notes/memory.md"},
            record_id="rec-1",
            created_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        ),
        score=0.42,
        evidence={"lane_scores": {"lexical": 1.0}},
    )

    count = store.log_hits(
        "memory palace",
        [hit],
        consumer="agent_runner.prompt",
        task_id="task-1",
    )

    assert count == 1
    rows = store.recent(limit=5, consumer="agent_runner.prompt")
    assert len(rows) == 1
    assert rows[0]["query_text"] == "memory palace"
    assert rows[0]["record_id"] == "rec-1"
    assert rows[0]["task_id"] == "task-1"
    assert rows[0]["evidence"]["lane_scores"]["lexical"] == 1.0
    assert rows[0]["evidence"]["record_metadata"]["source_path"] == "notes/memory.md"
    assert rows[0]["record_text"] == "Memory palace note"


def test_retrieval_feedback_store_stats_counts_rows(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = RetrievalFeedbackStore(db_path)
    base_hit = RetrievalHit(
        record=KnowledgeRecord(
            text="Event memory",
            metadata={"source_kind": "runtime_event"},
            record_id="evt-1",
            created_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        ),
        score=0.21,
        evidence={},
    )

    store.log_hits("memory", [base_hit, replace(base_hit, record=replace(base_hit.record, record_id="evt-2"))])

    assert store.stats()["retrieval_log"] == 2


def test_retrieval_feedback_store_records_outcome_and_profile(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = RetrievalFeedbackStore(db_path)
    success_hit = RetrievalHit(
        record=KnowledgeRecord(
            text="Note A",
            metadata={"source_kind": "note", "source_path": "notes/a.md"},
            record_id="rec-a",
            created_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        ),
        score=0.5,
        evidence={},
    )
    failure_hit = RetrievalHit(
        record=KnowledgeRecord(
            text="Event B",
            metadata={"source_kind": "runtime_event", "source_path": ""},
            record_id="rec-b",
            created_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        ),
        score=0.4,
        evidence={},
    )

    store.log_hits(
        "memory",
        [success_hit],
        consumer="agent_runner.prompt",
        task_id="task-success",
    )
    store.log_hits(
        "memory",
        [failure_hit],
        consumer="agent_runner.prompt",
        task_id="task-failure",
    )

    assert store.record_outcome(
        "task-success",
        outcome="success",
        consumer="agent_runner.prompt",
    ) == 1
    assert store.record_outcome(
        "task-failure",
        outcome="failure",
        consumer="agent_runner.prompt",
    ) == 1

    rows = store.recent(limit=5, consumer="agent_runner.prompt")
    assert {row["outcome"] for row in rows} == {"success", "failure"}

    profile = store.feedback_profile(consumer="agent_runner.prompt")
    assert profile.record_bias["rec-a"] > 0
    assert profile.record_bias["rec-b"] < 0
    assert profile.source_kind_bias["note"] > 0
    assert profile.source_kind_bias["runtime_event"] < 0


def test_feedback_profile_weights_similar_queries_more_heavily(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = RetrievalFeedbackStore(db_path)
    hit = RetrievalHit(
        record=KnowledgeRecord(
            text="Shared note",
            metadata={"source_kind": "note", "source_path": "notes/shared.md"},
            record_id="rec-shared",
            created_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        ),
        score=0.4,
        evidence={},
    )

    store.log_hits(
        "memory recall stable",
        [hit],
        consumer="agent_runner.prompt",
        task_id="task-memory",
    )
    store.log_hits(
        "compiler routing fallback",
        [hit],
        consumer="agent_runner.prompt",
        task_id="task-compiler",
    )
    store.record_outcome("task-memory", outcome="success", consumer="agent_runner.prompt")
    store.record_outcome("task-compiler", outcome="failure", consumer="agent_runner.prompt")

    memory_profile = store.feedback_profile(
        consumer="agent_runner.prompt",
        query="memory recall stable",
    )
    compiler_profile = store.feedback_profile(
        consumer="agent_runner.prompt",
        query="compiler routing fallback",
    )

    assert memory_profile.record_bias["rec-shared"] > compiler_profile.record_bias["rec-shared"]


def test_retrieval_feedback_store_records_citation_uptake(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = RetrievalFeedbackStore(db_path)
    hit = RetrievalHit(
        record=KnowledgeRecord(
            text="Latent gold memory palace index for abandoned conversation branches.",
            metadata={
                "source_kind": "note",
                "source_path": "notes/memory_palace.md",
                "section_title": "Latent Gold",
            },
            record_id="rec-gold",
            created_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        ),
        score=0.61,
        evidence={},
    )

    store.log_hits(
        "latent gold memory palace",
        [hit],
        consumer="agent_runner.prompt",
        task_id="task-gold",
    )
    used = store.record_citation_uptake(
        "task-gold",
        text="Implement the latent gold memory palace index for abandoned branches now.",
        consumer="agent_runner.prompt",
    )

    assert used == 1
    row = store.recent(limit=1, consumer="agent_runner.prompt")[0]
    assert row["uptake_state"] in {"used", "probably_used"}
    assert row["uptake_score"] is not None
    assert row["uptake_evidence"]["distinctive_overlap"] > 0


def test_feedback_profile_prefers_used_success_over_unused_success(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = RetrievalFeedbackStore(db_path)
    used_hit = RetrievalHit(
        record=KnowledgeRecord(
            text="Temporal memory graph for resurfacing abandoned ideas.",
            metadata={"source_kind": "note", "source_path": "notes/temporal_graph.md"},
            record_id="rec-used",
            created_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        ),
        score=0.55,
        evidence={},
    )
    unused_hit = RetrievalHit(
        record=KnowledgeRecord(
            text="Static changelog formatting checklist.",
            metadata={"source_kind": "note", "source_path": "notes/changelog.md"},
            record_id="rec-unused",
            created_at=datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc),
        ),
        score=0.44,
        evidence={},
    )

    store.log_hits(
        "temporal memory graph",
        [used_hit],
        consumer="agent_runner.prompt",
        task_id="task-used",
    )
    store.log_hits(
        "temporal memory graph",
        [unused_hit],
        consumer="agent_runner.prompt",
        task_id="task-unused",
    )
    store.record_citation_uptake(
        "task-used",
        text="Build the temporal memory graph for abandoned ideas.",
        consumer="agent_runner.prompt",
    )
    store.record_citation_uptake(
        "task-unused",
        text="Ship the runtime patch without touching formatting.",
        consumer="agent_runner.prompt",
    )
    store.record_outcome("task-used", outcome="success", consumer="agent_runner.prompt")
    store.record_outcome("task-unused", outcome="success", consumer="agent_runner.prompt")

    profile = store.feedback_profile(
        consumer="agent_runner.prompt",
        query="temporal memory graph",
    )

    assert profile.record_bias["rec-used"] > profile.record_bias["rec-unused"]
