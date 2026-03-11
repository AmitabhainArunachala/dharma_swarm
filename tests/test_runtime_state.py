from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from dharma_swarm.runtime_state import (
    ContextBundleRecord,
    MemoryFact,
    RuntimeStateStore,
    SessionState,
)


@pytest.mark.asyncio
async def test_runtime_state_initializes_wal_and_core_tables(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    store = RuntimeStateStore(db_path)
    await store.init_db()

    await store.upsert_session(
        SessionState(
            session_id="sess-1",
            operator_id="operator",
            status="active",
            current_task_id="task-1",
        )
    )
    fact = await store.record_memory_fact(
        MemoryFact(
            fact_id="fact-1",
            fact_kind="workspace_rule",
            truth_state="promoted",
            text="Use isolated workspaces with explicit publish/promotion.",
            confidence=0.95,
            session_id="sess-1",
            task_id="task-1",
        )
    )
    bundle = await store.record_context_bundle(
        ContextBundleRecord(
            bundle_id="ctx-1",
            session_id="sess-1",
            task_id="task-1",
            token_budget=1000,
            rendered_text="# Context",
            sections=[{"name": "Task State", "content": "task-1"}],
            source_refs=["memory://fact-1"],
            checksum="abc123",
        )
    )

    assert fact.fact_id == "fact-1"
    assert bundle.bundle_id == "ctx-1"
    assert (await store.get_session("sess-1")) is not None

    with sqlite3.connect(db_path) as db:
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        journal_mode = str(db.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    assert journal_mode == "wal"
    assert {"sessions", "task_claims", "delegation_runs", "context_bundles"} <= tables
    assert "event_log" in tables


@pytest.mark.asyncio
async def test_runtime_state_updates_memory_fact_truth(tmp_path) -> None:
    store = RuntimeStateStore(tmp_path / "runtime.db")
    await store.init_db()

    created = await store.record_memory_fact(
        MemoryFact(
            fact_id="fact-promote",
            fact_kind="lesson",
            truth_state="candidate",
            text="Operator-visible delivery ack prevents silent drop-off.",
            confidence=0.7,
            session_id="sess-2",
            task_id="task-2",
        )
    )
    updated = await store.update_memory_fact_truth(
        created.fact_id,
        truth_state="promoted",
        confidence=0.9,
        metadata={"promoted_by": "operator"},
    )
    facts = await store.list_memory_facts(
        session_id="sess-2",
        truth_state="promoted",
        limit=5,
    )

    assert updated.truth_state == "promoted"
    assert updated.confidence == 0.9
    assert updated.metadata["promoted_by"] == "operator"
    assert facts[0].fact_id == created.fact_id
    assert facts[0].updated_at >= datetime(2026, 1, 1, tzinfo=timezone.utc)
