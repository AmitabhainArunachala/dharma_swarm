"""Provider-neutral session persistence for DGC TUI."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import secrets
from pathlib import Path
from typing import Any

from .events import CanonicalEvent

HOME = Path.home()
DEFAULT_ROOT = HOME / ".dharma" / "sessions"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_session_id() -> str:
    now = datetime.now(timezone.utc)
    return f"dgc-{now:%Y%m%d}-{now:%H%M%S}-{secrets.token_hex(2)}"


class SessionStore:
    """Stores canonical event transcripts and session metadata."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        self._index_path = self.root / "index.json"
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
        return sid

    def append_event(self, session_id: str, event: CanonicalEvent, *, strip_raw: bool = True) -> None:
        payload = asdict(event)
        if strip_raw:
            payload["raw"] = None
        sp = self.root / session_id
        tp = sp / "transcript.jsonl"
        with open(tp, "a") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
        self._touch_session(session_id)

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

    def load_meta(self, session_id: str) -> dict[str, Any]:
        return json.loads((self.root / session_id / "meta.json").read_text())

    def set_provider_session_id(self, session_id: str, provider_session_id: str) -> None:
        meta = self.load_meta(session_id)
        meta["provider_session_id"] = provider_session_id
        meta["updated_at"] = _now_iso()
        self._write_meta(session_id, meta)
        self._upsert_index_entry(session_id, {"updated_at": meta["updated_at"]})

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
