"""DGC doctor diagnostics.

Health and readiness checks for router/memory/provider execution lanes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import contextlib
import importlib.util
import io
import json
import logging
import os
from pathlib import Path
import shutil
import sqlite3
import socket
import subprocess
import sys
from typing import Any
from urllib.parse import urlparse

from dharma_swarm.api_keys import RUNTIME_PROVIDER_API_KEY_ENV_KEYS
from dharma_swarm.claude_cli import unattended_claude_auth_error
from dharma_swarm.runtime_artifacts import dgc_health_snapshot_summary

logger = logging.getLogger(__name__)

HOME = Path.home()
REPO_ROOT = HOME / "dharma_swarm"
DOCTOR_DIR = HOME / ".dharma" / "doctor"
DOCTOR_HISTORY_DIR = DOCTOR_DIR / "history"


@dataclass
class DoctorCheck:
    name: str
    status: str  # PASS | WARN | FAIL
    summary: str
    detail: str = ""
    fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mask_secret(raw: str) -> str:
    if not raw:
        return ""
    if len(raw) <= 10:
        return "*" * len(raw)
    return f"{raw[:4]}...{raw[-4:]}"


def _add(checks: list[DoctorCheck], **kwargs: Any) -> None:
    checks.append(DoctorCheck(**kwargs))


def _parse_iso_datetime(raw: Any) -> datetime | None:
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


def _format_age(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{int(seconds)}s"
    minutes = seconds / 60
    if minutes < 60:
        return f"{int(minutes)}m"
    hours = minutes / 60
    if hours < 24:
        return f"{hours:.1f}h"
    days = hours / 24
    return f"{days:.1f}d"


def _venv_python() -> Path | None:
    candidate = HOME / "dharma_swarm" / ".venv" / "bin" / "python"
    if candidate.exists() and os.access(candidate, os.X_OK):
        return candidate
    return None


def _run_venv_probe(code: str, *, timeout_seconds: float) -> tuple[bool, str]:
    py = _venv_python()
    if py is None:
        return (False, "venv python not found")
    env = os.environ.copy()
    repo_root = str(HOME / "dharma_swarm")
    current_pp = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = (
        repo_root
        if not current_pp
        else f"{repo_root}{os.pathsep}{current_pp}"
    )
    try:
        proc = subprocess.run(
            [str(py), "-c", code],
            capture_output=True,
            text=True,
            timeout=max(0.5, timeout_seconds),
            env=env,
        )
    except Exception as exc:
        return (False, str(exc))
    out = (proc.stdout or proc.stderr or "").strip()
    if proc.returncode == 0:
        return (True, out)
    return (False, out or f"rc={proc.returncode}")


def _pid_alive(pid: int) -> bool:
    try:
        if pid <= 1:
            return False
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_pid_file(path: Path) -> tuple[int | None, str]:
    if not path.exists():
        return None, "missing"
    try:
        pid = int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return None, "invalid"
    if _pid_alive(pid):
        return pid, "alive"
    return pid, "stale"


def _list_daemon_like_processes(timeout_seconds: float) -> list[tuple[int, str]]:
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=max(0.5, timeout_seconds),
        )
    except Exception:
        return []

    if proc.returncode != 0:
        return []

    current_pid = os.getpid()
    matches: list[tuple[int, str]] = []
    needles = ("dharma_swarm.orchestrate_live", "orchestrate_live.py", "run_daemon.sh")
    skip_markers = ("dgc doctor", "ps -axo", "rg ", "pytest")

    for raw in proc.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        command = parts[1]
        if pid == current_pid:
            continue
        if not any(needle in command for needle in needles):
            continue
        if any(marker in command for marker in skip_markers):
            continue
        matches.append((pid, command))

    return matches


def _check_daemon_integrity(checks: list[DoctorCheck], timeout_seconds: float) -> None:
    state_dir = HOME / ".dharma"
    pid_files = {
        "daemon": state_dir / "daemon.pid",
        "orchestrator": state_dir / "orchestrator.pid",
        "cron_daemon": state_dir / "cron" / "daemon.pid",
    }
    pid_statuses = {
        label: _read_pid_file(path)
        for label, path in pid_files.items()
    }
    stale = [
        f"{label}={pid if pid is not None else '?'}"
        for label, (pid, status) in pid_statuses.items()
        if status == "stale"
    ]
    invalid = [
        label
        for label, (_, status) in pid_statuses.items()
        if status == "invalid"
    ]
    live_processes = _list_daemon_like_processes(timeout_seconds)

    if len(live_processes) > 1:
        detail = " | ".join(f"{pid}:{command}" for pid, command in live_processes[:4])
        _add(
            checks,
            name="daemon_integrity",
            status="FAIL",
            summary=f"multiple daemon-like processes detected ({len(live_processes)})",
            detail=detail,
            fix="Stop duplicate daemons, clear stale pid files, then start a single runtime.",
        )
        return

    daemon_pid, daemon_status = pid_statuses["daemon"]
    orchestrator_pid, orchestrator_status = pid_statuses["orchestrator"]
    legacy_details: list[str] = []
    if orchestrator_status == "alive":
        legacy_details.append(f"orchestrator={orchestrator_pid}")
    elif orchestrator_status == "stale":
        legacy_details.append(f"orchestrator={orchestrator_pid}")
    elif orchestrator_status == "invalid":
        legacy_details.append("orchestrator=invalid")

    owner_stale = [item for item in stale if not item.startswith("orchestrator=")]
    owner_invalid = [item for item in invalid if item != "orchestrator"]

    if owner_stale or owner_invalid:
        detail_parts: list[str] = []
        if owner_stale:
            detail_parts.append("stale pid files: " + ", ".join(owner_stale))
        if owner_invalid:
            detail_parts.append("invalid pid files: " + ", ".join(owner_invalid))
        if live_processes:
            pid, command = live_processes[0]
            detail_parts.append(f"live process: {pid}:{command}")
        if legacy_details:
            detail_parts.append("legacy pid files: " + ", ".join(legacy_details))
        _add(
            checks,
            name="daemon_integrity",
            status="WARN",
            summary="pid file state is inconsistent with runtime",
            detail=" | ".join(detail_parts),
            fix="Remove stale/invalid pid files and ensure only one daemon launcher owns the runtime.",
        )
        return

    if daemon_status != "alive" and orchestrator_status == "alive":
        detail_parts = ["legacy owner: orchestrator.pid"]
        if live_processes:
            pid, command = live_processes[0]
            detail_parts.append(f"live process: {pid}:{command}")
        _add(
            checks,
            name="daemon_integrity",
            status="WARN",
            summary="runtime is tracked only by legacy orchestrator.pid",
            detail=" | ".join(detail_parts),
            fix="Rewrite runtime ownership to ~/.dharma/daemon.pid and remove orchestrator.pid.",
        )
        return

    if daemon_status == "alive" and legacy_details and (live_processes or orchestrator_status == "alive"):
        detail_parts = ["legacy pid files: " + ", ".join(legacy_details)]
        if live_processes:
            pid, command = live_processes[0]
            detail_parts.append(f"live process: {pid}:{command}")
        _add(
            checks,
            name="daemon_integrity",
            status="WARN",
            summary="legacy pid file leftovers detected",
            detail=" | ".join(detail_parts),
            fix="Remove ~/.dharma/orchestrator.pid leftovers; ~/.dharma/daemon.pid is the runtime owner.",
        )
        return

    if live_processes:
        pid, command = live_processes[0]
        _add(
            checks,
            name="daemon_integrity",
            status="PASS",
            summary=f"single daemon-like process detected (PID {pid})",
            detail=command,
        )
        return

    _add(
        checks,
        name="daemon_integrity",
        status="PASS",
        summary="no duplicate daemon signals detected",
    )


def _check_message_bus_integrity(checks: list[DoctorCheck], timeout_seconds: float) -> None:
    canonical = HOME / ".dharma" / "db" / "messages.db"
    shadow_paths = [
        HOME / ".dharma" / "message_bus.db",
        HOME / ".dharma" / "db" / "message_bus.db",
    ]
    live_processes = _list_daemon_like_processes(timeout_seconds)

    if not canonical.exists():
        _add(
            checks,
            name="message_bus_integrity",
            status="FAIL" if live_processes else "WARN",
            summary="canonical message bus database is missing",
            detail=str(canonical),
            fix="Keep the shared bus at ~/.dharma/db/messages.db and initialize it before relying on cross-process signals.",
        )
        return

    try:
        with sqlite3.connect(canonical) as conn:
            cur = conn.cursor()
            journal_mode = str(cur.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            busy_timeout_ms = int(cur.execute("PRAGMA busy_timeout").fetchone()[0])
            counts = {
                "messages": int(cur.execute("SELECT COUNT(*) FROM messages").fetchone()[0]),
                "heartbeats": int(cur.execute("SELECT COUNT(*) FROM heartbeats").fetchone()[0]),
                "subscriptions": int(cur.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0]),
                "artifacts": int(cur.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0]),
                "events_total": int(cur.execute("SELECT COUNT(*) FROM events").fetchone()[0]),
                "events_unconsumed": int(
                    cur.execute("SELECT COUNT(*) FROM events WHERE consumed_at IS NULL").fetchone()[0]
                ),
                "stale_heartbeats": int(
                    cur.execute(
                        "SELECT COUNT(*) FROM heartbeats "
                        "WHERE datetime(last_seen) < datetime('now', '-5 minutes')"
                    ).fetchone()[0]
                ),
            }
            oldest_heartbeat = cur.execute("SELECT MIN(last_seen) FROM heartbeats").fetchone()[0]
            latest_heartbeat = cur.execute("SELECT MAX(last_seen) FROM heartbeats").fetchone()[0]
    except Exception as exc:
        _add(
            checks,
            name="message_bus_integrity",
            status="FAIL" if live_processes else "WARN",
            summary="message bus database could not be inspected",
            detail=f"{canonical}: {exc}",
            fix="Repair ~/.dharma/db/messages.db or reinitialize the shared bus schema.",
        )
        return

    shadow_present = [path for path in shadow_paths if path.exists()]
    detail_parts = [
        f"db={canonical}",
        f"journal={journal_mode}",
        f"busy_timeout_ms={busy_timeout_ms}",
        f"messages={counts['messages']}",
        f"heartbeats={counts['heartbeats']}",
        f"oldest_heartbeat={oldest_heartbeat or 'none'}",
        f"latest_heartbeat={latest_heartbeat or 'none'}",
        f"subscriptions={counts['subscriptions']}",
        f"events={counts['events_total']}",
        f"queued_events={counts['events_unconsumed']}",
        f"artifacts={counts['artifacts']}",
    ]
    if shadow_present:
        detail_parts.append(
            "shadow_paths=" + ", ".join(str(path) for path in shadow_present)
        )

    issues: list[str] = []
    if journal_mode != "wal":
        issues.append(f"journal mode is {journal_mode}, not wal")
    if shadow_present:
        issues.append("alternate message bus database path(s) still exist")
    if (
        counts["messages"] > 0
        and counts["heartbeats"] == 0
        and counts["subscriptions"] == 0
        and counts["events_total"] <= 1
    ):
        issues.append("bus traffic is mailbox-only; liveness/pubsub/event lanes are effectively idle")
    if live_processes and counts["heartbeats"] == 0:
        issues.append("no agent heartbeats recorded on the shared bus")
    if live_processes and counts["subscriptions"] == 0:
        issues.append("no topic subscriptions recorded on the shared bus")
    if live_processes and counts["events_total"] <= 1:
        issues.append("event rail is barely used")
    if counts["stale_heartbeats"] > 0:
        issues.append(f"{counts['stale_heartbeats']} stale heartbeat(s)")
    if counts["events_unconsumed"] > 50:
        issues.append(f"{counts['events_unconsumed']} unconsumed event(s)")

    if issues:
        _add(
            checks,
            name="message_bus_integrity",
            status="WARN",
            summary="shared message bus exists, but usage still looks thin or split",
            detail=" | ".join(detail_parts + issues),
            fix="Keep one canonical bus path, and make heartbeats, subscriptions, and cross-process events observable on it.",
        )
        return

    _add(
        checks,
        name="message_bus_integrity",
        status="PASS",
        summary="shared message bus is present and looks coherent",
        detail=" | ".join(detail_parts),
    )


def _check_dgc_health_snapshot(checks: list[DoctorCheck]) -> None:
    snapshot = dgc_health_snapshot_summary(HOME / ".dharma")
    if not snapshot["exists"]:
        _add(
            checks,
            name="dgc_health_snapshot",
            status="WARN",
            summary="dgc_health snapshot is missing",
            detail=str(snapshot["path"]),
            fix="Either restore a canonical snapshot publisher or stop depending on dgc_health.json in operator surfaces.",
        )
        return

    if snapshot["status"] == "unreadable":
        _add(
            checks,
            name="dgc_health_snapshot",
            status="WARN",
            summary="dgc_health snapshot is unreadable",
            detail=f"{snapshot['path']}: {snapshot.get('error', 'unknown error')}",
            fix="Repair or replace ~/.dharma/stigmergy/dgc_health.json before trusting snapshot-based dashboards.",
        )
        return

    detail_parts = [f"path={snapshot['path']}"]
    if snapshot["timestamp"] is not None:
        detail_parts.append(f"age={_format_age(float(snapshot['age_seconds'] or 0.0))}")
    if snapshot["daemon_pid"] is not None:
        detail_parts.append(f"daemon_pid={snapshot['daemon_pid']}")
    if snapshot["live_pid"] is not None:
        detail_parts.append(f"live_pid={snapshot['live_pid']}")
    if snapshot["daemon_pid_mismatch"]:
        detail_parts.append("daemon_pid_mismatch")

    if snapshot["status"] == "stale":
        _add(
            checks,
            name="dgc_health_snapshot",
            status="WARN",
            summary="dgc_health snapshot is stale",
            detail=" | ".join(detail_parts),
            fix="Refresh or retire the dgc_health publisher; stale snapshot state should not be treated as live runtime truth.",
        )
        return

    if snapshot["status"] == "unknown":
        _add(
            checks,
            name="dgc_health_snapshot",
            status="WARN",
            summary="dgc_health snapshot has no parseable timestamp",
            detail=" | ".join(detail_parts),
            fix="Persist an ISO timestamp in ~/.dharma/stigmergy/dgc_health.json or retire the snapshot.",
        )
        return

    _add(
        checks,
        name="dgc_health_snapshot",
        status="PASS",
        summary="dgc_health snapshot looks fresh",
        detail=" | ".join(detail_parts),
    )


def _check_doctor_schedule(checks: list[DoctorCheck]) -> None:
    jobs_path = HOME / ".dharma" / "cron" / "jobs.json"
    if not jobs_path.exists():
        _add(
            checks,
            name="doctor_schedule",
            status="WARN",
            summary="doctor cron schedule file is missing",
            detail=str(jobs_path),
            fix="Create a recurring doctor_assurance cron job before relying on unattended sweeps.",
        )
        return

    try:
        payload = json.loads(jobs_path.read_text(encoding="utf-8"))
    except Exception as exc:
        _add(
            checks,
            name="doctor_schedule",
            status="WARN",
            summary="doctor cron schedule file is unreadable",
            detail=f"{jobs_path}: {exc}",
            fix="Repair ~/.dharma/cron/jobs.json so Doctor sweeps can be scheduled safely.",
        )
        return

    if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
        _add(
            checks,
            name="doctor_schedule",
            status="WARN",
            summary="doctor cron schedule file has unexpected shape",
            detail=str(jobs_path),
            fix="Normalize ~/.dharma/cron/jobs.json to the scheduler's {'jobs': [...]} format.",
        )
        return

    jobs = [
        job
        for job in payload["jobs"]
        if isinstance(job, dict)
        and job.get("enabled", True)
        and str(job.get("handler", "")).strip() == "doctor_assurance"
    ]
    if not jobs:
        _add(
            checks,
            name="doctor_schedule",
            status="WARN",
            summary="no enabled doctor_assurance cron job is configured",
            detail=str(jobs_path),
            fix="Schedule a recurring Doctor sweep so assurance keeps running overnight.",
        )
        return

    now = datetime.now(timezone.utc)
    overdue: list[str] = []
    upcoming: list[str] = []
    for job in jobs:
        label = str(job.get("name") or job.get("id") or "doctor_assurance")
        next_run = _parse_iso_datetime(job.get("next_run_at"))
        last_run = _parse_iso_datetime(job.get("last_run_at"))
        if next_run is None:
            overdue.append(f"{label}: next_run_at missing")
            continue
        if next_run < now:
            overdue.append(f"{label}: next run overdue since {next_run.isoformat()}")
            continue
        summary = f"{label} next={next_run.isoformat()}"
        if last_run is not None:
            summary += f" last={last_run.isoformat()}"
        upcoming.append(summary)

    if overdue:
        _add(
            checks,
            name="doctor_schedule",
            status="WARN",
            summary="doctor cron is configured but at least one sweep is overdue",
            detail=" | ".join(overdue + upcoming),
            fix="Kick the cron daemon or repair overdue doctor jobs so unattended sweeps keep running.",
        )
        return

    _add(
        checks,
        name="doctor_schedule",
        status="PASS",
        summary=f"{len(jobs)} doctor cron job(s) armed for unattended sweeps",
        detail=" | ".join(upcoming),
    )


def _check_env_autoload(checks: list[DoctorCheck]) -> None:
    cli_path = HOME / "dharma_swarm" / "dharma_swarm" / "dgc_cli.py"
    cli_has_bootstrap = False
    if cli_path.exists():
        try:
            cli_has_bootstrap = "_bootstrap_env()" in cli_path.read_text(errors="ignore")
        except Exception:
            cli_has_bootstrap = False

    dgc_path = shutil.which("dgc")
    active_path = Path(sys.argv[0]).expanduser()

    launchers: list[Path] = []
    if dgc_path:
        launchers.append(Path(dgc_path))
    if active_path.exists() and active_path not in launchers:
        launchers.append(active_path)

    if not launchers:
        _add(
            checks,
            name="env_autoload",
            status="FAIL",
            summary="`dgc` command not found on PATH",
            fix="Ensure dgc is installed and available on PATH.",
        )
        return

    details: list[str] = []
    launcher_ok = False
    for launcher in launchers:
        has_bootstrap = False
        delegates_to_cli = False
        if launcher.exists() and launcher.is_file():
            try:
                text = launcher.read_text(errors="ignore")
            except Exception:
                text = ""
            has_bootstrap = "_bootstrap_env()" in text
            delegates_to_cli = (
                "from dharma_swarm.dgc_cli import main" in text
                or "dharma_swarm.dgc_cli:main" in text
            )

        lane_ok = has_bootstrap or (delegates_to_cli and cli_has_bootstrap)
        launcher_ok = launcher_ok or lane_ok
        details.append(
            f"{launcher} bootstrap={has_bootstrap} delegates={delegates_to_cli} lane_ok={lane_ok}"
        )

    if launcher_ok and cli_has_bootstrap:
        _add(
            checks,
            name="env_autoload",
            status="PASS",
            summary="autoload wired for active launcher path(s) and CLI",
            detail=" | ".join(details),
        )
        return

    if launcher_ok or cli_has_bootstrap:
        _add(
            checks,
            name="env_autoload",
            status="WARN",
            summary="autoload wired in one path but not both",
            detail=" | ".join(details) + f" | cli={cli_has_bootstrap}",
            fix="Keep both launcher and dharma_swarm/dgc_cli.py env bootstrap enabled.",
        )
        return

    _add(
        checks,
        name="env_autoload",
        status="FAIL",
        summary="no env bootstrap detected in active launcher paths",
        fix="Add .env bootstrap to dgc launcher and dharma_swarm.dgc_cli.",
    )


def _check_router_env(checks: list[DoctorCheck]) -> None:
    required = (
        "DGC_ROUTER_REDIS_URL",
        "DGC_FASTTEXT_MODEL_PATH",
        "DGC_ROUTER_CANARY_PERCENT",
        "DGC_ROUTER_LEARNING_ENABLED",
    )
    missing = [key for key in required if not os.getenv(key, "").strip()]
    if missing:
        _add(
            checks,
            name="router_env",
            status="WARN",
            summary=f"missing {len(missing)} router env value(s)",
            detail=", ".join(missing),
            fix="Populate missing keys in ~/dharma_swarm/.env.",
        )
        return
    _add(
        checks,
        name="router_env",
        status="PASS",
        summary="core router env values present",
    )


def _check_worker_bins(checks: list[DoctorCheck], timeout_seconds: float) -> None:
    bins = ("claude", "codex")
    found = []
    details = []
    for name in bins:
        path = shutil.which(name)
        if not path:
            details.append(f"{name}=MISSING")
            continue
        found.append(name)
        try:
            proc = subprocess.run(
                [path, "--version"],
                capture_output=True,
                text=True,
                timeout=max(1.0, timeout_seconds),
            )
            line = (proc.stdout or proc.stderr or "").strip().splitlines()
            details.append(f"{name}=OK ({line[0] if line else 'version unknown'})")
        except Exception as exc:
            details.append(f"{name}=ERROR ({exc})")

    if found:
        _add(
            checks,
            name="worker_bins",
            status="PASS",
            summary=f"worker CLIs available: {', '.join(found)}",
            detail="; ".join(details),
        )
        return

    _add(
        checks,
        name="worker_bins",
        status="WARN",
        summary="no worker CLI found (`claude`/`codex`)",
        detail="; ".join(details),
        fix="Install at least one worker CLI and ensure it is on PATH.",
    )


def _check_provider_env(checks: list[DoctorCheck]) -> None:
    provider_keys = RUNTIME_PROVIDER_API_KEY_ENV_KEYS
    present: list[str] = []
    for key in provider_keys:
        value = os.getenv(key, "").strip()
        if value:
            present.append(f"{key}={_mask_secret(value)}")

    ollama = os.getenv("OLLAMA_BASE_URL", "").strip()
    if ollama:
        present.append(f"OLLAMA_BASE_URL={ollama}")

    if present:
        _add(
            checks,
            name="provider_env",
            status="PASS",
            summary=f"provider lane configured ({len(present)} entries)",
            detail=", ".join(present),
        )
        return

    _add(
        checks,
        name="provider_env",
        status="WARN",
        summary="no provider credentials/endpoints found in env",
        fix="Set at least one provider key in env (.env or shell).",
    )


def _recent_unattended_claude_auth_failures() -> list[str]:
    findings: list[str] = []
    auth_markers = (
        "Not logged in",
        "unattended Claude bare mode requires ANTHROPIC_API_KEY",
    )

    pulse_last_run = HOME / ".dharma" / "cron" / "last_run" / "pulse.json"
    try:
        if pulse_last_run.exists():
            payload = json.loads(pulse_last_run.read_text(encoding="utf-8"))
            error = str(payload.get("error", "")).strip()
            if any(marker in error for marker in auth_markers):
                findings.append(f"pulse={pulse_last_run}")
    except Exception:
        pass

    garden_latest = HOME / ".dharma" / "garden" / "latest_cycle.json"
    try:
        if garden_latest.exists():
            payload = json.loads(garden_latest.read_text(encoding="utf-8"))
            for result in payload.get("results", []):
                preview = str(result.get("output_preview", "")).strip()
                if any(marker in preview for marker in auth_markers):
                    skill = result.get("skill") or result.get("key") or "unknown"
                    findings.append(f"garden:{skill}={garden_latest}")
                    break
    except Exception:
        pass

    return findings


def _check_claude_unattended_auth(checks: list[DoctorCheck]) -> None:
    claude_bin = shutil.which("claude")
    if not claude_bin:
        _add(
            checks,
            name="claude_unattended_auth",
            status="WARN",
            summary="claude CLI unavailable for unattended auth check",
            fix="Install Claude Code or keep unattended jobs off the Claude lane.",
        )
        return

    auth_error = unattended_claude_auth_error(bare=True)
    if auth_error is None:
        _add(
            checks,
            name="claude_unattended_auth",
            status="PASS",
            summary="unattended Claude bare-mode auth configured",
            detail="ANTHROPIC_API_KEY present for `claude -p --bare` lanes.",
        )
        return

    failures = _recent_unattended_claude_auth_failures()
    detail = auth_error
    if failures:
        detail = " | ".join([detail, *failures])
        _add(
            checks,
            name="claude_unattended_auth",
            status="FAIL",
            summary="unattended Claude lanes lack bare-mode auth and are actively failing",
            detail=detail,
            fix="Set ANTHROPIC_API_KEY for unattended `claude -p --bare` runs, or rework those jobs off bare mode.",
        )
        return

    _add(
        checks,
        name="claude_unattended_auth",
        status="WARN",
        summary="unattended Claude bare-mode auth is not configured",
        detail=detail,
        fix="Set ANTHROPIC_API_KEY for unattended `claude -p --bare` runs, or rework those jobs off bare mode.",
    )


def _check_fasttext(checks: list[DoctorCheck]) -> None:
    path = os.getenv("DGC_FASTTEXT_MODEL_PATH", "").strip()
    if not path:
        path = str(HOME / ".dharma" / "models" / "lid.176.bin")
    model_path = Path(path)

    if not model_path.exists():
        _add(
            checks,
            name="fasttext",
            status="WARN",
            summary=f"model missing: {model_path}",
            fix="Download lid.176.bin and set DGC_FASTTEXT_MODEL_PATH.",
        )
        return

    size_mb = model_path.stat().st_size / (1024 * 1024)
    def _venv_fasttext_ok() -> bool:
        ok, out = _run_venv_probe(
            (
                "from dharma_swarm.router_v1 import _predict_fasttext_language; "
                "p=_predict_fasttext_language('日本語の文章です。'); "
                "print('ok' if p else 'none')"
            ),
            timeout_seconds=1.2,
        )
        return ok and "ok" in out

    try:
        from dharma_swarm.router_v1 import _predict_fasttext_language

        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            pred = _predict_fasttext_language("日本語の文章です。")
        if pred and pred[0]:
            _add(
                checks,
                name="fasttext",
                status="PASS",
                summary=f"model loaded ({size_mb:.1f}MB), sample={pred[0]}:{pred[1]:.3f}",
            )
            return
        if _venv_fasttext_ok():
            _add(
                checks,
                name="fasttext",
                status="PASS",
                summary=f"model loaded via venv runtime ({size_mb:.1f}MB)",
                detail="Primary interpreter missing fasttext bindings; venv path works.",
            )
            return
    except Exception as exc:
        if _venv_fasttext_ok():
            _add(
                checks,
                name="fasttext",
                status="PASS",
                summary=f"model loaded via venv runtime ({size_mb:.1f}MB)",
                detail="Primary interpreter missing fasttext bindings; venv path works.",
            )
            return
        _add(
            checks,
            name="fasttext",
            status="WARN",
            summary=f"model exists ({size_mb:.1f}MB) but runtime failed",
            detail=str(exc),
            fix="Install fasttext-wheel in active runtime and verify import path.",
        )
        return

    _add(
        checks,
        name="fasttext",
        status="WARN",
        summary=f"model exists ({size_mb:.1f}MB) but prediction unavailable",
        fix="Check fasttext-wheel install and router_v1 fasttext path.",
    )


def _check_redis(checks: list[DoctorCheck], timeout_seconds: float, quick: bool) -> None:
    url = os.getenv("DGC_ROUTER_REDIS_URL", "").strip()
    if not url:
        _add(
            checks,
            name="redis",
            status="WARN",
            summary="DGC_ROUTER_REDIS_URL not set",
            fix="Set DGC_ROUTER_REDIS_URL in .env (e.g. redis://127.0.0.1:6379/0).",
        )
        return

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    try:
        with socket.create_connection((host, port), timeout=max(0.2, timeout_seconds)):
            pass
    except Exception as exc:
        lowered = str(exc).lower()
        if "operation not permitted" in lowered or "permission denied" in lowered:
            _add(
                checks,
                name="redis",
                status="WARN",
                summary=f"redis probe blocked by runtime permissions ({host}:{port})",
                detail=str(exc),
                fix="Run `dgc doctor` directly in terminal (not sandbox) for live Redis probe.",
            )
            return
        _add(
            checks,
            name="redis",
            status="FAIL",
            summary=f"socket connect failed ({host}:{port})",
            detail=str(exc),
            fix="Run scripts/start_router_redis.sh then re-run `dgc doctor`.",
        )
        return

    if quick:
        _add(
            checks,
            name="redis",
            status="PASS",
            summary=f"socket reachable at {host}:{port}",
        )
        return

    redis_spec = importlib.util.find_spec("redis")
    if redis_spec is None:
        ok, out = _run_venv_probe(
            (
                "import redis; "
                "c=redis.Redis.from_url("
                f"'{url}', decode_responses=True, socket_connect_timeout=0.8, socket_timeout=0.8"
                "); "
                "print('ok' if c.ping() else 'none')"
            ),
            timeout_seconds=1.5,
        )
        if ok and "ok" in out:
            _add(
                checks,
                name="redis",
                status="PASS",
                summary=f"redis ping OK via venv runtime ({host}:{port})",
            )
            return
        _add(
            checks,
            name="redis",
            status="WARN",
            summary=f"socket reachable at {host}:{port}, but `redis` package missing",
            fix="Install router extras: pip install 'dharma-swarm[router]'.",
        )
        return

    try:
        import redis  # type: ignore

        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=max(0.2, timeout_seconds),
            socket_timeout=max(0.2, timeout_seconds),
        )
        ok = bool(client.ping())
        if ok:
            _add(
                checks,
                name="redis",
                status="PASS",
                summary=f"redis ping OK ({host}:{port})",
            )
            return
    except Exception as exc:
        _add(
            checks,
            name="redis",
            status="WARN",
            summary=f"socket reachable but ping failed ({host}:{port})",
            detail=str(exc),
            fix="Check redis credentials/network and redis Python package runtime.",
        )
        return

    _add(
        checks,
        name="redis",
        status="WARN",
        summary=f"socket reachable but redis ping response was unexpected ({host}:{port})",
    )


def _check_router_wiring(checks: list[DoctorCheck]) -> None:
    try:
        from dharma_swarm.providers import ModelRouter, ProviderType
        from dharma_swarm.resilience import CircuitBreakerRegistry
        from dharma_swarm.router_v1 import detect_language_profile

        _ = ModelRouter
        _ = ProviderType
        _ = CircuitBreakerRegistry
        _ = detect_language_profile("This is a router smoke test.")
        _add(
            checks,
            name="router_wiring",
            status="PASS",
            summary="router modules import and basic language detection works",
        )
    except Exception as exc:
        _add(
            checks,
            name="router_wiring",
            status="FAIL",
            summary="router module wiring/import failed",
            detail=str(exc),
            fix="Fix import/runtime errors in providers/resilience/router_v1.",
        )


def _check_router_paths(checks: list[DoctorCheck]) -> None:
    memory_db = Path(
        os.getenv(
            "DGC_ROUTER_MEMORY_DB",
            str(HOME / ".dharma" / "logs" / "router" / "routing_memory.sqlite3"),
        )
    )
    audit_log = Path(
        os.getenv(
            "DGC_ROUTER_AUDIT_LOG",
            str(HOME / ".dharma" / "logs" / "router" / "routing_decisions.jsonl"),
        )
    )
    needs = [memory_db.parent, audit_log.parent]
    missing = [str(path) for path in needs if not path.exists()]

    if missing:
        _add(
            checks,
            name="router_paths",
            status="WARN",
            summary=f"router log dirs missing ({len(missing)})",
            detail=", ".join(missing),
            fix="Create directories before long-run: mkdir -p ~/.dharma/logs/router",
        )
        return

    _add(
        checks,
        name="router_paths",
        status="PASS",
        summary="router log/memory directories exist",
    )


def _doctor_status(summary: dict[str, int]) -> str:
    status = "PASS"
    if int(summary.get("fail", 0)) > 0:
        status = "FAIL"
    elif int(summary.get("warn", 0)) > 0:
        status = "WARN"
    return status


def _assurance_report(*, repo_root: Path, quick: bool) -> dict[str, Any]:
    from dharma_swarm.assurance.runner import assurance_checks, run_assurance
    changed_files: list[str] | None = None
    if quick:
        try:
            from dharma_swarm.assurance.scanner_test_gaps import _git_changed_files
            changed_files = _git_changed_files(repo_root)
        except Exception:
            changed_files = None
    assurance = run_assurance(repo_root=repo_root, changed_files=changed_files)
    assurance["checks"] = assurance_checks(assurance)
    return assurance


def write_doctor_artifacts(
    report: dict[str, Any],
    *,
    output_dir: Path | None = None,
    write_history: bool = True,
) -> dict[str, str]:
    target_dir = output_dir or DOCTOR_DIR
    history_dir = target_dir / "history"
    target_dir.mkdir(parents=True, exist_ok=True)
    history_dir.mkdir(parents=True, exist_ok=True)

    persisted_report = dict(report)
    if not persisted_report.get("generated_at"):
        legacy_timestamp = _parse_iso_datetime(persisted_report.get("timestamp_utc"))
        if legacy_timestamp is not None:
            persisted_report["generated_at"] = legacy_timestamp.isoformat()
        else:
            persisted_report["generated_at"] = datetime.now(timezone.utc).isoformat()

    rendered = render_doctor_report(persisted_report)
    latest_json = target_dir / "latest_report.json"
    latest_markdown = target_dir / "latest_report.md"
    latest_json.write_text(json.dumps(persisted_report, indent=2), encoding="utf-8")
    latest_markdown.write_text(rendered + "\n", encoding="utf-8")

    history_json = ""
    history_markdown = ""
    if write_history:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        history_json_path = history_dir / f"doctor_{stamp}.json"
        history_markdown_path = history_dir / f"doctor_{stamp}.md"
        history_json_path.write_text(json.dumps(persisted_report, indent=2), encoding="utf-8")
        history_markdown_path.write_text(rendered + "\n", encoding="utf-8")
        history_json = str(history_json_path)
        history_markdown = str(history_markdown_path)

    return {
        "json": str(latest_json),
        "markdown": str(latest_markdown),
        "history_json": history_json,
        "history_markdown": history_markdown,
    }


def load_latest_doctor_report(*, output_dir: Path | None = None) -> dict[str, Any] | None:
    target_dir = output_dir or DOCTOR_DIR
    latest_json = target_dir / "latest_report.json"
    if not latest_json.exists():
        return None
    try:
        return json.loads(latest_json.read_text(encoding="utf-8"))
    except Exception:
        return None


def create_doctor_job(
    *,
    schedule: str = "every 6h",
    quick: bool = True,
    strict: bool = False,
    timeout_seconds: float = 1.5,
) -> dict[str, Any]:
    from dharma_swarm.cron_scheduler import create_job

    return create_job(
        prompt="Run the DGC Doctor assurance sweep and persist the latest report.",
        schedule=schedule,
        name="doctor_assurance",
        handler="doctor_assurance",
        urgent=True,
        doctor_quick=quick,
        doctor_strict=strict,
        timeout_sec=timeout_seconds,
    )


def doctor_run_fn(job: dict[str, Any]) -> tuple[bool, str, str | None]:
    quick = bool(job.get("doctor_quick", True))
    strict = bool(job.get("doctor_strict", False))
    timeout_seconds = float(job.get("timeout_sec", 1.5) or 1.5)
    report = run_doctor(timeout_seconds=timeout_seconds, quick=quick)
    artifacts = write_doctor_artifacts(report)
    output = render_doctor_report(report)
    output += (
        "\n\nArtifacts:\n"
        f"- latest json: {artifacts['json']}\n"
        f"- latest markdown: {artifacts['markdown']}"
    )
    status = str(report.get("status", "PASS"))
    success = status == "PASS" or (status == "WARN" and not strict)
    error = None if success else f"Doctor report status={status}"
    return success, output, error


def run_doctor(
    *,
    timeout_seconds: float = 1.5,
    quick: bool = False,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    checks: list[DoctorCheck] = []
    _check_env_autoload(checks)
    _check_daemon_integrity(checks, timeout_seconds=timeout_seconds)
    _check_dgc_health_snapshot(checks)
    _check_message_bus_integrity(checks, timeout_seconds=timeout_seconds)
    _check_doctor_schedule(checks)
    _check_router_env(checks)
    _check_worker_bins(checks, timeout_seconds=timeout_seconds)
    _check_provider_env(checks)
    _check_claude_unattended_auth(checks)
    _check_fasttext(checks)
    _check_redis(checks, timeout_seconds=timeout_seconds, quick=quick)
    _check_router_paths(checks)
    _check_router_wiring(checks)

    root = repo_root or REPO_ROOT
    assurance: dict[str, Any] = {}
    try:
        assurance = _assurance_report(repo_root=root, quick=quick)
        for check in assurance.get("checks", []):
            _add(
                checks,
                name=str(check.get("name", "assurance_unknown")),
                status=str(check.get("status", "WARN")),
                summary=str(check.get("summary", "")).strip(),
                detail=str(check.get("detail", "")).strip(),
            )
    except Exception as exc:
        _add(
            checks,
            name="assurance_runner",
            status="WARN",
            summary="assurance mesh failed to run",
            detail=str(exc),
            fix="Fix scanner/runtime errors under dharma_swarm/assurance before trusting doctor output.",
        )

    pass_count = sum(1 for c in checks if c.status == "PASS")
    warn_count = sum(1 for c in checks if c.status == "WARN")
    fail_count = sum(1 for c in checks if c.status == "FAIL")

    fixes = [c.fix for c in checks if c.fix]
    for fix in assurance.get("recommended_fixes", []):
        if fix and fix not in fixes:
            fixes.append(str(fix))

    summary = {
        "total": len(checks),
        "pass": pass_count,
        "warn": warn_count,
        "fail": fail_count,
    }
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": _doctor_status(summary),
        "summary": summary,
        "checks": [c.to_dict() for c in checks],
        "recommended_fixes": fixes,
        "assurance": assurance,
        "artifacts": {
            "latest_json": str(DOCTOR_DIR / "latest_report.json"),
            "latest_markdown": str(DOCTOR_DIR / "latest_report.md"),
        },
    }


def doctor_exit_code(report: dict[str, Any], *, strict: bool = False) -> int:
    summary = report.get("summary", {})
    fail_count = int(summary.get("fail", 0))
    warn_count = int(summary.get("warn", 0))
    if fail_count > 0:
        return 2
    if strict and warn_count > 0:
        return 1
    return 0


def render_doctor_report(report: dict[str, Any]) -> str:
    lines = ["=== DGC DOCTOR ==="]
    lines.append(
        "Overall: "
        f"{report.get('status', 'UNKNOWN')} "
        f"(pass={report.get('summary', {}).get('pass', 0)}, "
        f"warn={report.get('summary', {}).get('warn', 0)}, "
        f"fail={report.get('summary', {}).get('fail', 0)})"
    )

    for check in report.get("checks", []):
        status = str(check.get("status", "UNKNOWN"))
        name = str(check.get("name", "unknown"))
        summary = str(check.get("summary", "")).strip()
        detail = str(check.get("detail", "")).strip()
        lines.append(f"[{status}] {name}: {summary}")
        if detail:
            lines.append(f"  detail: {detail}")

    assurance = report.get("assurance", {})
    if assurance:
        try:
            from dharma_swarm.assurance.runner import render_assurance_report

            lines.append("")
            lines.append(render_assurance_report(assurance))
        except Exception:
            logger.debug("Assurance report render failed", exc_info=True)

    fixes = [str(item).strip() for item in report.get("recommended_fixes", []) if str(item).strip()]
    if fixes:
        lines.append("")
        lines.append("Recommended fixes:")
        for idx, item in enumerate(fixes, start=1):
            lines.append(f"{idx}. {item}")

    artifacts = report.get("artifacts", {})
    latest_json = str(artifacts.get("latest_json", "")).strip()
    latest_markdown = str(artifacts.get("latest_markdown", "")).strip()
    if latest_json or latest_markdown:
        lines.append("")
        lines.append("Artifact targets:")
        if latest_json:
            lines.append(f"- json: {latest_json}")
        if latest_markdown:
            lines.append(f"- markdown: {latest_markdown}")

    return "\n".join(lines)
