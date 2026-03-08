"""Tests for session-scoped JSONL ledgers."""

import json

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
