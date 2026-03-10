"""Canonical runtime contract for DGC control-plane events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Any
from uuid import uuid4


RUNTIME_CONTRACT_VERSION = "1.0.0"


class RuntimeEventType(str, Enum):
    STATE_SNAPSHOT = "state.snapshot"
    MEMORY_EVENT = "memory.event"
    ACTION_EVENT = "action.event"
    AUDIT_EVENT = "audit.event"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RuntimeEnvelope:
    contract_version: str
    event_id: str
    event_type: str
    emitted_at: str
    source: str
    agent_id: str
    session_id: str
    trace_id: str
    payload: dict[str, Any]
    checksum: str

    @classmethod
    def create(
        cls,
        *,
        event_type: RuntimeEventType,
        source: str,
        agent_id: str,
        session_id: str,
        payload: dict[str, Any],
        trace_id: str | None = None,
        emitted_at: str | None = None,
        event_id: str | None = None,
    ) -> "RuntimeEnvelope":
        ts = emitted_at or _utc_now_iso()
        eid = event_id or f"evt_{uuid4().hex}"
        tid = trace_id or f"trc_{uuid4().hex}"
        base = {
            "contract_version": RUNTIME_CONTRACT_VERSION,
            "event_id": eid,
            "event_type": event_type.value,
            "emitted_at": ts,
            "source": source,
            "agent_id": agent_id,
            "session_id": session_id,
            "trace_id": tid,
            "payload": payload,
        }
        checksum = _sha256(_canonical_json(base))
        return cls(**base, checksum=checksum)

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "emitted_at": self.emitted_at,
            "source": self.source,
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "payload": self.payload,
            "checksum": self.checksum,
        }


def _validate_common_fields(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("contract_version") != RUNTIME_CONTRACT_VERSION:
        errors.append("contract_version mismatch")
    for key in (
        "event_id",
        "emitted_at",
        "source",
        "agent_id",
        "session_id",
        "trace_id",
        "checksum",
    ):
        if not _is_non_empty_str(data.get(key)):
            errors.append(f"{key} must be a non-empty string")
    if not isinstance(data.get("payload"), dict):
        errors.append("payload must be an object")
    if not _is_non_empty_str(data.get("event_type")):
        errors.append("event_type must be a non-empty string")
    return errors


def _validate_payload(event_type: str, payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if event_type == RuntimeEventType.STATE_SNAPSHOT.value:
        for key in ("cycle_count", "uptime_seconds", "runtime_mode", "status"):
            if key not in payload:
                errors.append(f"state payload missing '{key}'")
        if "cycle_count" in payload and not isinstance(payload["cycle_count"], int):
            errors.append("state payload cycle_count must be int")
        if "uptime_seconds" in payload and not isinstance(payload["uptime_seconds"], int):
            errors.append("state payload uptime_seconds must be int")
    elif event_type == RuntimeEventType.MEMORY_EVENT.value:
        for key in ("memory_id", "memory_type", "importance", "summary"):
            if key not in payload:
                errors.append(f"memory payload missing '{key}'")
        if "importance" in payload and not isinstance(payload["importance"], int):
            errors.append("memory payload importance must be int")
    elif event_type == RuntimeEventType.ACTION_EVENT.value:
        for key in ("action_name", "decision", "confidence"):
            if key not in payload:
                errors.append(f"action payload missing '{key}'")
        if "confidence" in payload and not isinstance(payload["confidence"], (int, float)):
            errors.append("action payload confidence must be numeric")
    elif event_type == RuntimeEventType.AUDIT_EVENT.value:
        for key in ("gate", "result", "reason"):
            if key not in payload:
                errors.append(f"audit payload missing '{key}'")
    else:
        errors.append(f"unsupported event_type '{event_type}'")
    return errors


def _validate_checksum(data: dict[str, Any]) -> bool:
    material = {
        "contract_version": data.get("contract_version"),
        "event_id": data.get("event_id"),
        "event_type": data.get("event_type"),
        "emitted_at": data.get("emitted_at"),
        "source": data.get("source"),
        "agent_id": data.get("agent_id"),
        "session_id": data.get("session_id"),
        "trace_id": data.get("trace_id"),
        "payload": data.get("payload"),
    }
    expected = _sha256(_canonical_json(material))
    return data.get("checksum") == expected


def validate_envelope(data: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate runtime envelope shape, payload, and checksum."""
    errors = _validate_common_fields(data)
    payload = data.get("payload")
    event_type = str(data.get("event_type") or "")
    if isinstance(payload, dict) and event_type:
        errors.extend(_validate_payload(event_type, payload))
    if not errors and not _validate_checksum(data):
        errors.append("checksum mismatch")
    return (len(errors) == 0, errors)
