"""JSON-ready approval payload builders for the shared operator core."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from dharma_swarm.tui.engine.events import PermissionDecisionEvent, PermissionOutcomeEvent, PermissionResolutionEvent, ToolCallComplete

from .adapters import permission_decision_from_tool_call
from .contracts import (
    CanonicalPermissionDecision,
    CanonicalPermissionOutcome,
    CanonicalPermissionResolution,
    PermissionOutcomeKind,
    PermissionResolutionKind,
)
from .permissions import GovernancePolicy
from .session_store import SessionStore

PERMISSION_PAYLOAD_VERSION = "v1"
PERMISSION_PAYLOAD_DOMAIN = "permission_decision"
PERMISSION_RESOLUTION_PAYLOAD_DOMAIN = "permission_resolution"
PERMISSION_OUTCOME_PAYLOAD_DOMAIN = "permission_outcome"
PERMISSION_HISTORY_PAYLOAD_DOMAIN = "permission_history"


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _clean_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in metadata.items() if value is not None}


def permission_decision_payload_from_decision(decision: CanonicalPermissionDecision) -> dict[str, Any]:
    """Convert a canonical permission decision into a shell-neutral JSON payload."""

    metadata = _clean_metadata(
        {
            **decision.metadata,
            "workspace_scope": decision.workspace_scope,
        }
    )
    return {
        "version": PERMISSION_PAYLOAD_VERSION,
        "domain": PERMISSION_PAYLOAD_DOMAIN,
        "action_id": decision.action_id,
        "tool_name": decision.tool_name,
        "risk": _enum_value(decision.risk),
        "decision": _enum_value(decision.decision),
        "rationale": decision.rationale,
        "policy_source": decision.policy_source,
        "requires_confirmation": decision.requires_confirmation,
        "command_prefix": decision.command_prefix,
        "metadata": metadata,
    }


def permission_resolution_payload_from_resolution(resolution: CanonicalPermissionResolution) -> dict[str, Any]:
    """Convert a canonical approval resolution into a shell-neutral JSON payload."""

    return {
        "version": PERMISSION_PAYLOAD_VERSION,
        "domain": PERMISSION_RESOLUTION_PAYLOAD_DOMAIN,
        "action_id": resolution.action_id,
        "resolution": _enum_value(resolution.resolution),
        "resolved_at": resolution.resolved_at,
        "actor": resolution.actor,
        "summary": resolution.summary,
        "note": resolution.note,
        "enforcement_state": resolution.enforcement_state,
        "metadata": _clean_metadata(resolution.metadata),
    }


def permission_outcome_payload_from_outcome(outcome: CanonicalPermissionOutcome) -> dict[str, Any]:
    """Convert a canonical approval outcome into a shell-neutral JSON payload."""

    return {
        "version": PERMISSION_PAYLOAD_VERSION,
        "domain": PERMISSION_OUTCOME_PAYLOAD_DOMAIN,
        "action_id": outcome.action_id,
        "outcome": _enum_value(outcome.outcome),
        "outcome_at": outcome.outcome_at,
        "source": outcome.source,
        "summary": outcome.summary,
        "metadata": _clean_metadata(outcome.metadata),
    }


def build_permission_decision_payload(
    event: ToolCallComplete,
    *,
    policy: GovernancePolicy | None = None,
    policy_source: str = "legacy-governance",
) -> dict[str, Any]:
    """Build a canonical approval payload from a legacy tool-call event."""

    decision = permission_decision_from_tool_call(event, policy=policy, policy_source=policy_source)
    return permission_decision_payload_from_decision(decision)


def build_permission_resolution_payload(
    *,
    action_id: str,
    resolution: str,
    actor: str = "operator",
    note: str | None = None,
    metadata: dict[str, Any] | None = None,
    enforcement_state: str = "recorded_only",
    resolved_at: str | None = None,
) -> dict[str, Any]:
    """Build a canonical approval resolution payload from operator action state."""

    resolved = CanonicalPermissionResolution(
        action_id=action_id,
        resolution=PermissionResolutionKind(resolution),
        resolved_at=resolved_at or datetime.now(timezone.utc).isoformat(),
        actor=actor,
        summary=f"{resolution.replace('_', ' ')} {action_id}",
        note=note.strip() if isinstance(note, str) and note.strip() else None,
        enforcement_state=enforcement_state,
        metadata=dict(metadata or {}),
    )
    return permission_resolution_payload_from_resolution(resolved)


def build_permission_outcome_payload(
    *,
    action_id: str,
    outcome: str,
    source: str = "runtime",
    metadata: dict[str, Any] | None = None,
    outcome_at: str | None = None,
) -> dict[str, Any]:
    """Build a canonical approval outcome payload from runtime state."""

    resolved = CanonicalPermissionOutcome(
        action_id=action_id,
        outcome=PermissionOutcomeKind(outcome),
        outcome_at=outcome_at or datetime.now(timezone.utc).isoformat(),
        source=source,
        summary=f"{outcome.replace('_', ' ')} {action_id}",
        metadata=dict(metadata or {}),
    )
    return permission_outcome_payload_from_outcome(resolved)


def _created_at(entry: dict[str, Any]) -> str:
    return str(entry.get("created_at", "") or "")


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _empty_permission_record(action_id: str, created_at: str) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "decision": None,
        "resolution": None,
        "outcome": None,
        "first_seen_at": created_at,
        "last_seen_at": created_at,
        "seen_count": 0,
    }


def _apply_permission_entry(
    entries_by_action_id: dict[str, dict[str, Any]],
    *,
    action_id: str,
    created_at: str,
    domain: str,
    payload_record: dict[str, Any],
) -> None:
    current = entries_by_action_id.setdefault(action_id, _empty_permission_record(action_id, created_at))
    current["seen_count"] = int(current.get("seen_count", 0) or 0) + 1
    if created_at and (
        not current.get("first_seen_at") or created_at < str(current.get("first_seen_at", ""))
    ):
        current["first_seen_at"] = created_at
    if created_at and created_at > str(current.get("last_seen_at", "") or ""):
        current["last_seen_at"] = created_at
    if domain == PERMISSION_PAYLOAD_DOMAIN:
        current["decision"] = payload_record
    elif domain == PERMISSION_RESOLUTION_PAYLOAD_DOMAIN:
        current["resolution"] = payload_record
    elif domain == PERMISSION_OUTCOME_PAYLOAD_DOMAIN:
        current["outcome"] = payload_record


def _legacy_permission_payload_from_audit(domain: str, audit: dict[str, Any]) -> dict[str, Any] | None:
    payload = audit.get("payload")
    payload_record = payload if isinstance(payload, dict) else {}
    action_id = _first_non_empty(audit.get("action_id"), payload_record.get("action_id"))
    if not action_id:
        return None
    if payload_record:
        return {
            "version": PERMISSION_PAYLOAD_VERSION,
            "domain": domain,
            **payload_record,
        }
    if domain == PERMISSION_PAYLOAD_DOMAIN:
        return {
            "version": PERMISSION_PAYLOAD_VERSION,
            "domain": PERMISSION_PAYLOAD_DOMAIN,
            "action_id": action_id,
            "tool_name": audit.get("tool_name"),
            "risk": audit.get("risk"),
            "decision": audit.get("decision"),
            "rationale": audit.get("rationale"),
            "policy_source": audit.get("policy_source"),
            "requires_confirmation": audit.get("requires_confirmation"),
            "command_prefix": audit.get("command_prefix"),
            "metadata": audit.get("metadata", {}),
        }
    if domain == PERMISSION_RESOLUTION_PAYLOAD_DOMAIN:
        return {
            "version": PERMISSION_PAYLOAD_VERSION,
            "domain": PERMISSION_RESOLUTION_PAYLOAD_DOMAIN,
            "action_id": action_id,
            "resolution": audit.get("resolution"),
            "resolved_at": audit.get("resolved_at"),
            "actor": audit.get("actor"),
            "summary": audit.get("summary"),
            "note": audit.get("note"),
            "enforcement_state": audit.get("enforcement_state"),
            "metadata": audit.get("metadata", {}),
        }
    if domain == PERMISSION_OUTCOME_PAYLOAD_DOMAIN:
        return {
            "version": PERMISSION_PAYLOAD_VERSION,
            "domain": PERMISSION_OUTCOME_PAYLOAD_DOMAIN,
            "action_id": action_id,
            "outcome": audit.get("outcome"),
            "outcome_at": audit.get("outcome_at") or audit.get("created_at"),
            "source": audit.get("source"),
            "summary": audit.get("summary"),
            "metadata": audit.get("metadata", {}),
        }
    return None


def _migrate_legacy_permission_audit_for_session(store: SessionStore, session_id: str) -> None:
    domains = {PERMISSION_PAYLOAD_DOMAIN, PERMISSION_RESOLUTION_PAYLOAD_DOMAIN, PERMISSION_OUTCOME_PAYLOAD_DOMAIN}
    existing = store.load_transcript(session_id, include_types=domains, limit=1)
    if existing:
        return

    audit_entries = store.load_audit(session_id, include_domains=domains)
    if not audit_entries:
        return

    migrated = 0
    for audit in audit_entries:
        domain = str(audit.get("domain", "") or "").strip()
        payload_record = _legacy_permission_payload_from_audit(domain, audit)
        if not isinstance(payload_record, dict):
            continue
        metadata = payload_record.get("metadata")
        metadata_record = metadata if isinstance(metadata, dict) else {}
        provider_id = str(metadata_record.get("provider_id", "") or "")
        if domain == PERMISSION_PAYLOAD_DOMAIN:
            store.append_event(
                session_id,
                PermissionDecisionEvent(
                    session_id=session_id,
                    provider_id=provider_id,
                    action_id=str(payload_record.get("action_id", "") or ""),
                    tool_name=str(payload_record.get("tool_name", "") or ""),
                    risk=str(payload_record.get("risk", "") or ""),
                    decision=str(payload_record.get("decision", "") or ""),
                    rationale=str(payload_record.get("rationale", "") or ""),
                    policy_source=str(payload_record.get("policy_source", "") or ""),
                    requires_confirmation=bool(payload_record.get("requires_confirmation")),
                    command_prefix=str(payload_record.get("command_prefix", "") or "") or None,
                    metadata=dict(metadata_record),
                ),
                strip_raw=True,
            )
            migrated += 1
        elif domain == PERMISSION_RESOLUTION_PAYLOAD_DOMAIN:
            store.append_event(
                session_id,
                PermissionResolutionEvent(
                    session_id=session_id,
                    provider_id=provider_id,
                    action_id=str(payload_record.get("action_id", "") or ""),
                    resolution=str(payload_record.get("resolution", "") or ""),
                    resolved_at=_first_non_empty(
                        payload_record.get("resolved_at"),
                        audit.get("created_at"),
                    ),
                    actor=str(payload_record.get("actor", "") or "operator"),
                    summary=str(payload_record.get("summary", "") or ""),
                    note=str(payload_record.get("note", "") or "") or None,
                    enforcement_state=str(payload_record.get("enforcement_state", "") or "recorded_only"),
                    metadata=dict(metadata_record),
                ),
                strip_raw=True,
            )
            migrated += 1
        elif domain == PERMISSION_OUTCOME_PAYLOAD_DOMAIN:
            store.append_event(
                session_id,
                PermissionOutcomeEvent(
                    session_id=session_id,
                    provider_id=provider_id,
                    action_id=str(payload_record.get("action_id", "") or ""),
                    outcome=str(payload_record.get("outcome", "") or ""),
                    outcome_at=_first_non_empty(
                        payload_record.get("outcome_at"),
                        audit.get("created_at"),
                    ),
                    source=str(payload_record.get("source", "") or "runtime"),
                    summary=str(payload_record.get("summary", "") or ""),
                    metadata=dict(metadata_record),
                ),
                strip_raw=True,
            )
            migrated += 1

    if migrated:
        store.prune_audit_domains(session_id, domains=domains)


def _permission_history_entries_for_session(store: SessionStore, session_id: str) -> list[dict[str, Any]]:
    entries_by_action_id: dict[str, dict[str, Any]] = {}
    domains = {PERMISSION_PAYLOAD_DOMAIN, PERMISSION_RESOLUTION_PAYLOAD_DOMAIN, PERMISSION_OUTCOME_PAYLOAD_DOMAIN}
    _migrate_legacy_permission_audit_for_session(store, session_id)
    transcript_events = store.load_transcript(session_id, include_types=domains)
    for event in transcript_events:
        payload_record = {
            "version": PERMISSION_PAYLOAD_VERSION,
            "domain": getattr(event, "type", ""),
            **_clean_metadata(asdict(event)),
        }
        action_id = _first_non_empty(payload_record.get("action_id"))
        if not action_id:
            continue
        created_at = _first_non_empty(
            payload_record.get("resolved_at"),
            datetime.fromtimestamp(float(getattr(event, "timestamp", 0.0)), tz=timezone.utc).isoformat()
            if getattr(event, "timestamp", None) is not None
            else "",
        )
        _apply_permission_entry(
            entries_by_action_id,
            action_id=action_id,
            created_at=created_at,
            domain=payload_record["domain"],
            payload_record=payload_record,
        )

    records: list[dict[str, Any]] = []
    for record in entries_by_action_id.values():
        decision = record.get("decision")
        if not isinstance(decision, dict):
            continue
        resolution = record.get("resolution") if isinstance(record.get("resolution"), dict) else None
        outcome = record.get("outcome") if isinstance(record.get("outcome"), dict) else None
        pending = (
            str(decision.get("decision", "") or "") == "require_approval"
            and bool(decision.get("requires_confirmation"))
            and resolution is None
        )
        records.append(
            {
                "action_id": record["action_id"],
                "decision": decision,
                "resolution": resolution,
                "outcome": outcome,
                "first_seen_at": _first_non_empty(record.get("first_seen_at"), record.get("last_seen_at")),
                "last_seen_at": _first_non_empty(record.get("last_seen_at"), record.get("first_seen_at")),
                "seen_count": int(record.get("seen_count", 0) or 0),
                "pending": pending,
                "status": (
                    str(outcome.get("outcome"))
                    if outcome
                    else str(resolution.get("resolution")) if resolution else ("pending" if pending else "observed")
                ),
            }
        )
    records.sort(key=lambda item: str(item.get("last_seen_at", "") or ""), reverse=True)
    return records


def build_permission_history_payload(
    store: SessionStore,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """Build a shell-neutral approval history payload from canonical session history."""

    records: list[dict[str, Any]] = []
    for session_entry in reversed(store.list_sessions()):
        session_id = str(session_entry.get("session_id", "") or "").strip()
        if not session_id:
            continue
        records.extend(_permission_history_entries_for_session(store, session_id))
    records.sort(key=lambda item: str(item.get("last_seen_at", "") or ""), reverse=True)
    bounded = records[: max(1, limit)]
    return {
        "version": PERMISSION_PAYLOAD_VERSION,
        "domain": PERMISSION_HISTORY_PAYLOAD_DOMAIN,
        "count": len(bounded),
        "entries": bounded,
    }
