"""Append-only JSONL event and snapshot log for canonical replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dharma_swarm.continuity_harness import (
    SnapshotRecord,
    append_snapshot,
    load_snapshots,
    validate_snapshot,
)
from dharma_swarm.runtime_contract import RuntimeEnvelope, validate_envelope

DEFAULT_EVENT_LOG_DIR = Path.home() / ".dharma" / "events"


class EventLog:
    """Manage append-only runtime envelope and snapshot streams."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir or DEFAULT_EVENT_LOG_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def stream_path(self, stream: str) -> Path:
        safe_name = str(stream).strip() or "runtime"
        return self.base_dir / f"{safe_name}.jsonl"

    def append_envelope(
        self,
        envelope: RuntimeEnvelope | dict[str, Any],
        *,
        stream: str = "runtime",
    ) -> dict[str, Any]:
        data = envelope.as_dict() if isinstance(envelope, RuntimeEnvelope) else dict(envelope)
        ok, errors = validate_envelope(data)
        if not ok:
            raise ValueError(f"invalid runtime envelope: {errors}")
        path = self.stream_path(stream)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(data, sort_keys=True, ensure_ascii=True) + "\n")
        return data

    def append_snapshot(
        self,
        state: dict[str, Any],
        *,
        stream: str = "snapshots",
    ) -> SnapshotRecord:
        return append_snapshot(self.stream_path(stream), state)

    def read_envelopes(
        self,
        *,
        stream: str = "runtime",
        session_id: str | None = None,
        trace_id: str | None = None,
        event_type: str | None = None,
        limit: int | None = None,
        newest_first: bool = False,
    ) -> list[dict[str, Any]]:
        path = self.stream_path(stream)
        if not path.exists():
            return []

        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                ok, _errors = validate_envelope(data)
                if not ok:
                    continue
                if session_id is not None and str(data.get("session_id", "")) != session_id:
                    continue
                if trace_id is not None and str(data.get("trace_id", "")) != trace_id:
                    continue
                if event_type is not None and str(data.get("event_type", "")) != event_type:
                    continue
                rows.append(data)

        rows.sort(
            key=lambda item: (
                str(item.get("emitted_at", "")),
                str(item.get("event_id", "")),
            ),
            reverse=newest_first,
        )
        if limit is not None and limit > 0:
            return rows[:limit]
        return rows

    def tail(self, *, stream: str = "runtime", limit: int = 20) -> list[dict[str, Any]]:
        return self.read_envelopes(stream=stream, limit=limit, newest_first=True)

    def read_snapshots(
        self,
        *,
        stream: str = "snapshots",
        limit: int | None = None,
    ) -> list[SnapshotRecord]:
        rows = load_snapshots(self.stream_path(stream))
        if limit is not None and limit > 0:
            return rows[-limit:]
        return rows

    def verify_stream(self, *, stream: str = "runtime") -> tuple[bool, list[str]]:
        path = self.stream_path(stream)
        if not path.exists():
            return (False, ["runtime stream missing"])

        errors: list[str] = []
        with path.open("r", encoding="utf-8") as handle:
            for idx, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    errors.append(f"line {idx}: invalid json")
                    continue
                ok, row_errors = validate_envelope(data)
                if not ok:
                    errors.append(f"line {idx}: {'; '.join(row_errors)}")
        return (len(errors) == 0, errors)

    def verify_snapshot_stream(self, *, stream: str = "snapshots") -> tuple[bool, list[str]]:
        path = self.stream_path(stream)
        if not path.exists():
            return (False, ["snapshot stream missing"])

        errors: list[str] = []
        with path.open("r", encoding="utf-8") as handle:
            for idx, line in enumerate(handle, start=1):
                raw = line.strip()
                if not raw:
                    continue
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    errors.append(f"line {idx}: invalid json")
                    continue
                ok, message = validate_snapshot(data)
                if not ok:
                    errors.append(f"line {idx}: {message}")
        return (len(errors) == 0, errors)
