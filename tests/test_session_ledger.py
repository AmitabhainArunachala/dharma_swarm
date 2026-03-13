"""Tests for session-scoped JSONL ledgers."""

import json

from dharma_swarm.runtime_state import RuntimeStateStore
from dharma_swarm.session_ledger import SessionLedger


def test_session_ledger_writes_task_and_progress(tmp_path):
    ledger = SessionLedger(base_dir=tmp_path, session_id="sess_a")

    ledger.task_event("dispatch_assigned", task_id="t1", agent_id="a1")
    ledger.progress_event("task_started", task_id="t1", agent_id="a1")

    task_path = tmp_path / "sess_a" / "task_ledger.jsonl"
    progress_path = tmp_path / "sess_a" / "progress_ledger.jsonl"
    assert task_path.exists()
    assert progress_path.exists()

    task_row = json.loads(task_path.read_text().strip())
    progress_row = json.loads(progress_path.read_text().strip())
    assert task_row["event"] == "dispatch_assigned"
    assert progress_row["event"] == "task_started"
    assert task_row["session_id"] == "sess_a"
    assert progress_row["session_id"] == "sess_a"


def test_session_ledger_uses_env_dir_and_session(tmp_path, monkeypatch):
    monkeypatch.setenv("DGC_LEDGER_DIR", str(tmp_path))
    monkeypatch.setenv("DGC_SESSION_ID", "sess_env")
    ledger = SessionLedger()
    ledger.task_event("dispatch_blocked", task_id="t2", reason="blocked")

    task_path = tmp_path / "sess_env" / "task_ledger.jsonl"
    assert task_path.exists()


def test_session_ledger_updates_runtime_search_index(tmp_path):
    runtime_db = tmp_path / "runtime.db"
    ledger = SessionLedger(base_dir=tmp_path, session_id="sess_idx", runtime_db_path=runtime_db)

    ledger.progress_event(
        "task_failed",
        task_id="t9",
        agent_id="worker-loop",
        failure_signature="provider_timeout",
        summary="provider timeout on fallback lane",
    )

    hits = RuntimeStateStore(runtime_db).search_session_events_sync("provider timeout")

    assert len(hits) == 1
    assert hits[0].session_id == "sess_idx"
    assert hits[0].ledger_kind == "progress"
    assert hits[0].event_name == "task_failed"
