"""Tests for conversation flow capture and latent-gold recall."""

from __future__ import annotations

import sqlite3

from dharma_swarm.engine.conversation_memory import ConversationMemoryStore


def test_record_turn_harvests_multiple_idea_shards(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = ConversationMemoryStore(db_path)

    turn_id = store.record_turn(
        session_id="sess-flow",
        task_id="task-flow",
        role="user",
        content=(
            "We could build a memory palace index for task recall.\n"
            "Maybe we should also preserve abandoned branches from the conversation.\n"
            "What if latent gold resurfaced automatically later?"
        ),
        turn_index=1,
    )

    turns = store.recent_turns(task_id="task-flow", limit=5)
    assert len(turns) == 1
    assert turns[0].turn_id == turn_id
    latent = store.latent_gold("abandoned branches latent gold", limit=5)
    assert len(latent) >= 2
    assert {shard.shard_kind for shard in latent} & {"proposal", "question"}


def test_record_uptake_marks_implemented_and_orphaned(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = ConversationMemoryStore(db_path)
    store.record_turn(
        session_id="sess-ideas",
        task_id="task-ideas",
        role="user",
        content=(
            "We could build a memory palace index for task recall.\n"
            "We could also add a graph of abandoned ideas for resurfacing later."
        ),
        turn_index=1,
    )

    matched = store.record_uptake_from_text(
        task_id="task-ideas",
        text="Implement the memory palace index for task recall now.",
    )

    assert matched >= 1
    with sqlite3.connect(str(db_path)) as db:
        rows = db.execute(
            "SELECT text, state FROM idea_shards WHERE task_id = ? ORDER BY created_at ASC",
            ("task-ideas",),
        ).fetchall()
    states = {text: state for text, state in rows}
    assert any("memory palace index" in text and state == "implemented" for text, state in states.items())
    assert any("abandoned ideas" in text and state == "orphaned" for text, state in states.items())


def test_mark_task_outcome_failure_defers_open_ideas(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = ConversationMemoryStore(db_path)
    store.record_turn(
        session_id="sess-fail",
        task_id="task-fail",
        role="assistant",
        content="Maybe we should add a temporal graph memory and a residue sweep for missed ideas.",
        turn_index=1,
    )

    updated = store.mark_task_outcome("task-fail", outcome="failure")

    assert updated >= 1
    latent = store.latent_gold("temporal graph memory", limit=5)
    assert latent
    assert latent[0].state == "deferred"


def test_follow_up_task_marks_shard_reopened_then_implemented(tmp_path) -> None:
    db_path = tmp_path / "memory_plane.db"
    store = ConversationMemoryStore(db_path)
    store.record_turn(
        session_id="sess-follow",
        task_id="task-source",
        role="user",
        content="Maybe we should build a temporal memory graph for abandoned ideas.",
        turn_index=1,
    )
    store.mark_task_outcome("task-source", outcome="success")
    shard = store.latent_gold("temporal memory graph", limit=1)[0]

    reopened = store.record_follow_up_task(
        shard_id=shard.shard_id,
        follow_up_task_id="task-follow",
        title="Reopen latent branch: temporal memory graph",
    )
    assert reopened is True
    assert all(item.shard_id != shard.shard_id for item in store.latent_gold("", limit=10))

    completed = store.record_follow_up_outcome(
        shard_id=shard.shard_id,
        follow_up_task_id="task-follow",
        outcome="success",
        evidence_text="Implemented the temporal memory graph.",
    )
    assert completed is True

    with sqlite3.connect(str(db_path)) as db:
        row = db.execute(
            "SELECT state FROM idea_shards WHERE shard_id = ?",
            (shard.shard_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == "implemented"
