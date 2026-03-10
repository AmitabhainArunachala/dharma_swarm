from __future__ import annotations

from dharma_swarm.runtime_contract import (
    RUNTIME_CONTRACT_VERSION,
    RuntimeEnvelope,
    RuntimeEventType,
    validate_envelope,
)


def test_create_and_validate_state_snapshot() -> None:
    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.STATE_SNAPSHOT,
        source="unified_daemon",
        agent_id="main",
        session_id="main",
        payload={
            "cycle_count": 12,
            "uptime_seconds": 900,
            "runtime_mode": "autonomous",
            "status": "healthy",
        },
    )
    ok, errors = validate_envelope(event.as_dict())
    assert ok is True
    assert errors == []


def test_create_and_validate_memory_event() -> None:
    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.MEMORY_EVENT,
        source="agentic_memory_fabric",
        agent_id="swarm_orchestrator",
        session_id="cycle-1",
        payload={
            "memory_id": "mem_123",
            "memory_type": "insight",
            "importance": 8,
            "summary": "Detected regression in recall path.",
        },
    )
    ok, errors = validate_envelope(event.as_dict())
    assert ok is True
    assert errors == []


def test_action_event_requires_confidence() -> None:
    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.ACTION_EVENT,
        source="reflex_layer",
        agent_id="main",
        session_id="main",
        payload={
            "action_name": "apply_patch",
            "decision": "approve",
            "confidence": 0.92,
        },
    )
    ok, errors = validate_envelope(event.as_dict())
    assert ok is True
    assert errors == []


def test_tamper_detected_by_checksum() -> None:
    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.AUDIT_EVENT,
        source="unified_gates",
        agent_id="main",
        session_id="main",
        payload={
            "gate": "AHIMSA",
            "result": "pass",
            "reason": "No harm pattern detected",
        },
    )
    tampered = event.as_dict()
    tampered["payload"]["result"] = "fail"
    ok, errors = validate_envelope(tampered)
    assert ok is False
    assert "checksum mismatch" in errors


def test_invalid_contract_version_fails() -> None:
    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.AUDIT_EVENT,
        source="unified_gates",
        agent_id="main",
        session_id="main",
        payload={
            "gate": "SATYA",
            "result": "warn",
            "reason": "Low evidence confidence",
        },
    )
    data = event.as_dict()
    data["contract_version"] = "0.9.0"
    ok, errors = validate_envelope(data)
    assert ok is False
    assert "contract_version mismatch" in errors


def test_missing_required_payload_fields_fail() -> None:
    event = RuntimeEnvelope.create(
        event_type=RuntimeEventType.STATE_SNAPSHOT,
        source="unified_daemon",
        agent_id="main",
        session_id="main",
        payload={
            "cycle_count": 2,
            "status": "healthy",
        },
    )
    ok, errors = validate_envelope(event.as_dict())
    assert ok is False
    assert any("state payload missing" in item for item in errors)


def test_contract_version_constant() -> None:
    assert RUNTIME_CONTRACT_VERSION == "1.0.0"
