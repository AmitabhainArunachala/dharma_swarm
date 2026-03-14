"""Canonical event schema for provider-agnostic orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    """Normalized event taxonomy for cross-agent orchestration."""

    # Session lifecycle
    SESSION_START = "session_start"
    SESSION_END = "session_end"

    # Agent communication
    TASK_ASSIGNED = "task_assigned"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"

    # Artifact lifecycle
    ARTIFACT_CREATED = "artifact_created"
    ARTIFACT_UPDATED = "artifact_updated"
    ARTIFACT_VERIFIED = "artifact_verified"
    ARTIFACT_REJECTED = "artifact_rejected"
    ARTIFACT_ARCHIVED = "artifact_archived"

    # Knowledge operations
    KNOWLEDGE_EXTRACTED = "knowledge_extracted"
    KNOWLEDGE_CONFLICT = "knowledge_conflict"
    KNOWLEDGE_SUPERSEDED = "knowledge_superseded"

    # Evaluation
    EVAL_STARTED = "eval_started"
    EVAL_COMPLETED = "eval_completed"

    # Human-in-the-loop
    HUMAN_REVIEW_REQUESTED = "human_review_requested"
    HUMAN_REVIEW_COMPLETED = "human_review_completed"

    # Inter-loop signals (Strange Loop: shared downbeat)
    FITNESS_IMPROVED = "fitness_improved"
    FITNESS_DEGRADED = "fitness_degraded"
    ANOMALY_DETECTED = "anomaly_detected"
    CASCADE_EIGENFORM_DISTANCE = "cascade_eigenform_distance"
    GATE_REJECTION_SPIKE = "gate_rejection_spike"
    RECOGNITION_UPDATED = "recognition_updated"


@dataclass(slots=True)
class CanonicalEvent:
    """Provider-neutral event envelope."""

    event_type: EventType
    timestamp: datetime = field(default_factory=_utc_now)
    event_id: str = field(default_factory=lambda: uuid4().hex)
    source_agent: str = ""
    target_agent: str = ""
    session_id: str = ""
    artifact_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-safe representation."""
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp.isoformat(),
            "event_id": self.event_id,
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "session_id": self.session_id,
            "artifact_id": self.artifact_id,
            "payload": self.payload,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CanonicalEvent":
        """Rehydrate event from dict."""
        timestamp_raw = data.get("timestamp")
        timestamp = _utc_now()
        if isinstance(timestamp_raw, str):
            timestamp = datetime.fromisoformat(timestamp_raw)

        event_type_raw = data.get("event_type", EventType.TASK_FAILED.value)
        event_type = EventType(event_type_raw)

        return cls(
            event_type=event_type,
            timestamp=timestamp,
            event_id=str(data.get("event_id") or uuid4().hex),
            source_agent=str(data.get("source_agent", "")),
            target_agent=str(data.get("target_agent", "")),
            session_id=str(data.get("session_id", "")),
            artifact_id=data.get("artifact_id"),
            payload=dict(data.get("payload", {})),
            metadata=dict(data.get("metadata", {})),
        )

