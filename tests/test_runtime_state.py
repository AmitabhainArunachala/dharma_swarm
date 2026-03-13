from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import pytest

from dharma_swarm.runtime_state import (
    ContextBundleRecord,
    MemoryFact,
    RuntimeStateStore,
    SessionState,
    SessionEventRecord,
    build_session_event_from_ledger_record,
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


@pytest.mark.asyncio
async def test_runtime_state_records_and_searches_session_events(tmp_path) -> None:
    store = RuntimeStateStore(tmp_path / "runtime.db")
    await store.record_session_event(
        SessionEventRecord(
            event_id="sevt-1",
            session_id="sess-search",
            ledger_kind="progress",
            event_name="task_failed",
            task_id="task-9",
            agent_id="worker-loop",
            summary="provider timeout on fallback lane",
            event_text="task_failed task-9 worker-loop provider timeout on fallback lane",
            payload={"failure_signature": "provider_timeout"},
        )
    )

    hits = store.search_session_events_sync("provider timeout", session_id="sess-search")
    sessions = store.list_sessions_sync(limit=5)

    assert len(hits) == 1
    assert hits[0].event_name == "task_failed"
    assert hits[0].task_id == "task-9"
    assert sessions[0].session_id == "sess-search"


def test_runtime_state_indexes_historic_ledgers(tmp_path) -> None:
    ledger_base = tmp_path / "ledgers"
    session_dir = ledger_base / "sess-old"
    session_dir.mkdir(parents=True)
    task_record = {
        "ts_utc": "2026-03-13T08:38:16+00:00",
        "session_id": "sess-old",
        "event": "dispatch_assigned",
        "task_id": "task-1",
        "agent_id": "a1",
        "reason": "architectural pass",
    }
    progress_record = {
        "ts_utc": "2026-03-13T08:39:16+00:00",
        "session_id": "sess-old",
        "event": "task_failed",
        "task_id": "task-1",
        "failure_signature": "provider_timeout",
    }
    (session_dir / "task_ledger.jsonl").write_text(json.dumps(task_record) + "\n", encoding="utf-8")
    (session_dir / "progress_ledger.jsonl").write_text(json.dumps(progress_record) + "\n", encoding="utf-8")

    store = RuntimeStateStore(tmp_path / "runtime.db")
    sessions_scanned, events_scanned = store.index_ledgers_sync(ledger_base=ledger_base)
    hits = store.search_session_events_sync("provider timeout", session_id="sess-old")
    rebuilt = build_session_event_from_ledger_record(
        session_id="sess-old",
        ledger_kind="progress",
        record=progress_record,
    )

    assert sessions_scanned == 1
    assert events_scanned == 2
    assert len(hits) == 1
    assert hits[0].event_id == rebuilt.event_id
