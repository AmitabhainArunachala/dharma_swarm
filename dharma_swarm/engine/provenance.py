"""Append-only provenance logging for artifact and workflow events."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .events import CanonicalEvent


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ProvenanceEntry:
    """A single append-only provenance record."""

    event: str
    artifact_id: str = ""
    agent: str = ""
    session_id: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "event": self.event,
            "artifact_id": self.artifact_id,
            "agent": self.agent,
            "session_id": self.session_id,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "citations": list(self.citations),
            "confidence": self.confidence,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProvenanceEntry":
        ts_raw = data.get("timestamp")
        ts = _utc_now()
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw)
        return cls(
            event=str(data.get("event", "")),
            artifact_id=str(data.get("artifact_id", "")),
            agent=str(data.get("agent", "")),
            session_id=str(data.get("session_id", "")),
            inputs=list(data.get("inputs", [])),
            outputs=list(data.get("outputs", [])),
            citations=list(data.get("citations", [])),
            confidence=float(data.get("confidence", 0.0)),
            metadata=dict(data.get("metadata", {})),
            timestamp=ts,
        )


class ProvenanceLogger:
    """Append-only JSONL provenance log manager."""

    def __init__(self, base_dir: Path | str = Path("workspace") / "sessions") -> None:
        self.base_dir = Path(base_dir)

    def _log_path(self, session_id: str) -> Path:
        return self.base_dir / session_id / "provenance" / "log.jsonl"

    def append(self, entry: ProvenanceEntry) -> None:
        if not entry.session_id:
            raise ValueError("session_id is required for provenance entries")
        path = self._log_path(entry.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def append_event(self, event: CanonicalEvent) -> None:
        """Convenience bridge from CanonicalEvent to ProvenanceEntry."""
        entry = ProvenanceEntry(
            event=event.event_type.value,
            artifact_id=event.artifact_id or "",
            agent=event.source_agent,
            session_id=event.session_id,
            inputs=list(event.metadata.get("inputs", [])),
            outputs=list(event.metadata.get("outputs", [])),
            citations=list(event.metadata.get("citations", [])),
            confidence=float(event.metadata.get("confidence", 0.0)),
            metadata=dict(event.metadata),
            timestamp=event.timestamp,
        )
        self.append(entry)

    def read(self, session_id: str, limit: int | None = None) -> list[ProvenanceEntry]:
        path = self._log_path(session_id)
        if not path.exists():
            return []
        entries: list[ProvenanceEntry] = []
        with path.open("r") as f:
            for line in f:
                raw = line.strip()
                if raw:
                    entries.append(ProvenanceEntry.from_dict(json.loads(raw)))
        if limit is None or limit <= 0:
            return entries
        return entries[-limit:]

