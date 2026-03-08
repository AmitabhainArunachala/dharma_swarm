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


# ---------------------------------------------------------------------------
# Additional tests
# ---------------------------------------------------------------------------

import json
import pytest
from datetime import datetime, timezone


# --- ProvenanceEntry unit tests ---


def test_provenance_entry_to_dict_from_dict_roundtrip():
    """Full round-trip must preserve every field exactly."""
    entry = ProvenanceEntry(
        event="knowledge_extracted",
        artifact_id="art-7",
        agent="miner",
        session_id="sess-rt",
        inputs=["doc-1", "doc-2"],
        outputs=["graph-1"],
        citations=["doi:10.1/a", "doi:10.2/b"],
        confidence=0.82,
        metadata={"source": "arxiv", "pages": 12},
    )
    d = entry.to_dict()
    restored = ProvenanceEntry.from_dict(d)

    assert restored.event == entry.event
    assert restored.artifact_id == entry.artifact_id
    assert restored.agent == entry.agent
    assert restored.session_id == entry.session_id
    assert restored.inputs == entry.inputs
    assert restored.outputs == entry.outputs
    assert restored.citations == entry.citations
    assert restored.confidence == entry.confidence
    assert restored.metadata == entry.metadata
    assert restored.timestamp == entry.timestamp


def test_provenance_entry_to_dict_returns_plain_types():
    """to_dict output must be JSON-serializable (no datetime objects)."""
    entry = ProvenanceEntry(event="test_event", session_id="s1")
    d = entry.to_dict()

    assert isinstance(d["timestamp"], str)
    assert isinstance(d["inputs"], list)
    assert isinstance(d["outputs"], list)
    assert isinstance(d["citations"], list)
    assert isinstance(d["metadata"], dict)
    # Verify JSON round-trip works
    json_str = json.dumps(d)
    assert json.loads(json_str) == d


def test_provenance_entry_from_dict_empty_dict():
    """Empty dict should produce a valid entry with safe defaults."""
    entry = ProvenanceEntry.from_dict({})

    assert entry.event == ""
    assert entry.artifact_id == ""
    assert entry.agent == ""
    assert entry.session_id == ""
    assert entry.inputs == []
    assert entry.outputs == []
    assert entry.citations == []
    assert entry.confidence == 0.0
    assert entry.metadata == {}
    # timestamp should be close to now
    delta = (datetime.now(timezone.utc) - entry.timestamp).total_seconds()
    assert abs(delta) < 5


def test_provenance_entry_from_dict_partial_fields():
    """Supply only some fields; others should default safely."""
    data = {
        "event": "eval_started",
        "agent": "scorer",
        "confidence": 0.55,
    }
    entry = ProvenanceEntry.from_dict(data)

    assert entry.event == "eval_started"
    assert entry.agent == "scorer"
    assert entry.confidence == 0.55
    assert entry.artifact_id == ""
    assert entry.session_id == ""
    assert entry.inputs == []
    assert entry.outputs == []
    assert entry.citations == []


def test_provenance_entry_from_dict_ignores_non_string_timestamp():
    """Non-string timestamp should fall back to utcnow."""
    data = {"event": "test", "timestamp": 99999}
    entry = ProvenanceEntry.from_dict(data)
    delta = (datetime.now(timezone.utc) - entry.timestamp).total_seconds()
    assert abs(delta) < 5


def test_provenance_entry_from_dict_preserves_string_timestamp():
    """An ISO-format string timestamp must be parsed faithfully."""
    ts = datetime(2025, 6, 15, 12, 30, 0, tzinfo=timezone.utc)
    data = {"event": "test", "timestamp": ts.isoformat()}
    entry = ProvenanceEntry.from_dict(data)
    assert entry.timestamp == ts


# --- ProvenanceLogger unit tests ---


def test_append_raises_on_empty_session_id():
    """Appending an entry without session_id must raise ValueError."""
    logger = ProvenanceLogger(base_dir=Path("/tmp/unused"))
    entry = ProvenanceEntry(event="test", session_id="")
    with pytest.raises(ValueError, match="session_id is required"):
        logger.append(entry)


def test_log_path_structure(tmp_path: Path):
    """_log_path must produce base_dir/session_id/provenance/log.jsonl."""
    logger = ProvenanceLogger(base_dir=tmp_path)
    path = logger._log_path("my-session")
    expected = tmp_path / "my-session" / "provenance" / "log.jsonl"
    assert path == expected


def test_read_limit_zero_returns_all(tmp_path: Path):
    """limit=0 should behave the same as limit=None (return everything)."""
    logger = ProvenanceLogger(base_dir=tmp_path)
    for i in range(4):
        logger.append(
            ProvenanceEntry(
                event="tick",
                artifact_id=f"a{i}",
                session_id="sess-zero",
            )
        )
    rows = logger.read("sess-zero", limit=0)
    assert len(rows) == 4


def test_read_limit_exceeds_total_returns_all(tmp_path: Path):
    """limit larger than total entries should return everything."""
    logger = ProvenanceLogger(base_dir=tmp_path)
    for i in range(3):
        logger.append(
            ProvenanceEntry(event="tick", artifact_id=f"a{i}", session_id="sess-big")
        )
    rows = logger.read("sess-big", limit=100)
    assert len(rows) == 3


def test_multiple_sessions_are_isolated(tmp_path: Path):
    """Entries from different sessions must not leak across sessions."""
    logger = ProvenanceLogger(base_dir=tmp_path)
    logger.append(
        ProvenanceEntry(event="alpha", artifact_id="x1", session_id="sess-A")
    )
    logger.append(
        ProvenanceEntry(event="beta", artifact_id="x2", session_id="sess-B")
    )
    logger.append(
        ProvenanceEntry(event="gamma", artifact_id="x3", session_id="sess-A")
    )

    rows_a = logger.read("sess-A")
    rows_b = logger.read("sess-B")

    assert len(rows_a) == 2
    assert len(rows_b) == 1
    assert rows_a[0].event == "alpha"
    assert rows_a[1].event == "gamma"
    assert rows_b[0].event == "beta"


def test_append_creates_directories(tmp_path: Path):
    """Logger must create the full directory tree on first append."""
    logger = ProvenanceLogger(base_dir=tmp_path / "deep" / "nested")
    entry = ProvenanceEntry(event="init", session_id="new-session")
    logger.append(entry)

    log_path = tmp_path / "deep" / "nested" / "new-session" / "provenance" / "log.jsonl"
    assert log_path.exists()
    assert log_path.stat().st_size > 0


def test_append_event_bridge_transfers_inputs_outputs_citations(tmp_path: Path):
    """append_event must extract inputs, outputs, citations from metadata."""
    logger = ProvenanceLogger(base_dir=tmp_path)
    event = CanonicalEvent(
        event_type=EventType.ARTIFACT_CREATED,
        source_agent="builder",
        session_id="sess-bridge",
        artifact_id="art-1",
        metadata={
            "inputs": ["plan-1", "plan-2"],
            "outputs": ["code-1"],
            "citations": ["ref-a"],
            "confidence": 0.77,
            "extra": "kept",
        },
    )
    logger.append_event(event)

    rows = logger.read("sess-bridge")
    assert len(rows) == 1
    assert rows[0].inputs == ["plan-1", "plan-2"]
    assert rows[0].outputs == ["code-1"]
    assert rows[0].citations == ["ref-a"]
    assert rows[0].confidence == 0.77
    # Full metadata dict is also preserved
    assert rows[0].metadata["extra"] == "kept"


def test_append_event_bridge_with_none_artifact_id(tmp_path: Path):
    """When CanonicalEvent.artifact_id is None, entry should get empty string."""
    logger = ProvenanceLogger(base_dir=tmp_path)
    event = CanonicalEvent(
        event_type=EventType.TASK_COMPLETED,
        source_agent="worker",
        session_id="sess-none-art",
        artifact_id=None,
    )
    logger.append_event(event)

    rows = logger.read("sess-none-art")
    assert len(rows) == 1
    assert rows[0].artifact_id == ""


def test_append_event_preserves_canonical_timestamp(tmp_path: Path):
    """The provenance entry timestamp must match the source event timestamp."""
    logger = ProvenanceLogger(base_dir=tmp_path)
    event = CanonicalEvent(
        event_type=EventType.SESSION_START,
        source_agent="init",
        session_id="sess-ts",
    )
    logger.append_event(event)

    rows = logger.read("sess-ts")
    assert len(rows) == 1
    assert rows[0].timestamp == event.timestamp


def test_log_file_is_valid_jsonl(tmp_path: Path):
    """Each line in the log file must be independently parseable JSON."""
    logger = ProvenanceLogger(base_dir=tmp_path)
    for i in range(3):
        logger.append(
            ProvenanceEntry(
                event=f"step_{i}",
                session_id="sess-jsonl",
            )
        )

    log_path = logger._log_path("sess-jsonl")
    with log_path.open("r") as f:
        lines = [line.strip() for line in f if line.strip()]

    assert len(lines) == 3
    for line in lines:
        parsed = json.loads(line)
        assert "event" in parsed
        assert "timestamp" in parsed


def test_read_preserves_insertion_order(tmp_path: Path):
    """Entries must come back in the same order they were appended."""
    logger = ProvenanceLogger(base_dir=tmp_path)
    events = ["first", "second", "third", "fourth", "fifth"]
    for name in events:
        logger.append(
            ProvenanceEntry(event=name, session_id="sess-order")
        )

    rows = logger.read("sess-order")
    assert [r.event for r in rows] == events


def test_base_dir_as_string(tmp_path: Path):
    """ProvenanceLogger should accept a string path, not only Path objects."""
    logger = ProvenanceLogger(base_dir=str(tmp_path / "str-path"))
    entry = ProvenanceEntry(event="str_test", session_id="sess-str")
    logger.append(entry)

    rows = logger.read("sess-str")
    assert len(rows) == 1
    assert rows[0].event == "str_test"
