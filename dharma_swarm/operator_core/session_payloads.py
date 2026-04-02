"""JSON-ready session payload builders for the shared operator core."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Any

from .adapters import event_envelope_from_legacy_event, session_from_meta
from .contracts import CanonicalEventEnvelope, CanonicalSession
from .permission_payloads import PERMISSION_PAYLOAD_VERSION, _permission_history_entries_for_session
from .session_store import SessionStore, cwd_matches

SESSION_PAYLOAD_VERSION = "v1"
SESSION_CATALOG_DOMAIN = "session_catalog"
SESSION_DETAIL_DOMAIN = "session_detail"


def _string(value: Any) -> str:
    return str(value or "").strip()


def _session_payload(session: CanonicalSession) -> dict[str, Any]:
    return asdict(session)


def _event_payload(event: CanonicalEventEnvelope) -> dict[str, Any]:
    return asdict(event)


def _event_compaction_preview(events: list[Any]) -> dict[str, Any]:
    counts = Counter(getattr(event, "type", "unknown") for event in events)
    recent_event_types = [getattr(event, "type", "unknown") for event in events[-12:]]
    verbose_event_total = sum(counts.get(kind, 0) for kind in ("text_delta", "thinking_delta", "tool_args_delta"))
    compactable_ratio = (verbose_event_total / len(events)) if events else 0.0
    protected = [
        kind
        for kind in ("session_start", "tool_call_complete", "tool_result", "usage", "session_end", "error")
        if counts.get(kind, 0) > 0
    ]
    return {
        "event_count": len(events),
        "by_type": dict(counts),
        "compactable_ratio": round(compactable_ratio, 3),
        "protected_event_types": protected,
        "recent_event_types": recent_event_types,
    }


def build_session_catalog_payload(
    store: SessionStore,
    *,
    cwd: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Build a shell-neutral session catalog payload."""

    records: list[dict[str, Any]] = []
    for entry in reversed(store.list_sessions()):
        session_id = _string(entry.get("session_id"))
        if not session_id:
            continue
        try:
            meta = store.load_meta(session_id)
        except Exception:
            continue
        if cwd and not cwd_matches(str(meta.get("cwd", "")), cwd):
            continue
        replay_ok, replay_issues = store.verify_session_replay(session_id)
        records.append(
            {
                "session": _session_payload(session_from_meta(meta)),
                "replay_ok": replay_ok,
                "replay_issues": list(replay_issues),
                "total_turns": int(meta.get("total_turns", 0) or 0),
                "total_cost_usd": float(meta.get("total_cost_usd", 0.0) or 0.0),
            }
        )
        if len(records) >= max(1, limit):
            break

    return {
        "version": SESSION_PAYLOAD_VERSION,
        "domain": SESSION_CATALOG_DOMAIN,
        "count": len(records),
        "sessions": records,
    }


def build_session_detail_payload(
    store: SessionStore,
    session_id: str,
    *,
    transcript_limit: int = 80,
) -> dict[str, Any]:
    """Build a shell-neutral session detail payload."""

    meta = store.load_meta(session_id)
    events = store.load_transcript(session_id, limit=transcript_limit)
    replay_ok, replay_issues = store.verify_session_replay(session_id)
    envelopes = [event_envelope_from_legacy_event(event) for event in events]
    session_permission_entries = _permission_history_entries_for_session(store, session_id)
    return {
        "version": SESSION_PAYLOAD_VERSION,
        "domain": SESSION_DETAIL_DOMAIN,
        "session": _session_payload(session_from_meta(meta)),
        "replay_ok": replay_ok,
        "replay_issues": list(replay_issues),
        "compaction_preview": _event_compaction_preview(events),
        "recent_events": [_event_payload(envelope) for envelope in envelopes],
        "approval_history": {
            "version": PERMISSION_PAYLOAD_VERSION,
            "domain": "permission_history",
            "count": len(session_permission_entries),
            "entries": session_permission_entries,
        },
    }
