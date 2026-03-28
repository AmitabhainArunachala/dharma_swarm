"""Helpers for canonical runtime artifacts under ``~/.dharma``."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


def parse_iso_datetime(raw: Any) -> datetime | None:
    """Return a UTC datetime for an ISO-ish timestamp, or ``None``."""
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def pulse_log_candidates(state_dir: Path) -> tuple[Path, ...]:
    """Return pulse log locations in canonical preference order."""
    return (
        state_dir / "logs" / "pulse.log",
        state_dir / "pulse.log",
    )


def freshest_pulse_log_path(state_dir: Path) -> Path | None:
    """Return the freshest existing pulse log, if any."""
    existing = [path for path in pulse_log_candidates(state_dir) if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def pulse_log_fresh(state_dir: Path, *, freshness_seconds: float) -> bool:
    """Whether any known pulse log was updated recently enough."""
    pulse_log = freshest_pulse_log_path(state_dir)
    if pulse_log is None:
        return False
    age_seconds = max(
        0.0,
        datetime.now(timezone.utc).timestamp() - pulse_log.stat().st_mtime,
    )
    return age_seconds < freshness_seconds


def append_pulse_log(state_dir: Path, entry: str) -> None:
    """Write a pulse entry to the canonical log and mirror the legacy path."""
    for path in pulse_log_candidates(state_dir):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(entry)


def dgc_health_snapshot_summary(
    state_dir: Path,
    *,
    stale_after_seconds: float = 3600.0,
) -> dict[str, Any]:
    """Read ``dgc_health.json`` with freshness metadata."""
    path = state_dir / "stigmergy" / "dgc_health.json"
    summary: dict[str, Any] = {
        "path": path,
        "exists": path.exists(),
        "status": "missing",
        "payload": None,
        "timestamp": None,
        "age_seconds": None,
        "daemon_pid": None,
        "live_pid": None,
        "daemon_pid_mismatch": False,
    }
    if not path.exists():
        return summary

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        summary["status"] = "unreadable"
        summary["error"] = str(exc)
        return summary

    timestamp = parse_iso_datetime(payload.get("timestamp"))
    now = datetime.now(timezone.utc)
    age_seconds = None if timestamp is None else max(0.0, (now - timestamp).total_seconds())

    daemon_pid = payload.get("daemon_pid")
    live_pid = None
    pid_file = state_dir / "daemon.pid"
    if pid_file.exists():
        try:
            live_pid = int(pid_file.read_text(encoding="utf-8").strip())
        except Exception:
            live_pid = None

    summary.update(
        {
            "payload": payload,
            "timestamp": timestamp,
            "age_seconds": age_seconds,
            "daemon_pid": daemon_pid,
            "live_pid": live_pid,
            "daemon_pid_mismatch": (
                daemon_pid is not None
                and live_pid is not None
                and str(daemon_pid).strip() != str(live_pid).strip()
            ),
        }
    )

    if timestamp is None:
        summary["status"] = "unknown"
    elif age_seconds is not None and age_seconds > stale_after_seconds:
        summary["status"] = "stale"
    else:
        summary["status"] = "fresh"
    return summary


def write_dgc_health_snapshot(
    state_dir: Path,
    *,
    daemon_pid: int,
    agent_count: int,
    task_count: int,
    anomaly_count: int,
    source: str,
) -> Path:
    """Persist a fresh canonical ``dgc_health.json`` snapshot."""
    path = state_dir / "stigmergy" / "dgc_health.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "daemon_pid": int(daemon_pid),
        "agent_count": int(agent_count),
        "task_count": int(task_count),
        "anomaly_count": int(anomaly_count),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": source,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
