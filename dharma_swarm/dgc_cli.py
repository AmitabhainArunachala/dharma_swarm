"""DGC CLI — unified command interface for the dharmic swarm.

Merges dgc-core commands (status, pulse, swarm, gates, memory, witness,
context, agni, etc.) with dharma_swarm's async orchestrator (spawn, task,
evolve, run, health-check).  No sys.path hacks — all imports are proper
``from dharma_swarm.*`` paths.

Usage:
  dgc                           Launch interactive TUI (or Claude Code if DGC_DEFAULT_MODE=chat)
  dgc chat                      Launch native Claude Code interactive UI
  dgc dashboard                 Launch interactive DGC dashboard (TUI)
  dgc status                    System status overview
  dgc runtime-status            Canonical runtime control-plane summary
  dgc mission-status            Mission-level readiness across core/accelerators
  dgc mission-brief             Show the active mission continuity state
  dgc campaign-brief            Show the active dual-engine campaign state
  dgc canonical-status          Show which DGC/SAB repos are canonical vs split
  dgc up [--background]         Start the daemon
  dgc down                      Stop the daemon
  dgc daemon-status             Show daemon state
  dgc pulse                     Run one heartbeat pulse
  dgc swarm [plan]              Run orchestrator (build/research/deploy/maintenance)
  dgc stress [--profile max]    Run end-to-end max-capacity stress harness
  dgc full-power-probe          Run operator-facing full-power verification
  dgc provider-smoke            Probe Ollama and NVIDIA NIM completion lanes
  dgc provider-matrix           Run the live provider/model matrix harness
  dgc swarm --status            Show orchestrator state
  dgc swarm live [N]            Persistent tmux swarm (N agents)
  dgc swarm overnight start [H] [--aggressive]
  dgc swarm overnight stop|status|report
  dgc swarm codex-night start [H] [--yolo] [--mission-file PATH]
  dgc swarm codex-night yolo [H]
  dgc swarm codex-night stop|status|report
  dgc swarm yolo                Aggressive Codex overnight (10h)
  dgc context [domain]          Load context (research/content/ops/all)
  dgc memory                    Show memory status
  dgc witness "msg"             Record a witness observation
  dgc develop "what" "evidence" Record a development marker
  dgc gates "action"            Run telos gates on an action
  dgc meta                      Overseeing I — wholistic system assessment
  dgc prune [--dry-run]         Sweep the zen garden — cut noise, keep signal
  dgc health                    Ecosystem file health
  dgc ouroboros connections|record  Inspect or canonically bind behavioral observations
  dgc health-check              Monitor-based system health (v0.2.0)
  dgc doctor                    Deep runtime diagnostics + fix guidance
  dgc spawn --name X --role Y   Spawn a new agent
  dgc task create "title"       Create a task
  dgc task list [--status S]    List tasks
  dgc evolve propose COMP DESC  Run evolution pipeline
  dgc evolve trend [--component C]
  dgc reciprocity health|summary|record|publish  Planetary Reciprocity Commons endpoints
  dgc rag health|search|chat    NVIDIA RAG integration endpoints
  dgc flywheel jobs|export|record|...  NVIDIA Data Flywheel job lifecycle
  dgc run [--interval N]        Run orchestration loop
  dgc setup                     Install dependencies
  dgc migrate                   Migrate old DGC memory
  dgc agni "cmd"                Run command on AGNI VPS via SSH
  dgc foundations [pillar]        Intellectual pillars and syntheses
  dgc telos [doc]                 Telos Engine research documents
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HOME = Path.home()
DHARMA_STATE = HOME / ".dharma"
DHARMA_SWARM = HOME / "dharma_swarm"
DGC_CORE = HOME / "dgc-core"
DEFAULT_SPRINT_LLM_TIMEOUT_SEC = 12.0

# Keep mission-status aligned with the lanes the overnight cycle depends on:
# accelerator adapters, canonical evaluation binding, and behavioral feedback.
MISSION_TRACKED_PATHS: tuple[str, ...] = (
    "dharma_swarm/evaluation_registry.py",
    "dharma_swarm/integrations/nvidia_rag.py",
    "dharma_swarm/integrations/data_flywheel.py",
    "dharma_swarm/integrations/reciprocity_commons.py",
    "dharma_swarm/ouroboros.py",
    "scripts/caffeine_until_jst.sh",
    "scripts/connection_finder.py",
    "scripts/ouroboros_experiment.py",
    "scripts/thinkodynamic_director.py",
    "docs/NVIDIA_INFRA_SELF_HEAL.md",
    "tests/test_evaluation_registry.py",
    "tests/test_integrations_nvidia_rag.py",
    "tests/test_integrations_data_flywheel.py",
    "tests/test_integrations_reciprocity_commons.py",
    "tests/test_ouroboros.py",
    "tests/tui/test_app_plan_mode.py",
)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(errors="ignore").splitlines()
    except Exception:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if (
            len(value) >= 2
            and ((value[0] == value[-1] == '"') or (value[0] == value[-1] == "'"))
        ):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _bootstrap_env() -> None:
    # Load dharma_swarm defaults and optional local runtime overrides.
    _load_env_file(HOME / "dharma_swarm" / ".env")
    _load_env_file(HOME / ".dharma" / "env" / "nvidia_remote.env")


_bootstrap_env()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


def _load_json_object(
    *,
    json_payload: str | None = None,
    file_path: str | None = None,
    label: str = "JSON payload",
) -> dict[str, Any]:
    if json_payload is None and file_path is None:
        raise ValueError(f"{label} is required")

    raw = json_payload
    if file_path is not None:
        raw = Path(file_path).read_text(encoding="utf-8")

    try:
        payload = json.loads(raw if raw is not None else "")
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"{label} must decode to a JSON object")
    return payload


def _normalize_optional_text(value: str | None, *, default: str = "") -> str:
    normalized = str(value or "").strip()
    return normalized or default


def _default_ouroboros_log_path() -> Path:
    candidates = (
        DHARMA_STATE / "evolution" / "observations" / "ouroboros_log.jsonl",
        DHARMA_STATE / "evolution" / "ouroboros_log.jsonl",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _load_ouroboros_observation(
    *,
    log_path: Path,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    if not log_path.exists():
        raise FileNotFoundError(f"ouroboros log not found: {log_path}")

    selected: dict[str, Any] | None = None
    for line_no, raw_line in enumerate(log_path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            decoded = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"ouroboros log {log_path} contains invalid JSON on line {line_no}"
            ) from exc
        if not isinstance(decoded, dict):
            raise ValueError(
                f"ouroboros log {log_path} contains a non-object JSON record on line {line_no}"
            )
        if cycle_id:
            if str(decoded.get("cycle_id") or "").strip() == cycle_id:
                selected = decoded
        else:
            selected = decoded

    if selected is None:
        if cycle_id:
            raise ValueError(f"no ouroboros observation found for cycle_id={cycle_id}")
        raise ValueError(f"no ouroboros observations found in {log_path}")
    return selected


async def _get_swarm(state_dir: str = ".dharma"):
    from dharma_swarm.swarm import SwarmManager

    swarm = SwarmManager(state_dir=state_dir)
    await swarm.init()
    return swarm


async def _get_task_board(state_dir: str = ".dharma"):
    """Thin path: open just the TaskBoard without booting the full swarm.

    Used by CLI task create/list/show to avoid spawning agents and seed tasks.
    """
    from dharma_swarm.task_board import TaskBoard

    db_path = Path(state_dir) / "db" / "tasks.db"
    tb = TaskBoard(db_path)
    await tb.init_db()
    return tb


def _pid_alive(pid: int) -> bool:
    try:
        if pid <= 1:
            return False
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _tail(path: Path, lines: int = 60) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(errors="ignore")
        return "\n".join(text.splitlines()[-lines:])
    except Exception:
        return ""


def _parse_iso_datetime(raw: str | None) -> datetime | None:
    if not raw:
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
    total = max(0, int(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _runtime_pid_status() -> tuple[int | None, str]:
    pid_file = DHARMA_STATE / "daemon.pid"
    if not pid_file.exists():
        return (None, "missing")
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except Exception:
        return (None, "invalid")
    if _pid_alive(pid):
        return (pid, "alive")
    return (pid, "stale")


def _list_daemon_like_processes() -> list[tuple[int, str]]:
    """Best-effort process scan for live daemon/orchestrator launchers."""
    try:
        proc = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
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


def _first_daemon_like_process() -> tuple[int, str] | None:
    matches = _list_daemon_like_processes()
    if not matches:
        return None
    return matches[0]


def _pulse_sort_key(last_seen: str | None, source: Path) -> float:
    parsed = _parse_iso_datetime(last_seen)
    if parsed is not None:
        return parsed.timestamp()
    try:
        return source.stat().st_mtime
    except Exception:
        return 0.0


def _pulse_timestamp_or_mtime(
    timestamp: datetime | None,
    source: Path,
    *,
    future_tolerance_seconds: float = 300.0,
) -> datetime:
    """Use parsed pulse timestamps unless they are implausibly in the future."""
    if timestamp is not None:
        now = datetime.now(timezone.utc)
        if (timestamp - now).total_seconds() <= future_tolerance_seconds:
            return timestamp
    return datetime.fromtimestamp(source.stat().st_mtime, timezone.utc)


def _pulse_summary_from_log(path: Path) -> tuple[int, str | None, Path] | None:
    if not path.exists():
        return None
    try:
        count = 0
        last_seen: str | None = None
        for raw_line in path.read_text(errors="ignore").splitlines():
            line = raw_line.strip()
            if line.startswith("--- PULSE @"):
                count += 1
                marker = line[len("--- PULSE @"):].strip()
                timestamp = marker.split(" [", 1)[0].strip()
                if timestamp:
                    last_seen = timestamp
                continue
            marker = "pulse_"
            if marker not in line:
                continue
            start = line.rfind(marker)
            end = line.find(".md", start)
            if start == -1 or end == -1:
                continue
            count += 1
            raw_stamp = line[start + len(marker):end]
            try:
                parsed = datetime.strptime(raw_stamp, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
                last_seen = _pulse_timestamp_or_mtime(parsed, path).isoformat()
            except ValueError:
                last_seen = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        if last_seen:
            return (count, last_seen, path)
        return (1, datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(), path)
    except Exception:
        return None


def _canonical_pulse_summary() -> tuple[int, str | None, Path | None]:
    candidates = [
        summary
        for summary in (
            _pulse_summary_from_log(DHARMA_STATE / "pulse.log"),
            _pulse_summary_from_log(DHARMA_STATE / "logs" / "pulse.log"),
        )
        if summary is not None
    ]

    cron_dir = DHARMA_STATE / "cron"
    pulse_artifacts = sorted(cron_dir.glob("pulse_*.md"))
    if pulse_artifacts:
        latest = pulse_artifacts[-1].stem.removeprefix("pulse_")
        try:
            parsed = datetime.strptime(latest, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
            timestamp = _pulse_timestamp_or_mtime(parsed, pulse_artifacts[-1])
            candidates.append((len(pulse_artifacts), timestamp.isoformat(), pulse_artifacts[-1]))
        except ValueError:
            candidates.append(
                (
                    len(pulse_artifacts),
                    datetime.fromtimestamp(pulse_artifacts[-1].stat().st_mtime, timezone.utc).isoformat(),
                    pulse_artifacts[-1],
                )
            )

    if candidates:
        log_candidates = [
            item for item in candidates
            if item[2].name == "pulse.log"
        ]
        if log_candidates:
            freshest_log = max(log_candidates, key=lambda item: _pulse_sort_key(item[1], item[2]))
            freshest_log_ts = _pulse_sort_key(freshest_log[1], freshest_log[2])
            if freshest_log_ts >= datetime.now(timezone.utc).timestamp() - 3600:
                return freshest_log
        count, last_seen, source = max(candidates, key=lambda item: _pulse_sort_key(item[1], item[2]))
        return (count, last_seen, source)

    return (0, None, None)


def _witness_sort_key(path: Path, *, prefix: str, fmt: str) -> float:
    stem = path.stem
    raw_stamp = stem.removeprefix(prefix) if prefix else stem
    try:
        return datetime.strptime(raw_stamp, fmt).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        try:
            return path.stat().st_mtime
        except Exception:
            return 0.0


def _latest_witness_count(directory: Path, *, pattern: str, prefix: str, fmt: str) -> int | None:
    if not directory.exists():
        return None

    candidates = sorted(
        directory.glob(pattern),
        key=lambda path: _witness_sort_key(path, prefix=prefix, fmt=fmt),
        reverse=True,
    )
    for witness_file in candidates:
        try:
            with witness_file.open(encoding="utf-8") as handle:
                return sum(1 for line in handle if line.strip())
        except Exception:
            continue
    return None


def _canonical_gate_count() -> int:
    canonical_count = _latest_witness_count(
        DHARMA_STATE / "witness",
        pattern="witness_*.jsonl",
        prefix="witness_",
        fmt="%Y%m%d",
    )
    if canonical_count is not None:
        return canonical_count

    legacy_count = _latest_witness_count(
        DGC_CORE / "memory" / "witness",
        pattern="*.jsonl",
        prefix="",
        fmt="%Y-%m-%d",
    )
    if legacy_count is not None:
        return legacy_count

    return 0


def _control_plane_snapshot() -> str | None:
    details: list[str] = []

    _, _, pulse_source = _canonical_pulse_summary()
    if pulse_source is not None:
        details.append(f"pulse_source={pulse_source}")

    live_pid, live_pid_state = _runtime_pid_status()
    if live_pid is not None:
        details.append(f"runtime_pid={live_pid}")
    elif live_pid_state != "missing":
        details.append(f"runtime_pid={live_pid_state}")

    snapshot_path = DHARMA_STATE / "stigmergy" / "dgc_health.json"
    if snapshot_path.exists():
        try:
            payload = json.loads(snapshot_path.read_text())
        except Exception:
            details.append("dgc_health=unreadable")
        else:
            timestamp = str(payload.get("timestamp", "")).strip()
            freshness = "unknown"
            parsed_timestamp = _parse_iso_datetime(timestamp)
            if parsed_timestamp is not None:
                age_seconds = (
                    datetime.now(timezone.utc) - parsed_timestamp
                ).total_seconds()
                freshness = "fresh" if age_seconds <= 3600 else "stale"
                details.append(f"snapshot_age={_format_age(age_seconds)}")
            elif timestamp:
                freshness = "unknown"
            daemon_pid = payload.get("daemon_pid")
            details.append(f"dgc_health={freshness}")
            if daemon_pid is not None:
                details.append(f"daemon_pid={daemon_pid}")
                try:
                    snapshot_pid = int(daemon_pid)
                except (TypeError, ValueError):
                    snapshot_pid = None
                if snapshot_pid is not None and live_pid is not None and snapshot_pid != live_pid:
                    details.append("daemon_pid_mismatch")

    if not details:
        return None
    return " | ".join(details)


def _accelerator_mode() -> str:
    configured = any(
        os.getenv(key, "").strip()
        for key in (
            "DGC_NVIDIA_RAG_URL",
            "DGC_NVIDIA_INGEST_URL",
            "DGC_DATA_FLYWHEEL_URL",
            "DGC_RECIPROCITY_COMMONS_URL",
        )
    )
    raw = os.getenv("DGC_ACCELERATOR_MODE", "enabled" if configured else "dormant")
    mode = raw.strip().lower()
    return mode or ("enabled" if configured else "dormant")


def _accelerators_enabled() -> bool:
    return _accelerator_mode() not in {"0", "off", "disabled", "none", "dormant"}


# ---------------------------------------------------------------------------
# Commands — carried over from dgc-core
# ---------------------------------------------------------------------------

def cmd_status() -> None:
    """System status overview."""
    print("=== DGC CORE STATUS ===\n")

    # Memory — try dharma_swarm async memory, fall back to summary
    try:
        from dharma_swarm.memory import StrangeLoopMemory

        async def _mem_stats():
            mem = StrangeLoopMemory(db_path=DHARMA_STATE / "db" / "memory.db")
            await mem.init_db()
            entries = await mem.recall(limit=5)
            await mem.close()
            return len(entries)

        count = _run(_mem_stats())
        print(f"Memory (async SQLite): {count} recent entries")
    except Exception as exc:
        print(f"Memory: unavailable ({exc})")

    # Daemon state
    pulse_count, last_pulse, pulse_source = _canonical_pulse_summary()
    if last_pulse:
        source_note = f" via {pulse_source}" if pulse_source is not None else ""
        print(f"Pulse: {pulse_count} logged{source_note}, last: {last_pulse}")
    else:
        print("Pulse: not yet run")

    # Gate witness log
    print(f"Gates today: {_canonical_gate_count()} checks")

    snapshot = _control_plane_snapshot()
    if snapshot:
        print(f"Control plane snapshot: {snapshot}")

    try:
        from dharma_swarm.tui_helpers import load_resident_seat_summary

        resident_seats = load_resident_seat_summary(
            runtime_db_path=DHARMA_STATE / "state" / "runtime.db",
            limit=4,
        )
    except Exception:
        resident_seats = []
    if resident_seats:
        print("\nResident seats:")
        for seat in resident_seats:
            seat_id = seat["seat_id"] or "unscoped"
            binding = seat["current_binding"] or "binding pending"
            print(f"  {seat['display_name']} [{seat_id}] -> {binding}")
            print(
                f"    id={seat['agent_id']}  runtime={seat['runtime_name']}  "
                f"status={seat['status']}"
            )

    # AGNI sync
    agni = HOME / "agni-workspace"
    if agni.exists():
        working = agni / "WORKING.md"
        if working.exists():
            age = (time.time() - working.stat().st_mtime) / 60
            print(f"\nAGNI workspace: synced, WORKING.md updated {age:.0f} min ago")
        else:
            print("\nAGNI workspace: synced but no WORKING.md")
    else:
        print("\nAGNI workspace: NOT SYNCED")

    # Trishula
    trishula = HOME / "trishula" / "inbox"
    if trishula.exists():
        msgs = list(trishula.glob("*.json"))
        print(f"Trishula inbox: {len(msgs)} messages")

    # Claude Code
    try:
        result = subprocess.run(
            ["claude", "--version"], capture_output=True, text=True, timeout=5,
        )
        print(f"\nClaude Code: {result.stdout.strip()}")
    except Exception:
        print("\nClaude Code: not found")

    print("\nMission spine: run `dgc mission-status` for full readiness lanes")
    print("Canonical topology: run `dgc canonical-status`")


def cmd_runtime_status(
    *,
    limit: int = 5,
    db_path: str | None = None,
) -> None:
    """Show the canonical runtime control-plane summary."""
    from dharma_swarm.tui_helpers import build_runtime_status_text

    print(
        build_runtime_status_text(
            limit=limit,
            runtime_db_path=Path(db_path) if db_path else None,
        )
    )


def _read_openclaw_summary() -> dict[str, Any]:
    """Best-effort OpenClaw summary from ~/.openclaw/openclaw.json."""
    oc_path = HOME / ".openclaw" / "openclaw.json"
    if not oc_path.exists():
        return {"present": False}
    try:
        payload = json.loads(oc_path.read_text())
    except Exception:
        return {"present": True, "readable": False}

    providers = []
    models = payload.get("models", {})
    if isinstance(models, dict):
        prov = models.get("providers", {})
        if isinstance(prov, dict):
            providers = sorted(prov.keys())

    agents_count = 0
    agents = payload.get("agents", {})
    if isinstance(agents, dict):
        lst = agents.get("list", [])
        if isinstance(lst, list):
            agents_count = len(lst)

    return {
        "present": True,
        "readable": True,
        "agents_count": agents_count,
        "providers": providers,
    }


def _tracked_paths(paths: list[str]) -> dict[str, bool]:
    """Return path->tracked bool for files relative to DHARMA_SWARM."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(DHARMA_SWARM), "ls-files", *paths],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        tracked = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    except Exception:
        tracked = set()
    return {p: (p in tracked) for p in paths}


def _core_mission_checks() -> dict[str, bool]:
    """Checks for core mission-critical intelligence wiring."""
    checks: dict[str, bool] = {}
    try:
        from dharma_swarm import evolution as evo

        checks["planner_executor"] = hasattr(evo, "EvolutionPlan")
        checks["circuit_breaker"] = "circuit_breaker_limit" in inspect.signature(
            evo.DarwinEngine.__init__
        ).parameters
        checks["traceability_fields"] = all(
            field in getattr(evo.Proposal, "model_fields", {})
            for field in ("spec_ref", "requirement_refs")
        )
    except Exception:
        checks["planner_executor"] = False
        checks["circuit_breaker"] = False
        checks["traceability_fields"] = False

    try:
        from dharma_swarm.telos_gates import TelosGatekeeper

        params = inspect.signature(TelosGatekeeper.check).parameters
        checks["think_points"] = (
            "think_phase" in params and "reflection" in params
        )
    except Exception:
        checks["think_points"] = False

    try:
        from dharma_swarm import startup_crew as sc

        checks["memory_survival_instinct"] = "MEMORY SURVIVAL INSTINCT" in str(
            getattr(sc, "MEMORY_SURVIVAL_INSTINCT", "")
        )
    except Exception:
        checks["memory_survival_instinct"] = False

    try:
        from dharma_swarm.tui import app as tui_app

        checks["tui_plan_mode_contract"] = "EnterPlanMode" in str(
            getattr(tui_app, "_PLAN_MODE_SYSTEM_PROMPT", "")
        )
    except Exception:
        checks["tui_plan_mode_contract"] = False

    return checks


MISSION_AUTONOMY_PROFILES: dict[str, dict[str, Any]] = {
    "readonly_audit": {
        "strict_core": True,
        "require_tracked": True,
        "trust_mode": "external_strict",
        "description": "Read-only verification lane with strict safety posture.",
    },
    "workspace_auto": {
        "strict_core": True,
        "require_tracked": True,
        "trust_mode": "internal_yolo",
        "description": "Default autonomous local workspace lane.",
    },
    "strict_external": {
        "strict_core": True,
        "require_tracked": True,
        "trust_mode": "external_strict",
        "description": "External-facing lane with strict trust mode.",
    },
    "yolo_local_container": {
        "strict_core": True,
        "require_tracked": True,
        "trust_mode": "internal_yolo",
        "description": "Fast lane intended for isolated local/container execution.",
    },
}


def _resolve_mission_profile(
    profile: str | None,
) -> tuple[str, dict[str, Any]] | tuple[None, None]:
    if not profile:
        return None, None
    key = profile.strip().lower()
    cfg = MISSION_AUTONOMY_PROFILES.get(key)
    if not cfg:
        return None, None
    return key, cfg


def cmd_mission_status(
    *,
    as_json: bool = False,
    strict_core: bool = False,
    require_tracked: bool = False,
    profile: str | None = None,
) -> int:
    """Mission-level readiness report across core + accelerator lanes.

    Returns:
        Process-style status code:
        - 0: pass
        - 2: strict core lane failure
        - 3: tracked wiring requirement failure
    """
    profile_name, profile_cfg = _resolve_mission_profile(profile)
    if profile and not profile_cfg:
        valid = ", ".join(sorted(MISSION_AUTONOMY_PROFILES))
        if as_json:
            print(
                json.dumps(
                    {
                        "exit_code": 4,
                        "error": f"Unknown autonomy profile: {profile}",
                        "valid_profiles": sorted(MISSION_AUTONOMY_PROFILES),
                    },
                    indent=2,
                )
            )
        else:
            print(f"Unknown autonomy profile: {profile}")
            print(f"Valid profiles: {valid}")
        return 4

    if profile_cfg:
        strict_core = strict_core or bool(profile_cfg.get("strict_core", False))
        require_tracked = require_tracked or bool(
            profile_cfg.get("require_tracked", False)
        )

    core = _core_mission_checks()
    core_pass = sum(1 for v in core.values() if v)

    tracked = _tracked_paths(list(MISSION_TRACKED_PATHS))
    tracked_count = sum(1 for v in tracked.values() if v)
    local_only = [path for path, ok in tracked.items() if not ok]

    oc = _read_openclaw_summary()

    async def _probe_accelerators() -> dict[str, str]:
        if not _accelerators_enabled():
            return {
                "rag_health": "DORMANT",
                "ingest_health": "DORMANT",
                "flywheel_jobs": "DORMANT",
                "reciprocity_health": "DORMANT",
            }
        from dharma_swarm.integrations import (
            DataFlywheelClient,
            NvidiaRagClient,
            ReciprocityCommonsClient,
        )

        out: dict[str, str] = {}
        rag = NvidiaRagClient()
        fw = DataFlywheelClient()
        reciprocity = ReciprocityCommonsClient()
        for label, fn in (
            ("rag_health", lambda: rag.health(service="rag")),
            ("ingest_health", lambda: rag.health(service="ingest")),
            ("flywheel_jobs", fw.list_jobs),
            ("reciprocity_health", reciprocity.health),
        ):
            try:
                await fn()
                out[label] = "PASS"
            except Exception as exc:
                out[label] = f"BLOCKED: {exc}"
        return out

    try:
        accel = _run(_probe_accelerators())
    except Exception as exc:
        accel = {
            "rag_health": f"BLOCKED: {exc}",
            "ingest_health": f"BLOCKED: {exc}",
            "flywheel_jobs": f"BLOCKED: {exc}",
            "reciprocity_health": f"BLOCKED: {exc}",
        }

    core_ok = core_pass == len(core)
    tracked_ok = tracked_count == len(tracked)

    if strict_core and not core_ok:
        exit_code = 2
    elif require_tracked and not tracked_ok:
        exit_code = 3
    else:
        exit_code = 0

    report: dict[str, Any] = {
        "vision": (
            "open, self-evolving, evidence-grounded agent orchestrator "
            "with durable memory, quality gates, and optional accelerator lanes"
        ),
        "core": {
            "pass_count": core_pass,
            "total": len(core),
            "ok": core_ok,
            "checks": core,
        },
        "autonomy_profile": {
            "name": profile_name or "none",
            "strict_core": strict_core,
            "require_tracked": require_tracked,
            "trust_mode": (
                profile_cfg.get("trust_mode")
                if profile_cfg
                else os.getenv("DGC_TRUST_MODE", "internal_yolo")
            ),
            "description": (
                profile_cfg.get("description")
                if profile_cfg
                else "No profile selected."
            ),
        },
        "tracked_wiring": {
            "tracked_count": tracked_count,
            "total": len(tracked),
            "ok": tracked_ok,
            "local_only": local_only,
        },
        "openclaw": oc,
        "accelerators": accel,
        "exit_code": exit_code,
    }

    if as_json:
        print(json.dumps(report, indent=2))
        return exit_code

    print("=== DGC MISSION STATUS ===")
    print(f"Vision: {report['vision']}.")
    ap = report["autonomy_profile"]
    print(
        "Autonomy profile: "
        f"{ap['name']} "
        f"(strict_core={int(ap['strict_core'])}, "
        f"require_tracked={int(ap['require_tracked'])}, "
        f"trust_mode={ap['trust_mode']})"
    )
    print(f"\nCore intelligence lane: {core_pass}/{len(core)} wired")
    for key in sorted(core):
        status = "PASS" if core[key] else "MISS"
        print(f"  [{status}] {key}")

    print(f"\nTracked wiring footprint: {tracked_count}/{len(tracked)} in git")
    for path in local_only:
        print(f"  [LOCAL-ONLY] {path}")

    print("\nOpenClaw lane:")
    if not oc.get("present"):
        print("  [MISS] ~/.openclaw/openclaw.json not found")
    elif not oc.get("readable", True):
        print("  [MISS] openclaw.json exists but is unreadable")
    else:
        print(
            "  [PASS] config present "
            f"(agents={oc.get('agents_count', 0)}, providers={len(oc.get('providers', []))})"
        )

    print("\nAccelerator lane (optional):")
    for key in ("rag_health", "ingest_health", "flywheel_jobs", "reciprocity_health"):
        val = accel.get(key, "BLOCKED")
        print(f"  [{key}] {val}")

    print("\nInterpretation:")
    if core_ok:
        print("  Core lane is wired. Mission can proceed without accelerator deps.")
    else:
        print("  Core lane has gaps. Fix misses before scaling autonomy.")
    if not tracked_ok:
        print("  Promote LOCAL-ONLY files into git to avoid drift between sessions.")
    if strict_core and not core_ok:
        print("  Strict core mode failed.")
    if require_tracked and not tracked_ok:
        print("  Required-tracked mode failed.")

    return exit_code


def cmd_mission_brief(
    *,
    path: str | None = None,
    state_dir: str | None = None,
    as_json: bool = False,
) -> int:
    """Show the active mission continuity state for the director."""
    from dharma_swarm.mission_contract import load_active_mission_state, render_mission_brief

    try:
        artifact = load_active_mission_state(
            state_dir=state_dir or DHARMA_STATE,
            path=path,
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    if artifact is None:
        state_root = Path(state_dir).expanduser() if state_dir else DHARMA_STATE
        mission_path = Path(path).expanduser() if path else state_root / "mission.json"
        print(f"No active mission state found at {mission_path}")
        return 1
    if as_json:
        print(json.dumps(artifact.model_dump(mode="json"), indent=2))
    else:
        print(render_mission_brief(artifact))
    return 0


def cmd_campaign_brief(
    *,
    path: str | None = None,
    state_dir: str | None = None,
    as_json: bool = False,
) -> int:
    """Show the active campaign continuity state for the director."""
    from dharma_swarm.mission_contract import load_active_campaign_state, render_campaign_brief

    try:
        artifact = load_active_campaign_state(
            state_dir=state_dir or DHARMA_STATE,
            path=path,
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    if artifact is None:
        state_root = Path(state_dir).expanduser() if state_dir else DHARMA_STATE
        campaign_path = Path(path).expanduser() if path else state_root / "campaign.json"
        print(f"No active campaign state found at {campaign_path}")
        return 1
    if as_json:
        print(json.dumps(artifact.model_dump(mode="json"), indent=2))
    else:
        print(render_campaign_brief(artifact))
    return 0


def cmd_canonical_status(*, as_json: bool = False) -> int:
    """Show which local repos are canonical, support shells, or legacy."""
    from dharma_swarm.workspace_topology import build_workspace_topology

    topo = build_workspace_topology()
    if as_json:
        print(json.dumps(topo, indent=2))
        return 0

    print("=== DGC CANONICAL STATUS ===")
    for domain in ("dgc", "sab"):
        block = topo.get(domain, {})
        label = domain.upper()
        merged = "YES" if block.get("fully_merged") else "NO"
        print(f"\n[{label}] fully merged: {merged}")
        canonical_repo = block.get("canonical_repo") or "unknown"
        print(f"Canonical authority: {canonical_repo}")
        for repo in block.get("repos", []):
            if not repo.get("exists"):
                state = "missing"
            elif not repo.get("is_git"):
                state = "not-git"
            else:
                dirty = repo.get("dirty")
                if dirty is None:
                    state = "git-unknown"
                else:
                    counts = []
                    if repo.get("modified_count"):
                        counts.append(f"modified={repo['modified_count']}")
                    if repo.get("untracked_count"):
                        counts.append(f"untracked={repo['untracked_count']}")
                    suffix = f" ({', '.join(counts)})" if counts else ""
                    state = ("dirty" if dirty else "clean") + suffix
            marker = "canonical" if repo.get("canonical") else repo.get("role")
            branch = repo.get("branch") or "unknown-branch"
            print(f"  - {repo.get('name')}: {marker} | {branch} | {state}")
            print(f"    {repo.get('path')}")

    if topo.get("warnings"):
        print("\nWarnings:")
        for warning in topo["warnings"]:
            print(f"  - {warning}")

    merge_summary = topo.get("merge_summary") or {}
    if merge_summary:
        print("\nMerge ledger:")
        bits = []
        for key in ("snapshot", "branch", "head", "mission_exit", "tracked", "legacy_imported", "predictor_rows"):
            if merge_summary.get(key):
                bits.append(f"{key}={merge_summary[key]}")
        if bits:
            print(f"  - {' '.join(bits)}")

    answer = topo.get("operator_answer", {})
    print("\nOperator answer:")
    print(f"  - Use {answer.get('dgc_code_authority')} as DGC code authority")
    print(f"  - Use {answer.get('sab_runtime_authority')} as SAB runtime authority")
    print(f"  - Treat {answer.get('legacy_dgc_archive')} as legacy until explicitly archived/frozen")
    print(f"  - Treat {answer.get('sab_strategy_shell')} as SAB strategy shell, not runtime authority")
    return 0


def cmd_context(domain: str = "all") -> None:
    """Load context for a domain."""
    try:
        from dharma_swarm.ecosystem_map import get_context_for

        print(get_context_for(domain))
    except ImportError:
        from dharma_swarm.context import build_agent_context

        print(build_agent_context(role=domain))


def cmd_memory() -> None:
    """Show memory status, recent entries, and unresolved latent gold."""
    async def _show():
        from dharma_swarm.memory import StrangeLoopMemory
        from dharma_swarm.context import read_latent_gold_overview
        from dharma_swarm.routing_memory import (
            RoutingMemoryStore,
            default_routing_memory_db_path,
        )

        mem = StrangeLoopMemory(db_path=DHARMA_STATE / "db" / "memory.db")
        await mem.init_db()
        entries = await mem.recall(limit=10)
        await mem.close()
        if not entries:
            print("Memory: empty")
        else:
            print(f"=== Strange Loop Memory ({len(entries)} recent) ===\n")
            for e in entries:
                ts = e.timestamp.isoformat()[:19] if hasattr(e.timestamp, "isoformat") else str(e.timestamp)[:19]
                print(f"  [{e.layer.value:>11}] {ts}  {e.content[:100]}")

        latent = read_latent_gold_overview(state_dir=DHARMA_STATE, limit=5)
        if latent:
            print("\n=== Latent Gold (unresolved high-salience ideas) ===\n")
            for line in latent.splitlines():
                print(line)

        routing_db = default_routing_memory_db_path()
        if routing_db.exists():
            routing = RoutingMemoryStore(routing_db)
            top_routes = routing.top_routes(limit=5)
            if top_routes:
                print("\n=== Routing Memory (top learned lanes) ===\n")
                for lane in top_routes:
                    print(
                        "  "
                        f"{lane.provider.value}:{lane.model} "
                        f"[{lane.task_signature}] "
                        f"score={lane.blended_score:.3f} "
                        f"samples={lane.sample_count}"
                    )

        retrospective_path = Path(
            os.environ.get(
                "DGC_ROUTER_RETROSPECTIVE_LOG",
                str(DHARMA_STATE / "logs" / "router" / "route_retrospectives.jsonl"),
            )
        )
        if retrospective_path.exists():
            recent: list[dict[str, Any]] = []
            for line in retrospective_path.read_text(encoding="utf-8").splitlines()[-5:]:
                try:
                    recent.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
            if recent:
                print("\n=== Route Retrospectives (recent high-confidence misses) ===\n")
                for item in recent:
                    record = item.get("route_record") or {}
                    provider = str(record.get("selected_provider") or "?")
                    action = str(record.get("action_name") or "?")
                    quality = record.get("quality_score")
                    severity = str(item.get("severity") or "review")
                    quality_text = (
                        f"{float(quality):.2f}"
                        if isinstance(quality, (int, float))
                        else "?"
                    )
                    print(
                        "  "
                        f"[{severity}] {action} -> {provider} "
                        f"quality={quality_text}"
                    )

    _run(_show())


def cmd_witness(msg: str) -> None:
    """Record a witness observation."""
    async def _witness():
        from dharma_swarm.memory import StrangeLoopMemory
        from dharma_swarm.models import MemoryLayer

        mem = StrangeLoopMemory(db_path=DHARMA_STATE / "db" / "memory.db")
        await mem.init_db()
        entry = await mem.remember(content=msg, layer=MemoryLayer.WITNESS)
        await mem.close()
        ts = entry.timestamp.isoformat()[:19] if hasattr(entry.timestamp, "isoformat") else str(entry.timestamp)[:19]
        print(f"Witnessed: {ts} | quality: {entry.witness_quality:.2f}")
        print(f"  {msg}")

    _run(_witness())


def cmd_develop(what: str, evidence: str) -> None:
    """Record a development marker."""
    async def _develop():
        from dharma_swarm.memory import StrangeLoopMemory
        from dharma_swarm.models import MemoryLayer

        mem = StrangeLoopMemory(db_path=DHARMA_STATE / "db" / "memory.db")
        await mem.init_db()
        content = f"DEVELOPMENT: {what} | Evidence: {evidence}"
        entry = await mem.remember(content=content, layer=MemoryLayer.DEVELOPMENT, development_marker=True)
        await mem.close()
        ts = entry.timestamp.isoformat()[:19] if hasattr(entry.timestamp, "isoformat") else str(entry.timestamp)[:19]
        print(f"Development recorded: {ts}")
        print(f"  What: {what}")
        print(f"  Evidence: {evidence}")

    _run(_develop())


def cmd_gates(action: str) -> None:
    """Run telos gates on an action."""
    from dharma_swarm.telos_gates import DEFAULT_GATEKEEPER

    result = DEFAULT_GATEKEEPER.check(action=action)
    print(f"Decision: {result.decision.value.upper()}")
    print(f"Reason: {result.reason}")


def cmd_maintenance(*, dry_run: bool = False, max_mb: float = 50.0) -> None:
    """Run WAL checkpoint + JSONL rotation for ~/.dharma/ housekeeping."""
    from dharma_swarm.maintenance import checkpoint_wal_files, rotate_jsonl_files

    print("=== WAL Checkpoint ===")
    wal = checkpoint_wal_files()
    for path, pages in wal.items():
        status = f"{pages} pages" if pages >= 0 else "FAILED"
        print(f"  {Path(path).name}: {status}")

    print(f"\n=== JSONL Rotation (threshold={max_mb}MB{', DRY-RUN' if dry_run else ''}) ===")
    rotated = rotate_jsonl_files(max_mb=max_mb, dry_run=dry_run)
    if rotated:
        for p in rotated:
            print(f"  Rotated: {Path(p).name}")
    else:
        print("  No files above threshold.")


def cmd_health() -> None:
    """Check ecosystem file health."""
    try:
        from dharma_swarm.ecosystem_map import check_health

        h = check_health()
        print(f"Ecosystem: {h['ok']} OK, {h['missing']} MISSING")
        if h["details"]:
            print("\nMissing paths:")
            for p, d in h["details"].items():
                print(f"  {p} -- {d}")
    except ImportError:
        print("ecosystem_map not available")


def cmd_cascade(
    domain: str = "code",
    seed_path: str | None = None,
    seed_skill: str | None = None,
    seed_project: str | None = None,
    track: str | None = None,
    max_iter: int | None = None,
) -> None:
    """Run a strange loop cascade domain."""
    import asyncio

    async def _run():
        from dharma_swarm.cascade import get_registered_domains, run_domain

        if domain == "all":
            domains = get_registered_domains()
            for name in sorted(domains):
                try:
                    config = {"max_iterations": max_iter} if max_iter else None
                    r = await run_domain(name, resume=False, config=config)
                    status = "EIGENFORM" if r.eigenform_reached else ("CONVERGED" if r.converged else "INCOMPLETE")
                    print(f"  [{name}] {status} iter={r.iterations_completed} fitness={r.best_fitness:.3f} ({r.duration_seconds:.1f}s)")
                except Exception as e:
                    print(f"  [{name}] ERROR: {e}")
            return

        seed = None
        if seed_path:
            seed = {"path": seed_path}
            if track:
                seed["track"] = track
        elif seed_skill:
            seed = {"skill_name": seed_skill}
        elif seed_project:
            seed = {"project_path": seed_project}

        config = {"max_iterations": max_iter} if max_iter else None
        r = await run_domain(domain, seed=seed, resume=False, config=config)
        status = "EIGENFORM" if r.eigenform_reached else ("CONVERGED" if r.converged else "INCOMPLETE")
        print(f"Domain:     {r.domain}")
        print(f"Status:     {status}")
        print(f"Iterations: {r.iterations_completed}")
        print(f"Best fit:   {r.best_fitness:.3f}")
        if r.convergence_reason:
            print(f"Reason:     {r.convergence_reason}")
        print(f"Duration:   {r.duration_seconds:.1f}s")
        if r.fitness_trajectory:
            print(f"Trajectory: {' → '.join(f'{f:.3f}' for f in r.fitness_trajectory[-5:])}")

    asyncio.run(_run())


def cmd_forge(path: str | None = None, batch: str | None = None) -> None:
    """Score artifact(s) through the quality forge."""
    from pathlib import Path as P

    def _score_file(filepath: str) -> None:
        p = P(filepath).resolve()
        if not p.exists():
            print(f"  {filepath}: NOT FOUND")
            return

        content = p.read_text()
        scores: dict[str, float] = {}

        if p.suffix == ".py":
            try:
                from dharma_swarm.elegance import evaluate_elegance
                e = evaluate_elegance(content)
                scores["elegance"] = e.overall
            except Exception:
                scores["elegance"] = 0.0

        try:
            from dharma_swarm.metrics import MetricsAnalyzer
            sig = MetricsAnalyzer().analyze(content)
            scores["swabhaav"] = sig.swabhaav_ratio
            scores["entropy"] = sig.entropy
            scores["mimicry"] = 1.0 if sig.recognition_type.value == "MIMICRY" else 0.0
        except Exception:
            pass

        # Composite
        elegance = scores.get("elegance", 0.5)
        swabhaav = scores.get("swabhaav", 0.5)
        stars = elegance * 0.5 + swabhaav * 0.3 + (1.0 - scores.get("mimicry", 0.0)) * 0.2
        print(f"  {p.name}: {stars*10:.1f}★  elegance={elegance:.2f} swabhaav={swabhaav:.2f}")

    if batch:
        bp = P(batch)
        files = sorted(bp.glob("**/*.py")) + sorted(bp.glob("**/*.md"))
        print(f"Scoring {len(files)} files in {batch}:")
        for f in files[:20]:
            _score_file(str(f))
        if len(files) > 20:
            print(f"  ... and {len(files) - 20} more")
    elif path:
        print("Forge Score:")
        _score_file(path)
    else:
        print("Usage: dgc forge <path> | dgc forge --batch <dir>")


def cmd_loops() -> None:
    """Show strange loop status and cascade history."""
    import json
    from pathlib import Path as P

    state_dir = P.home() / ".dharma"
    meta_dir = state_dir / "meta"

    # Recognition seed
    seed_path = meta_dir / "recognition_seed.md"
    if seed_path.exists():
        lines = seed_path.read_text().split("\n")
        print(f"Recognition seed: {len(seed_path.read_text())} chars ({lines[0].strip()})")
    else:
        print("Recognition seed: NOT YET GENERATED")

    # TCS
    tcs_path = state_dir / "stigmergy" / "mycelium_identity_tcs.json"
    if tcs_path.exists():
        try:
            d = json.loads(tcs_path.read_text())
            print(f"TCS: {d.get('tcs', '?')} ({d.get('regime', '?')})")
        except Exception:
            print("TCS: error reading")
    else:
        print("TCS: no data")

    # Cascade history
    history_path = meta_dir / "cascade_history.jsonl"
    if history_path.exists():
        lines = [l for l in history_path.read_text().strip().split("\n") if l.strip()]
        print(f"\nCascade history: {len(lines)} runs")
        for line in lines[-5:]:
            try:
                d = json.loads(line)
                status = "EIGENFORM" if d.get("eigenform_reached") else ("CONVERGED" if d.get("converged") else "INCOMPLETE")
                print(f"  {d.get('domain', '?')}: {status} fitness={d.get('best_fitness', 0):.3f} iter={d.get('iterations', 0)}")
            except json.JSONDecodeError:
                pass
    else:
        print("\nCascade history: no runs yet")

    # Daemon status
    pid_file = state_dir / "daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            print(f"\nDaemon: running (PID {pid})")
        except (ValueError, OSError):
            print("\nDaemon: dead (stale PID file)")
    else:
        print("\nDaemon: not running")

    # Domain summary (latest scores per domain)
    if history_path.exists():
        all_lines = [l for l in history_path.read_text().strip().split("\n") if l.strip()]
        latest_by_domain: dict[str, dict] = {}
        for line in all_lines:
            try:
                d = json.loads(line)
                domain_name = d.get("domain", "?")
                latest_by_domain[domain_name] = d
            except json.JSONDecodeError:
                pass
        if latest_by_domain:
            print("\nDomain states:")
            for name in sorted(latest_by_domain):
                d = latest_by_domain[name]
                status = "EIGENFORM" if d.get("eigenform_reached") else ("CONVERGED" if d.get("converged") else "INCOMPLETE")
                note = f" ({d.get('note', '')})" if d.get("note") else ""
                print(f"  {name:10s}: {status:10s} fitness={d.get('best_fitness', 0):.3f}{note}")

    # Scoring reports
    scoring_report = state_dir / "stigmergy" / "mycelium_scoring_report.json"
    skill_health = state_dir / "stigmergy" / "mycelium_skill_health.json"
    if scoring_report.exists():
        try:
            d = json.loads(scoring_report.read_text())
            print(f"\nModule scoring: {d.get('scored_count', '?')} modules, mean {d.get('mean_stars', 0):.2f} stars")
        except Exception:
            pass
    if skill_health.exists():
        try:
            d = json.loads(skill_health.read_text())
            print(f"Skill health:   {d.get('healthy', '?')}/{d.get('total_skills', '?')} healthy, mean {d.get('mean_stars', 0):.1f} stars")
        except Exception:
            pass

    # Signal bus
    try:
        from dharma_swarm.signal_bus import SignalBus
        bus = SignalBus.get()
        cascade_signals = bus.drain(["CASCADE_COMPLETE"])
        if cascade_signals:
            print(f"\nSignal bus: {len(cascade_signals)} cascade completion(s) pending")
        else:
            print("\nSignal bus: clear")
    except Exception:
        print("\nSignal bus: not available")


def cmd_health_check() -> None:
    """Monitor-based system health check (v0.2.0)."""
    async def _check():
        swarm = await _get_swarm()
        report = await swarm.health_check()
        status = report.get("overall_status", "unknown")
        print(f"Overall: {status}")
        print(f"  Total traces: {report.get('total_traces', 0)}")
        print(f"  Traces last hour: {report.get('traces_last_hour', 0)}")
        print(f"  Failure rate: {report.get('failure_rate', 0):.1%}")
        mean_f = report.get("mean_fitness")
        if mean_f is not None:
            print(f"  Mean fitness: {mean_f:.3f}")
        anomalies = report.get("anomalies", [])
        if anomalies:
            print(f"\nAnomalies ({len(anomalies)}):")
            for a in anomalies:
                print(f"  [{a.get('severity', '?')}] {a.get('description', '')}")
        await swarm.shutdown()

    _run(_check())


def cmd_doctor(
    *,
    doctor_cmd: str = "run",
    as_json: bool = False,
    strict: bool = False,
    quick: bool = False,
    timeout: float = 1.5,
    schedule: str = "every 6h",
    interval_sec: float = 1800.0,
    max_runs: int | None = None,
) -> int:
    """Deep readiness diagnostics and recurring assurance control."""
    from dharma_swarm.doctor import (
        create_doctor_job,
        doctor_exit_code,
        load_latest_doctor_report,
        render_doctor_report,
        run_doctor,
        write_doctor_artifacts,
    )

    if doctor_cmd == "schedule":
        job = create_doctor_job(
            schedule=schedule,
            quick=quick,
            strict=strict,
            timeout_seconds=timeout,
        )
        print(f"Doctor job created: {job['id']}")
        print(f"  Name: {job['name']}")
        print(f"  Schedule: {job.get('schedule_display', schedule)}")
        print(f"  Handler: {job.get('handler', 'doctor_assurance')}")
        print("  Next step: ensure `dgc cron daemon` or the launchd cron service is running.")
        return 0

    if doctor_cmd == "latest":
        report = load_latest_doctor_report()
        if report is None:
            print("No cached Doctor report found at ~/.dharma/doctor/latest_report.json")
            return 1
        if as_json:
            print(json.dumps(report, indent=2))
        else:
            print(render_doctor_report(report))
        return doctor_exit_code(report, strict=strict)

    if doctor_cmd == "watch":
        runs = 0
        while True:
            report = run_doctor(timeout_seconds=timeout, quick=quick)
            write_doctor_artifacts(report)
            if runs:
                print()
            print(render_doctor_report(report) if not as_json else json.dumps(report, indent=2))
            runs += 1
            if max_runs is not None and runs >= max_runs:
                return doctor_exit_code(report, strict=strict)
            time.sleep(max(1.0, interval_sec))

    report = run_doctor(timeout_seconds=timeout, quick=quick)
    write_doctor_artifacts(report)
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(render_doctor_report(report))
    return doctor_exit_code(report, strict=strict)


def cmd_pulse() -> None:
    """Run one heartbeat pulse."""
    from dharma_swarm.dgc.commands.runtime import cmd_pulse as _cmd_pulse

    _cmd_pulse()


def cmd_organism_pulse(task: str | None = None, dry_run: bool = False) -> None:
    """Run one canonical organism pulse (9 stages)."""
    import asyncio

    async def _run():
        from dharma_swarm.organism_pulse import run_pulse

        result = await run_pulse(
            task=None if dry_run else task,
            persist=True,
        )
        print(f"Pulse {result.pulse_id}")
        print(f"  Duration: {result.duration_ms:.0f}ms")
        print(f"  Health:   {result.overall_health}")
        print(f"  Gate:     {result.gate_decision}")
        print(f"  Agents:   {result.agent_count}")
        if result.invariants:
            inv = result.invariants
            print(f"  Invariants:")
            print(f"    Criticality:  {inv.criticality:.4f} ({inv.criticality_status})")
            print(f"    Closure:      {inv.closure_ratio:.4f} ({inv.closure_status})")
            print(f"    Info Retain:   {inv.info_retention:.6f} ({inv.info_retention_status})")
            print(f"    Diversity:    {inv.diversity_equilibrium:.4f} ({inv.diversity_status})")
            print(f"    Overall:      {inv.overall}")
        if result.transcendence_metrics:
            tm = result.transcendence_metrics
            print(f"  Transcendence:")
            print(f"    Margin:    {tm.transcendence_margin:.4f}")
            print(f"    Diversity: {tm.behavioral_div:.4f}")
            print(f"    Families:  {tm.n_model_families}")
        if result.prediction:
            print(f"  Self-Prediction:")
            print(f"    Predicted: {result.prediction.predicted_duration_ms:.0f}ms")
            if result.prediction.duration_error is not None:
                print(f"    Error:     {result.prediction.duration_error:.0f}ms")
            if result.prediction.surprise:
                print(f"    SURPRISE detected!")
        print(f"  Stages: {result.stage_timings}")

    asyncio.run(_run())


def cmd_invariants() -> None:
    """Show the 4 computable system invariants."""
    from dharma_swarm.invariants import snapshot
    import numpy as np

    # Try to get real data from catalytic graph
    try:
        from dharma_swarm.catalytic_graph import CatalyticGraph
        graph = CatalyticGraph()
        # Load from seed if available
        try:
            from dharma_swarm.catalytic_graph import seed_ecosystem
            seed_ecosystem(graph)
        except ImportError:
            pass
        mat, nodes = graph.adjacency_matrix()
        total_nodes = graph.node_count
        ac_sets = graph.detect_autocatalytic_sets()
        ac_count = sum(len(s) for s in ac_sets)
    except Exception:
        mat = np.zeros((0, 0))
        total_nodes = 0
        ac_count = 0

    snap = snapshot(
        adjacency_matrix=mat,
        total_nodes=total_nodes,
        autocatalytic_node_count=ac_count,
    )

    print("=== System Invariants ===")
    print(f"  Criticality (λ_max):   {snap.criticality:.4f}  [{snap.criticality_status}]")
    print(f"  Closure ratio:          {snap.closure_ratio:.4f}  [{snap.closure_status}]")
    print(f"  Info retention:         {snap.info_retention:.6f}  [{snap.info_retention_status}]")
    print(f"  Diversity equilibrium:  {snap.diversity_equilibrium:.4f}  [{snap.diversity_status}]")
    print(f"  Overall:                {snap.overall}")
    print(f"  Timestamp:              {snap.timestamp}")


def cmd_transcendence() -> None:
    """Show transcendence metrics (ensemble vs individual)."""
    try:
        from dharma_swarm.ginko_brier import ensemble_brier_report
        report = ensemble_brier_report()
        print("=== Transcendence Report ===")
        print(f"  Status: {report['status']}")
        if report.get("ensemble_brier") is not None:
            print(f"  Ensemble Brier:       {report['ensemble_brier']}")
            print(f"  Best Individual:      {report.get('best_individual_brier', 'N/A')}")
            print(f"  Mean Individual:      {report.get('mean_individual_brier', 'N/A')}")
            print(f"  Transcendence Margin: {report.get('transcendence_margin', 'N/A')}")
            print(f"  Aggregation Lift:     {report.get('aggregation_lift', 'N/A')}")
            print(f"  Transcended:          {report.get('transcended', 'N/A')}")
        if report.get("individual_briers"):
            print(f"\n  Individual Brier Scores:")
            for src, score in sorted(report["individual_briers"].items()):
                print(f"    {src}: {score}")
    except Exception as e:
        print(f"Transcendence report unavailable: {e}")


def cmd_orchestrate_live(background: bool = False) -> None:
    """Run all DGC systems concurrently (live orchestrator)."""
    from dharma_swarm.dgc.commands.runtime import cmd_orchestrate_live as _cmd_orchestrate_live

    _cmd_orchestrate_live(background=background)


def cmd_up(background: bool = False) -> None:
    """Start the dharma_swarm daemon (pulse heartbeat loop)."""
    from dharma_swarm.dgc.commands.runtime import cmd_up as _cmd_up

    _cmd_up(background=background)


def cmd_down() -> None:
    """Stop the daemon."""
    from dharma_swarm.dgc.commands.runtime import cmd_down as _cmd_down

    _cmd_down()


def cmd_daemon_status() -> None:
    """Show daemon state."""
    from dharma_swarm.dgc.commands.runtime import cmd_daemon_status as _cmd_daemon_status

    _cmd_daemon_status()


def cmd_agni(command: str) -> None:
    """Run command on AGNI VPS."""
    from dharma_swarm.telos_gates import check_with_reflective_reroute

    gate = check_with_reflective_reroute(
        action=f"agni:{command}",
        content=command,
        tool_name="dgc_cli_agni",
        think_phase="before_complete",
        reflection=(
            "Remote command execution on AGNI. Validate blast radius, "
            "rollback path, and least-privilege intent."
        ),
        max_reroutes=1,
        requirement_refs=["agni:remote_exec"],
    )
    if gate.result.decision.value == "block":
        print(f"TELOS BLOCK: {gate.result.reason}")
        sys.exit(2)
    if gate.attempts:
        print(f"[witness] reflective reroute applied ({gate.attempts} attempts)")

    ssh_key = HOME / ".ssh" / "openclaw_do"
    result = subprocess.run(
        ["ssh", "-i", str(ssh_key), "-o", "ConnectTimeout=10",
         "root@157.245.193.15", command],
        capture_output=True, text=True, timeout=30,
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}", file=sys.stderr)


def cmd_migrate() -> None:
    """Migrate old DGC memory to new system."""
    sys.path.insert(0, str(DGC_CORE / "memory"))
    try:
        from strange_loop import migrate_from_old_dgc  # type: ignore[import-untyped]
        migrate_from_old_dgc()
    except ImportError:
        print("Migration module not available.")
    finally:
        sys.path.pop(0)


def cmd_setup() -> None:
    """Install dependencies and configure."""
    setup_script = DGC_CORE / "setup.sh"
    if setup_script.exists():
        os.execvp("bash", ["bash", str(setup_script)])
    else:
        print(f"Setup script not found: {setup_script}")


# ---------------------------------------------------------------------------
# Swarm command (with overnight / yolo / live subcommands)
# ---------------------------------------------------------------------------

def cmd_swarm(extra_args: list[str]) -> None:
    """Run the dharma_swarm orchestrator with subcommands."""
    scripts = DHARMA_SWARM / "scripts"
    start_script = scripts / "start_overnight.sh"
    stop_script = scripts / "stop_overnight.sh"
    codex_start_script = scripts / "start_codex_overnight_tmux.sh"
    codex_status_script = scripts / "status_codex_overnight_tmux.sh"
    codex_stop_script = scripts / "stop_codex_overnight_tmux.sh"
    run_file = DHARMA_STATE / "overnight_run_dir.txt"
    codex_run_file = DHARMA_STATE / "codex_overnight_run_dir.txt"
    pid_files = {
        "overnight": DHARMA_STATE / "overnight.pid",
        "daemon": DHARMA_STATE / "daemon.pid",
        "sentinel": DHARMA_STATE / "sentinel.pid",
    }

    def _overnight(args: list[str]) -> None:
        action = args[0] if args else "status"

        if action == "start":
            hours = "8"
            aggressive = False
            for a in args[1:]:
                if a in ("--aggressive", "--yolo", "--caffeine"):
                    aggressive = True
                    continue
                try:
                    float(a)
                    hours = a
                except ValueError:
                    pass

            env = os.environ.copy()
            if aggressive:
                env.update({
                    "POLL_SECONDS": "120",
                    "MIN_PENDING": "12",
                    "TASKS_PER_LOOP": "5",
                    "QUALITY_EVERY_LOOPS": "10",
                })
                if hours == "8":
                    hours = "10"

            proc = subprocess.run(
                ["bash", str(start_script), hours],
                capture_output=True, text=True, env=env,
            )
            if proc.stdout:
                print(proc.stdout.strip())
            if proc.stderr:
                print(proc.stderr.strip(), file=sys.stderr)
            if proc.returncode != 0:
                sys.exit(proc.returncode)
            return

        if action == "stop":
            proc = subprocess.run(
                ["bash", str(stop_script)], capture_output=True, text=True,
            )
            if proc.stdout:
                print(proc.stdout.strip())
            if proc.stderr:
                print(proc.stderr.strip(), file=sys.stderr)
            if proc.returncode != 0:
                sys.exit(proc.returncode)
            return

        if action in ("status", "state"):
            print("=== Swarm Overnight Status ===")
            if run_file.exists():
                run_dir = Path(run_file.read_text().strip())
                print(f"run_dir: {run_dir}")
                report = run_dir / "report.md"
                if report.exists():
                    print("\n--- report tail ---")
                    print(_tail(report, lines=40))
            else:
                print("run_dir: n/a")

            print("\n--- processes ---")
            for label, pf in pid_files.items():
                if not pf.exists():
                    print(f"{label}: missing pid file")
                    continue
                try:
                    pid = int(pf.read_text().strip())
                except Exception:
                    print(f"{label}: invalid pid file")
                    continue
                alive = _pid_alive(pid)
                print(f"{label}: pid={pid} alive={alive}")
                if alive:
                    ps = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "pid=,etime=,command="],
                        capture_output=True, text=True,
                    )
                    if ps.stdout.strip():
                        print("  " + ps.stdout.strip())
            return

        if action in ("report", "logs"):
            if not run_file.exists():
                print("No overnight run metadata found.")
                return
            run_dir = Path(run_file.read_text().strip())
            report = run_dir / "report.md"
            log = run_dir / "autopilot.log"
            print(f"run_dir: {run_dir}\n")
            if report.exists():
                print("--- report tail ---")
                print(_tail(report, lines=80))
            if log.exists():
                print("\n--- autopilot log tail ---")
                print(_tail(log, lines=80))
            return

        print(
            "Usage:\n"
            "  dgc swarm overnight start [HOURS] [--aggressive]\n"
            "  dgc swarm overnight stop\n"
            "  dgc swarm overnight status\n"
            "  dgc swarm overnight report\n"
        )

    def _codex_night(args: list[str]) -> None:
        action = args[0] if args else "status"

        if action in ("start", "yolo"):
            parser = argparse.ArgumentParser(add_help=False)
            parser.add_argument("hours", nargs="?", default="10" if action == "yolo" else "8")
            parser.add_argument("--yolo", action="store_true")
            parser.add_argument("--model", default="")
            parser.add_argument("--mission-file", default="")
            parser.add_argument("--max-cycles", type=int, default=0)
            parser.add_argument("--poll-seconds", type=int, default=0)
            parser.add_argument("--cycle-timeout", type=int, default=0)
            parser.add_argument("--state-dir", default="")
            parser.add_argument("--label", default="")
            parsed = parser.parse_args(args[1:])

            env = os.environ.copy()
            if action == "yolo" or parsed.yolo:
                env["DGC_CODEX_NIGHT_YOLO"] = "1"
            if parsed.model:
                env["DGC_CODEX_NIGHT_MODEL"] = parsed.model
            if parsed.mission_file:
                env["DGC_CODEX_NIGHT_MISSION_FILE"] = parsed.mission_file
            if parsed.max_cycles > 0:
                env["MAX_CYCLES"] = str(parsed.max_cycles)
            if parsed.poll_seconds > 0:
                env["POLL_SECONDS"] = str(parsed.poll_seconds)
            if parsed.cycle_timeout > 0:
                env["CYCLE_TIMEOUT"] = str(parsed.cycle_timeout)
            if parsed.state_dir:
                env["DGC_CODEX_NIGHT_STATE_DIR"] = parsed.state_dir
            if parsed.label:
                env["DGC_CODEX_NIGHT_LABEL"] = parsed.label

            proc = subprocess.run(
                ["bash", str(codex_start_script), parsed.hours],
                capture_output=True,
                text=True,
                env=env,
            )
            if proc.stdout:
                print(proc.stdout.strip())
            if proc.stderr:
                print(proc.stderr.strip(), file=sys.stderr)
            if proc.returncode != 0:
                sys.exit(proc.returncode)
            return

        if action == "stop":
            proc = subprocess.run(
                ["bash", str(codex_stop_script)],
                capture_output=True,
                text=True,
            )
            if proc.stdout:
                print(proc.stdout.strip())
            if proc.stderr:
                print(proc.stderr.strip(), file=sys.stderr)
            if proc.returncode != 0:
                sys.exit(proc.returncode)
            return

        if action in ("status", "state"):
            proc = subprocess.run(
                ["bash", str(codex_status_script)],
                capture_output=True,
                text=True,
            )
            if proc.stdout:
                print(proc.stdout.strip())
            if proc.stderr:
                print(proc.stderr.strip(), file=sys.stderr)
            if proc.returncode != 0:
                sys.exit(proc.returncode)
            return

        if action in ("report", "logs"):
            if not codex_run_file.exists():
                print("No Codex overnight run metadata found.")
                return
            run_dir = Path(codex_run_file.read_text().strip())
            report = run_dir / "report.md"
            latest_output = run_dir / "latest_last_message.txt"
            manifest = run_dir / "run_manifest.json"
            handoff = run_dir / "morning_handoff.md"
            print(f"run_dir: {run_dir}\n")
            if manifest.exists():
                print("--- run manifest ---")
                print(_tail(manifest, lines=80))
            if report.exists():
                print("\n--- report tail ---")
                print(_tail(report, lines=80))
            if latest_output.exists():
                print("\n--- latest last message ---")
                print(_tail(latest_output, lines=80))
            if handoff.exists():
                print("\n--- morning handoff ---")
                print(_tail(handoff, lines=80))
            return

        print(
            "Usage:\n"
            "  dgc swarm codex-night start [HOURS] [--yolo] [--mission-file PATH] [--model MODEL]\n"
            "  dgc swarm codex-night yolo [HOURS]\n"
            "  dgc swarm codex-night stop\n"
            "  dgc swarm codex-night status\n"
            "  dgc swarm codex-night report\n"
        )

    # --- Dispatch subcommands ---

    if extra_args and extra_args[0] == "yolo":
        _codex_night(["yolo"])
        return

    if extra_args and extra_args[0] in ("codex-night", "codex-overnight"):
        _codex_night(extra_args[1:])
        return

    if extra_args and extra_args[0] in ("overnight", "autopilot"):
        _overnight(extra_args[1:])
        return

    if "--status" in extra_args or (extra_args and extra_args[0] in ("status", "state")):
        state_file = DHARMA_STATE / "orchestrator_state.json"
        if state_file.exists():
            state = json.loads(state_file.read_text())
            print("=== DHARMA SWARM Orchestrator State ===")
            for k, v in state.items():
                print(f"  {k}: {v}")
        else:
            print("No orchestrator state yet. Run: dgc swarm")
        return

    if "live" in extra_args:
        live_script = DHARMA_SWARM / "swarm_live.sh"
        num = "3"
        for a in extra_args:
            if a.isdigit():
                num = a
        os.execvp("bash", ["bash", str(live_script), num])
        return

    # Default: run orchestrator with optional plan name
    from dharma_swarm.orchestrate import run as orchestrate_run

    plan_name = None
    for a in extra_args:
        if a in ("build", "research", "maintenance", "deploy"):
            plan_name = a
    orchestrate_run(plan_name)


def cmd_stress(
    profile: str,
    state_dir: str,
    provider_mode: str,
    agents: int,
    tasks: int,
    evolutions: int,
    evolution_concurrency: int,
    cli_rounds: int,
    cli_concurrency: int,
    orchestration_timeout_sec: int,
    external_research: bool,
    external_timeout_sec: int,
) -> None:
    """Run the max-capacity stress harness."""
    harness = DHARMA_SWARM / "scripts" / "dgc_max_stress.py"
    if not harness.exists():
        print(f"Stress harness not found: {harness}")
        raise SystemExit(2)

    cmd = [
        sys.executable,
        str(harness),
        "--profile",
        profile,
        "--state-dir",
        state_dir,
        "--provider-mode",
        provider_mode,
        "--agents",
        str(agents),
        "--tasks",
        str(tasks),
        "--evolutions",
        str(evolutions),
        "--evolution-concurrency",
        str(evolution_concurrency),
        "--cli-rounds",
        str(cli_rounds),
        "--cli-concurrency",
        str(cli_concurrency),
        "--orchestration-timeout-sec",
        str(orchestration_timeout_sec),
        "--external-timeout-sec",
        str(external_timeout_sec),
    ]
    if external_research:
        cmd.append("--external-research")

    print("Running DGC max stress harness...")
    proc = subprocess.run(cmd, cwd=str(DHARMA_SWARM))
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)


def cmd_full_power_probe(
    route_task: str,
    context_search_query: str,
    compose_task: str,
    autonomy_action: str,
    skip_sprint_probe: bool,
    skip_stress: bool,
    skip_pytest: bool,
) -> None:
    """Run the operator-facing full-power probe and emit artifact paths."""
    from dharma_swarm.full_power_probe import run_full_power_probe

    payload = run_full_power_probe(
        python_executable=sys.executable,
        route_task=route_task,
        context_search_query=context_search_query,
        compose_task=compose_task,
        autonomy_action=autonomy_action,
        include_sprint_probe=not skip_sprint_probe,
        run_stress=not skip_stress,
        run_pytest=not skip_pytest,
    )
    print(f"Report: {payload['report_markdown_path']}")
    print(f"JSON:   {payload['report_json_path']}")


# ---------------------------------------------------------------------------
# Commands from dharma_swarm Typer CLI
# ---------------------------------------------------------------------------

def cmd_spawn(name: str, role: str, model: str) -> None:
    """Spawn a new agent."""
    async def _spawn():
        from dharma_swarm.models import AgentRole

        swarm = await _get_swarm()
        try:
            agent_role = AgentRole(role)
        except ValueError:
            print(f"Invalid role: {role}. Choose from: {[r.value for r in AgentRole]}")
            await swarm.shutdown()
            sys.exit(1)
        state = await swarm.spawn_agent(name=name, role=agent_role, model=model)
        print(f"Spawned agent: {state.name} ({state.role.value}) -- ID: {state.id}")
        await swarm.shutdown()

    _run(_spawn())


def cmd_task_create(title: str, description: str, priority: str) -> None:
    """Create a new task (thin path — no full swarm boot)."""
    async def _create():
        from dharma_swarm.models import TaskPriority

        try:
            p = TaskPriority(priority)
        except ValueError:
            print(f"Invalid priority: {priority}")
            sys.exit(1)
        tb = await _get_task_board(state_dir=str(DHARMA_STATE))
        task = await tb.create(title=title, description=description, priority=p)
        print(f"Created task: {task.title} -- ID: {task.id}")

    _run(_create())


def cmd_task_list(status_filter: str | None) -> None:
    """List tasks (thin path — no full swarm boot)."""
    async def _list():
        from dharma_swarm.models import TaskStatus

        tb = await _get_task_board(state_dir=str(DHARMA_STATE))
        s = TaskStatus(status_filter) if status_filter else None
        tasks = await tb.list_tasks(status=s)
        if not tasks:
            print("No tasks.")
        else:
            print(f"{'ID':>8}  {'STATUS':<10}  {'PRI':<8}  {'ASSIGNED':<10}  TITLE")
            print("-" * 70)
            for t in tasks:
                print(f"{t.id[:8]}  {t.status.value:<10}  {t.priority.value:<8}  {(t.assigned_to or '-'):<10}  {t.title}")

    _run(_list())


def cmd_evolve_propose(component: str, description: str, change_type: str, diff: str) -> None:
    """Propose an evolution and run it through the pipeline."""
    async def _propose():
        swarm = await _get_swarm()
        result = await swarm.evolve(
            component=component,
            change_type=change_type,
            description=description,
            diff=diff,
        )
        if result["status"] == "rejected":
            print(f"REJECTED: {result['reason']}")
        else:
            print(f"ARCHIVED: {result['entry_id']} (fitness: {result['weighted_fitness']:.3f})")
        await swarm.shutdown()

    _run(_propose())


def cmd_evolve_trend(component: str | None) -> None:
    """Show fitness trend over time."""
    async def _trend():
        from dharma_swarm.archive import EvolutionArchive

        archive = EvolutionArchive()
        await archive.load()
        trend = archive.fitness_over_time(component=component)
        if not trend:
            print("No fitness data yet.")
        else:
            print("Fitness Trend:")
            for ts, fitness in trend:
                print(f"  {ts[:19]}  {fitness:.3f}")

    _run(_trend())


def cmd_dharma_status() -> None:
    """Show kernel integrity, principle count, and corpus claim counts by status."""
    async def _status() -> None:
        from dharma_swarm.dharma_kernel import KernelGuard
        from dharma_swarm.dharma_corpus import DharmaCorpus, ClaimStatus
        from dharma_swarm.stigmergy import StigmergyStore
        from collections import Counter

        print("=== Dharma Kernel ===")
        guard = KernelGuard(kernel_path=DHARMA_STATE / "kernel.json")
        try:
            kernel = await guard.load()
            integrity = kernel.verify_integrity()
            print(f"  Integrity:  {'OK' if integrity else 'TAMPERED'}")
            print(f"  Principles: {len(kernel.principles)}")
            print(f"  Signature:  {kernel.signature[:16]}...")
            critical = [p for p in kernel.principles.values() if p.severity == "critical"]
            print(f"  Critical:   {len(critical)}  High: {len(kernel.principles) - len(critical)}")
        except FileNotFoundError:
            print("  Kernel not initialized (run swarm init to create default)")
        except ValueError as exc:
            print(f"  Kernel INVALID: {exc}")

        print("\n=== Dharma Corpus ===")
        corpus = DharmaCorpus(path=DHARMA_STATE / "corpus.jsonl")
        await corpus.load()
        all_claims = await corpus.list_claims()
        if not all_claims:
            print("  No claims in corpus.")
        else:
            counts: Counter[str] = Counter()
            for cl in all_claims:
                counts[cl.status.value] += 1
            print(f"  Total claims: {len(all_claims)}")
            for status_val in ClaimStatus:
                c = counts.get(status_val.value, 0)
                if c > 0:
                    print(f"    {status_val.value:<14} {c}")

        print("\n=== Stigmergy ===")
        store = StigmergyStore(base_path=DHARMA_STATE / "stigmergy")
        density = store.density()
        print(f"  Mark density: {density}")
        if density > 0:
            hot = await store.hot_paths(window_hours=48, min_marks=2)
            print(f"  Hot paths (48h): {len(hot)}")

    _run(_status())


def cmd_dharma_corpus(status_filter: str | None = None, category_filter: str | None = None) -> None:
    """List corpus claims with optional status/category filters."""
    async def _corpus() -> None:
        from dharma_swarm.dharma_corpus import DharmaCorpus, ClaimStatus, ClaimCategory

        corpus = DharmaCorpus(path=DHARMA_STATE / "corpus.jsonl")
        await corpus.load()
        s = ClaimStatus(status_filter) if status_filter else None
        c = ClaimCategory(category_filter) if category_filter else None
        claims = await corpus.list_claims(status=s, category=c)
        if not claims:
            print("No claims found.")
        else:
            print(f"{'ID':<16}  {'STATUS':<14}  {'CAT':<18}  {'CONF':>4}  STATEMENT")
            print("-" * 80)
            for cl in claims:
                print(
                    f"{cl.id:<16}  {cl.status.value:<14}  {cl.category.value:<18}  "
                    f"{cl.confidence:.1f}   {cl.statement[:40]}"
                )
            print(f"\n{len(claims)} claim(s) shown.")
    _run(_corpus())


def cmd_dharma_review(claim_id: str) -> None:
    """Show full claim details for review."""
    async def _review() -> None:
        from dharma_swarm.dharma_corpus import DharmaCorpus

        corpus = DharmaCorpus(path=DHARMA_STATE / "corpus.jsonl")
        await corpus.load()
        claim = await corpus.get(claim_id)
        if claim is None:
            print(f"Claim not found: {claim_id}")
            return

        print(f"=== Claim {claim.id} ===")
        print(f"  Status:     {claim.status.value}")
        print(f"  Category:   {claim.category.value}")
        print(f"  Confidence: {claim.confidence:.2f}")
        print(f"  Enforcement:{claim.enforcement}")
        print(f"  Created by: {claim.created_by}")
        print(f"  Created at: {claim.created_at}")
        if claim.parent_id:
            print(f"  Parent ID:  {claim.parent_id}")
        if claim.tags:
            print(f"  Tags:       {', '.join(claim.tags)}")
        if claim.parent_axiom:
            print(f"  Axioms:     {', '.join(claim.parent_axiom)}")

        print(f"\n  Statement:\n    {claim.statement}")

        if claim.evidence_links:
            print(f"\n  Evidence ({len(claim.evidence_links)}):")
            for ev in claim.evidence_links:
                print(f"    [{ev.type}] {ev.url_or_ref}")
                print(f"      {ev.description}")

        if claim.counterarguments:
            print(f"\n  Counterarguments ({len(claim.counterarguments)}):")
            for ca in claim.counterarguments:
                print(f"    - {ca}")

        if claim.review_history:
            print(f"\n  Review History ({len(claim.review_history)}):")
            for rr in claim.review_history:
                print(f"    [{rr.timestamp[:19]}] {rr.reviewer}: {rr.action}")
                print(f"      {rr.comment}")

        # Show lineage if this claim has a parent
        lineage = await corpus.get_lineage(claim_id)
        if len(lineage) > 1:
            print(f"\n  Lineage ({len(lineage)} claims):")
            for lc in lineage:
                marker = " <-- current" if lc.id == claim_id else ""
                print(f"    {lc.id} ({lc.status.value}){marker}")

    _run(_review())


def cmd_evolve_apply(component: str, description: str) -> None:
    """Run evolution with sandbox."""
    async def _apply():
        swarm = await _get_swarm()
        if swarm._engine is None:
            print("Engine not initialized")
            await swarm.shutdown()
            return
        from dharma_swarm.evolution import Proposal
        proposal = await swarm._engine.propose(
            component=component, change_type="mutation", description=description,
        )
        await swarm._engine.gate_check(proposal)
        if proposal.status.value == "rejected":
            print(f"REJECTED: {proposal.gate_reason}")
            await swarm.shutdown()
            return
        proposal_out, sr = await swarm._engine.apply_in_sandbox(proposal, timeout=30.0)
        test_results = swarm._engine._parse_sandbox_result(sr)
        await swarm._engine.evaluate(proposal_out, test_results=test_results)
        entry_id = await swarm._engine.archive_result(proposal_out)
        fitness = proposal_out.actual_fitness
        print(f"APPLIED: {entry_id} (fitness: {fitness.weighted():.3f}, tests: {test_results.get('pass_rate', 0):.0%})")
        await swarm.shutdown()
    _run(_apply())


def cmd_evolve_promote(entry_id: str) -> None:
    """Promote a canary deployment."""
    async def _promote():
        swarm = await _get_swarm()
        if swarm._canary is None:
            print("Canary not initialized")
            await swarm.shutdown()
            return
        ok = await swarm._canary.promote(entry_id)
        print(f"Promoted: {entry_id}" if ok else f"Entry not found: {entry_id}")
        await swarm.shutdown()
    _run(_promote())


def cmd_evolve_rollback(entry_id: str, reason: str = "Manual rollback") -> None:
    """Rollback a deployment."""
    async def _rollback():
        swarm = await _get_swarm()
        if swarm._canary is None:
            print("Canary not initialized")
            await swarm.shutdown()
            return
        ok = await swarm._canary.rollback(entry_id, reason=reason)
        print(f"Rolled back: {entry_id} ({reason})" if ok else f"Entry not found: {entry_id}")
        await swarm.shutdown()
    _run(_rollback())


def cmd_evolve_auto(
    files: list[str] | None, model: str, context: str,
    single_model: bool = False,
    shadow: bool = False,
    token_budget: int = 0,
) -> None:
    """LLM-powered autonomous evolution cycle."""
    async def _auto():
        from pathlib import Path
        from dharma_swarm.models import ProviderType

        swarm = await _get_swarm()
        if swarm._engine is None:
            print("Engine not initialized")
            await swarm.shutdown()
            return

        # Default: core modules worth evolving
        if files:
            source_files = [Path(f) for f in files]
        else:
            src = Path.home() / "dharma_swarm" / "dharma_swarm"
            source_files = [
                src / "evolution.py",
                src / "selector.py",
                src / "archive.py",
                src / "monitor.py",
                src / "telos_gates.py",
                src / "context.py",
            ]

        # Fallback provider (OpenRouter)
        provider = swarm._router.get_provider(ProviderType.OPENROUTER)

        # Token budget
        if token_budget > 0:
            swarm._engine._max_cycle_tokens = token_budget
            print(f"Token budget: {token_budget:,}")

        # Multi-model mode (default) vs single-model
        use_router = not single_model
        if use_router:
            from dharma_swarm.evolution_roster import roster_summary
            print("Multi-model evolution enabled")
            print(roster_summary())
            print(f"\nEvolving {len(source_files)} files{' [SHADOW]' if shadow else ''}...")
        else:
            print(f"Auto-evolving {len(source_files)} files with {model}{' [SHADOW]' if shadow else ''}...")
        for sf in source_files:
            print(f"  {sf.name}")
        print()

        result = await swarm._engine.auto_evolve(
            provider=provider,
            source_files=source_files,
            model=model,
            context=context,
            router=swarm._router if use_router else None,
            shadow=shadow,
        )

        print(f"\n=== Auto-Evolution Results ===")
        print(f"Proposals generated: {result.proposals_submitted}")
        print(f"Passed gates:        {result.proposals_gated}")
        print(f"Tested:              {result.proposals_tested}")
        print(f"Archived:            {result.proposals_archived}")
        print(f"Best fitness:        {result.best_fitness:.3f}")
        print(f"Duration:            {result.duration_seconds:.1f}s")
        if result.reflection:
            print(f"Reflection:          {result.reflection[:200]}")
        if result.lessons_learned:
            print("Lessons:")
            for lesson in result.lessons_learned:
                print(f"  - {lesson}")
        await swarm.shutdown()

    _run(_auto())


def cmd_evolve_daemon(
    interval: float, threshold: float, model: str, cycles: int | None,
    single_model: bool = False,
    shadow: bool = False,
    token_budget: int = 0,
) -> None:
    """Run continuous autonomous evolution daemon."""
    async def _daemon():
        swarm = await _get_swarm()
        if swarm._engine is None:
            print("Engine not initialized")
            await swarm.shutdown()
            return

        from dharma_swarm.models import ProviderType

        provider = swarm._router.get_provider(ProviderType.OPENROUTER)
        use_router = not single_model

        # Token budget
        if token_budget > 0:
            swarm._engine._max_cycle_tokens = token_budget

        print(f"Darwin daemon starting{' [SHADOW]' if shadow else ''}")
        if use_router:
            from dharma_swarm.evolution_roster import roster_summary
            print(f"  Mode:      MULTI-MODEL (roster)")
            print(roster_summary())
        else:
            print(f"  Model:     {model}")
        print(f"  Interval:  {interval:.0f}s ({interval/60:.0f}min)")
        print(f"  Threshold: {threshold}")
        print(f"  Cycles:    {'infinite' if cycles is None else cycles}")
        if token_budget > 0:
            print(f"  Token cap: {token_budget:,}")
        print(f"  Ctrl+C to stop\n")

        try:
            await swarm._engine.daemon_loop(
                think_provider=provider,
                model=model,
                interval=interval,
                fitness_threshold=threshold,
                max_cycles=cycles,
                router=swarm._router if use_router else None,
            )
        except KeyboardInterrupt:
            pass
        finally:
            await swarm.shutdown()
            print("\nDaemon stopped.")

    _run(_daemon())


def cmd_stigmergy(file_path: str | None = None) -> None:
    """Show recent stigmergic marks, hot paths, and high salience marks."""
    async def _stig() -> None:
        from dharma_swarm.stigmergy import StigmergyStore

        store = StigmergyStore(base_path=DHARMA_STATE / "stigmergy")
        density = store.density()
        print(f"=== Stigmergy ({density} marks) ===\n")

        if file_path:
            marks = await store.read_marks(file_path=file_path, limit=15)
            if not marks:
                print(f"No marks for {file_path}")
            else:
                print(f"Marks for {file_path}:")
                for m in marks:
                    ts = m.timestamp.isoformat()[:19]
                    print(f"  [{ts}] {m.agent} ({m.action}): {m.observation} [sal={m.salience:.1f}]")
                    if m.connections:
                        print(f"    connections: {', '.join(m.connections)}")
        else:
            # Recent marks
            recent = await store.read_marks(limit=10)
            if recent:
                print("Recent marks:")
                for m in recent:
                    ts = m.timestamp.isoformat()[:19]
                    print(f"  [{ts}] {m.agent} -> {m.file_path}")
                    print(f"    {m.action}: {m.observation} [sal={m.salience:.1f}]")

            # Hot paths
            hot = await store.hot_paths(window_hours=48, min_marks=2)
            if hot:
                print("\nHot paths (last 48h):")
                for path, count in hot:
                    print(f"  {path}: {count} marks")

            # High salience
            high = await store.high_salience(threshold=0.7, limit=5)
            if high:
                print("\nHigh salience marks (>= 0.7):")
                for m in high:
                    ts = m.timestamp.isoformat()[:19]
                    print(f"  [{ts}] {m.agent}: {m.observation} [sal={m.salience:.2f}]")

            if not recent and not hot and not high:
                print("No stigmergic marks yet. The lattice is empty.")

    _run(_stig())


def cmd_hum() -> None:
    """Show recent subconscious associations and strongest resonances."""
    async def _hum() -> None:
        from dharma_swarm.stigmergy import StigmergyStore
        from dharma_swarm.subconscious import SubconsciousStream

        store = StigmergyStore(base_path=DHARMA_STATE / "stigmergy")
        stream = SubconsciousStream(stigmergy=store)

        dreams = await stream.get_recent_dreams(limit=10)
        if not dreams:
            print("No dreams yet. The HUM is silent.")
            return

        print("=== Subconscious HUM ===\n")
        print("Recent associations:")
        for d in dreams:
            ts = d.timestamp.isoformat()[:19]
            print(f"  [{ts}] {d.source_a}")
            print(f"       <-> {d.source_b}")
            print(f"    {d.resonance_type} (strength={d.strength:.2f}): {d.description[:80]}")
            print()

        strong = await stream.strongest_resonances(threshold=0.3)
        if strong:
            print(f"Strongest resonances (>= 0.3): {len(strong)}")
            for s in strong[:5]:
                print(f"  {s.strength:.2f}  {s.resonance_type}: {s.description[:60]}")

    _run(_hum())


def cmd_rag_health(service: str = "rag", check_dependencies: bool = True) -> None:
    """Check NVIDIA RAG health."""

    async def _health():
        from dharma_swarm.integrations import NvidiaRagClient

        client = NvidiaRagClient()
        payload = await client.health(
            service=service,
            check_dependencies=check_dependencies,
        )
        print(json.dumps(payload, indent=2))

    _run(_health())


def cmd_rag_search(query: str, top_k: int = 5, collection: str | None = None) -> None:
    """Query NVIDIA RAG search endpoint."""

    async def _search():
        from dharma_swarm.integrations import NvidiaRagClient

        client = NvidiaRagClient()
        payload = await client.search(
            query=query,
            top_k=top_k,
            collection_name=collection,
        )
        print(json.dumps(payload, indent=2))

    _run(_search())


def cmd_rag_chat(prompt: str, model: str | None = None) -> None:
    """Run grounded chat via NVIDIA RAG."""

    async def _chat():
        from dharma_swarm.integrations import NvidiaRagClient

        client = NvidiaRagClient()
        payload = await client.chat(prompt=prompt, model=model)
        print(json.dumps(payload, indent=2))

    _run(_chat())


def cmd_flywheel_jobs() -> None:
    """List Data Flywheel jobs."""

    async def _jobs():
        from dharma_swarm.integrations import DataFlywheelClient

        client = DataFlywheelClient()
        payload = await client.list_jobs()
        print(json.dumps(payload, indent=2))

    _run(_jobs())


async def _flywheel_export_payload(
    *,
    run_id: str,
    workload_id: str,
    client_id: str,
    trace_id: str | None = None,
    db_path: str | None = None,
    event_log_dir: str | None = None,
    export_root: str | None = None,
    data_split_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from dharma_swarm.flywheel_exporter import FlywheelExporter
    from dharma_swarm.memory_lattice import MemoryLattice
    from dharma_swarm.runtime_state import RuntimeStateStore

    runtime_state = RuntimeStateStore(Path(db_path) if db_path else None)
    memory_lattice = MemoryLattice(
        db_path=runtime_state.db_path,
        event_log_dir=Path(event_log_dir) if event_log_dir else None,
    )
    exporter = FlywheelExporter(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        export_root=Path(export_root) if export_root else None,
    )
    try:
        result = await exporter.export_run(
            run_id=run_id,
            workload_id=workload_id,
            client_id=client_id,
            trace_id=trace_id,
            created_by="dgc_cli",
            data_split_config=data_split_config,
        )
    finally:
        await memory_lattice.close()
    return {
        "export_id": result.record.export_id,
        "artifact_id": result.artifact.artifact_id,
        "run_id": result.record.run_id,
        "task_id": result.record.task_id,
        "session_id": result.record.session_id,
        "trace_id": result.record.trace_id,
        "workload_id": result.record.workload_id,
        "client_id": result.record.client_id,
        "status": result.record.status,
        "metrics": dict(result.record.metrics),
        "job_request": dict(result.record.job_request),
        "export_path": str(result.export_path),
        "manifest_path": str(result.manifest_path),
        "receipt_event_id": str(result.receipt.get("event_id", "")),
    }


def cmd_flywheel_export(
    *,
    run_id: str,
    workload_id: str,
    client_id: str,
    trace_id: str | None = None,
    db_path: str | None = None,
    event_log_dir: str | None = None,
    export_root: str | None = None,
) -> None:
    """Materialize a local canonical flywheel export artifact."""

    payload = _run(
        _flywheel_export_payload(
            run_id=run_id,
            workload_id=workload_id,
            client_id=client_id,
            trace_id=trace_id,
            db_path=db_path,
            event_log_dir=event_log_dir,
            export_root=export_root,
        )
    )
    print(json.dumps(payload, indent=2))


async def _flywheel_record_payload(
    *,
    job_id: str,
    workload_id: str | None = None,
    client_id: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    trace_id: str | None = None,
    db_path: str | None = None,
    event_log_dir: str | None = None,
    workspace_root: str | None = None,
    provenance_root: str | None = None,
) -> dict[str, Any]:
    from dharma_swarm.evaluation_registry import EvaluationRegistry
    from dharma_swarm.integrations import DataFlywheelClient
    from dharma_swarm.memory_lattice import MemoryLattice
    from dharma_swarm.runtime_state import RuntimeStateStore

    client = DataFlywheelClient()
    job = await client.get_job(job_id)
    runtime_state = RuntimeStateStore(Path(db_path) if db_path else None)
    memory_lattice = MemoryLattice(
        db_path=runtime_state.db_path,
        event_log_dir=Path(event_log_dir) if event_log_dir else None,
    )
    registry = EvaluationRegistry(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        workspace_root=Path(workspace_root) if workspace_root else None,
        provenance_root=Path(provenance_root) if provenance_root else None,
    )
    try:
        result = await registry.record_flywheel_job(
            job,
            job_id=job_id,
            workload_id=workload_id,
            client_id=client_id,
            run_id=run_id or "",
            session_id=session_id or "",
            task_id=task_id or "",
            trace_id=trace_id,
            created_by="dgc_cli",
        )
    finally:
        await memory_lattice.close()
    return {
        "job": job,
        "registry": {
            "artifact_id": result.artifact.artifact_id,
            "manifest_path": str(result.manifest_path),
            "summary": dict(result.summary),
            "fact_ids": [fact.fact_id for fact in result.facts],
            "receipt_event_id": str(result.receipt.get("event_id", "")),
        },
    }


def cmd_flywheel_record(
    *,
    job_id: str,
    workload_id: str | None = None,
    client_id: str | None = None,
    run_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    trace_id: str | None = None,
    db_path: str | None = None,
    event_log_dir: str | None = None,
    workspace_root: str | None = None,
    provenance_root: str | None = None,
) -> None:
    """Record a remote Flywheel job result into canonical DGC truth."""

    payload = _run(
        _flywheel_record_payload(
            job_id=job_id,
            workload_id=workload_id,
            client_id=client_id,
            run_id=run_id,
            session_id=session_id,
            task_id=task_id,
            trace_id=trace_id,
            db_path=db_path,
            event_log_dir=event_log_dir,
            workspace_root=workspace_root,
            provenance_root=provenance_root,
        )
    )
    print(json.dumps(payload, indent=2))


def cmd_flywheel_start(
    workload_id: str,
    client_id: str,
    eval_size: int,
    val_ratio: float,
    min_total_records: int,
    limit: int,
    run_id: str | None = None,
    trace_id: str | None = None,
    db_path: str | None = None,
    event_log_dir: str | None = None,
    export_root: str | None = None,
) -> None:
    """Start a Data Flywheel job."""

    async def _start():
        from dharma_swarm.integrations import DataFlywheelClient

        local_export: dict[str, Any] | None = None
        data_split_config = {
            "eval_size": eval_size,
            "val_ratio": val_ratio,
            "min_total_records": min_total_records,
            "limit": limit,
        }
        if run_id:
            local_export = await _flywheel_export_payload(
                run_id=run_id,
                workload_id=workload_id,
                client_id=client_id,
                trace_id=trace_id,
                db_path=db_path,
                event_log_dir=event_log_dir,
                export_root=export_root,
                data_split_config=data_split_config,
            )
        client = DataFlywheelClient()
        payload = await client.create_job(
            workload_id=workload_id,
            client_id=client_id,
            data_split_config=data_split_config,
        )
        if local_export is not None:
            payload = {
                "local_export": local_export,
                "job": payload,
            }
        print(json.dumps(payload, indent=2))

    _run(_start())


def cmd_flywheel_get(job_id: str) -> None:
    """Get Data Flywheel job details."""

    async def _get():
        from dharma_swarm.integrations import DataFlywheelClient

        client = DataFlywheelClient()
        payload = await client.get_job(job_id)
        print(json.dumps(payload, indent=2))

    _run(_get())


def cmd_flywheel_cancel(job_id: str) -> None:
    """Cancel Data Flywheel job."""

    async def _cancel():
        from dharma_swarm.integrations import DataFlywheelClient

        client = DataFlywheelClient()
        payload = await client.cancel_job(job_id)
        print(json.dumps(payload, indent=2))

    _run(_cancel())


def cmd_flywheel_delete(job_id: str) -> None:
    """Delete Data Flywheel job."""

    async def _delete():
        from dharma_swarm.integrations import DataFlywheelClient

        client = DataFlywheelClient()
        payload = await client.delete_job(job_id)
        print(json.dumps(payload, indent=2))

    _run(_delete())


def cmd_flywheel_watch(job_id: str, poll_sec: float, timeout_sec: float) -> None:
    """Wait until a Data Flywheel job reaches terminal state."""

    async def _watch():
        from dharma_swarm.integrations import DataFlywheelClient

        client = DataFlywheelClient()
        payload = await client.wait_for_terminal(
            job_id,
            poll_sec=poll_sec,
            timeout_sec=timeout_sec,
        )
        print(json.dumps(payload, indent=2))

    _run(_watch())


def cmd_reciprocity_health() -> None:
    """Check Planetary Reciprocity Commons service health."""

    async def _health():
        from dharma_swarm.integrations import ReciprocityCommonsClient

        client = ReciprocityCommonsClient()
        payload = await client.health()
        print(json.dumps(payload, indent=2))

    _run(_health())


def cmd_reciprocity_summary() -> None:
    """Fetch the current reciprocity ledger summary."""

    async def _summary():
        from dharma_swarm.integrations import ReciprocityCommonsClient

        client = ReciprocityCommonsClient()
        payload = await client.ledger_summary()
        print(json.dumps(payload, indent=2))

    _run(_summary())


async def _reciprocity_publish_payload(
    *,
    record_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    from dharma_swarm.integrations import ReciprocityCommonsClient

    client = ReciprocityCommonsClient()
    publishers = {
        "activity": client.publish_activity,
        "obligation": client.publish_obligation,
        "project": client.publish_project,
        "outcome": client.publish_outcome,
    }
    try:
        publish = publishers[record_type]
    except KeyError as exc:
        raise ValueError(f"unsupported reciprocity record type: {record_type}") from exc

    response = await publish(payload)
    return {
        "record_type": record_type,
        "record": payload,
        "response": response,
    }


def cmd_reciprocity_publish(
    *,
    record_type: str,
    json_payload: str | None = None,
    file_path: str | None = None,
) -> None:
    """Publish a reciprocity activity, obligation, project, or outcome."""

    payload = _load_json_object(
        json_payload=json_payload,
        file_path=file_path,
        label="reciprocity publish payload",
    )
    result = _run(
        _reciprocity_publish_payload(
            record_type=record_type,
            payload=payload,
        )
    )
    print(json.dumps(result, indent=2))


async def _reciprocity_record_payload(
    *,
    run_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    trace_id: str | None = None,
    summary_type: str = "ledger_summary",
    json_payload: str | None = None,
    file_path: str | None = None,
    db_path: str | None = None,
    event_log_dir: str | None = None,
    workspace_root: str | None = None,
    provenance_root: str | None = None,
) -> dict[str, Any]:
    from dharma_swarm.evaluation_registry import EvaluationRegistry
    from dharma_swarm.integrations import ReciprocityCommonsClient
    from dharma_swarm.memory_lattice import MemoryLattice
    from dharma_swarm.runtime_state import RuntimeStateStore

    normalized_run_id = _normalize_optional_text(run_id)
    normalized_session_id = _normalize_optional_text(session_id)
    normalized_task_id = _normalize_optional_text(task_id)
    normalized_trace_id = _normalize_optional_text(trace_id) or None
    normalized_summary_type = _normalize_optional_text(
        summary_type,
        default="ledger_summary",
    )
    if not normalized_run_id and not normalized_session_id:
        raise ValueError("session_id or run_id is required to record evaluation outputs canonically")

    provided_payload = (
        _load_json_object(
            json_payload=json_payload,
            file_path=file_path,
            label="reciprocity summary payload",
        )
        if json_payload is not None or file_path is not None
        else None
    )
    if provided_payload is not None:
        summary_payload = dict(provided_payload)
    else:
        client = ReciprocityCommonsClient()
        summary_payload = dict(await client.ledger_summary())
    summary_payload.setdefault("service", "reciprocity_commons")
    summary_payload.setdefault("source", "reciprocity_commons")
    summary_payload.setdefault("summary_type", normalized_summary_type)

    runtime_state = RuntimeStateStore(Path(db_path) if db_path else None)
    memory_lattice = MemoryLattice(
        db_path=runtime_state.db_path,
        event_log_dir=Path(event_log_dir) if event_log_dir else None,
    )
    registry = EvaluationRegistry(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        workspace_root=Path(workspace_root) if workspace_root else None,
        provenance_root=Path(provenance_root) if provenance_root else None,
    )
    try:
        result = await registry.record_reciprocity_summary(
            summary_payload,
            run_id=normalized_run_id,
            session_id=normalized_session_id,
            task_id=normalized_task_id,
            trace_id=normalized_trace_id,
            created_by="dgc_cli",
        )
    finally:
        await memory_lattice.close()

    return {
        "summary": summary_payload,
        "registry": {
            "artifact_id": result.artifact.artifact_id,
            "manifest_path": str(result.manifest_path),
            "summary": dict(result.summary),
            "fact_ids": [fact.fact_id for fact in result.facts],
            "receipt_event_id": str(result.receipt.get("event_id", "")),
        },
    }


def cmd_reciprocity_record(
    *,
    run_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    trace_id: str | None = None,
    summary_type: str = "ledger_summary",
    json_payload: str | None = None,
    file_path: str | None = None,
    db_path: str | None = None,
    event_log_dir: str | None = None,
    workspace_root: str | None = None,
    provenance_root: str | None = None,
) -> None:
    """Record the current reciprocity ledger summary into canonical DGC truth."""

    payload = _run(
        _reciprocity_record_payload(
            run_id=run_id,
            session_id=session_id,
            task_id=task_id,
            trace_id=trace_id,
            summary_type=summary_type,
            json_payload=json_payload,
            file_path=file_path,
            db_path=db_path,
            event_log_dir=event_log_dir,
            workspace_root=workspace_root,
            provenance_root=provenance_root,
        )
    )
    print(json.dumps(payload, indent=2))


def cmd_ouroboros_connections(
    *,
    package_dir: str | None = None,
    threshold: float = 0.08,
    disagreement_threshold: float = 0.1,
    min_text_length: int = 50,
    limit: int = 15,
    as_json: bool = False,
) -> None:
    """Profile module docstrings and report behavioral affinities/disagreements."""
    from dharma_swarm.ouroboros import profile_python_modules

    if limit < 0:
        raise ValueError("limit must be >= 0")
    if threshold < 0:
        raise ValueError("threshold must be >= 0")
    if disagreement_threshold < 0:
        raise ValueError("disagreement_threshold must be >= 0")

    target_dir = Path(package_dir) if package_dir else DHARMA_SWARM / "dharma_swarm"
    finder, profiles = profile_python_modules(
        target_dir,
        min_text_length=min_text_length,
    )
    connections = finder.find_connections(threshold=threshold)
    disagreements = finder.find_h1_disagreements(threshold=disagreement_threshold)
    payload = {
        "package_dir": str(target_dir),
        "profiles": profiles,
        "connections": connections,
        "disagreements": disagreements,
        "summary": {
            "modules_profiled": len(profiles),
            "connections": len(connections),
            "disagreements": len(disagreements),
            "threshold": threshold,
            "disagreement_threshold": disagreement_threshold,
            "min_text_length": min_text_length,
        },
    }
    if as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Profiling {len(profiles)} modules from {target_dir}...\n")
    for row in profiles[:limit]:
        print(
            f"  {row['module']:<30} "
            f"entropy={row['entropy']:.3f}  "
            f"self_ref={row['self_reference_density']:.4f}  "
            f"swabhaav={row['swabhaav_ratio']:.3f}  "
            f"recog={row['recognition_type']}"
        )
    if len(profiles) > limit:
        print(f"  ... {len(profiles) - limit} more module profiles")

    print("\n" + "=" * 80)
    print("H0: STRUCTURAL CONNECTIONS (similar behavioral profiles)")
    print("=" * 80)
    if connections:
        for conn in connections[:limit]:
            print(
                f"  {conn['module_a']:<25} <-> {conn['module_b']:<25} "
                f"d={conn['distance']:.4f}  type={conn['connection_type']}"
            )
        if len(connections) > limit:
            print(f"  ... {len(connections) - limit} more H0 connections")
    else:
        print(f"  No close connections found (threshold={threshold:.3f})")

    print("\n" + "=" * 80)
    print("H1: PRODUCTIVE DISAGREEMENTS (divergent profiles)")
    print("=" * 80)
    if disagreements:
        for dis in disagreements[:limit]:
            print(
                f"  {dis['module_a']:<25} =/= {dis['module_b']:<25} "
                f"d={dis['distance']:.4f}  "
                f"type={dis['disagreement_type']}  "
                f"({dis['recognition_a']} vs {dis['recognition_b']})"
            )
        if len(disagreements) > limit:
            print(f"  ... {len(disagreements) - limit} more H1 disagreements")
    else:
        print(f"  No H1 disagreements found (threshold={disagreement_threshold:.3f})")

    print("\n" + "=" * 80)
    print("SYNTHESIS")
    print("=" * 80)
    print(f"\n  Modules profiled: {len(profiles)}")
    print(f"  H0 connections:   {len(connections)}")
    print(f"  H1 disagreements: {len(disagreements)}")


async def _ouroboros_record_payload(
    *,
    run_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    trace_id: str | None = None,
    log_path: str | None = None,
    cycle_id: str | None = None,
    json_payload: str | None = None,
    file_path: str | None = None,
    db_path: str | None = None,
    event_log_dir: str | None = None,
    workspace_root: str | None = None,
    provenance_root: str | None = None,
) -> dict[str, Any]:
    from dharma_swarm.evaluation_registry import EvaluationRegistry
    from dharma_swarm.memory_lattice import MemoryLattice
    from dharma_swarm.runtime_state import RuntimeStateStore

    normalized_run_id = _normalize_optional_text(run_id)
    normalized_session_id = _normalize_optional_text(session_id)
    normalized_task_id = _normalize_optional_text(task_id)
    normalized_trace_id = _normalize_optional_text(trace_id) or None
    normalized_cycle_id = _normalize_optional_text(cycle_id) or None
    if not normalized_run_id and not normalized_session_id:
        raise ValueError("session_id or run_id is required to record evaluation outputs canonically")

    inline_payload_requested = json_payload is not None or file_path is not None
    if inline_payload_requested and (log_path is not None or normalized_cycle_id is not None):
        raise ValueError(
            "ouroboros record accepts either --json/--file or --log-path/--cycle-id, not both"
        )

    resolved_log_path: Path | None
    if inline_payload_requested:
        observation_payload = _load_json_object(
            json_payload=json_payload,
            file_path=file_path,
            label="ouroboros observation payload",
        )
        resolved_log_path = None
    else:
        resolved_log_path = Path(log_path) if log_path else _default_ouroboros_log_path()
        observation_payload = _load_ouroboros_observation(
            log_path=resolved_log_path,
            cycle_id=normalized_cycle_id,
        )

    runtime_state = RuntimeStateStore(Path(db_path) if db_path else None)
    memory_lattice = MemoryLattice(
        db_path=runtime_state.db_path,
        event_log_dir=Path(event_log_dir) if event_log_dir else None,
    )
    registry = EvaluationRegistry(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        workspace_root=Path(workspace_root) if workspace_root else None,
        provenance_root=Path(provenance_root) if provenance_root else None,
    )
    try:
        result = await registry.record_ouroboros_observation(
            observation_payload,
            run_id=normalized_run_id,
            session_id=normalized_session_id,
            task_id=normalized_task_id,
            trace_id=normalized_trace_id,
            created_by="dgc_cli",
        )
    finally:
        await memory_lattice.close()

    return {
        "observation": observation_payload,
        "log_path": str(resolved_log_path) if resolved_log_path is not None else None,
        "registry": {
            "artifact_id": result.artifact.artifact_id,
            "manifest_path": str(result.manifest_path),
            "summary": dict(result.summary),
            "fact_ids": [fact.fact_id for fact in result.facts],
            "receipt_event_id": str(result.receipt.get("event_id", "")),
        },
    }


def cmd_ouroboros_record(
    *,
    run_id: str | None = None,
    session_id: str | None = None,
    task_id: str | None = None,
    trace_id: str | None = None,
    log_path: str | None = None,
    cycle_id: str | None = None,
    json_payload: str | None = None,
    file_path: str | None = None,
    db_path: str | None = None,
    event_log_dir: str | None = None,
    workspace_root: str | None = None,
    provenance_root: str | None = None,
) -> None:
    """Record an ouroboros observation into canonical runtime truth."""

    payload = _run(
        _ouroboros_record_payload(
            run_id=run_id,
            session_id=session_id,
            task_id=task_id,
            trace_id=trace_id,
            log_path=log_path,
            cycle_id=cycle_id,
            json_payload=json_payload,
            file_path=file_path,
            db_path=db_path,
            event_log_dir=event_log_dir,
            workspace_root=workspace_root,
            provenance_root=provenance_root,
        )
    )
    print(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# v0.4.0: Oz-inspired commands
# ---------------------------------------------------------------------------


def cmd_skills() -> None:
    """List all discovered skills."""
    from dharma_swarm.skills import SkillRegistry
    registry = SkillRegistry()
    skills = registry.discover()
    if not skills:
        print("No skills discovered. Add .skill.md files to dharma_swarm/skills/")
        return
    print(f"Discovered {len(skills)} skills:\n")
    for skill in sorted(skills.values(), key=lambda s: s.priority):
        tags = ", ".join(skill.tags[:5]) if skill.tags else "none"
        print(f"  {skill.name:<16} model={skill.model:<12} "
              f"autonomy={skill.autonomy:<10} tags=[{tags}]")
        if skill.description:
            print(f"  {'':16} {skill.description[:80]}")


def cmd_route(description: str) -> None:
    """Route a task to the best skill."""
    from dharma_swarm.skills import SkillRegistry
    from dharma_swarm.intent_router import IntentRouter
    registry = SkillRegistry()
    registry.discover()
    router = IntentRouter(registry=registry)
    skill_name, intent = router.route(description)
    print(f"Task: {description}")
    print(f"  Skill:      {skill_name}")
    print(f"  Confidence: {intent.confidence:.0%}")
    print(f"  Complexity: {intent.complexity}")
    print(f"  Risk:       {intent.risk_level}")
    print(f"  Agents:     {intent.recommended_agents}")
    if intent.parallel:
        print(f"  Parallel:   yes")


def cmd_orchestrate(description: str) -> None:
    """Decompose a task and show the orchestration plan."""
    from dharma_swarm.skills import SkillRegistry
    from dharma_swarm.intent_router import IntentRouter
    registry = SkillRegistry()
    registry.discover()
    router = IntentRouter(registry=registry)
    result = router.decompose(description)
    print(f"Task: {result.original}")
    print(f"Complexity: {result.estimated_complexity}")
    print(f"Total agents: {result.total_agents}")
    print(f"Parallel: {'yes' if result.has_parallel_work else 'no'}")
    print(f"\nSub-tasks ({len(result.sub_tasks)}):")
    for i, st in enumerate(result.sub_tasks, 1):
        print(f"  {i}. [{st.primary_skill or 'general'}] {st.task}")
        print(f"     complexity={st.complexity} risk={st.risk_level}")


def cmd_autonomy(action: str) -> None:
    """Check autonomy decision for an action."""
    from dharma_swarm.adaptive_autonomy import AdaptiveAutonomy
    auto = AdaptiveAutonomy(base_level="balanced")
    decision = auto.should_auto_approve(action)
    status = "AUTO-APPROVE" if decision.auto_approve else "REQUIRES APPROVAL"
    print(f"Action: {action}")
    print(f"  Risk:     {decision.risk.value}")
    print(f"  Decision: {status}")
    if decision.reason:
        print(f"  Reason:   {decision.reason}")
    if decision.escalate_to:
        print(f"  Escalate: {decision.escalate_to}")


def cmd_context_search(query: str, budget: int = 10_000) -> None:
    """Search for task-relevant context."""
    from dharma_swarm.context_search import ContextSearchEngine
    engine = ContextSearchEngine()
    engine.build_index()
    results = engine.search(query, max_results=10)
    if not results:
        print("No relevant context found.")
        return
    print(f"Context search: '{query}'\n")
    for r in results:
        print(f"  [{r.relevance:.1f}] {r.path}")
        if r.snippet:
            print(f"         {r.snippet[:80]}...")
        print()


def cmd_compose(description: str) -> None:
    """Compose a task into a DAG execution plan."""
    async def _compose():
        swarm = await _get_swarm()
        result = await swarm.compose_task(description)
        await swarm.shutdown()
        if "error" in result:
            print(f"Error: {result['error']}")
            return
        print(f"Task: {result['task']}")
        print(f"Status: {result['status']}")
        print(f"\nSteps ({len(result['steps'])}):")
        for s in result["steps"]:
            deps = f" (depends on: {', '.join(s['deps'])})" if s["deps"] else ""
            print(f"  {s['id']}: [{s['skill']}] {s['task']}{deps}")
        print(f"\nExecution waves: {len(result['waves'])}")
        for i, wave in enumerate(result["waves"]):
            print(f"  Wave {i+1}: {', '.join(wave)}")
        if result["ready"]:
            print(f"\nReady now: {', '.join(result['ready'])}")
    _run(_compose())


def cmd_execute_compose(description: str) -> None:
    """Compose and execute a task DAG end-to-end."""
    async def _exec():
        swarm = await _get_swarm()
        result = await swarm.execute_composition(description)
        await swarm.shutdown()
        if "error" in result:
            print(f"Error: {result['error']}")
            return
        print(f"Task: {result['task']}")
        print(f"Status: {result['status']}")
        print(f"Completed: {result['steps_completed']}  "
              f"Failed: {result['steps_failed']}  "
              f"Skipped: {result['steps_skipped']}  "
              f"Duration: {result['duration']}s")
        for s in result.get("steps", []):
            icon = "+" if s["success"] else "x"
            line = f"  [{icon}] {s['id']}: [{s['skill']}]"
            if s["error"]:
                line += f" ERROR: {s['error']}"
            elif s["output"]:
                line += f" {s['output'][:100]}"
            print(line)
    _run(_exec())


def cmd_handoff(from_agent: str, to_agent: str, context: str, content: str) -> None:
    """Create a structured handoff between agents."""
    async def _handoff():
        swarm = await _get_swarm()
        result = await swarm.create_handoff(
            from_agent=from_agent, to_agent=to_agent,
            task_context=context,
            artifacts=[{"type": "context", "content": content, "summary": content[:60]}],
        )
        await swarm.shutdown()
        print(f"Handoff created: {result.get('id', 'unknown')}")
        print(f"  {result.get('summary', '')}")
    _run(_handoff())


def cmd_agent_memory(agent_name: str) -> None:
    """Show agent memory stats."""
    async def _mem():
        swarm = await _get_swarm()
        stats = await swarm.get_agent_memory(agent_name)
        await swarm.shutdown()
        print(f"Agent Memory: {agent_name}")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    _run(_mem())


def cmd_model(action: str) -> None:
    """Handle model management commands."""
    from dharma_swarm.model_manager import (
        show_current_model,
        list_models,
        format_model_table,
        switch_model,
        MODELS,
    )

    if action == "status" or action is None:
        print(show_current_model())
    elif action == "list":
        models = list_models()
        print(format_model_table(models))
    elif action in MODELS or action.startswith("claude-") or action.startswith("gpt-"):
        success, message = switch_model(action)
        print(message)
        if not success:
            sys.exit(1)
    else:
        print(f"Unknown action or model: {action}")
        print("Usage: dgc model [status|list|opus|sonnet|haiku|gpt-4o]")
        sys.exit(1)


def cmd_run(interval: float) -> None:
    """Run the orchestration loop."""
    async def _run_loop():
        swarm = await _get_swarm()
        print("DHARMA SWARM running. Ctrl+C to stop.")
        try:
            await swarm.run(interval=interval)
        except KeyboardInterrupt:
            pass
        finally:
            await swarm.shutdown()
            print("Swarm stopped.")

    _run(_run_loop())


def cmd_tui() -> None:
    """Launch the interactive TUI dashboard."""
    from dharma_swarm.dgc.commands.ux import cmd_tui as _cmd_tui

    _cmd_tui()


def cmd_ui(surface: str = "list") -> None:
    """Print the canonical operator-surface map."""
    from dharma_swarm.dgc.commands.ux import cmd_ui as _cmd_ui

    _cmd_ui(surface)


def _build_chat_context_snapshot() -> str:
    """Backward-compatible chat context snapshot helper."""
    from dharma_swarm.dgc.commands.ux import _build_chat_context_snapshot as _snapshot

    return _snapshot(state_dir=DHARMA_STATE, home=HOME)


def cmd_chat(
    continue_last: bool = False,
    offline: bool = False,
    model: str | None = None,
    effort: str | None = None,
    include_context: bool = True,
) -> None:
    """Launch native Claude Code interactive UI (full experience)."""
    from dharma_swarm.dgc.commands.ux import cmd_chat as _cmd_chat

    _cmd_chat(
        continue_last=continue_last,
        offline=offline,
        model=model,
        effort=effort,
        include_context=include_context,
    )


# ---------------------------------------------------------------------------
# Sprint generator
# ---------------------------------------------------------------------------

def cmd_sprint(
    output: str | None = None,
    local: bool = False,
    test_summary: str = "",
    prev_todo: str = "",
    llm_timeout_sec: float = DEFAULT_SPRINT_LLM_TIMEOUT_SEC,
) -> None:
    """Generate today's adaptive 8-hour sprint prompt from live system state."""
    from datetime import date as _date
    from dharma_swarm.master_prompt_engineer import (
        gather_system_state,
        generate_evolved_prompt,
        generate_local_prompt,
        _days_to_colm,
        _SHARED_DIR,
    )

    today = _date.today().strftime("%Y%m%d")
    out_path = Path(output) if output else _SHARED_DIR / f"SPRINT_8H_{today}.md"
    colm_days, colm_paper = _days_to_colm()

    print(f"[sprint] Generating sprint for {today}")
    print(f"  COLM: {colm_days}d (abstract) / {colm_paper}d (paper)")

    state = gather_system_state()
    live = state.get("live_signals", {})
    morning_ok = "no morning" not in live.get("morning_brief", "no morning")
    dream_ok = "no dream" not in live.get("dream_seeds", "no dream")
    handoff_ok = "no handoff" not in live.get("sprint_handoff", "no handoff")
    print(f"  signals: morning={'yes' if morning_ok else 'none'} "
          f"dreams={'yes' if dream_ok else 'none'} "
          f"handoff={'yes' if handoff_ok else 'none'}")

    if local:
        prompt_text = generate_local_prompt(
            test_summary=test_summary,
            prev_todo=prev_todo,
            colm_days=colm_days,
        )
        mode = "local"
    else:
        try:
            import asyncio as _asyncio
            prompt_text = _asyncio.run(generate_evolved_prompt(
                system_state=state,
                test_summary=test_summary,
                prev_todo=prev_todo,
                colm_days=colm_days,
                llm_timeout_sec=llm_timeout_sec,
            ))
            mode = "LLM"
        except Exception as exc:
            print(f"  LLM unavailable ({exc}), using local mode")
            prompt_text = generate_local_prompt(
                test_summary=test_summary,
                prev_todo=prev_todo,
                colm_days=colm_days,
            )
            mode = "local (fallback)"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        f"# 8-HOUR SPRINT — {today}\n"
        f"**Generated**: {_date.today().isoformat()} | **Mode**: {mode}\n"
        f"**COLM**: {colm_days} days (abstract) / {colm_paper} days (paper)\n\n"
        + prompt_text
    )
    print(f"[sprint] Written to: {out_path}")
    print(f"  length: {len(prompt_text):,} chars | mode: {mode}")


# ---------------------------------------------------------------------------
# Ledger viewer
# ---------------------------------------------------------------------------

def cmd_ledger(
    ledger_cmd: str | None = None,
    n: int = 20,
    session: str | None = None,
    kind: str = "all",
    query: str | None = None,
    db_path: str | None = None,
    sync_ledgers: bool = True,
    limit_sessions: int | None = None,
) -> None:
    """Inspect orchestrator session ledgers."""
    ledger_base = Path.home() / ".dharma" / "ledgers"

    if ledger_cmd == "sessions" or ledger_cmd is None:
        if not ledger_base.exists():
            print("No ledgers directory found at ~/.dharma/ledgers/")
            return
        sessions = sorted(
            (p for p in ledger_base.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )[:10]
        if not sessions:
            print("No sessions found.")
            return
        print(f"{'Session ID':<22} {'Task':>6} {'Progress':>10} {'Age':>10}")
        print("-" * 52)
        import time as _time
        now = _time.time()
        for sess in sessions:
            tf = sess / "task_ledger.jsonl"
            pf = sess / "progress_ledger.jsonl"
            tc = sum(1 for _ in open(tf)) if tf.exists() else 0
            pc = sum(1 for _ in open(pf)) if pf.exists() else 0
            age_h = (now - sess.stat().st_mtime) / 3600
            age_s = f"{age_h:.1f}h" if age_h < 48 else f"{age_h/24:.0f}d"
            print(f"{sess.name:<22} {tc:>6} {pc:>10} {age_s:>10}")
        if ledger_cmd is None:
            print("\nUsage: dgc ledger tail | dgc ledger sessions")
        return

    if ledger_cmd == "tail":
        if not ledger_base.exists():
            print("No ledgers directory found.")
            return
        sessions = sorted(
            (p for p in ledger_base.iterdir() if p.is_dir()),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not sessions:
            print("No sessions found.")
            return
        target = (ledger_base / session) if session else sessions[0]
        if not target.exists():
            print(f"Session not found: {session}")
            return
        print(f"Session: {target.name}")

        def _tail_file(path: Path, label: str) -> None:
            if not path.exists():
                return
            lines = [l for l in path.read_text().splitlines() if l.strip()][-n:]
            if not lines:
                return
            print(f"\n{label} ({path.name})")
            for line in lines:
                try:
                    ev = json.loads(line)
                    ts = ev.get("ts_utc", "")[:19]
                    event = ev.get("event", "?")
                    tid = ev.get("task_id", "")[:8]
                    extra = ""
                    if "duration_sec" in ev:
                        extra = f" ({ev['duration_sec']:.2f}s)"
                    if "failure_signature" in ev:
                        extra = f" sig={ev['failure_signature'][:50]}"
                    print(f"  {ts}  {event:<28} {tid}{extra}")
                except Exception:
                    print(f"  {line[:120]}")

        if kind in ("task", "all"):
            _tail_file(target / "task_ledger.jsonl", "Task Ledger")
        if kind in ("progress", "all"):
            _tail_file(target / "progress_ledger.jsonl", "Progress Ledger")
        return

    if ledger_cmd == "index":
        from dharma_swarm.runtime_state import RuntimeStateStore

        runtime_state = RuntimeStateStore(Path(db_path) if db_path else None)
        sessions_scanned, events_scanned = runtime_state.index_ledgers_sync(
            ledger_base=ledger_base,
            session_id=session,
            limit_sessions=limit_sessions,
        )
        print(
            f"Indexed {events_scanned} ledger events across "
            f"{sessions_scanned} session(s) into {runtime_state.db_path}"
        )
        return

    if ledger_cmd == "search":
        from dharma_swarm.runtime_state import RuntimeStateStore

        normalized_query = (query or "").strip()
        if not normalized_query:
            print("Search query is required.")
            return
        runtime_state = RuntimeStateStore(Path(db_path) if db_path else None)
        if sync_ledgers:
            runtime_state.index_ledgers_sync(
                ledger_base=ledger_base,
                session_id=session,
                limit_sessions=limit_sessions,
            )
        ledger_kind = None if kind == "all" else kind
        results = runtime_state.search_session_events_sync(
            normalized_query,
            session_id=session,
            ledger_kind=ledger_kind,
            limit=n,
        )
        if not results:
            print(f"No indexed ledger events matched: {normalized_query}")
            return
        print(f"Search: {normalized_query}")
        for item in results:
            ts = item.created_at.isoformat()[:19]
            task = item.task_id[:8] if item.task_id else "-"
            summary = item.summary or item.event_text
            summary = " ".join(summary.split())
            if len(summary) > 96:
                summary = summary[:93] + "..."
            print(
                f"  {ts}  {item.session_id:<22} {item.ledger_kind:<8} "
                f"{item.event_name:<28} {task}  {summary}"
            )
        return

    print(f"Unknown ledger subcommand: {ledger_cmd}")
    print("Usage: dgc ledger tail | dgc ledger sessions | dgc ledger search | dgc ledger index")


# ---------------------------------------------------------------------------
# Semantic Evolution Engine
# ---------------------------------------------------------------------------

_DEFAULT_GRAPH_PATH = DHARMA_STATE / "semantic" / "concept_graph.json"


def _resolve_graph_path(graph_path: str | None) -> Path:
    return Path(graph_path) if graph_path else _DEFAULT_GRAPH_PATH


def cmd_semantic_digest(
    *,
    root: str,
    output: str | None = None,
    include_tests: bool = False,
    max_files: int = 500,
) -> None:
    """Phase 1: Read codebase files and build the ConceptGraph."""
    from dharma_swarm.semantic_digester import SemanticDigester

    root_path = Path(root)
    out_path = Path(output) if output else _DEFAULT_GRAPH_PATH

    # Digest the dharma_swarm package directory
    package_dir = root_path / "dharma_swarm"
    if not package_dir.is_dir():
        package_dir = root_path  # Fall back to root itself

    print(f"[semantic digest] Scanning {package_dir}")
    digester = SemanticDigester()
    graph = digester.digest_directory(
        package_dir,
        include_tests=include_tests,
        max_files=max_files,
    )

    print(f"  nodes: {graph.node_count}  edges: {graph.edge_count}")
    _run(graph.save(out_path))
    print(f"  graph saved to: {out_path}")


def cmd_semantic_ingest(
    ingest_cmd: str | None,
    *,
    name: str | None = None,
    roots: list[str] | None = None,
    tags: list[str] | None = None,
    suffixes: list[str] | None = None,
    kind: str = "local_path",
    recursive: bool = True,
    enabled_only: bool = True,
    source_names: list[str] | None = None,
    max_files: int = 200,
    state_dir: str | None = None,
    query: str = "",
    limit: int = 10,
) -> None:
    """Operate the semantic ingestion spine."""
    from dharma_swarm.semantic_ingestion import (
        IngestionSourceSpec,
        SemanticIngestionSpine,
    )

    spine = SemanticIngestionSpine(state_dir=Path(state_dir) if state_dir else DHARMA_STATE)

    match ingest_cmd:
        case "add-source":
            spec = IngestionSourceSpec(
                name=str(name or "").strip(),
                roots=list(roots or []),
                kind=kind,
                tags=list(tags or []),
                suffixes=list(suffixes or []),
                enabled=True,
                recursive=recursive,
            )
            if not spec.suffixes:
                spec.suffixes = []
            added = spine.add_source(spec)
            print(f"[semantic ingest] added source: {added.name}")
            for root in added.roots:
                print(f"  root: {root}")
            if added.tags:
                print(f"  tags: {', '.join(added.tags)}")
        case "list-sources":
            specs = spine.list_sources(enabled_only=enabled_only)
            if not specs:
                print("[semantic ingest] no sources configured")
                return
            print(f"[semantic ingest] sources: {len(specs)}")
            for spec in specs:
                status = "enabled" if spec.enabled else "disabled"
                print(f"  - {spec.name} [{status}] ({spec.kind})")
                for root in spec.roots:
                    print(f"      {root}")
        case "register-defaults":
            added = spine.register_default_sources()
            if not added:
                print("[semantic ingest] default sources already registered")
                return
            print(f"[semantic ingest] registered default sources: {len(added)}")
            for spec in added:
                print(f"  - {spec.name}")
                for root in spec.roots:
                    print(f"      {root}")
        case "bootstrap":
            report = spine.bootstrap_from_concept_graph()
            print(f"[semantic ingest] bootstrap run_id: {report.run_id}")
            print(f"  files ingested: {report.files_ingested}")
            print(f"  files skipped: {report.files_skipped}")
            print(f"  concept graph: {report.concept_nodes} nodes / {report.concept_edges} edges")
            print(f"  concepts indexed: {report.indexed_concepts}")
            print(f"  graph saved to: {report.graph_path}")
        case "run":
            report = spine.run(source_names=source_names, max_files=max_files)
            print(f"[semantic ingest] run_id: {report.run_id}")
            print(f"  sources: {', '.join(report.source_names)}")
            print(f"  files scanned: {report.files_scanned}")
            print(f"  files ingested: {report.files_ingested}")
            print(f"  files skipped: {report.files_skipped}")
            print(f"  concept graph: {report.concept_nodes} nodes / {report.concept_edges} edges")
            print(f"  concepts indexed: {report.indexed_concepts}")
            print(f"  graph saved to: {report.graph_path}")
            if report.errors:
                print(f"  errors: {len(report.errors)}")
                for err in report.errors[:5]:
                    print(f"    - {err}")
        case "status":
            status = spine.status()
            print("[semantic ingest] status")
            print(f"  sources: {status['sources_enabled']}/{status['sources_total']} enabled")
            print(f"  documents: {status['documents']}")
            print(f"  registry: {status['registry_path']}")
            print(f"  graph: {status['graph_path']}")
            vector_stats = status.get("vector_store", {})
            print(f"  vector docs: {vector_stats.get('total_documents', 0)}")
            last_run = status.get("last_run")
            if last_run:
                print(
                    "  last run: "
                    f"{last_run.get('run_id', '')} [{last_run.get('status', '')}] "
                    f"{last_run.get('completed_at', '') or last_run.get('started_at', '')}",
                )
                stats = last_run.get("stats", {}) if isinstance(last_run, dict) else {}
                sources = stats.get("source_names", [])
                if sources:
                    print(f"  last run sources: {', '.join(str(source) for source in sources)}")
                if any(key in stats for key in ("indexed_concepts", "concept_nodes", "concept_edges")):
                    print(
                        "  last run concepts: "
                        f"{int(stats.get('indexed_concepts', 0))} indexed / "
                        f"{int(stats.get('concept_nodes', 0))} nodes / "
                        f"{int(stats.get('concept_edges', 0))} edges",
                    )
                if any(key in stats for key in ("files_ingested", "files_skipped")):
                    print(
                        "  last run files: "
                        f"{int(stats.get('files_ingested', 0))} ingested / "
                        f"{int(stats.get('files_skipped', 0))} skipped",
                    )
        case "search":
            results = spine.search(query, limit=limit)
            if not results:
                print(f"[semantic ingest] no hits for: {query}")
                return
            print(f"[semantic ingest] hits for: {query}")
            for idx, hit in enumerate(results, start=1):
                print(
                    f"  {idx}. {hit.get('title', hit.get('source_path', 'unknown'))} "
                    f"(score={float(hit.get('score', 0.0)):.3f})",
                )
                print(f"     source: {hit.get('source_name', 'unknown')} :: {hit.get('source_path', '')}")
                summary = str(hit.get("summary", "")).strip()
                if summary:
                    print(f"     summary: {summary[:180]}")
        case _:
            raise ValueError("semantic ingest command is required")


def cmd_semantic_research(*, graph_path: str | None = None) -> None:
    """Phase 2: Annotate the graph with external research connections."""
    from dharma_swarm.semantic_gravity import ConceptGraph
    from dharma_swarm.semantic_researcher import SemanticResearcher

    gp = _resolve_graph_path(graph_path)
    graph = _run(ConceptGraph.load(gp))
    if graph.node_count == 0:
        print("[semantic research] Empty graph — run 'dgc semantic digest' first.")
        return

    researcher = SemanticResearcher()
    annotations = researcher.annotate_graph(graph)
    for ann in annotations:
        graph.add_annotation(ann)
    print(f"[semantic research] {len(annotations)} annotations added")

    coverage = researcher.coverage_report(graph)
    print(f"  coverage: {coverage.get('coverage_pct', 0):.1f}%")

    _run(graph.save(gp))
    print(f"  graph updated: {gp}")


def cmd_semantic_synthesize(
    *, graph_path: str | None = None, max_clusters: int = 10,
) -> None:
    """Phase 3: Generate file cluster specs from concept intersections."""
    from dharma_swarm.semantic_gravity import ConceptGraph
    from dharma_swarm.semantic_synthesizer import SemanticSynthesizer

    gp = _resolve_graph_path(graph_path)
    graph = _run(ConceptGraph.load(gp))
    if graph.node_count == 0:
        print("[semantic synthesize] Empty graph — run digest first.")
        return

    synth = SemanticSynthesizer(max_clusters=max_clusters)
    clusters = synth.synthesize(graph)

    print(f"[semantic synthesize] {len(clusters)} cluster specs generated")
    for c in clusters:
        print(f"  • {c.name}: {len(c.files)} files ({c.intersection_type})")

    gaps = synth.gap_analysis(graph)
    if gaps.get("structures_uncovered"):
        print(f"  uncovered structures: {', '.join(gaps['structures_uncovered'][:5])}")


def cmd_semantic_harden(
    *, graph_path: str | None = None, root: str = str(DHARMA_SWARM),
) -> None:
    """Phase 4: Run 6-angle hardening on synthesized clusters."""
    from dharma_swarm.semantic_gravity import ConceptGraph
    from dharma_swarm.semantic_hardener import SemanticHardener
    from dharma_swarm.semantic_synthesizer import SemanticSynthesizer

    gp = _resolve_graph_path(graph_path)
    graph = _run(ConceptGraph.load(gp))
    if graph.node_count == 0:
        print("[semantic harden] Empty graph — run digest first.")
        return

    synth = SemanticSynthesizer()
    clusters = synth.synthesize(graph)
    if not clusters:
        print("[semantic harden] No clusters to harden.")
        return

    hardener = SemanticHardener(project_root=Path(root))
    reports = hardener.harden_batch(clusters, graph)
    summary = hardener.summary(reports)

    print(f"[semantic harden] {summary['total']} clusters tested")
    print(f"  passed: {summary['passed']}  failed: {summary['failed']}")
    print(f"  avg_score: {summary.get('avg_score', 0):.3f}")
    for angle, stats in summary.get("angle_stats", {}).items():
        print(f"  {angle}: score={stats['avg_score']:.3f} pass_rate={stats['pass_rate']:.0%}")


def cmd_semantic_brief(
    *,
    graph_path: str | None = None,
    root: str = str(DHARMA_SWARM),
    max_briefs: int = 3,
    json_output: str | None = None,
    markdown_output: str | None = None,
    state_dir: str | None = None,
    campaign_path: str | None = None,
) -> None:
    """Compile hardened semantic clusters into campaign-grade briefs."""
    from dharma_swarm.mission_contract import (
        CampaignArtifact,
        build_campaign_state,
        default_campaign_state_path,
        load_active_campaign_state,
        load_active_mission_state,
        save_campaign_state,
    )
    from dharma_swarm.semantic_briefs import build_brief_packet, write_brief_packet
    from dharma_swarm.semantic_gravity import ConceptGraph
    from dharma_swarm.semantic_hardener import SemanticHardener
    from dharma_swarm.semantic_synthesizer import SemanticSynthesizer

    gp = _resolve_graph_path(graph_path)
    graph = _run(ConceptGraph.load(gp))
    if graph.node_count == 0:
        print("[semantic brief] Empty graph — run digest first.")
        return

    synth = SemanticSynthesizer(max_clusters=max(max_briefs * 2, max_briefs))
    clusters = synth.synthesize(graph)
    if not clusters:
        print("[semantic brief] No clusters available — run research/synthesize first.")
        return

    hardener = SemanticHardener(project_root=Path(root))
    reports = hardener.harden_batch(clusters, graph)
    packet = build_brief_packet(
        graph=graph,
        clusters=clusters,
        reports=reports,
        graph_path=str(gp),
        project_root=str(Path(root)),
        max_briefs=max_briefs,
    )

    json_target = Path(json_output) if json_output else gp.with_name("semantic_brief_packet.json")
    markdown_target = (
        Path(markdown_output)
        if markdown_output
        else json_target.with_suffix(".md")
    )
    json_path, markdown_path = write_brief_packet(
        packet,
        json_path=json_target,
        markdown_path=markdown_target,
    )

    state_root = Path(state_dir).expanduser() if state_dir else DHARMA_STATE
    mission_artifact = load_active_mission_state(state_dir=state_root)
    if mission_artifact is not None:
        try:
            previous_campaign_artifact = load_active_campaign_state(
                state_dir=state_root,
                path=campaign_path,
            )
        except ValueError:
            previous_campaign_artifact = None
        campaign_state = build_campaign_state(
            mission_state=mission_artifact.state,
            previous=previous_campaign_artifact.state if previous_campaign_artifact else None,
            semantic_briefs=packet.semantic_briefs,
            execution_briefs=packet.execution_briefs,
            artifacts=[
                CampaignArtifact(
                    artifact_kind="semantic_brief_packet_json",
                    title="semantic brief packet json",
                    path=str(json_path),
                    summary=f"{len(packet.semantic_briefs)} semantic briefs",
                    source="cmd_semantic_brief",
                ),
                CampaignArtifact(
                    artifact_kind="semantic_brief_packet_markdown",
                    title="semantic brief packet markdown",
                    path=str(markdown_path) if markdown_path else "",
                    summary=f"{len(packet.execution_briefs)} execution briefs",
                    source="cmd_semantic_brief",
                ),
            ],
            evidence_paths=[str(gp), str(json_path), str(markdown_path) if markdown_path else ""],
            metrics=dict(packet.metrics),
        )
        target_campaign = (
            Path(campaign_path).expanduser()
            if campaign_path
            else default_campaign_state_path(state_root)
        )
        save_campaign_state(target_campaign, campaign_state)
        print(f"[semantic brief] campaign updated: {target_campaign}")

    print(f"[semantic brief] semantic briefs: {len(packet.semantic_briefs)}")
    print(f"[semantic brief] execution briefs: {len(packet.execution_briefs)}")
    print(f"  json: {json_path}")
    if markdown_path:
        print(f"  markdown: {markdown_path}")


def cmd_semantic_proof(*, root: str = str(DHARMA_SWARM)) -> None:
    """Run live end-to-end proof of the Semantic Evolution Engine."""
    import subprocess

    script = Path(root).parent / "scripts" / "semantic_proof.py"
    if not script.exists():
        script = Path(root) / "scripts" / "semantic_proof.py"
    if not script.exists():
        print(f"[semantic proof] Script not found: {script}")
        raise SystemExit(2)

    print(f"[semantic proof] Running {script}")
    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(Path(root).parent if (Path(root).parent / "scripts").is_dir() else root),
    )
    raise SystemExit(result.returncode)


def cmd_semantic_status(*, graph_path: str | None = None) -> None:
    """Show semantic graph status overview."""
    from dharma_swarm.semantic_gravity import ConceptGraph

    gp = _resolve_graph_path(graph_path)
    if not gp.exists():
        print(f"[semantic status] No graph found at {gp}")
        print("  Run 'dgc semantic digest' to build one.")
        return

    graph = _run(ConceptGraph.load(gp))
    components = graph.connected_components()

    print(f"[semantic status] Graph: {gp}")
    print(f"  nodes: {graph.node_count}")
    print(f"  edges: {graph.edge_count}")
    print(f"  annotations: {graph.annotation_count}")
    print(f"  density: {graph.density():.4f}")
    print(f"  connected components: {len(components)}")

    # Category breakdown
    categories: dict[str, int] = {}
    for node in graph.all_nodes():
        cat = node.category or "uncategorized"
        categories[cat] = categories.get(cat, 0) + 1
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {count}")

    # High salience concepts
    top = graph.high_salience_nodes(threshold=0.7)[:10]
    if top:
        print(f"  top concepts:")
        for n in top:
            print(f"    {n.name} (salience={n.salience:.2f}, {n.category})")


def cmd_provider_smoke(
    *,
    ollama_model: str | None = None,
    nim_model: str | None = None,
    qwen_provider: str | None = None,
    qwen_task: str | None = None,
    telemetry_db: str | None = None,
    as_json: bool = False,
) -> int:
    """Run best-effort smoke tests for local and external provider lanes."""
    from dharma_swarm.provider_smoke import run_provider_smoke

    payload = run_provider_smoke(
        ollama_model=ollama_model,
        nim_model=nim_model,
        qwen_provider=qwen_provider,
        qwen_task=qwen_task,
        telemetry_db_path=telemetry_db,
    )
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    for label, block in payload.items():
        if label.startswith("_"):
            continue
        print(
            f"[{label}] status={block.get('status')} "
            f"model={block.get('model') or block.get('configured_model')}"
        )
        if label == "ollama":
            installed = block.get("installed_models") or []
            if installed:
                print(f"  installed={', '.join(installed[:10])}")
            if block.get("strongest_installed"):
                print(f"  strongest_installed={block['strongest_installed']}")
            if block.get("root_issue"):
                print(f"  root_issue={block['root_issue']}")
        if block.get("strongest_verified"):
            print(f"  strongest_verified={block['strongest_verified']}")
        verified = block.get("verified_models") or []
        if verified:
            summary = ", ".join(
                f"{item.get('model')}:{item.get('status')}" for item in verified[:6]
            )
            print(f"  verified={summary}")
        if label == "qwen_dashboard":
            if block.get("resolved_provider"):
                print(f"  resolved_provider={block['resolved_provider']}")
            if block.get("tool_names"):
                print(f"  tool_names={', '.join(block['tool_names'])}")
            if block.get("required_env_key") and block.get("status") == "missing_config":
                print(f"  required_env_key={block['required_env_key']}")
        if block.get("configured_base_url"):
            print(f"  base_url={block['configured_base_url']}")
        if block.get("response_preview"):
            print(f"  preview={block['response_preview']}")
        if block.get("error"):
            print(f"  error={block['error']}")
    telemetry = payload.get("_telemetry")
    if isinstance(telemetry, dict):
        print(
            f"[telemetry] status={telemetry.get('status')} "
            f"outcomes={telemetry.get('outcome_count', 0)} "
            f"session_id={telemetry.get('session_id')}"
        )
        if telemetry.get("db_path"):
            print(f"  db_path={telemetry['db_path']}")
        for item in (telemetry.get("errors") or [])[:5]:
            print(f"  error={item}")
    return 0


def cmd_provider_matrix(
    *,
    profile: str,
    corpus: str,
    max_targets: int | None,
    max_prompts: int | None,
    timeout_seconds: float,
    concurrency: int,
    budget_units: int | None,
    artifact_dir: str | None,
    include_unavailable: bool,
    write_artifacts: bool,
    as_json: bool = False,
) -> int:
    """Run the live provider/model matrix harness."""
    from dharma_swarm.provider_matrix import run_provider_matrix

    payload = run_provider_matrix(
        profile=profile,
        corpus=corpus,
        max_targets=max_targets,
        max_prompts=max_prompts,
        timeout_seconds=timeout_seconds,
        concurrency=concurrency,
        budget_units=budget_units,
        artifact_dir=artifact_dir,
        include_unavailable=include_unavailable,
        write_artifacts=write_artifacts,
        working_dir=str(DHARMA_SWARM),
    )
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    counts = payload.get("counts", {})
    budget = payload.get("budget", {})
    print(
        f"[provider-matrix] profile={payload.get('profile')} corpus={payload.get('corpus')} "
        f"attempted={counts.get('attempted', 0)} ok={counts.get('ok', 0)} "
        f"schema_valid={counts.get('schema_valid', 0)} "
        f"budget={budget.get('units_consumed')}/{budget.get('budget_units')}"
    )
    for row in payload.get("leaderboard", [])[:10]:
        print(
            f"  {row.get('provider')} / {row.get('model')} "
            f"[{row.get('lane_role')}, {row.get('tier')}] "
            f"score={row.get('avg_score')} ok={row.get('ok_count')}/{row.get('attempts')} "
            f"latency={row.get('avg_elapsed_sec')}s"
        )
    artifacts = payload.get("artifacts", {})
    if artifacts:
        print(
            f"[artifacts] json={artifacts.get('json_path')} "
            f"md={artifacts.get('markdown_path')}"
        )
    return 0


# ---------------------------------------------------------------------------
# Bootstrap command
# ---------------------------------------------------------------------------


def cmd_bootstrap() -> None:
    """Generate and display the bootstrap manifest (NOW.json)."""
    from dharma_swarm.bootstrap import generate_manifest, print_manifest
    manifest = generate_manifest()
    print_manifest(manifest)


# ---------------------------------------------------------------------------
# D3 Field Intelligence commands
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Cron and Gateway commands (v0.6.0)
# ---------------------------------------------------------------------------

def cmd_cron(
    cron_cmd: str | None,
    prompt: str = "",
    schedule: str = "",
    name: str | None = None,
    repeat: int | None = None,
    deliver: str = "local",
    urgent: bool = False,
    job_id: str = "",
    interval_sec: float = 60.0,
    max_loops: int | None = None,
    run_immediately: bool = True,
) -> None:
    """Cron scheduler commands."""
    from dharma_swarm.cron_scheduler import (
        create_job,
        list_jobs,
        remove_job,
        tick,
    )
    from dharma_swarm.cron_daemon import run_cron_daemon
    from dharma_swarm.cron_runner import run_cron_job

    match cron_cmd:
        case "add":
            job = create_job(
                prompt=prompt,
                schedule=schedule,
                name=name,
                repeat=repeat,
                deliver=deliver,
                urgent=urgent,
            )
            print(f"  Created job {job['id']}: {job['name']}")
            print(f"  Schedule: {job['schedule_display']}")
            print(f"  Next run: {job.get('next_run_at', 'N/A')}")
        case "list":
            jobs = list_jobs(include_disabled=True)
            if not jobs:
                print("  No cron jobs.")
                return
            for j in jobs:
                status = j.get("last_status", "-")
                enabled = "✓" if j.get("enabled", True) else "✗"
                completed = j.get("repeat", {}).get("completed", 0)
                times = j.get("repeat", {}).get("times")
                repeat_str = f"{completed}/{times}" if times else f"{completed}/∞"
                print(f"  {enabled} {j['id']}  {j['name'][:40]:<40}  "
                      f"{j.get('schedule_display', '?'):<20}  "
                      f"runs={repeat_str}  last={status}")
        case "remove":
            if remove_job(job_id):
                print(f"  Removed job {job_id}")
            else:
                print(f"  Job {job_id} not found")
        case "tick":
            executed = tick(verbose=True, run_fn=run_cron_job)
            print(f"  Tick complete: {executed} job(s) executed")
        case "daemon":
            executed = run_cron_daemon(
                interval_sec=interval_sec,
                max_loops=max_loops,
                run_immediately=run_immediately,
                tick_verbose=False,
            )
            print(f"  Cron daemon exited: {executed} job(s) executed")
        case _:
            print("Usage: dgc cron {add|list|remove|tick|daemon}")


def cmd_xray(
    repo_path: str,
    output: str | None = None,
    as_json: bool = False,
    exclude: list[str] | None = None,
    packet: bool = False,
    buyer: str = "CTO or founder under shipping pressure",
) -> None:
    """Run a Repo X-Ray analysis."""
    from pathlib import Path
    from dharma_swarm.xray import (
        analyze_repo,
        render_markdown,
        run_xray,
        run_xray_packet,
    )

    path = Path(repo_path).expanduser().resolve()
    if not path.is_dir():
        print(f"  Error: {path} is not a directory")
        raise SystemExit(1)

    exclude_set = set(exclude) if exclude else None
    print(f"  Scanning {path}...")
    if packet:
        outputs = run_xray_packet(
            path,
            output_dir=output,
            buyer=buyer,
            exclude_patterns=exclude_set,
        )
        print(f"  Packet saved to: {outputs['output_dir']}")
        print(f"  Service brief: {outputs['service_brief']}")
        print(f"  Mission brief: {outputs['mission_brief']}")
        print(f"  Report JSON: {outputs['report_json']}")
        return

    report_path = run_xray(path, output_path=output, as_json=as_json, exclude_patterns=exclude_set)

    if not as_json:
        report = analyze_repo(path, exclude_patterns=exclude_set)
        md = render_markdown(report)
        print(md)

    print(f"\n  Report saved to: {report_path}")


def cmd_foreman(
    foreman_cmd: str | None = None,
    path: str = "",
    name: str | None = None,
    test_command: str | None = None,
    exclude: list[str] | None = None,
    level: str = "observe",
    project: str | None = None,
    skip_tests: bool = False,
    schedule: str = "every 4h",
) -> None:
    """Foreman Quality Forge commands."""
    from dharma_swarm.foreman import (
        add_project,
        format_status,
        load_projects,
        run_cycle,
        create_foreman_cron_job,
    )

    match foreman_cmd:
        case "add":
            if not path:
                print("  Error: path is required")
                return
            entry = add_project(
                path=path,
                name=name,
                test_command=test_command,
                exclude=exclude or [],
            )
            print(f"  Registered: {entry.name} ({entry.path})")
        case "run":
            if level not in ("observe", "advise", "build"):
                print(f"  Error: level must be observe/advise/build, got {level}")
                return
            report = run_cycle(
                level=level,
                project_filter=project,
                skip_tests=skip_tests,
            )
            print(f"  Forge cycle complete ({report.duration_seconds}s, {len(report.per_project)} projects)\n")
            for p in report.per_project:
                weakest = p["weakest_dimension"]
                print(f"  {p['name']}: {p['grade']} (avg={p['avg_quality']:.2f})")
                print(f"    weakest: {weakest}={p['dimensions'][weakest]:.2f}")
                print(f"    → {p['task']['task']}")
        case "status":
            print(format_status())
        case "cron":
            job = create_foreman_cron_job(every=schedule, level=level)
            print(f"  Foreman cron job: {job.get('id', '?')}")
            print(f"  Schedule: {job.get('schedule_display', schedule)}")
            print(f"  Level: {level}")
        case _:
            print("Usage: dgc foreman {add|run|status|cron}")
            print("  add <path>          Register a project")
            print("  run [--level L]     Run one forge cycle")
            print("  status              Show quality dashboard")
            print("  cron [--schedule S] Start recurring forge")


def cmd_review(hours: float = 6.0, skip_tests: bool = False) -> None:
    """Manually trigger a review cycle report."""
    from dharma_swarm.review_cycle import generate_review_sync

    print(f"  Generating {hours:.0f}h review cycle report...")
    report = generate_review_sync(
        hours=hours,
        run_tests=not skip_tests,
    )
    print(report)


def cmd_initiatives(
    init_cmd: str | None = None,
    title: str = "",
    description: str = "",
    initiative_id: str = "",
    reason: str = "",
) -> None:
    """Initiative depth ledger commands."""
    from dharma_swarm.iteration_depth import IterationLedger, CompoundingQueue

    ledger = IterationLedger()
    ledger.load()

    match init_cmd:
        case "list":
            inits = ledger.get_all()
            if not inits:
                print("  No initiatives tracked.")
                return
            for i in sorted(inits, key=lambda x: x.updated_at, reverse=True):
                icon = {"seed": "\U0001f331", "growing": "\U0001f33f",
                        "solid": "\U0001faa8", "shipped": "\U0001f680",
                        "abandoned": "\u274c"}.get(i.status.value, "?")
                print(f"  {icon} {i.id}  {i.title[:40]:<40}  "
                      f"iter={i.iteration_count}  quality={i.quality_score:.3f}  "
                      f"status={i.status.value}")
        case "add":
            if not title:
                print("  Error: --title is required")
                return
            init = ledger.create(title=title, description=description)
            print(f"  Created initiative {init.id}: {init.title}")
        case "abandon":
            if not initiative_id or not reason:
                print("  Error: initiative_id and --reason are required")
                return
            if ledger.abandon(initiative_id, reason):
                print(f"  Abandoned {initiative_id}: {reason}")
            else:
                print(f"  Initiative {initiative_id} not found")
        case "promote":
            if not initiative_id:
                print("  Error: initiative_id is required")
                return
            ok, msg = ledger.promote(initiative_id)
            icon = '\u2705' if ok else '\u274c'
            print(f"  {icon} {msg}")
        case "summary":
            summary = ledger.summary()
            print(f"  Total: {summary['total']}  Active: {summary['active_count']}")
            print(f"  Avg iterations: {summary['avg_iterations']}  "
                  f"Avg quality: {summary['avg_quality']:.3f}")
            if summary["shallow"]:
                print(f"  Shallow ({summary['shallow_count']}):")
                for s in summary["shallow"]:
                    print(f"    - {s['title']}: {s['iterations']} iterations")
            if summary["ready_to_promote"]:
                print(f"  Ready to promote:")
                for r in summary["ready_to_promote"]:
                    print(f"    - {r['title']}: quality={r['quality']:.3f}")
        case _:
            print("Usage: dgc initiatives {list|add|abandon|promote|summary}")


def cmd_free_fleet(
    tier: int | None = None,
    as_json: bool = False,
    set_env: bool = False,
) -> None:
    """Show free-fleet model configuration, optionally filtered by tier."""
    import json as _json
    from dharma_swarm.free_fleet import FREE_FLEET, TIER_MODELS, ALL_FREE_MODELS

    if set_env:
        print("export DGC_FREE_FLEET=1")
        return

    if tier is not None:
        if tier not in (1, 2, 3):
            print(f"Error: invalid tier {tier!r}. Must be 1, 2, or 3.")
            raise SystemExit(1)
        models = TIER_MODELS.get(tier, [])
        if as_json:
            print(_json.dumps({"tier": tier, "models": models}, indent=2))
        else:
            print(f"Tier {tier} models:")
            for m in models:
                print(f"  {m}")
        return

    if as_json:
        data = {
            "tiers": {str(k): v for k, v in TIER_MODELS.items()},
            "all_models": ALL_FREE_MODELS,
            "default_tier": FREE_FLEET.default_tier,
        }
        print(_json.dumps(data, indent=2))
    else:
        print("FREE_FLEET — zero-cost OpenRouter models")
        print(f"  Default tier: {FREE_FLEET.default_tier}")
        for tier_num, models in TIER_MODELS.items():
            print(f"\n  Tier {tier_num}:")
            for m in models:
                print(f"    {m}")


def cmd_model_catalog(
    selector: str | None = None,
    as_json: bool = False,
) -> None:
    """Show the canonical model catalog or a specific named pack."""
    from dharma_swarm.model_catalog import model_catalog_summary

    print(model_catalog_summary(selector=selector, as_json=as_json))


def cmd_custodians(
    custodians_cmd: str | None = None,
    roles: str | None = None,
    dry_run: bool = True,
) -> None:
    """Autonomous code maintenance fleet commands."""
    from dharma_swarm.custodians import (
        run_custodian_cycle, format_status, create_custodian_cron_jobs, ROLES,
    )

    match custodians_cmd:
        case "run":
            role_list = [r.strip() for r in roles.split(",")] if roles else None
            if role_list:
                invalid = [r for r in role_list if r not in ROLES]
                if invalid:
                    print(f"  Unknown roles: {', '.join(invalid)}")
                    print(f"  Valid: {', '.join(ROLES)}")
                    return
            mode = "DRY RUN" if dry_run else "LIVE"
            print(f"  Custodian fleet — {mode}")
            results = run_custodian_cycle(roles=role_list, dry_run=dry_run)
            for r in results:
                icon = "✅" if r.success else "❌"
                dry_tag = " [DRY]" if r.dry_run else ""
                print(f"  {icon} {r.role}{dry_tag}  model={r.model}  {r.duration_seconds}s")
                if r.files_targeted:
                    print(f"    targets: {', '.join(r.files_targeted[:5])}")
                if r.files_changed:
                    print(f"    changed: {', '.join(r.files_changed[:5])}")
                if r.committed:
                    print(f"    committed: yes")
                if r.error:
                    print(f"    error: {r.error}")
                if r.agent_output and not r.dry_run:
                    print(f"    output: {r.agent_output[:200]}")
        case "status":
            print(format_status())
        case "schedule":
            created = create_custodian_cron_jobs()
            if created:
                print(f"  Created {len(created)} custodian cron job(s):")
                for j in created:
                    print(f"    - {j.get('name', j.get('id', '?'))}")
            else:
                print("  All custodian cron jobs already exist.")
            # Install launchd service so daemon survives reboots
            from dharma_swarm.custodians import install_launchd_service
            if install_launchd_service():
                print("  Launchd service installed — daemon will auto-start on boot.")
            else:
                print("  Launchd service not installed (run `dgc cron daemon` manually).")
        case _:
            print("Usage: dgc custodians {run|status|schedule}")


def cmd_gateway(config_path: str | None = None) -> None:
    """Start the messaging gateway."""
    from pathlib import Path

    async def _run_gateway() -> None:
        from dharma_swarm.gateway.runner import GatewayRunner, load_gateway_config

        config = load_gateway_config(
            Path(config_path) if config_path else None
        )
        if not config:
            print("  No gateway config found. Create ~/.dharma/gateway.yaml")
            print("  Example:")
            print("    telegram:")
            print("      enabled: true")
            print("      token: ${TELEGRAM_BOT_TOKEN}")
            return

        runner = GatewayRunner(config=config)
        print("  Starting gateway...")
        await runner.start()
        print(f"  Gateway running with {len(runner.adapters)} adapter(s). Press Ctrl+C to stop.")

        try:
            while runner.is_running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n  Stopping gateway...")
        finally:
            await runner.stop()
            print("  Gateway stopped.")

    asyncio.run(_run_gateway())


def cmd_field_scan() -> None:
    """Run full D3 field intelligence scan."""
    import subprocess

    script = DHARMA_SWARM / "scripts" / "field_scan.py"
    if not script.exists():
        print(f"[field scan] Script not found: {script}")
        raise SystemExit(2)
    result = subprocess.run([sys.executable, str(script)], cwd=str(DHARMA_SWARM))
    raise SystemExit(result.returncode)


def cmd_field_gaps() -> None:
    """Show DGC capability gaps vs external field."""
    from dharma_swarm.field_graph import gap_report

    gp = gap_report()
    print(f"  {gp['title']}")
    print(f"  Hard gaps: {gp['hard_gap_count']}  |  Integration opportunities: {gp['integration_count']}")
    print()
    for item in gp["hard_gaps"]:
        print(f"  ✗ {item['id']} ({item['field']})")
        print(f"    → {item['source']}")
        print(f"    {item['relevance'][:140]}")
        print()
    for item in gp["integration_opportunities"]:
        print(f"  ⊕ {item['id']} ({item['field']})")
        print(f"    → {item['source']}")
        print()


def cmd_field_position() -> None:
    """Show DGC competitive positioning."""
    from dharma_swarm.field_graph import competitive_position

    cp = competitive_position()
    sa = cp["strategic_assessment"]
    print(f"  {cp['title']}")
    print(f"  Overall: {sa['overall']}  |  Moats: {sa['moat_count']}  "
          f"Gaps: {sa['gap_count']}  Validated: {sa['validated_count']}  "
          f"Threats: {sa['threat_count']}")
    print()
    for t in cp["competitive_threats"]:
        print(f"  [{t['threat_level']}] {t['id']}: {t['source']}")
    print()
    for domain, info in cp["domain_coverage"].items():
        print(f"  {domain:<24} [{info['strength']:<12}] "
              f"unique={info['unique']} gaps={info['gaps']} validated={info['validated']}")


def cmd_field_unique() -> None:
    """Show DGC unique moats."""
    from dharma_swarm.field_graph import uniqueness_report

    un = uniqueness_report()
    print(f"  {un['title']}")
    print(f"  Moat count: {un['count']}")
    print()
    for item in un["moats"]:
        print(f"  ★ {item['id']}")
        print(f"    {item['summary'][:140]}")
        print()


def cmd_field_summary() -> None:
    """Field KB summary statistics."""
    from dharma_swarm.field_knowledge_base import field_summary

    s = field_summary()
    print(f"  D3 Field KB: {s['total_entries']} entries")
    print(f"  Unique: {s['dgc_unique']}  Gaps: {s['dgc_gaps']}  Competitors: {s['dgc_competitors']}")
    print()
    print("  By relation:")
    for r, c in sorted(s["by_relation"].items(), key=lambda x: -x[1]):
        print(f"    {r:<16} {c}")
    print("  By field:")
    for f, c in sorted(s["by_field"].items(), key=lambda x: -x[1]):
        print(f"    {f:<32} {c}")


def cmd_foundations(pillar: str | None = None) -> None:
    """Show intellectual pillars and syntheses, or preview a specific pillar."""
    fdir = DHARMA_SWARM / "foundations"
    if not fdir.exists():
        print("No foundations/ directory found.")
        return

    if pillar:
        query = pillar.upper()
        matches = sorted(fdir.glob(f"*{query}*.md"))
        if not matches:
            print(f"No pillar matching '{pillar}'")
            available = sorted(f.stem for f in fdir.glob("PILLAR_*.md"))
            print(f"Available: {', '.join(available)}")
            return
        target = matches[0]
        lines = target.read_text().split("\n")
        print(f"=== {target.name} ({len(lines)} lines) ===\n")
        for line in lines[:60]:
            print(line)
        if len(lines) > 60:
            print(f"\n... ({len(lines) - 60} more lines)")
        return

    # List all
    pillars = sorted(fdir.glob("PILLAR_*.md"))
    synths = sorted(fdir.glob("*SYNTHESIS*.md"))
    arch = DHARMA_SWARM / "architecture" / "PRINCIPLES.md"

    print(f"=== Intellectual Pillars ({len(pillars)}) ===\n")
    for p in pillars:
        name = p.stem.replace("PILLAR_", "").replace("_", " ")
        size = len(p.read_text().split("\n"))
        print(f"  {p.name:<35} {name:<25} ({size} lines)")

    if synths:
        print(f"\n=== Syntheses ({len(synths)}) ===\n")
        for s in synths:
            size = len(s.read_text().split("\n"))
            print(f"  {s.name:<35} ({size} lines)")

    if arch.exists():
        size = len(arch.read_text().split("\n"))
        print(f"\n  PRINCIPLES.md  Architecture bridge ({size} lines)")

    total_lines = sum(len(f.read_text().split("\n")) for f in pillars)
    total_lines += sum(len(f.read_text().split("\n")) for f in synths)
    print(f"\n  Total: {len(pillars)} pillars, {len(synths)} syntheses, ~{total_lines} lines")
    print(f"\n  Usage: dgc foundations <name> (e.g. dgc foundations hofstadter)")


def _run_prune(
    dry_run: bool = False,
    stig_threshold: float = 0.3,
    bridge_threshold: float = 0.2,
    trace_days: int = 14,
) -> None:
    """Sweep the zen garden."""
    try:
        from dharma_swarm.pruner import Pruner

        pruner = Pruner(
            state_dir=DHARMA_STATE,
            stigmergy_threshold=stig_threshold,
            bridge_threshold=bridge_threshold,
            trace_max_days=trace_days,
            dry_run=dry_run,
        )
        report = asyncio.run(pruner.sweep())
        pruner.print_report(report)
    except Exception as exc:
        print(f"Pruner failed: {exc}")
        raise SystemExit(1)


def _run_meta() -> None:
    """Run the Overseeing I wholistic assessment."""
    try:
        from dharma_swarm.overseeing_i import OverseeingI

        oi = OverseeingI(state_dir=DHARMA_STATE)
        assessment = asyncio.run(oi.assess())
        oi.print_assessment(assessment)
    except Exception as exc:
        print(f"Overseeing I failed: {exc}")
        raise SystemExit(1)


def cmd_telos(doc: str | None = None) -> None:
    """Show telos engine research documents, or preview a specific document."""
    tdir = DHARMA_SWARM / "docs" / "telos-engine"
    if not tdir.exists():
        print("No docs/telos-engine/ directory found.")
        return

    if doc:
        query = doc.lower()
        matches = sorted(f for f in tdir.glob("*.md") if query in f.name.lower())
        if not matches:
            print(f"No document matching '{doc}'")
            available = sorted(f.stem for f in tdir.glob("[0-9]*.md"))
            print(f"Available: {', '.join(available)}")
            return
        target = matches[0]
        lines = target.read_text().split("\n")
        print(f"=== {target.name} ({len(lines)} lines) ===\n")
        for line in lines[:60]:
            print(line)
        if len(lines) > 60:
            print(f"\n... ({len(lines) - 60} more lines)")
        return

    docs = sorted(f for f in tdir.glob("*.md") if f.name != "INDEX.md")
    print(f"=== Telos Engine Research ({len(docs)} documents) ===\n")
    for d in docs:
        display = d.stem.lstrip("0123456789_").replace("_", " ")
        size = len(d.read_text().split("\n"))
        print(f"  {d.name:<35} {display:<30} ({size} lines)")

    total_lines = sum(len(f.read_text().split("\n")) for f in docs)
    print(f"\n  Total: {len(docs)} documents, ~{total_lines} lines")
    print(f"\n  Usage: dgc telos <name> (e.g. dgc telos competitive)")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dgc",
        description="DGC -- Dharmic Godel Claw unified CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")
    from dharma_swarm.dgc.main import _build_registry as _build_modular_registry

    _build_modular_registry().populate_subparsers(sub)

    return parser


# ---------------------------------------------------------------------------
# Autonomous agent commands
# ---------------------------------------------------------------------------


def _cmd_agent_wake(name: str, task: str, model: str | None) -> None:
    """Wake an autonomous agent with a task."""
    from dharma_swarm.autonomous_agent import cli_wake
    asyncio.run(cli_wake(name, task, model=model))


def _cmd_agent_list() -> None:
    """List available preset agents."""
    from dharma_swarm.autonomous_agent import PRESET_AGENTS
    print("Available autonomous agents:")
    print()
    for name, identity in PRESET_AGENTS.items():
        tools = ", ".join(identity.allowed_tools)
        print(f"  {name:<12} role={identity.role:<12} model={identity.model}")
        print(f"  {'':12} cwd={identity.working_directory}")
        print(f"  {'':12} tools=[{tools}]")
        print()


def _cmd_agent_runs() -> None:
    """Show recent agent run reports."""
    report_dir = Path.home() / ".dharma" / "agent_runs"
    if not report_dir.exists():
        print("No agent runs yet.")
        return
    for report_file in sorted(report_dir.glob("*_latest.json")):
        try:
            data = json.loads(report_file.read_text())
            print(
                f"  {data['agent']:<12} {data['turns']} turns, "
                f"{data.get('tokens_in', 0) + data.get('tokens_out', 0)} tokens, "
                f"{data['tool_calls']} tools, {data['duration_s']:.1f}s"
            )
            print(f"  {'':12} task: {data['task'][:80]}")
            if data.get("errors"):
                print(f"  {'':12} errors: {data['errors']}")
            print()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point for the unified DGC CLI."""
    # Compatibility shim: legacy habit `DGC TUI` / `dgc tui`
    if len(sys.argv) >= 2 and sys.argv[1].lower() == "tui":
        sys.argv = [sys.argv[0], "--tui", *sys.argv[2:]]

    # Optional default mode toggle: `DGC_DEFAULT_MODE=chat dgc`
    if len(sys.argv) < 2:
        default_mode = os.getenv("DGC_DEFAULT_MODE", "tui").strip().lower()
        if default_mode in {"chat", "claude", "cc"}:
            cmd_chat(
                continue_last=False,
                offline=os.getenv("DGC_CHAT_OFFLINE", "").strip() in {"1", "true", "yes", "on"},
                model=os.getenv("DGC_CHAT_MODEL") or None,
                effort=os.getenv("DGC_CHAT_EFFORT") or None,
                include_context=os.getenv("DGC_CHAT_NO_CONTEXT", "").strip().lower()
                not in {"1", "true", "yes", "on"},
            )
            return
        try:
            cmd_tui()
        except ImportError as e:
            print(f"TUI not available ({e}). Install: pip3 install textual")
            print("Falling back to status...\n")
            cmd_status()
        except Exception as e:
            print(f"TUI error: {e}")
            print("Falling back to status...\n")
            cmd_status()
        return

    # Explicit --tui -> launch TUI
    if sys.argv[1] == "--tui":
        try:
            cmd_tui()
        except ImportError as e:
            print(f"TUI not available ({e}). Install: pip3 install textual")
            print("Falling back to status...\n")
            cmd_status()
        except Exception as e:
            print(f"TUI error: {e}")
            print("Falling back to status...\n")
            cmd_status()
        return

    # Route extracted commands through the modular dispatcher even when callers
    # still invoke the legacy entrypoint directly.
    from dharma_swarm.dgc.main import _dispatch_known_command

    if _dispatch_known_command(sys.argv[1:]):
        return

    parser = _build_parser()
    args = parser.parse_args()
    # All named commands are now handled by the modular dispatcher above.
    # Reaching this point means argparse was invoked for help or for an
    # unexpected fallback path, so show the compatibility parser surface.
    _ = args
    parser.print_help()


if __name__ == "__main__":
    main()
