"""Replay-safe session continuity snapshots for crash and restart validation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SnapshotRecord:
    snapshot_id: str
    recorded_at: str
    state: dict[str, Any]
    checksum: str

    @classmethod
    def from_state(
        cls,
        state: dict[str, Any],
        *,
        snapshot_id: str | None = None,
        recorded_at: str | None = None,
    ) -> "SnapshotRecord":
        sid = snapshot_id or f"snp_{uuid4().hex}"
        ts = recorded_at or _utc_now_iso()
        material = {
            "snapshot_id": sid,
            "recorded_at": ts,
            "state": state,
        }
        checksum = _sha256(_canonical_json(material))
        return cls(snapshot_id=sid, recorded_at=ts, state=state, checksum=checksum)

    def as_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "recorded_at": self.recorded_at,
            "state": self.state,
            "checksum": self.checksum,
        }


def validate_snapshot(record: dict[str, Any]) -> tuple[bool, str]:
    for key in ("snapshot_id", "recorded_at", "state", "checksum"):
        if key not in record:
            return (False, f"missing field '{key}'")
    if not isinstance(record["state"], dict):
        return (False, "state must be object")
    material = {
        "snapshot_id": record["snapshot_id"],
        "recorded_at": record["recorded_at"],
        "state": record["state"],
    }
    expected = _sha256(_canonical_json(material))
    if record["checksum"] != expected:
        return (False, "checksum mismatch")
    return (True, "")


def append_snapshot(path: Path, state: dict[str, Any]) -> SnapshotRecord:
    record = SnapshotRecord.from_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.as_dict(), ensure_ascii=True) + "\n")
    return record


def load_snapshots(path: Path) -> list[SnapshotRecord]:
    if not path.exists():
        return []
    rows: list[SnapshotRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            data = json.loads(raw)
            rows.append(
                SnapshotRecord(
                    snapshot_id=str(data["snapshot_id"]),
                    recorded_at=str(data["recorded_at"]),
                    state=dict(data["state"]),
                    checksum=str(data["checksum"]),
                )
            )
    return rows


def verify_replay_integrity(path: Path) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not path.exists():
        return (False, ["snapshot log missing"])

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
