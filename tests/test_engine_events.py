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
