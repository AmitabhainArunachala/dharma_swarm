"""Tests for dharma_swarm.engine.events."""

from __future__ import annotations

from dharma_swarm.engine.events import CanonicalEvent, EventType


def test_event_type_count_is_17():
    assert len(list(EventType)) == 17


def test_canonical_event_roundtrip_dict():
    event = CanonicalEvent(
        event_type=EventType.ARTIFACT_CREATED,
        source_agent="builder",
        target_agent="verifier",
        session_id="sess-1",
        artifact_id="abc",
        payload={"path": "workspace/s1/artifacts/code/a.py"},
        metadata={"confidence": 0.9, "inputs": ["plan-1"]},
    )
    loaded = CanonicalEvent.from_dict(event.to_dict())

    assert loaded.event_type == EventType.ARTIFACT_CREATED
    assert loaded.source_agent == "builder"
    assert loaded.target_agent == "verifier"
    assert loaded.session_id == "sess-1"
    assert loaded.artifact_id == "abc"
    assert loaded.payload["path"].endswith("a.py")
    assert loaded.metadata["confidence"] == 0.9


def test_canonical_event_from_dict_defaults():
    event = CanonicalEvent.from_dict({"event_type": "session_start"})
    assert event.event_type == EventType.SESSION_START
    assert event.event_id
    assert event.payload == {}
    assert event.metadata == {}


def test_canonical_event_ids_are_unique():
    a = CanonicalEvent(event_type=EventType.SESSION_START)
    b = CanonicalEvent(event_type=EventType.SESSION_START)
    assert a.event_id != b.event_id


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------

from datetime import datetime, timezone


def test_to_dict_from_dict_full_roundtrip_preserves_timestamp():
    """Round-trip must preserve the exact timestamp (ISO-format fidelity)."""
    original = CanonicalEvent(
        event_type=EventType.EVAL_COMPLETED,
        source_agent="evaluator",
        target_agent="orchestrator",
        session_id="sess-rt",
        artifact_id="art-99",
        payload={"score": 0.88, "nested": {"a": [1, 2, 3]}},
        metadata={"tag": "deep"},
    )
    d = original.to_dict()
    restored = CanonicalEvent.from_dict(d)

    assert restored.event_type == original.event_type
    assert restored.timestamp == original.timestamp
    assert restored.event_id == original.event_id
    assert restored.source_agent == original.source_agent
    assert restored.target_agent == original.target_agent
    assert restored.session_id == original.session_id
    assert restored.artifact_id == original.artifact_id
    assert restored.payload == original.payload
    assert restored.metadata == original.metadata


def test_to_dict_returns_plain_types():
    """to_dict output must be JSON-safe: no Enum members, no datetime objects."""
    event = CanonicalEvent(
        event_type=EventType.KNOWLEDGE_EXTRACTED,
        source_agent="miner",
        session_id="s1",
    )
    d = event.to_dict()

    assert isinstance(d["event_type"], str)
    assert isinstance(d["timestamp"], str)
    assert isinstance(d["payload"], dict)
    assert isinstance(d["metadata"], dict)
    assert d["event_type"] == "knowledge_extracted"


def test_from_dict_empty_dict_uses_defaults():
    """Completely empty dict should still produce a valid event."""
    event = CanonicalEvent.from_dict({})
    # Default event_type is TASK_FAILED per source line 85
    assert event.event_type == EventType.TASK_FAILED
    assert event.event_id  # non-empty UUID hex
    assert event.source_agent == ""
    assert event.target_agent == ""
    assert event.session_id == ""
    assert event.artifact_id is None
    assert event.payload == {}
    assert event.metadata == {}
    # timestamp should be close to now
    delta = (datetime.now(timezone.utc) - event.timestamp).total_seconds()
    assert abs(delta) < 5


def test_from_dict_partial_fields_preserve_given_values():
    """Only supply a subset of fields; others should get safe defaults."""
    data = {
        "event_type": "session_end",
        "source_agent": "cleanup-agent",
        "payload": {"reason": "timeout"},
    }
    event = CanonicalEvent.from_dict(data)

    assert event.event_type == EventType.SESSION_END
    assert event.source_agent == "cleanup-agent"
    assert event.payload == {"reason": "timeout"}
    assert event.target_agent == ""
    assert event.session_id == ""
    assert event.artifact_id is None
    assert event.metadata == {}


def test_from_dict_ignores_non_string_timestamp():
    """If timestamp is not a string (e.g. int), from_dict falls back to utcnow."""
    data = {"event_type": "session_start", "timestamp": 12345}
    event = CanonicalEvent.from_dict(data)
    delta = (datetime.now(timezone.utc) - event.timestamp).total_seconds()
    assert abs(delta) < 5


def test_from_dict_with_explicit_event_id():
    """Supplying event_id in the dict must be respected (no re-generation)."""
    data = {"event_type": "task_assigned", "event_id": "my-custom-id-42"}
    event = CanonicalEvent.from_dict(data)
    assert event.event_id == "my-custom-id-42"


def test_event_type_enum_has_at_least_15_members():
    """Guard against accidental removal of enum members."""
    assert len(EventType) >= 15


def test_event_type_enum_expected_members():
    """Spot-check that key categories of events exist."""
    names = {e.name for e in EventType}
    expected = {
        "SESSION_START",
        "SESSION_END",
        "TASK_ASSIGNED",
        "TASK_COMPLETED",
        "TASK_FAILED",
        "ARTIFACT_CREATED",
        "ARTIFACT_UPDATED",
        "ARTIFACT_VERIFIED",
        "ARTIFACT_REJECTED",
        "ARTIFACT_ARCHIVED",
        "KNOWLEDGE_EXTRACTED",
        "KNOWLEDGE_CONFLICT",
        "KNOWLEDGE_SUPERSEDED",
        "EVAL_STARTED",
        "EVAL_COMPLETED",
        "HUMAN_REVIEW_REQUESTED",
        "HUMAN_REVIEW_COMPLETED",
    }
    assert expected.issubset(names)


def test_event_type_is_str_enum():
    """EventType members should also be usable as plain strings."""
    assert EventType.TASK_COMPLETED == "task_completed"
    assert isinstance(EventType.TASK_COMPLETED, str)


def test_20_event_ids_all_unique():
    """Create 20 events and verify every event_id is distinct."""
    events = [CanonicalEvent(event_type=EventType.SESSION_START) for _ in range(20)]
    ids = [e.event_id for e in events]
    assert len(set(ids)) == 20


def test_roundtrip_with_none_artifact_id():
    """artifact_id=None must survive the round-trip as None."""
    event = CanonicalEvent(
        event_type=EventType.TASK_ASSIGNED,
        source_agent="planner",
        session_id="s1",
        artifact_id=None,
    )
    restored = CanonicalEvent.from_dict(event.to_dict())
    assert restored.artifact_id is None


def test_roundtrip_preserves_nested_payload():
    """Deeply nested payload dicts must survive serialization."""
    payload = {
        "level1": {
            "level2": {
                "level3": [1, 2, {"level4": True}],
            },
        },
        "tags": ["a", "b", "c"],
    }
    event = CanonicalEvent(
        event_type=EventType.ARTIFACT_CREATED,
        payload=payload,
    )
    restored = CanonicalEvent.from_dict(event.to_dict())
    assert restored.payload == payload


def test_each_event_type_value_is_unique():
    """No two enum members should share the same string value."""
    values = [e.value for e in EventType]
    assert len(values) == len(set(values))
