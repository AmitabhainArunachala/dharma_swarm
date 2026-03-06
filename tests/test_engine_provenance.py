"""Tests for dharma_swarm.engine.provenance."""

from __future__ import annotations

from pathlib import Path

from dharma_swarm.engine.events import CanonicalEvent, EventType
from dharma_swarm.engine.provenance import ProvenanceEntry, ProvenanceLogger


def test_append_and_read_entries(tmp_path: Path):
    logger = ProvenanceLogger(base_dir=tmp_path / "workspace" / "sessions")
    entry = ProvenanceEntry(
        event="artifact_created",
        artifact_id="a1",
        agent="builder",
        session_id="sess-1",
        inputs=["plan-1"],
        outputs=["artifact-a1"],
        confidence=0.7,
    )
    logger.append(entry)

    rows = logger.read("sess-1")
    assert len(rows) == 1
    assert rows[0].event == "artifact_created"
    assert rows[0].artifact_id == "a1"
    assert rows[0].agent == "builder"
    assert rows[0].confidence == 0.7


def test_append_event_bridge_from_canonical_event(tmp_path: Path):
    logger = ProvenanceLogger(base_dir=tmp_path / "workspace" / "sessions")
    event = CanonicalEvent(
        event_type=EventType.ARTIFACT_VERIFIED,
        source_agent="verifier",
        session_id="sess-2",
        artifact_id="a2",
        metadata={"confidence": 0.95, "citations": ["doi:10.1/x"]},
    )
    logger.append_event(event)

    rows = logger.read("sess-2")
    assert len(rows) == 1
    assert rows[0].event == "artifact_verified"
    assert rows[0].artifact_id == "a2"
    assert rows[0].agent == "verifier"
    assert rows[0].citations == ["doi:10.1/x"]


def test_read_missing_session_is_empty(tmp_path: Path):
    logger = ProvenanceLogger(base_dir=tmp_path / "workspace" / "sessions")
    assert logger.read("missing") == []


def test_read_limit_returns_tail(tmp_path: Path):
    logger = ProvenanceLogger(base_dir=tmp_path / "workspace" / "sessions")
    for i in range(5):
        logger.append(
            ProvenanceEntry(
                event="artifact_updated",
                artifact_id=f"a{i}",
                agent="builder",
                session_id="sess-limit",
            )
        )

    rows = logger.read("sess-limit", limit=2)
    assert len(rows) == 2
    assert rows[0].artifact_id == "a3"
    assert rows[1].artifact_id == "a4"
