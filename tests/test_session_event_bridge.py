from __future__ import annotations

import json

from dharma_swarm.runtime_contract import RuntimeEventType, validate_envelope
from dharma_swarm.session_event_bridge import SessionEventBridge
from dharma_swarm.tui.engine.events import ErrorEvent, TextComplete


def _load_runtime_rows(path):
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def test_session_start_emits_valid_runtime_action_event(tmp_path) -> None:
    path = tmp_path / "runtime.jsonl"
    bridge = SessionEventBridge(runtime_log_path=path)
    envelope = bridge.session_start(
        "sess-start-1",
        {"task": "integration", "model_id": "test-model"},
    )

    assert envelope is not None
    ok, errors = validate_envelope(envelope)
    assert ok is True, errors
    assert envelope["event_type"] == RuntimeEventType.ACTION_EVENT.value
    assert envelope["payload"]["action_name"] == "session_start"
    assert envelope["payload"]["decision"] == "started"
    assert len(_load_runtime_rows(path)) == 1


def test_low_significance_interaction_is_filtered(tmp_path) -> None:
    path = tmp_path / "runtime.jsonl"
    bridge = SessionEventBridge(runtime_log_path=path, significance_threshold=0.8)
    bridge.session_start("sess-low", {"task": "filter"})
    result = bridge.session_interaction(
        "sess-low",
        content="small update",
        significance=0.4,
    )

    assert result is None
    assert len(_load_runtime_rows(path)) == 1


def test_session_failure_maps_to_audit_event(tmp_path) -> None:
    path = tmp_path / "runtime.jsonl"
    bridge = SessionEventBridge(runtime_log_path=path)
    envelope = bridge.session_failure(
        "sess-fail",
        error_type="timeout_error",
        error_message="tool execution timed out",
        recoverable=False,
    )

    assert envelope is not None
    ok, errors = validate_envelope(envelope)
    assert ok is True, errors
    assert envelope["event_type"] == RuntimeEventType.AUDIT_EVENT.value
    assert envelope["payload"]["gate"] == "session_bridge"
    assert envelope["payload"]["result"] == "fail"
    assert "timeout_error" in envelope["payload"]["reason"]


def test_record_canonical_event_bridges_assistant_completion(tmp_path) -> None:
    path = tmp_path / "runtime.jsonl"
    bridge = SessionEventBridge(runtime_log_path=path)
    bridge.session_start("sess-canon", {"task": "assistant"})
    envelope = bridge.record_canonical_event(
        TextComplete(
            provider_id="claude",
            session_id="sess-canon",
            content="Long enough assistant message to count as a significant interaction.",
            role="assistant",
        )
    )

    assert envelope is not None
    ok, errors = validate_envelope(envelope)
    assert ok is True, errors
    assert envelope["payload"]["action_name"] == "session_interaction"


def test_record_canonical_error_bridges_failure(tmp_path) -> None:
    path = tmp_path / "runtime.jsonl"
    bridge = SessionEventBridge(runtime_log_path=path)
    bridge.session_start("sess-err", {"task": "assistant"})
    envelope = bridge.record_canonical_event(
        ErrorEvent(
            provider_id="claude",
            session_id="sess-err",
            code="rate_limit",
            message="too many requests",
            retryable=True,
        )
    )

    assert envelope is not None
    assert envelope["event_type"] == RuntimeEventType.AUDIT_EVENT.value
    assert envelope["payload"]["result"] == "warn"
