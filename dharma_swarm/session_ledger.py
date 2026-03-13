"""Session-scoped task/progress ledgers for orchestration traces.

Writes compact JSONL events for:
- task_ledger.jsonl: assignment/routing lifecycle
- progress_ledger.jsonl: execution outcomes, pivots, timing
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.runtime_state import (
    RuntimeStateStore,
    build_session_event_from_ledger_record,
)


def _utc_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _session_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


class SessionLedger:
    """Append-only JSONL ledgers grouped by session ID."""

    def __init__(
        self,
        base_dir: Path | None = None,
        session_id: str | None = None,
        runtime_db_path: Path | None = None,
    ) -> None:
        self.base_dir = Path(
            base_dir
            or os.getenv("DGC_LEDGER_DIR")
            or (Path.home() / ".dharma" / "ledgers")
        )
        self.session_id = session_id or os.getenv("DGC_SESSION_ID") or _session_stamp()
        self.session_dir = self.base_dir / self.session_id
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.task_path = self.session_dir / "task_ledger.jsonl"
        self.progress_path = self.session_dir / "progress_ledger.jsonl"
        self._runtime_state = RuntimeStateStore(runtime_db_path)

    def task_event(self, event: str, **payload: Any) -> None:
        self._append(self.task_path, "task", event, payload)

    def progress_event(self, event: str, **payload: Any) -> None:
        self._append(self.progress_path, "progress", event, payload)

    def _append(
        self,
        path: Path,
        ledger_kind: str,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        record = {
            "ts_utc": _utc_ts(),
            "session_id": self.session_id,
            "event": event,
            "ledger_kind": ledger_kind,
            **payload,
        }
        indexed = build_session_event_from_ledger_record(
            session_id=self.session_id,
            ledger_kind=ledger_kind,
            record=record,
        )
        record["event_id"] = indexed.event_id
        # Never break orchestration because ledger persistence failed.
        try:
            with open(path, "a") as f:
                f.write(json.dumps(record, ensure_ascii=True) + "\n")
        except Exception:
            return
        try:
            self._runtime_state.record_session_event_sync(indexed)
        except Exception:
            return
