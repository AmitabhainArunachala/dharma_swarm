from __future__ import annotations

from dharma_swarm.event_log import EventLog
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType


def test_event_log_appends_reads_and_verifies_runtime_stream(tmp_path) -> None:
    log = EventLog(tmp_path / "events")
    early = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="test.runtime",
        agent_id="agent-1",
        session_id="sess-1",
        trace_id="trace-1",
        event_id="evt-1",
        emitted_at="2026-03-10T00:00:00+00:00",
        payload={
            "action_name": "claim",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )
    late = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="test.runtime",
        agent_id="agent-1",
        session_id="sess-1",
        trace_id="trace-1",
        event_id="evt-2",
        emitted_at="2026-03-10T00:00:10+00:00",
        payload={
            "action_name": "acknowledge",
            "decision": "recorded",
            "confidence": 1.0,
        },
    )

    log.append_envelope(late)
    log.append_envelope(early)
    snapshot = log.append_snapshot({"status": "healthy", "cycle": 2})

    rows = log.read_envelopes(session_id="sess-1")
    newest = log.tail(limit=1)
    ok, errors = log.verify_stream()
    snapshot_ok, snapshot_errors = log.verify_snapshot_stream()

    assert [row["event_id"] for row in rows] == ["evt-1", "evt-2"]
    assert newest[0]["event_id"] == "evt-2"
    assert snapshot.state["cycle"] == 2
    assert ok is True
    assert errors == []
    assert snapshot_ok is True
    assert snapshot_errors == []
