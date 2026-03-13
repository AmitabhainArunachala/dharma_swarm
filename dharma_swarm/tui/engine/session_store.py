"""Provider-neutral session persistence for DGC TUI."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import secrets
from pathlib import Path
from typing import Any

from dharma_swarm.continuity_harness import append_snapshot, verify_replay_integrity
from dharma_swarm.session_event_bridge import SessionEventBridge

from .events import CanonicalEvent, CanonicalEventType, EVENT_TYPES

HOME = Path.home()
DEFAULT_ROOT = HOME / ".dharma" / "sessions"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_session_id() -> str:
    now = datetime.now(timezone.utc)
    return f"dgc-{now:%Y%m%d}-{now:%H%M%S}-{secrets.token_hex(2)}"


def _normalize_cwd(cwd: str) -> str:
    """Return a stable absolute cwd string for path-equivalent matching."""
    try:
        return str(Path(cwd).expanduser().resolve())
    except Exception:
        return str(Path(cwd).expanduser())


def _cwd_matches(meta_cwd: str, expected_cwd: str) -> bool:
    if meta_cwd == expected_cwd:
        return True
    return _normalize_cwd(meta_cwd) == _normalize_cwd(expected_cwd)


class SessionStore:
    """Stores canonical event transcripts and session metadata."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.json"
        self._bridges: dict[str, SessionEventBridge] = {}
        if not self._index_path.exists():
            self._index_path.write_text(json.dumps({"schema_version": 1, "sessions": []}))

    def create_session(
        self,
        *,
        provider_id: str,
        model_id: str,
        cwd: str,
        title: str | None = None,
        provider_session_id: str | None = None,
        parent_session_id: str | None = None,
        forked_from: str | None = None,
        session_id: str | None = None,
    ) -> str:
        sid = session_id or _new_session_id()
        sp = self.root / sid
        sp.mkdir(parents=True, exist_ok=True)

        meta = {
            "schema_version": 1,
            "session_id": sid,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "provider_id": provider_id,
            "model_id": model_id,
            "provider_session_id": provider_session_id,
            "title": title or "",
            "cwd": cwd,
            "git_branch": "",
            "tags": [],
            "total_cost_usd": 0.0,
            "total_turns": 0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "capabilities_used": [],
            "status": "running",
            "parent_session_id": parent_session_id,
            "forked_from": forked_from,
        }
        (sp / "meta.json").write_text(json.dumps(meta, indent=2))
        (sp / "transcript.jsonl").touch(exist_ok=True)
        (sp / "audit.jsonl").touch(exist_ok=True)
        (sp / "runtime.jsonl").touch(exist_ok=True)
        (sp / "snapshots.jsonl").touch(exist_ok=True)

        index = self._read_index()
        sessions = index.get("sessions", [])
        sessions.append(
            {
                "session_id": sid,
                "title": meta["title"],
                "provider_id": provider_id,
                "model_id": model_id,
                "created_at": meta["created_at"],
                "updated_at": meta["updated_at"],
                "status": "running",
                "total_cost_usd": 0.0,
                "total_turns": 0,
            }
        )
        index["sessions"] = sessions
        self._write_index(index)
        try:
            self._bridge_for(sid).session_start(
                sid,
                {
                    "provider_id": provider_id,
                    "model_id": model_id,
                    "cwd": cwd,
                    "title": meta["title"],
                    "provider_session_id": provider_session_id or "",
                },
            )
            self._append_session_snapshot(sid, reason="session_created", meta=meta)
        except Exception:
            pass
        return sid

    def append_event(self, session_id: str, event: CanonicalEvent, *, strip_raw: bool = True) -> None:
        payload = asdict(event)
        if strip_raw:
            payload["raw"] = None
        sp = self.root / session_id
        tp = sp / "transcript.jsonl"
        with open(tp, "a") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
        try:
            bridge = self._bridge_for(session_id)
            bridge.record_canonical_event(event)
        except Exception:
            pass
        self._touch_session(session_id)

    def load_transcript(
        self,
        session_id: str,
        *,
        include_types: set[str] | None = None,
        limit: int | None = None,
    ) -> list[CanonicalEventType]:
        """Load canonical events from the persisted transcript jsonl."""
        tp = self.root / session_id / "transcript.jsonl"
        if not tp.exists():
            return []

        events: list[CanonicalEventType] = []
        for raw_line in tp.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            event_type = str(payload.get("type", "") or "").strip()
            if not event_type:
                continue
            if include_types is not None and event_type not in include_types:
                continue
            event_cls = EVENT_TYPES.get(event_type)
            if event_cls is None:
                continue
            try:
                events.append(event_cls(**payload))
            except Exception:
                continue

        if limit is not None and limit >= 0:
            return events[-limit:]
        return events

    def append_audit(self, session_id: str, entry: dict[str, Any]) -> None:
        sp = self.root / session_id
        ap = sp / "audit.jsonl"
        payload = dict(entry)
        payload.setdefault("timestamp", datetime.now(timezone.utc).timestamp())
        payload.setdefault("session_id", session_id)
        with open(ap, "a") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
        self._touch_session(session_id)

    def finalize_session(
        self,
        session_id: str,
        *,
        status: str,
        total_cost_usd: float | None = None,
        total_turns: int | None = None,
        total_input_tokens: int | None = None,
        total_output_tokens: int | None = None,
        provider_session_id: str | None = None,
    ) -> None:
        meta = self.load_meta(session_id)
        meta["updated_at"] = _now_iso()
        meta["status"] = status
        if total_cost_usd is not None:
            meta["total_cost_usd"] = float(total_cost_usd)
        if total_turns is not None:
            meta["total_turns"] = int(total_turns)
        if total_input_tokens is not None:
            meta["total_input_tokens"] = int(total_input_tokens)
        if total_output_tokens is not None:
            meta["total_output_tokens"] = int(total_output_tokens)
        if provider_session_id:
            meta["provider_session_id"] = provider_session_id
        self._write_meta(session_id, meta)
        self._upsert_index_entry(
            session_id,
            {
                "updated_at": meta["updated_at"],
                "status": status,
                "total_cost_usd": meta.get("total_cost_usd", 0.0),
                "total_turns": meta.get("total_turns", 0),
            },
        )
        try:
            self._bridge_for(session_id).session_end(
                session_id,
                outcome=status,
                summary=(
                    f"status={status}; turns={meta.get('total_turns', 0)}; "
                    f"cost={meta.get('total_cost_usd', 0.0)}"
                ),
            )
            self._append_session_snapshot(session_id, reason="session_finalized", meta=meta)
        except Exception:
            pass

    def load_meta(self, session_id: str) -> dict[str, Any]:
        return json.loads((self.root / session_id / "meta.json").read_text())

    def set_provider_session_id(self, session_id: str, provider_session_id: str) -> None:
        meta = self.load_meta(session_id)
        meta["provider_session_id"] = provider_session_id
        meta["updated_at"] = _now_iso()
        self._write_meta(session_id, meta)
        self._upsert_index_entry(session_id, {"updated_at": meta["updated_at"]})
        try:
            self._append_session_snapshot(
                session_id,
                reason="provider_session_bound",
                meta=meta,
            )
        except Exception:
            pass

    def _touch_session(self, session_id: str) -> None:
        meta = self.load_meta(session_id)
        meta["updated_at"] = _now_iso()
        self._write_meta(session_id, meta)
        self._upsert_index_entry(session_id, {"updated_at": meta["updated_at"]})

    def _write_meta(self, session_id: str, meta: dict[str, Any]) -> None:
        (self.root / session_id / "meta.json").write_text(json.dumps(meta, indent=2))

    def _read_index(self) -> dict[str, Any]:
        try:
            return json.loads(self._index_path.read_text())
        except Exception:
            return {"schema_version": 1, "sessions": []}

    def _write_index(self, index: dict[str, Any]) -> None:
        self._index_path.write_text(json.dumps(index, indent=2))

    def _upsert_index_entry(self, session_id: str, updates: dict[str, Any]) -> None:
        index = self._read_index()
        sessions = index.get("sessions", [])
        for entry in sessions:
            if entry.get("session_id") == session_id:
                entry.update(updates)
                break
        index["sessions"] = sessions
        self._write_index(index)

    def list_sessions(self) -> list[dict[str, Any]]:
        """Return index sessions in stored order (oldest -> newest append order)."""
        index = self._read_index()
        sessions = index.get("sessions", [])
        return sessions if isinstance(sessions, list) else []

    def latest_session(
        self,
        *,
        cwd: str | None = None,
        provider_id: str | None = None,
        min_turns: int | None = None,
    ) -> dict[str, Any] | None:
        """Return the most recently updated session meta matching filters."""
        latest_meta: dict[str, Any] | None = None
        latest_key = ""
        for entry in self.list_sessions():
            sid = str(entry.get("session_id", "")).strip()
            if not sid:
                continue
            try:
                meta = self.load_meta(sid)
            except Exception:
                continue

            if cwd and not _cwd_matches(str(meta.get("cwd", "")), cwd):
                continue
            if provider_id and str(meta.get("provider_id", "")) != provider_id:
                continue
            if min_turns is not None:
                turns = int(meta.get("total_turns", 0) or 0)
                if turns < int(min_turns):
                    continue

            updated = str(meta.get("updated_at", ""))
            created = str(meta.get("created_at", ""))
            key = updated or created
            if not key:
                continue
            if key > latest_key:
                latest_key = key
                latest_meta = meta
        return latest_meta

    def verify_session_replay(self, session_id: str) -> tuple[bool, list[str]]:
        return verify_replay_integrity(self.root / session_id / "snapshots.jsonl")

    def _bridge_for(self, session_id: str) -> SessionEventBridge:
        bridge = self._bridges.get(session_id)
        if bridge is not None:
            return bridge
        bridge = SessionEventBridge(
            runtime_log_path=self.root / session_id / "runtime.jsonl",
        )
        self._bridges[session_id] = bridge
        return bridge

    def _append_session_snapshot(
        self,
        session_id: str,
        *,
        reason: str,
        meta: dict[str, Any] | None = None,
    ) -> None:
        state = self._snapshot_state(meta or self.load_meta(session_id), reason=reason)
        append_snapshot(self.root / session_id / "snapshots.jsonl", state)

    @staticmethod
    def _snapshot_state(meta: dict[str, Any], *, reason: str) -> dict[str, Any]:
        return {
            "snapshot_reason": reason,
            "session_id": str(meta.get("session_id", "")),
            "provider_id": str(meta.get("provider_id", "")),
            "model_id": str(meta.get("model_id", "")),
            "provider_session_id": str(meta.get("provider_session_id", "")),
            "cwd": str(meta.get("cwd", "")),
            "status": str(meta.get("status", "")),
            "total_turns": int(meta.get("total_turns", 0) or 0),
            "total_input_tokens": int(meta.get("total_input_tokens", 0) or 0),
            "total_output_tokens": int(meta.get("total_output_tokens", 0) or 0),
            "total_cost_usd": float(meta.get("total_cost_usd", 0.0) or 0.0),
            "updated_at": str(meta.get("updated_at", "")),
        }
