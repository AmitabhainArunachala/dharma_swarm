"""Canonical bridge from session lifecycle events to runtime envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from pathlib import Path
from typing import Any

from dharma_swarm.runtime_contract import (
    RuntimeEnvelope,
    RuntimeEventType,
    validate_envelope,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionEventType(str, Enum):
    START = "session_start"
    INTERACTION = "session_interaction"
    END = "session_end"
    FAILURE = "session_failure"


@dataclass(frozen=True)
class SessionEvent:
    event_type: SessionEventType
    session_id: str
    timestamp: str
    significance_score: float
    content_hash: str
    metadata: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            "significance_score": self.significance_score,
            "content_hash": self.content_hash,
            "metadata": self.metadata,
        }


class SessionEventBridge:
    """Translate session events into validated runtime envelopes."""

    def __init__(
        self,
        *,
        runtime_log_path: Path,
        significance_threshold: float = 0.6,
        runtime_source: str = "tui.session_bridge",
        runtime_agent_id: str = "dgc_tui",
    ) -> None:
        self.runtime_log_path = runtime_log_path
        self.runtime_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.significance_threshold = significance_threshold
        self.runtime_source = runtime_source
        self.runtime_agent_id = runtime_agent_id
        self.active_sessions: dict[str, dict[str, Any]] = {}

    def session_start(self, session_id: str, context: dict[str, Any]) -> dict[str, Any] | None:
        serialized_context = json.dumps(
            context,
            sort_keys=True,
            ensure_ascii=True,
            default=str,
        )
        self.active_sessions[session_id] = {
            "started_at": _utc_now_iso(),
            "context": dict(context),
            "interactions": 0,
            "significant_interactions": 0,
        }
        event = SessionEvent(
            event_type=SessionEventType.START,
            session_id=session_id,
            timestamp=_utc_now_iso(),
            significance_score=0.5,
            content_hash=self._compute_hash(serialized_context),
            metadata=dict(context),
        )
        return self._emit_runtime_envelope(event, serialized_context)

    def session_interaction(
        self,
        session_id: str,
        *,
        content: str,
        significance: float,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if session_id not in self.active_sessions:
            self.session_start(session_id, {"auto_started": True})

        self.active_sessions[session_id]["interactions"] += 1
        if significance < self.significance_threshold:
            return None

        self.active_sessions[session_id]["significant_interactions"] += 1
        event = SessionEvent(
            event_type=SessionEventType.INTERACTION,
            session_id=session_id,
            timestamp=_utc_now_iso(),
            significance_score=float(significance),
            content_hash=self._compute_hash(content),
            metadata=metadata or {},
        )
        return self._emit_runtime_envelope(event, content)

    def session_end(
        self,
        session_id: str,
        *,
        outcome: str,
        summary: str = "",
    ) -> dict[str, Any] | None:
        session_data = self.active_sessions.pop(session_id, {})
        total_interactions = int(session_data.get("interactions", 0) or 0)
        significant_interactions = int(session_data.get("significant_interactions", 0) or 0)
        significance = significant_interactions / max(total_interactions, 1)
        event = SessionEvent(
            event_type=SessionEventType.END,
            session_id=session_id,
            timestamp=_utc_now_iso(),
            significance_score=significance,
            content_hash=self._compute_hash(summary),
            metadata={
                "outcome": outcome,
                "total_interactions": total_interactions,
                "significant_interactions": significant_interactions,
                "duration_seconds": self._compute_duration_seconds(session_data),
            },
        )
        return self._emit_runtime_envelope(event, summary)

    def session_failure(
        self,
        session_id: str,
        *,
        error_type: str,
        error_message: str,
        recoverable: bool = True,
    ) -> dict[str, Any] | None:
        event = SessionEvent(
            event_type=SessionEventType.FAILURE,
            session_id=session_id,
            timestamp=_utc_now_iso(),
            significance_score=1.0,
            content_hash=self._compute_hash(error_message),
            metadata={
                "error_type": error_type,
                "recoverable": recoverable,
            },
        )
        return self._emit_runtime_envelope(event, error_message)

    def record_canonical_event(self, event: Any) -> dict[str, Any] | None:
        event_type = str(getattr(event, "type", "") or "")
        session_id = str(getattr(event, "session_id", "") or "")
        if not event_type or not session_id:
            return None

        if event_type == "error":
            return self.session_failure(
                session_id,
                error_type=str(getattr(event, "code", "") or "error"),
                error_message=str(getattr(event, "message", "") or ""),
                recoverable=bool(getattr(event, "retryable", False)),
            )

        interaction = self._canonical_interaction(event)
        if interaction is None:
            return None
        content, significance, metadata = interaction
        return self.session_interaction(
            session_id,
            content=content,
            significance=significance,
            metadata=metadata,
        )

    def _canonical_interaction(
        self,
        event: Any,
    ) -> tuple[str, float, dict[str, Any]] | None:
        event_type = str(getattr(event, "type", "") or "")
        provider_id = str(getattr(event, "provider_id", "") or "")
        metadata: dict[str, Any] = {
            "canonical_event_type": event_type,
            "provider_id": provider_id,
        }

        if event_type == "text_complete":
            role = str(getattr(event, "role", "") or "")
            if role != "assistant":
                return None
            content = str(getattr(event, "content", "") or "")
            significance = 0.65
            if len(content) >= 120:
                significance += 0.10
            if len(content) >= 400:
                significance += 0.10
            metadata["role"] = role
            return (content, min(significance, 1.0), metadata)

        if event_type == "tool_call_complete":
            tool_name = str(getattr(event, "tool_name", "") or "")
            content = str(getattr(event, "arguments", "") or tool_name)
            metadata["tool_name"] = tool_name
            metadata["tool_call_id"] = str(getattr(event, "tool_call_id", "") or "")
            return (content, 0.8, metadata)

        if event_type == "tool_result":
            tool_name = str(getattr(event, "tool_name", "") or "")
            content = str(getattr(event, "content", "") or tool_name)
            metadata["tool_name"] = tool_name
            metadata["tool_call_id"] = str(getattr(event, "tool_call_id", "") or "")
            metadata["is_error"] = bool(getattr(event, "is_error", False))
            significance = 0.9 if metadata["is_error"] else 0.75
            return (content, significance, metadata)

        if event_type == "task_complete":
            summary = str(getattr(event, "summary", "") or "")
            metadata["task_id"] = str(getattr(event, "task_id", "") or "")
            metadata["success"] = bool(getattr(event, "success", True))
            significance = 0.85 if metadata["success"] else 0.95
            return (summary, significance, metadata)

        return None

    def _emit_runtime_envelope(
        self,
        event: SessionEvent,
        content: str,
    ) -> dict[str, Any] | None:
        payload_spec = self._runtime_payload(event, content)
        if payload_spec is None:
            return None
        runtime_event_type, payload = payload_spec
        envelope = RuntimeEnvelope.create(
            event_type=runtime_event_type,
            source=self.runtime_source,
            agent_id=self.runtime_agent_id,
            session_id=event.session_id,
            payload=payload,
        )
        data = envelope.as_dict()
        ok, errors = validate_envelope(data)
        if not ok:
            raise ValueError(f"invalid runtime envelope: {errors}")
        with self.runtime_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=True) + "\n")
        return data

    def _runtime_payload(
        self,
        event: SessionEvent,
        content: str,
    ) -> tuple[RuntimeEventType, dict[str, Any]] | None:
        if event.event_type == SessionEventType.FAILURE:
            error_type = str(event.metadata.get("error_type", "session_failure"))
            reason = f"{error_type}: {content[:240]}".strip(": ")
            return (
                RuntimeEventType.AUDIT_EVENT,
                {
                    "gate": "session_bridge",
                    "result": "warn" if bool(event.metadata.get("recoverable", True)) else "fail",
                    "reason": reason or error_type,
                },
            )

        decision = "recorded"
        if event.event_type == SessionEventType.START:
            decision = "started"
        elif event.event_type == SessionEventType.INTERACTION:
            decision = "significant_recorded"
        elif event.event_type == SessionEventType.END:
            decision = str(event.metadata.get("outcome", "ended"))

        return (
            RuntimeEventType.ACTION_EVENT,
            {
                "action_name": event.event_type.value,
                "decision": decision,
                "confidence": float(event.significance_score),
                "content_hash": event.content_hash,
            },
        )

    @staticmethod
    def _compute_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _compute_duration_seconds(session_data: dict[str, Any]) -> float | None:
        started_at = str(session_data.get("started_at", "") or "")
        if not started_at:
            return None
        try:
            started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        return (datetime.now(timezone.utc) - started).total_seconds()
