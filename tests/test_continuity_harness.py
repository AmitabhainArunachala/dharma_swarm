from __future__ import annotations

import json

from dharma_swarm.continuity_harness import (
    append_snapshot,
    load_snapshots,
    verify_replay_integrity,
)


def test_append_and_load_snapshots(tmp_path) -> None:
    path = tmp_path / "snapshots.jsonl"
    append_snapshot(path, {"session_id": "s1", "status": "running"})
    append_snapshot(path, {"session_id": "s1", "status": "completed"})

    rows = load_snapshots(path)
    assert len(rows) == 2
    assert rows[0].state["status"] == "running"
    assert rows[1].state["status"] == "completed"

    ok, errors = verify_replay_integrity(path)
    assert ok is True
    assert errors == []


def test_verify_replay_integrity_detects_tamper(tmp_path) -> None:
    path = tmp_path / "snapshots.jsonl"
    record = append_snapshot(path, {"session_id": "s1", "status": "running"})
    tampered = record.as_dict()
    tampered["state"]["status"] = "corrupted"
    with path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(tampered) + "\n")

    ok, errors = verify_replay_integrity(path)
    assert ok is False
    assert any("checksum mismatch" in item for item in errors)
