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
    state_file = DGC_CORE / "daemon" / "state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        print(f"Pulse: {state.get('pulse_count', 0)} total, last: {state.get('last_pulse', 'never')}")
    else:
        print("Pulse: not yet run")

    # Gate witness log
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    gate_log = DGC_CORE / "memory" / "witness" / f"{today}.jsonl"
    if gate_log.exists():
        with open(gate_log) as f:
            count = sum(1 for _ in f)
        print(f"Gates today: {count} checks")
    else:
        print("Gates today: 0 checks")

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
    # Use the dgc-core ecosystem map (pure function, no side effects)
    sys.path.insert(0, str(DGC_CORE / "context"))
    try:
        from ecosystem_map import get_context_for  # type: ignore[import-untyped]
        print(get_context_for(domain))
    except ImportError:
        # Fallback: dharma_swarm context module
        from dharma_swarm.context import build_agent_context
        print(build_agent_context(role=domain))
    finally:
        sys.path.pop(0)


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


def cmd_health() -> None:
    """Check ecosystem file health."""
    sys.path.insert(0, str(DGC_CORE / "context"))
    try:
        from ecosystem_map import check_health  # type: ignore[import-untyped]
        h = check_health()
        print(f"Ecosystem: {h['ok']} OK, {h['missing']} MISSING")
        if h["details"]:
            print("\nMissing paths:")
            for p, d in h["details"].items():
                print(f"  {p} -- {d}")
    except ImportError:
        print("ecosystem_map not available (dgc-core missing?)")
    finally:
        sys.path.pop(0)


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
    as_json: bool = False,
    strict: bool = False,
    quick: bool = False,
    timeout: float = 1.5,
) -> int:
    """Deep readiness diagnostics for runtime, routing, and providers."""
    from dharma_swarm.doctor import doctor_exit_code, render_doctor_report, run_doctor

    report = run_doctor(timeout_seconds=timeout, quick=quick)
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(render_doctor_report(report))
    return doctor_exit_code(report, strict=strict)


def cmd_pulse() -> None:
    """Run one heartbeat pulse."""
    from dharma_swarm.pulse import pulse

    response = pulse()
    print(response)


def cmd_orchestrate_live(background: bool = False) -> None:
    """Run all DGC systems concurrently (live orchestrator)."""
    import asyncio

    pid_file = DHARMA_STATE / "orchestrator.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            print(f"Orchestrator already running (PID {pid})")
            return
        except (ValueError, OSError):
            pid_file.unlink(missing_ok=True)

    if background:
        import subprocess as sp
        proc = sp.Popen(
            [sys.executable, "-m", "dharma_swarm.orchestrate_live", "--background"],
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
            start_new_session=True,
        )
        print(f"Orchestrator started in background (PID {proc.pid})")
    else:
        from dharma_swarm.orchestrate_live import orchestrate
        asyncio.run(orchestrate())


def cmd_up(background: bool = False) -> None:
    """Start the dharma_swarm daemon (pulse heartbeat loop)."""
    pid_file = DHARMA_STATE / "daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if running
            print(f"Daemon already running (PID {pid})")
            return
        except (ValueError, OSError):
            pid_file.unlink(missing_ok=True)

    repo_root = Path(__file__).resolve().parent.parent
    daemon_script = repo_root / "run_daemon.sh"
    env = os.environ.copy()
    env["MISSION_PREFLIGHT"] = "0"  # Skip preflight for direct launch

    if background:
        import subprocess
        proc = subprocess.Popen(
            ["bash", str(daemon_script)],
            env=env,
            cwd=str(repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        print(f"Daemon started in background (PID {proc.pid})")
    else:
        os.execvpe("bash", ["bash", str(daemon_script)], env)


def cmd_down() -> None:
    """Stop the daemon."""
    pid_file = DHARMA_STATE / "daemon.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
        except ValueError:
            print("Corrupted PID file, removing")
            pid_file.unlink()
            return
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"Sent SIGTERM to daemon (PID {pid})")
        except OSError:
            print(f"Daemon PID {pid} not found (stale)")
            pid_file.unlink()
    else:
        print("Daemon not running (no PID file)")


def cmd_daemon_status() -> None:
    """Show daemon state."""
    pid_file = DHARMA_STATE / "daemon.pid"
    pulse_log = DHARMA_STATE / "pulse.log"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            print(f"  status: running (PID {pid})")
        except (ValueError, OSError):
            print("  status: stale PID file")
    else:
        print("  status: not running")
    if pulse_log.exists():
        # Show last 5 lines of pulse log
        lines = pulse_log.read_text().strip().split("\n")
        print(f"  pulse_log: {len(lines)} entries")
        for line in lines[-5:]:
            print(f"    {line[:120]}")
    else:
        print("  pulse_log: no entries")


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
    """Create a new task."""
    async def _create():
        from dharma_swarm.models import TaskPriority

        swarm = await _get_swarm()
        try:
            p = TaskPriority(priority)
        except ValueError:
            print(f"Invalid priority: {priority}")
            await swarm.shutdown()
            sys.exit(1)
        task = await swarm.create_task(title=title, description=description, priority=p)
        print(f"Created task: {task.title} -- ID: {task.id}")
        await swarm.shutdown()

    _run(_create())


def cmd_task_list(status_filter: str | None) -> None:
    """List tasks."""
    async def _list():
        from dharma_swarm.models import TaskStatus

        swarm = await _get_swarm()
        s = TaskStatus(status_filter) if status_filter else None
        tasks = await swarm.list_tasks(status=s)
        if not tasks:
            print("No tasks.")
        else:
            print(f"{'ID':>8}  {'STATUS':<10}  {'PRI':<8}  {'ASSIGNED':<10}  TITLE")
            print("-" * 70)
            for t in tasks:
                print(f"{t.id[:8]}  {t.status.value:<10}  {t.priority.value:<8}  {(t.assigned_to or '-'):<10}  {t.title}")
        await swarm.shutdown()

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
        swarm = await _get_swarm()
        trend = await swarm.fitness_trend(component=component)
        if not trend:
            print("No fitness data yet.")
        else:
            print("Fitness Trend:")
            for ts, fitness in trend:
                print(f"  {ts[:19]}  {fitness:.3f}")
        await swarm.shutdown()

    _run(_trend())


def cmd_dharma_status() -> None:
    """Show Dharma subsystem status."""
    async def _status():
        swarm = await _get_swarm()
        status = await swarm.dharma_status()
        print("=== Dharma Status ===")
        for key, val in status.items():
            print(f"  {key}: {val}")
        await swarm.shutdown()
    _run(_status())


def cmd_dharma_corpus(status_filter: str | None = None, category_filter: str | None = None) -> None:
    """List corpus claims."""
    async def _corpus():
        swarm = await _get_swarm()
        # Access corpus directly for listing
        if swarm._corpus is None:
            print("Corpus not initialized")
            await swarm.shutdown()
            return
        from dharma_swarm.dharma_corpus import ClaimStatus, ClaimCategory
        s = ClaimStatus(status_filter) if status_filter else None
        c = ClaimCategory(category_filter) if category_filter else None
        claims = await swarm._corpus.list_claims(status=s, category=c)
        if not claims:
            print("No claims found.")
        else:
            print(f"{'ID':<16}  {'STATUS':<12}  {'CAT':<16}  STATEMENT")
            print("-" * 70)
            for cl in claims:
                print(f"{cl.id:<16}  {cl.status.value:<12}  {cl.category.value:<16}  {cl.statement[:40]}")
        await swarm.shutdown()
    _run(_corpus())


def cmd_dharma_review(claim_id: str) -> None:
    """Review a claim."""
    async def _review():
        swarm = await _get_swarm()
        result = await swarm.review_claim(claim_id, reviewer="cli-user", action="review", comment="Reviewed via CLI")
        print(f"Reviewed: {result['id']} -> {result['status']}")
        await swarm.shutdown()
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
    """Show stigmergy marks and hot paths."""
    async def _stig():
        swarm = await _get_swarm()
        if swarm._stigmergy is None:
            print("Stigmergy not initialized")
            await swarm.shutdown()
            return
        if file_path:
            marks = await swarm._stigmergy.read_marks(file_path=file_path, limit=10)
            print(f"Marks for {file_path}:")
            for m in marks:
                ts = m.timestamp.isoformat()[:19]
                print(f"  [{ts}] {m.agent}: {m.observation} (salience={m.salience:.1f})")
        else:
            hot = await swarm._stigmergy.hot_paths(window_hours=48, min_marks=2)
            if hot:
                print("Hot paths (last 48h):")
                for path, count in hot:
                    print(f"  {path}: {count} marks")
            else:
                print("No hot paths yet.")
            high = await swarm._stigmergy.high_salience(threshold=0.7, limit=5)
            if high:
                print("\nHigh salience marks:")
                for m in high:
                    print(f"  [{m.agent}] {m.observation} (salience={m.salience:.1f})")
        await swarm.shutdown()
    _run(_stig())


def cmd_hum() -> None:
    """Show recent subconscious associations."""
    async def _hum():
        swarm = await _get_swarm()
        if swarm._stigmergy is None:
            print("Stigmergy not initialized (required for subconscious)")
            await swarm.shutdown()
            return
        try:
            from dharma_swarm.subconscious import SubconsciousStream
            stream = SubconsciousStream(stigmergy=swarm._stigmergy)
            dreams = await stream.get_recent_dreams(limit=10)
            if not dreams:
                print("No dreams yet. The HUM is silent.")
            else:
                print("Recent subconscious associations:")
                for d in dreams:
                    print(f"  {d.source_a} <-> {d.source_b}")
                    print(f"    {d.resonance_type}: {d.description[:80]} (strength={d.strength:.2f})")
        except ImportError:
            print("Subconscious module not available")
        await swarm.shutdown()
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
    try:
        from dharma_swarm.tui import run
        run()
    except Exception:
        # Fallback to legacy TUI
        from dharma_swarm.tui_legacy import run_tui
        run_tui()


def _build_chat_context_snapshot() -> str:
    """Build a compact DGC context snapshot for Claude chat sessions."""
    from dharma_swarm.prompt_builder import build_state_context_snapshot

    return build_state_context_snapshot(
        state_dir=DHARMA_STATE,
        home=HOME,
        max_chars=6000,
    )


def cmd_chat(
    continue_last: bool = False,
    offline: bool = False,
    model: str | None = None,
    effort: str | None = None,
    include_context: bool = True,
) -> None:
    """Launch native Claude Code interactive UI (full experience)."""
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", None)
    if offline:
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"

    cmd = ["claude"]
    if continue_last:
        cmd.append("--continue")
    if model:
        cmd.extend(["--model", model])
    if effort:
        cmd.extend(["--effort", effort])

    if include_context:
        snapshot = _build_chat_context_snapshot()
        if snapshot:
            cmd.extend(
                [
                    "--append-system-prompt",
                    "DGC mission-control context snapshot. Treat as hints and verify.\n\n"
                    + snapshot,
                ]
            )

    try:
        os.execvpe("claude", cmd, env)
    except FileNotFoundError:
        print("claude CLI not found. Install Claude Code first.")
        sys.exit(1)
    except Exception as e:
        print(f"Failed to launch Claude Code: {e}")
        sys.exit(1)


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
    as_json: bool = False,
) -> int:
    """Run best-effort smoke tests for local and external provider lanes."""
    from dharma_swarm.provider_smoke import run_provider_smoke

    payload = run_provider_smoke(
        ollama_model=ollama_model,
        nim_model=nim_model,
    )
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    for label, block in payload.items():
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
        if block.get("configured_base_url"):
            print(f"  base_url={block['configured_base_url']}")
        if block.get("response_preview"):
            print(f"  preview={block['response_preview']}")
        if block.get("error"):
            print(f"  error={block['error']}")
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
) -> None:
    """Cron scheduler commands."""
    from dharma_swarm.cron_scheduler import (
        create_job,
        list_jobs,
        remove_job,
        tick,
    )

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
            from dharma_swarm.review_cycle import review_run_fn
            executed = tick(verbose=True, run_fn=review_run_fn)
            print(f"  Tick complete: {executed} job(s) executed")
        case _:
            print("Usage: dgc cron {add|list|remove|tick}")


def cmd_xray(
    repo_path: str,
    output: str | None = None,
    as_json: bool = False,
) -> None:
    """Run a Repo X-Ray analysis."""
    from pathlib import Path
    from dharma_swarm.xray import run_xray, analyze_repo, render_markdown

    path = Path(repo_path).expanduser().resolve()
    if not path.is_dir():
        print(f"  Error: {path} is not a directory")
        raise SystemExit(1)

    print(f"  Scanning {path}...")
    report_path = run_xray(path, output_path=output, as_json=as_json)

    if not as_json:
        # Also print to stdout
        report = analyze_repo(path)
        md = render_markdown(report)
        print(md)

    print(f"\n  Report saved to: {report_path}")


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
            print(f"  {'\u2705' if ok else '\u274c'} {msg}")
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

    # -- status --
    sub.add_parser("status", help="System status overview")
    p_runtime = sub.add_parser("runtime-status", help="Canonical runtime control-plane summary")
    p_runtime.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of recent rows to show for active runs/artifacts/actions",
    )
    p_runtime.add_argument(
        "--db-path",
        default=None,
        help="Override runtime SQLite path (defaults to ~/.dharma/state/runtime.db)",
    )
    p_mission = sub.add_parser("mission-status", help="Mission readiness lanes + gap report")
    p_mission.add_argument("--json", action="store_true", help="Emit JSON report")
    p_mission.add_argument(
        "--strict-core",
        action="store_true",
        help="Exit non-zero if core lane is not fully wired",
    )
    p_mission.add_argument(
        "--require-tracked",
        action="store_true",
        help="Exit non-zero if mission-critical files are local-only",
    )
    p_mission.add_argument(
        "--profile",
        choices=sorted(MISSION_AUTONOMY_PROFILES),
        default=None,
        help=(
            "Apply autonomy profile defaults for strict checks "
            "(strict-core/require-tracked)."
        ),
    )
    p_mbrief = sub.add_parser("mission-brief", help="Show active mission continuity state")
    p_mbrief.add_argument("--json", action="store_true", help="Emit mission continuity as JSON")
    p_mbrief.add_argument(
        "--path",
        default=None,
        help="Explicit path to mission.json or thinkodynamic latest.json",
    )
    p_mbrief.add_argument(
        "--state-dir",
        default=None,
        help="Override state root (defaults to ~/.dharma)",
    )
    p_cbrief = sub.add_parser("campaign-brief", help="Show active campaign continuity state")
    p_cbrief.add_argument("--json", action="store_true", help="Emit campaign continuity as JSON")
    p_cbrief.add_argument(
        "--path",
        default=None,
        help="Explicit path to campaign.json",
    )
    p_cbrief.add_argument(
        "--state-dir",
        default=None,
        help="Override state root (defaults to ~/.dharma)",
    )
    p_canonical = sub.add_parser("canonical-status", help="Show canonical DGC/SAB repo topology")
    p_canonical.add_argument("--json", action="store_true", help="Emit JSON report")

    # -- chat --
    p_chat = sub.add_parser("chat", help="Launch native Claude Code interactive UI")
    p_chat.add_argument(
        "-c",
        "--continue",
        dest="continue_last",
        action="store_true",
        help="Continue the most recent Claude session in this directory",
    )
    p_chat.add_argument(
        "--offline",
        action="store_true",
        help="Disable nonessential network traffic for Claude session",
    )
    p_chat.add_argument("--model", default=None, help="Claude model alias/name")
    p_chat.add_argument(
        "--effort",
        choices=["low", "medium", "high"],
        default=None,
        help="Reasoning effort level",
    )
    p_chat.add_argument(
        "--no-context",
        action="store_true",
        help="Do not append DGC state snapshot to Claude system prompt",
    )

    # -- dashboard --
    sub.add_parser("dashboard", help="Launch DGC dashboard (TUI)")

    # -- up --
    p_up = sub.add_parser("up", help="Start the daemon")
    p_up.add_argument("--background", action="store_true")

    # -- down --
    sub.add_parser("down", help="Stop the daemon")

    # -- daemon-status --
    sub.add_parser("daemon-status", help="Show daemon state")

    # -- pulse --
    sub.add_parser("pulse", help="Run one heartbeat pulse")

    # -- orchestrate-live --
    p_orch_live = sub.add_parser(
        "orchestrate-live",
        help="Run all DGC systems concurrently (live orchestrator)",
    )
    p_orch_live.add_argument("--background", action="store_true", help="Run in background")

    # -- swarm (captures all remaining args) --
    p_swarm = sub.add_parser("swarm", help="Swarm orchestrator + overnight/live")
    p_swarm.add_argument("swarm_args", nargs="*", default=[])

    # -- stress --
    p_stress = sub.add_parser("stress", help="Run max-capacity DGC stress harness")
    p_stress.add_argument("--profile", choices=["quick", "full", "max"], default="full")
    p_stress.add_argument("--state-dir", default=str(HOME / ".dharma" / "stress_lab"))
    p_stress.add_argument(
        "--provider-mode",
        choices=["auto", "mock", "claude", "codex", "openrouter"],
        default="auto",
    )
    p_stress.add_argument("--agents", type=int, default=8)
    p_stress.add_argument("--tasks", type=int, default=36)
    p_stress.add_argument("--evolutions", type=int, default=24)
    p_stress.add_argument("--evolution-concurrency", type=int, default=6)
    p_stress.add_argument("--cli-rounds", type=int, default=2)
    p_stress.add_argument("--cli-concurrency", type=int, default=8)
    p_stress.add_argument("--orchestration-timeout-sec", type=int, default=240)
    p_stress.add_argument("--external-timeout-sec", type=int, default=120)
    p_stress.add_argument("--external-research", action="store_true")
    p_probe = sub.add_parser(
        "full-power-probe",
        aliases=["probe"],
        help="Run the reusable operator-facing full-power probe",
    )
    p_probe.add_argument(
        "--route-task",
        default="test the full power of dgc from inside the system and show what it can do",
    )
    p_probe.add_argument(
        "--context-search-query",
        default="mechanistic thread reports unfinished work active modules evidence paths",
    )
    p_probe.add_argument(
        "--compose-task",
        default=(
            "Probe DGC full power from inside this workspace, verify the mechanistic "
            "thread snapshot, and produce a concrete artifact"
        ),
    )
    p_probe.add_argument(
        "--autonomy-action",
        default="run a broad but safe local full-power probe without mutating external systems",
    )
    p_probe.add_argument("--skip-sprint-probe", action="store_true")
    p_probe.add_argument("--skip-stress", action="store_true")
    p_probe.add_argument("--skip-pytest", action="store_true")

    p_provider = sub.add_parser("provider-smoke", help="Probe local and external provider lanes")
    p_provider.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_provider.add_argument("--ollama-model", default=None, help="Override Ollama model")
    p_provider.add_argument("--nim-model", default=None, help="Override NVIDIA NIM model")

    # -- context --
    p_ctx = sub.add_parser("context", help="Load context for a domain")
    p_ctx.add_argument("domain", nargs="?", default="all")

    # -- memory --
    sub.add_parser("memory", help="Show memory status")

    # -- witness --
    p_wit = sub.add_parser("witness", help="Record a witness observation")
    p_wit.add_argument("message", nargs="+")

    # -- develop --
    p_dev = sub.add_parser("develop", help="Record a development marker")
    p_dev.add_argument("what", help="What was developed")
    p_dev.add_argument("evidence", nargs="+", help="Evidence")

    # -- gates --
    p_gates = sub.add_parser("gates", help="Run telos gates on an action")
    p_gates.add_argument("action", nargs="+")

    # -- health --
    sub.add_parser("health", help="Ecosystem file health")

    # -- health-check (v0.2.0 monitor) --
    sub.add_parser("health-check", help="Monitor-based system health check")

    # -- doctor --
    p_doc = sub.add_parser("doctor", help="Deep runtime diagnostics and fix guidance")
    p_doc.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    p_doc.add_argument("--strict", action="store_true", help="Exit non-zero on WARN")
    p_doc.add_argument("--quick", action="store_true", help="Skip deep network/package probes")
    p_doc.add_argument("--timeout", type=float, default=1.5, help="Probe timeout seconds")

    # -- setup --
    sub.add_parser("setup", help="Install dependencies")

    # -- migrate --
    sub.add_parser("migrate", help="Migrate old DGC memory")

    # -- model --
    p_model = sub.add_parser("model", help="Model management and switching")
    p_model.add_argument("action", nargs="?", default="status",
                         help="Action: status (default), list, or model alias (opus/sonnet/haiku/gpt-4o)")

    # -- agni --
    p_agni = sub.add_parser("agni", help="Run command on AGNI VPS")
    p_agni.add_argument("remote_cmd", nargs="+")

    # -- spawn --
    p_spawn = sub.add_parser("spawn", help="Spawn a new agent")
    p_spawn.add_argument("--name", required=True)
    p_spawn.add_argument("--role", default="general")
    p_spawn.add_argument("--model", default="anthropic/claude-sonnet-4")

    # -- task --
    p_task = sub.add_parser("task", help="Task management")
    task_sub = p_task.add_subparsers(dest="task_cmd")

    p_tc = task_sub.add_parser("create", help="Create a task")
    p_tc.add_argument("title")
    p_tc.add_argument("--description", default="")
    p_tc.add_argument("--priority", default="normal")

    p_tl = task_sub.add_parser("list", help="List tasks")
    p_tl.add_argument("--status", dest="status_filter", default=None)

    # -- evolve --
    p_evolve = sub.add_parser("evolve", help="Evolution engine commands")
    evolve_sub = p_evolve.add_subparsers(dest="evolve_cmd")

    p_ep = evolve_sub.add_parser("propose", help="Propose an evolution")
    p_ep.add_argument("component", help="Module or file being changed")
    p_ep.add_argument("description", help="Description of the change")
    p_ep.add_argument("--change-type", default="mutation")
    p_ep.add_argument("--diff", default="")

    p_et = evolve_sub.add_parser("trend", help="Show fitness trend")
    p_et.add_argument("--component", default=None)

    p_ea = evolve_sub.add_parser("apply", help="Apply evolution with sandbox")
    p_ea.add_argument("component")
    p_ea.add_argument("description")

    p_epr = evolve_sub.add_parser("promote", help="Promote a canary")
    p_epr.add_argument("entry_id")

    p_erb = evolve_sub.add_parser("rollback", help="Rollback a deployment")
    p_erb.add_argument("entry_id")
    p_erb.add_argument("--reason", default="Manual rollback")

    p_eauto = evolve_sub.add_parser("auto", help="LLM-powered autonomous evolution")
    p_eauto.add_argument("--files", nargs="*", help="Source files to evolve (default: core modules)")
    p_eauto.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    p_eauto.add_argument("--context", default="", help="Focus area or context for the LLM")
    p_eauto.add_argument("--single-model", action="store_true", help="Use only --model instead of full roster")
    p_eauto.add_argument("--shadow", action="store_true", help="Dry-run: generate proposals but don't apply diffs")
    p_eauto.add_argument("--token-budget", type=int, default=0, help="Max tokens per session (0=unlimited)")

    p_edaemon = evolve_sub.add_parser("daemon", help="Run continuous autonomous evolution")
    p_edaemon.add_argument("--interval", type=float, default=1800.0, help="Seconds between cycles (default: 30min)")
    p_edaemon.add_argument("--threshold", type=float, default=0.6, help="Min fitness to auto-commit")
    p_edaemon.add_argument("--model", default="meta-llama/llama-3.3-70b-instruct")
    p_edaemon.add_argument("--cycles", type=int, default=None, help="Max cycles (default: infinite)")
    p_edaemon.add_argument("--single-model", action="store_true", help="Use only --model instead of full roster")
    p_edaemon.add_argument("--shadow", action="store_true", help="Dry-run: generate proposals but don't apply diffs")
    p_edaemon.add_argument("--token-budget", type=int, default=0, help="Max tokens per session (0=unlimited)")

    # -- dharma --
    p_dharma = sub.add_parser("dharma", help="Dharma subsystem commands")
    dharma_sub = p_dharma.add_subparsers(dest="dharma_cmd")

    dharma_sub.add_parser("status", help="Dharma subsystem status")

    p_dc = dharma_sub.add_parser("corpus", help="List corpus claims")
    p_dc.add_argument("--status", dest="corpus_status", default=None)
    p_dc.add_argument("--category", dest="corpus_category", default=None)

    p_dr = dharma_sub.add_parser("review", help="Review a claim")
    p_dr.add_argument("claim_id")

    # -- stigmergy --
    p_stig = sub.add_parser("stigmergy", help="Stigmergy marks and hot paths")
    p_stig.add_argument("--file", dest="stig_file", default=None)

    # -- hum --
    sub.add_parser("hum", help="Subconscious associations")

    # -- run --
    p_run = sub.add_parser("run", help="Run orchestration loop")
    p_run.add_argument("--interval", type=float, default=2.0)

    # -- rag --
    p_rag = sub.add_parser("rag", help="NVIDIA RAG integration commands")
    rag_sub = p_rag.add_subparsers(dest="rag_cmd")

    p_rh = rag_sub.add_parser("health", help="Check rag/ingestor health")
    p_rh.add_argument(
        "--service",
        choices=["rag", "ingest"],
        default="rag",
    )
    p_rh.add_argument(
        "--no-deps",
        action="store_true",
        help="Skip dependency checks",
    )

    p_rs = rag_sub.add_parser("search", help="Query RAG search endpoint")
    p_rs.add_argument("query", nargs="+")
    p_rs.add_argument("--top-k", type=int, default=5)
    p_rs.add_argument("--collection", default=None)

    p_rc = rag_sub.add_parser("chat", help="Run grounded chat completion")
    p_rc.add_argument("prompt", nargs="+")
    p_rc.add_argument("--model", default=None)

    # -- flywheel --
    p_fw = sub.add_parser("flywheel", help="NVIDIA Data Flywheel commands")
    fw_sub = p_fw.add_subparsers(dest="flywheel_cmd")

    fw_sub.add_parser("jobs", help="List flywheel jobs")

    p_fwe = fw_sub.add_parser("export", help="Build a local canonical flywheel export")
    p_fwe.add_argument("--run-id", required=True)
    p_fwe.add_argument("--workload-id", required=True)
    p_fwe.add_argument("--client-id", required=True)
    p_fwe.add_argument("--trace-id", default=None)
    p_fwe.add_argument("--db-path", default=None)
    p_fwe.add_argument("--event-log-dir", default=None)
    p_fwe.add_argument("--export-root", default=None)

    p_fwr = fw_sub.add_parser("record", help="Record a flywheel job result into canonical runtime truth")
    p_fwr.add_argument("job_id")
    p_fwr.add_argument("--workload-id", default=None)
    p_fwr.add_argument("--client-id", default=None)
    p_fwr.add_argument("--run-id", default=None)
    p_fwr.add_argument("--session-id", default=None)
    p_fwr.add_argument("--task-id", default=None)
    p_fwr.add_argument("--trace-id", default=None)
    p_fwr.add_argument("--db-path", default=None)
    p_fwr.add_argument("--event-log-dir", default=None)
    p_fwr.add_argument("--workspace-root", default=None)
    p_fwr.add_argument("--provenance-root", default=None)

    p_fws = fw_sub.add_parser("start", help="Start a flywheel job")
    p_fws.add_argument("--workload-id", required=True)
    p_fws.add_argument("--client-id", required=True)
    p_fws.add_argument("--eval-size", type=int, default=20)
    p_fws.add_argument("--val-ratio", type=float, default=0.1)
    p_fws.add_argument("--min-total-records", type=int, default=50)
    p_fws.add_argument("--limit", type=int, default=10000)
    p_fws.add_argument("--run-id", default=None)
    p_fws.add_argument("--trace-id", default=None)
    p_fws.add_argument("--db-path", default=None)
    p_fws.add_argument("--event-log-dir", default=None)
    p_fws.add_argument("--export-root", default=None)

    p_fwg = fw_sub.add_parser("get", help="Get flywheel job details")
    p_fwg.add_argument("job_id")

    p_fwc = fw_sub.add_parser("cancel", help="Cancel flywheel job")
    p_fwc.add_argument("job_id")

    p_fwd = fw_sub.add_parser("delete", help="Delete flywheel job")
    p_fwd.add_argument("job_id")

    p_fww = fw_sub.add_parser("watch", help="Wait for job completion")
    p_fww.add_argument("job_id")
    p_fww.add_argument("--poll-sec", type=float, default=5.0)
    p_fww.add_argument("--timeout-sec", type=float, default=1800.0)

    # -- reciprocity --
    p_recip = sub.add_parser(
        "reciprocity",
        help="Planetary Reciprocity Commons commands",
    )
    reciprocity_sub = p_recip.add_subparsers(dest="reciprocity_cmd")

    reciprocity_sub.add_parser("health", help="Check reciprocity service health")
    reciprocity_sub.add_parser("summary", help="Fetch the current ledger summary")

    p_recp = reciprocity_sub.add_parser(
        "publish",
        help="Publish a reciprocity record to the service",
    )
    p_recp.add_argument(
        "publish_type",
        choices=["activity", "obligation", "project", "outcome"],
    )
    p_recp_payload = p_recp.add_mutually_exclusive_group(required=True)
    p_recp_payload.add_argument(
        "--json",
        dest="publish_json",
        default=None,
        help="Inline JSON object payload",
    )
    p_recp_payload.add_argument(
        "--file",
        dest="publish_file",
        default=None,
        help="Path to a JSON payload file",
    )

    p_recr = reciprocity_sub.add_parser(
        "record",
        help="Record the current reciprocity ledger summary into canonical runtime truth",
    )
    p_recr.add_argument("--run-id", default=None)
    p_recr.add_argument("--session-id", default=None)
    p_recr.add_argument("--task-id", default=None)
    p_recr.add_argument("--trace-id", default=None)
    p_recr.add_argument("--summary-type", default="ledger_summary")
    p_recr_payload = p_recr.add_mutually_exclusive_group(required=False)
    p_recr_payload.add_argument(
        "--json",
        dest="record_json",
        default=None,
        help="Inline JSON ledger summary payload to record instead of fetching live",
    )
    p_recr_payload.add_argument(
        "--file",
        dest="record_file",
        default=None,
        help="Path to a JSON ledger summary payload file to record instead of fetching live",
    )
    p_recr.add_argument("--db-path", default=None)
    p_recr.add_argument("--event-log-dir", default=None)
    p_recr.add_argument("--workspace-root", default=None)
    p_recr.add_argument("--provenance-root", default=None)

    # -- ouroboros --
    p_ouro = sub.add_parser("ouroboros", help="Behavioral self-observation tools")
    ouro_sub = p_ouro.add_subparsers(dest="ouroboros_cmd")

    p_ouro_conn = ouro_sub.add_parser(
        "connections",
        help="Profile module docstrings and surface H0/H1 behavioral structure",
    )
    p_ouro_conn.add_argument("--package-dir", default=None)
    p_ouro_conn.add_argument("--threshold", type=float, default=0.08)
    p_ouro_conn.add_argument("--disagreement-threshold", type=float, default=0.1)
    p_ouro_conn.add_argument("--min-text-length", type=int, default=50)
    p_ouro_conn.add_argument("--limit", type=int, default=15)
    p_ouro_conn.add_argument("--json", dest="as_json", action="store_true")

    p_ouro_record = ouro_sub.add_parser(
        "record",
        help="Record the latest ouroboros observation into canonical runtime truth",
    )
    p_ouro_record.add_argument("--run-id", default=None)
    p_ouro_record.add_argument("--session-id", default=None)
    p_ouro_record.add_argument("--task-id", default=None)
    p_ouro_record.add_argument("--trace-id", default=None)
    p_ouro_record.add_argument("--log-path", default=None)
    p_ouro_record.add_argument("--cycle-id", default=None)
    p_ouro_record_payload = p_ouro_record.add_mutually_exclusive_group(required=False)
    p_ouro_record_payload.add_argument(
        "--json",
        dest="observation_json",
        default=None,
        help="Inline JSON ouroboros observation payload to record instead of reading the log",
    )
    p_ouro_record_payload.add_argument(
        "--file",
        dest="observation_file",
        default=None,
        help="Path to a JSON ouroboros observation payload file to record instead of reading the log",
    )
    p_ouro_record.add_argument("--db-path", default=None)
    p_ouro_record.add_argument("--event-log-dir", default=None)
    p_ouro_record.add_argument("--workspace-root", default=None)
    p_ouro_record.add_argument("--provenance-root", default=None)

    # -- skills --
    sub.add_parser("skills", help="List discovered skills (v0.4.0)")

    # -- route --
    p_route = sub.add_parser("route", help="Route a task to best skill (v0.4.0)")
    p_route.add_argument("task_desc", nargs="+", help="Task description")

    # -- orchestrate --
    p_orch = sub.add_parser("orchestrate", help="Decompose and orchestrate a task (v0.4.0)")
    p_orch.add_argument("orch_desc", nargs="+", help="Task description")

    # -- autonomy --
    p_auto = sub.add_parser("autonomy", help="Check autonomy for an action (v0.4.0)")
    p_auto.add_argument("auto_action", nargs="+", help="Action to check")

    # -- context-search --
    p_cs = sub.add_parser("context-search", help="Search for task-relevant context (v0.4.0)")
    p_cs.add_argument("cs_query", nargs="+", help="Search query")
    p_cs.add_argument("--budget", type=int, default=10000)

    # -- compose (v0.4.1) --
    p_comp = sub.add_parser("compose", help="Compose a task into DAG execution plan (v0.4.1)")
    p_comp.add_argument("comp_desc", nargs="+", help="Task description")

    # -- execute-compose (v0.4.2) --
    p_exec_comp = sub.add_parser("execute-compose", help="Compose and execute a task DAG end-to-end")
    p_exec_comp.add_argument("exec_comp_desc", nargs="+", help="Task description")

    # -- handoff (v0.4.1) --
    p_ho = sub.add_parser("handoff", help="Create a structured agent handoff (v0.4.1)")
    p_ho.add_argument("--from", dest="ho_from", required=True, help="Source agent")
    p_ho.add_argument("--to", dest="ho_to", required=True, help="Target agent")
    p_ho.add_argument("--context", dest="ho_context", required=True, help="Task context")
    p_ho.add_argument("content", nargs="+", help="Handoff content")

    # -- agent-memory (v0.4.1) --
    p_am = sub.add_parser("agent-memory", help="Agent self-editing memory (v0.4.1)")
    p_am.add_argument("mem_agent", help="Agent name")

    # -- sprint --
    p_sprint = sub.add_parser("sprint", help="Generate today's adaptive 8-hour sprint prompt")
    p_sprint.add_argument(
        "--output", default=None, help="Output path (default: ~/.dharma/shared/SPRINT_8H_<date>.md)"
    )
    p_sprint.add_argument(
        "--local", action="store_true", help="Generate without LLM (offline mode)"
    )
    p_sprint.add_argument("--test-summary", default="", help="Test results to include")
    p_sprint.add_argument("--prev-todo", default="", help="Previous TODO items to include")
    p_sprint.add_argument(
        "--llm-timeout-sec",
        type=float,
        default=DEFAULT_SPRINT_LLM_TIMEOUT_SEC,
        help="Timeout for remote sprint prompt generation before local fallback",
    )

    # -- ledger --
    p_ledger = sub.add_parser("ledger", help="Inspect orchestrator session ledgers")
    ledger_sub = p_ledger.add_subparsers(dest="ledger_cmd")

    p_ledger_tail = ledger_sub.add_parser("tail", help="Show recent ledger events")
    p_ledger_tail.add_argument("-n", type=int, default=20, help="Number of events")
    p_ledger_tail.add_argument("--session", default=None, help="Session ID (default: most recent)")
    p_ledger_tail.add_argument(
        "--kind", choices=["task", "progress", "all"], default="all", help="Which ledger"
    )

    ledger_sub.add_parser("sessions", help="List recent sessions")
    p_ledger_search = ledger_sub.add_parser("search", help="Search indexed ledger events")
    p_ledger_search.add_argument("query", nargs="+", help="Search query")
    p_ledger_search.add_argument("-n", type=int, default=10, help="Number of matches")
    p_ledger_search.add_argument("--session", default=None, help="Limit search to one session ID")
    p_ledger_search.add_argument(
        "--kind", choices=["task", "progress", "all"], default="all", help="Which ledger"
    )
    p_ledger_search.add_argument("--db-path", default=None, help="Override runtime state DB path")
    p_ledger_search.add_argument(
        "--no-sync-ledgers",
        action="store_true",
        help="Skip ledger-dir reindex before searching",
    )
    p_ledger_search.add_argument(
        "--limit-sessions",
        type=int,
        default=None,
        help="Limit reindex to the most recent N sessions",
    )
    p_ledger_index = ledger_sub.add_parser("index", help="Index ledger JSONL into runtime search store")
    p_ledger_index.add_argument("--session", default=None, help="Index only one session ID")
    p_ledger_index.add_argument("--db-path", default=None, help="Override runtime state DB path")
    p_ledger_index.add_argument(
        "--limit-sessions",
        type=int,
        default=None,
        help="Limit indexing to the most recent N sessions",
    )

    # -- semantic --
    p_sem = sub.add_parser("semantic", help="Semantic Evolution Engine commands")
    sem_sub = p_sem.add_subparsers(dest="semantic_cmd")

    p_sd = sem_sub.add_parser("digest", help="Read codebase and build concept graph")
    p_sd.add_argument("--root", default=str(DHARMA_SWARM), help="Project root")
    p_sd.add_argument("--output", default=None, help="Graph output path")
    p_sd.add_argument(
        "--max-files",
        type=int,
        default=500,
        help="Safety cap on files processed during digest",
    )
    p_sd.add_argument(
        "--include-tests",
        action="store_true",
        help="Include test files in the digest",
    )

    p_sr = sem_sub.add_parser("research", help="Annotate graph with external research")
    p_sr.add_argument("--graph", default=None, help="Path to concept graph JSON")

    p_ss = sem_sub.add_parser("synthesize", help="Generate file cluster specs")
    p_ss.add_argument("--graph", default=None, help="Path to concept graph JSON")
    p_ss.add_argument("--max-clusters", type=int, default=10)

    p_sh = sem_sub.add_parser("harden", help="Run 6-angle hardening on clusters")
    p_sh.add_argument("--graph", default=None, help="Path to concept graph JSON")
    p_sh.add_argument("--root", default=str(DHARMA_SWARM), help="Project root")

    p_sb = sem_sub.add_parser("brief", help="Compile semantic clusters into campaign briefs")
    p_sb.add_argument("--graph", default=None, help="Path to concept graph JSON")
    p_sb.add_argument("--root", default=str(DHARMA_SWARM), help="Project root")
    p_sb.add_argument("--max-briefs", type=int, default=3)
    p_sb.add_argument("--json-output", default=None, help="Output path for brief packet JSON")
    p_sb.add_argument("--markdown-output", default=None, help="Output path for brief packet markdown")
    p_sb.add_argument("--state-dir", default=None, help="Override state root for campaign updates")
    p_sb.add_argument("--campaign-path", default=None, help="Explicit campaign.json path")

    p_sst = sem_sub.add_parser("status", help="Semantic graph status overview")
    p_sst.add_argument("--graph", default=None, help="Path to concept graph JSON")

    p_sp = sem_sub.add_parser("proof", help="Run live end-to-end proof of the semantic pipeline")
    p_sp.add_argument("--root", default=str(DHARMA_SWARM), help="Project root")

    # -- bootstrap --
    sub.add_parser("bootstrap", help="Generate bootstrap manifest (NOW.json) — orients any new LLM instance")

    # -- field (D3: External AI Field Intelligence) --
    p_field = sub.add_parser("field", help="D3 External AI Field Intelligence Engine")
    field_sub = p_field.add_subparsers(dest="field_cmd")
    field_sub.add_parser("scan", help="Full D3 field intelligence scan with all reports")
    field_sub.add_parser("gaps", help="Show DGC capability gaps vs external field")
    field_sub.add_parser("position", help="Show DGC competitive positioning")
    field_sub.add_parser("unique", help="Show DGC unique moats")
    field_sub.add_parser("summary", help="Field KB summary statistics")

    # -- xray (Phase 14: Repo X-Ray Product) --
    p_xray = sub.add_parser("xray", help="Run Repo X-Ray — codebase analysis for any repo")
    p_xray.add_argument("repo_path", help="Path to repository to analyze")
    p_xray.add_argument("--output", "-o", default=None, help="Output file path")
    p_xray.add_argument("--json", action="store_true", dest="as_json", help="Output JSON instead of markdown")

    # -- review (Phase 13: Quality Ratchet) --
    p_review = sub.add_parser("review", help="Generate 6-hour review cycle report")
    p_review.add_argument("--hours", type=float, default=6.0, help="Review window in hours")
    p_review.add_argument("--skip-tests", action="store_true", help="Skip running tests")

    # -- initiatives (Phase 13: Iteration Depth Tracker) --
    p_init = sub.add_parser("initiatives", help="Initiative depth ledger")
    init_sub = p_init.add_subparsers(dest="init_cmd")
    init_sub.add_parser("list", help="List all initiatives")
    p_init_add = init_sub.add_parser("add", help="Add a new initiative")
    p_init_add.add_argument("--title", required=True, help="Initiative title")
    p_init_add.add_argument("--description", default="", help="Description")
    p_init_promote = init_sub.add_parser("promote", help="Promote an initiative")
    p_init_promote.add_argument("initiative_id", help="Initiative ID")
    p_init_abandon = init_sub.add_parser("abandon", help="Abandon an initiative")
    p_init_abandon.add_argument("initiative_id", help="Initiative ID")
    p_init_abandon.add_argument("--reason", required=True, help="Reason for abandonment")
    init_sub.add_parser("summary", help="Show initiative summary")

    # -- cron (v0.6.0: Hermes-inspired cron scheduler) --
    p_cron = sub.add_parser("cron", help="Cron job scheduler (v0.6.0)")
    cron_sub = p_cron.add_subparsers(dest="cron_cmd")
    p_cron_add = cron_sub.add_parser("add", help="Add a new cron job")
    p_cron_add.add_argument("prompt", help="Task prompt to execute")
    p_cron_add.add_argument("schedule", help="Schedule: '30m', 'every 2h', '0 9 * * *'")
    p_cron_add.add_argument("--name", default=None, help="Friendly job name")
    p_cron_add.add_argument("--repeat", type=int, default=None, help="Repeat count (None=forever)")
    p_cron_add.add_argument("--deliver", default="local", help="Delivery target")
    p_cron_add.add_argument("--urgent", action="store_true", help="Run even during quiet hours")
    cron_sub.add_parser("list", help="List all cron jobs")
    p_cron_rm = cron_sub.add_parser("remove", help="Remove a cron job")
    p_cron_rm.add_argument("job_id", help="Job ID to remove")
    cron_sub.add_parser("tick", help="Manually trigger a cron tick")

    # -- gateway (v0.6.0: Hermes-inspired messaging gateway) --
    p_gw = sub.add_parser("gateway", help="Start messaging gateway (v0.6.0)")
    p_gw.add_argument("--config", default=None, help="Path to gateway.yaml")

    return parser


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

    parser = _build_parser()
    args = parser.parse_args()

    match args.command:
        case "chat":
            cmd_chat(
                continue_last=args.continue_last,
                offline=args.offline,
                model=args.model,
                effort=args.effort,
                include_context=not args.no_context,
            )
        case "dashboard":
            cmd_tui()
        case "status":
            cmd_status()
        case "runtime-status":
            cmd_runtime_status(limit=args.limit, db_path=args.db_path)
        case "mission-status":
            rc = cmd_mission_status(
                as_json=args.json,
                strict_core=args.strict_core,
                require_tracked=args.require_tracked,
                profile=args.profile,
            )
            if rc != 0:
                raise SystemExit(rc)
        case "mission-brief":
            rc = cmd_mission_brief(
                path=args.path,
                state_dir=args.state_dir,
                as_json=args.json,
            )
            if rc != 0:
                raise SystemExit(rc)
        case "campaign-brief":
            rc = cmd_campaign_brief(
                path=args.path,
                state_dir=args.state_dir,
                as_json=args.json,
            )
            if rc != 0:
                raise SystemExit(rc)
        case "canonical-status":
            rc = cmd_canonical_status(as_json=args.json)
            if rc != 0:
                raise SystemExit(rc)
        case "up":
            cmd_up(background=args.background)
        case "down":
            cmd_down()
        case "daemon-status":
            cmd_daemon_status()
        case "pulse":
            cmd_pulse()
        case "orchestrate-live":
            cmd_orchestrate_live(background=args.background)
        case "swarm":
            cmd_swarm(args.swarm_args)
        case "stress":
            cmd_stress(
                profile=args.profile,
                state_dir=args.state_dir,
                provider_mode=args.provider_mode,
                agents=args.agents,
                tasks=args.tasks,
                evolutions=args.evolutions,
                evolution_concurrency=args.evolution_concurrency,
                cli_rounds=args.cli_rounds,
                cli_concurrency=args.cli_concurrency,
                orchestration_timeout_sec=args.orchestration_timeout_sec,
                external_research=args.external_research,
                external_timeout_sec=args.external_timeout_sec,
            )
        case "full-power-probe" | "probe":
            cmd_full_power_probe(
                route_task=args.route_task,
                context_search_query=args.context_search_query,
                compose_task=args.compose_task,
                autonomy_action=args.autonomy_action,
                skip_sprint_probe=args.skip_sprint_probe,
                skip_stress=args.skip_stress,
                skip_pytest=args.skip_pytest,
            )
        case "provider-smoke":
            rc = cmd_provider_smoke(
                ollama_model=args.ollama_model,
                nim_model=args.nim_model,
                as_json=args.json,
            )
            if rc != 0:
                raise SystemExit(rc)
        case "context":
            cmd_context(args.domain)
        case "memory":
            cmd_memory()
        case "witness":
            cmd_witness(" ".join(args.message))
        case "develop":
            cmd_develop(args.what, " ".join(args.evidence))
        case "gates":
            cmd_gates(" ".join(args.action))
        case "health":
            cmd_health()
        case "health-check":
            cmd_health_check()
        case "doctor":
            rc = cmd_doctor(
                as_json=args.json,
                strict=args.strict,
                quick=args.quick,
                timeout=args.timeout,
            )
            if rc != 0:
                raise SystemExit(rc)
        case "setup":
            cmd_setup()
        case "migrate":
            cmd_migrate()
        case "model":
            cmd_model(action=args.action)
        case "agni":
            cmd_agni(" ".join(args.remote_cmd))
        case "spawn":
            cmd_spawn(name=args.name, role=args.role, model=args.model)
        case "task":
            match args.task_cmd:
                case "create":
                    cmd_task_create(args.title, args.description, args.priority)
                case "list":
                    cmd_task_list(args.status_filter)
                case _:
                    parser.parse_args(["task", "--help"])
        case "evolve":
            match args.evolve_cmd:
                case "propose":
                    cmd_evolve_propose(
                        args.component, args.description,
                        args.change_type, args.diff,
                    )
                case "trend":
                    cmd_evolve_trend(args.component)
                case "apply":
                    cmd_evolve_apply(args.component, args.description)
                case "promote":
                    cmd_evolve_promote(args.entry_id)
                case "rollback":
                    cmd_evolve_rollback(args.entry_id, args.reason)
                case "auto":
                    cmd_evolve_auto(
                        args.files, args.model, args.context,
                        single_model=args.single_model,
                        shadow=args.shadow,
                        token_budget=args.token_budget,
                    )
                case "daemon":
                    cmd_evolve_daemon(
                        args.interval, args.threshold, args.model, args.cycles,
                        single_model=args.single_model,
                        shadow=args.shadow,
                        token_budget=args.token_budget,
                    )
                case _:
                    parser.parse_args(["evolve", "--help"])
        case "run":
            cmd_run(interval=args.interval)
        case "rag":
            try:
                match args.rag_cmd:
                    case "health":
                        cmd_rag_health(
                            service=args.service,
                            check_dependencies=not args.no_deps,
                        )
                    case "search":
                        cmd_rag_search(
                            query=" ".join(args.query),
                            top_k=args.top_k,
                            collection=args.collection,
                        )
                    case "chat":
                        cmd_rag_chat(prompt=" ".join(args.prompt), model=args.model)
                    case _:
                        parser.parse_args(["rag", "--help"])
            except Exception as e:
                print(f"RAG command failed: {e}")
                raise SystemExit(2)
        case "flywheel":
            try:
                match args.flywheel_cmd:
                    case "jobs":
                        cmd_flywheel_jobs()
                    case "export":
                        cmd_flywheel_export(
                            run_id=args.run_id,
                            workload_id=args.workload_id,
                            client_id=args.client_id,
                            trace_id=args.trace_id,
                            db_path=args.db_path,
                            event_log_dir=args.event_log_dir,
                            export_root=args.export_root,
                        )
                    case "record":
                        cmd_flywheel_record(
                            job_id=args.job_id,
                            workload_id=args.workload_id,
                            client_id=args.client_id,
                            run_id=args.run_id,
                            session_id=args.session_id,
                            task_id=args.task_id,
                            trace_id=args.trace_id,
                            db_path=args.db_path,
                            event_log_dir=args.event_log_dir,
                            workspace_root=args.workspace_root,
                            provenance_root=args.provenance_root,
                        )
                    case "start":
                        cmd_flywheel_start(
                            workload_id=args.workload_id,
                            client_id=args.client_id,
                            eval_size=args.eval_size,
                            val_ratio=args.val_ratio,
                            min_total_records=args.min_total_records,
                            limit=args.limit,
                            run_id=args.run_id,
                            trace_id=args.trace_id,
                            db_path=args.db_path,
                            event_log_dir=args.event_log_dir,
                            export_root=args.export_root,
                        )
                    case "get":
                        cmd_flywheel_get(args.job_id)
                    case "cancel":
                        cmd_flywheel_cancel(args.job_id)
                    case "delete":
                        cmd_flywheel_delete(args.job_id)
                    case "watch":
                        cmd_flywheel_watch(args.job_id, args.poll_sec, args.timeout_sec)
                    case _:
                        parser.parse_args(["flywheel", "--help"])
            except Exception as e:
                print(f"Flywheel command failed: {e}")
                raise SystemExit(2)
        case "reciprocity":
            try:
                match args.reciprocity_cmd:
                    case "health":
                        cmd_reciprocity_health()
                    case "summary":
                        cmd_reciprocity_summary()
                    case "publish":
                        cmd_reciprocity_publish(
                            record_type=args.publish_type,
                            json_payload=args.publish_json,
                            file_path=args.publish_file,
                        )
                    case "record":
                        cmd_reciprocity_record(
                            run_id=args.run_id,
                            session_id=args.session_id,
                            task_id=args.task_id,
                            trace_id=args.trace_id,
                            summary_type=args.summary_type,
                            json_payload=args.record_json,
                            file_path=args.record_file,
                            db_path=args.db_path,
                            event_log_dir=args.event_log_dir,
                            workspace_root=args.workspace_root,
                            provenance_root=args.provenance_root,
                        )
                    case _:
                        parser.parse_args(["reciprocity", "--help"])
            except Exception as e:
                print(f"Reciprocity command failed: {e}")
                raise SystemExit(2)
        case "ouroboros":
            try:
                match args.ouroboros_cmd:
                    case "connections":
                        cmd_ouroboros_connections(
                            package_dir=args.package_dir,
                            threshold=args.threshold,
                            disagreement_threshold=args.disagreement_threshold,
                            min_text_length=args.min_text_length,
                            limit=args.limit,
                            as_json=args.as_json,
                        )
                    case "record":
                        cmd_ouroboros_record(
                            run_id=args.run_id,
                            session_id=args.session_id,
                            task_id=args.task_id,
                            trace_id=args.trace_id,
                            log_path=args.log_path,
                            cycle_id=args.cycle_id,
                            json_payload=args.observation_json,
                            file_path=args.observation_file,
                            db_path=args.db_path,
                            event_log_dir=args.event_log_dir,
                            workspace_root=args.workspace_root,
                            provenance_root=args.provenance_root,
                        )
                    case _:
                        parser.parse_args(["ouroboros", "--help"])
            except Exception as e:
                print(f"Ouroboros command failed: {e}")
                raise SystemExit(2)
        case "dharma":
            match args.dharma_cmd:
                case "status":
                    cmd_dharma_status()
                case "corpus":
                    cmd_dharma_corpus(args.corpus_status, args.corpus_category)
                case "review":
                    cmd_dharma_review(args.claim_id)
                case _:
                    parser.parse_args(["dharma", "--help"])
        case "stigmergy":
            cmd_stigmergy(args.stig_file)
        case "hum":
            cmd_hum()
        case "skills":
            cmd_skills()
        case "route":
            cmd_route(" ".join(args.task_desc))
        case "orchestrate":
            cmd_orchestrate(" ".join(args.orch_desc))
        case "autonomy":
            cmd_autonomy(" ".join(args.auto_action))
        case "context-search":
            cmd_context_search(" ".join(args.cs_query))
        case "compose":
            cmd_compose(" ".join(args.comp_desc))
        case "execute-compose":
            cmd_execute_compose(" ".join(args.exec_comp_desc))
        case "handoff":
            cmd_handoff(args.ho_from, args.ho_to, args.ho_context,
                        " ".join(args.content))
        case "agent-memory":
            cmd_agent_memory(args.mem_agent)
        case "sprint":
            cmd_sprint(
                output=args.output,
                local=args.local,
                test_summary=args.test_summary,
                prev_todo=args.prev_todo,
                llm_timeout_sec=args.llm_timeout_sec,
            )
        case "ledger":
            cmd_ledger(
                ledger_cmd=args.ledger_cmd,
                n=getattr(args, "n", 20),
                session=getattr(args, "session", None),
                kind=getattr(args, "kind", "all"),
                query=" ".join(getattr(args, "query", []) or []),
                db_path=getattr(args, "db_path", None),
                sync_ledgers=not getattr(args, "no_sync_ledgers", False),
                limit_sessions=getattr(args, "limit_sessions", None),
            )
        case "semantic":
            try:
                match args.semantic_cmd:
                    case "digest":
                        cmd_semantic_digest(
                            root=args.root,
                            output=args.output,
                            include_tests=args.include_tests,
                            max_files=args.max_files,
                        )
                    case "research":
                        cmd_semantic_research(graph_path=args.graph)
                    case "synthesize":
                        cmd_semantic_synthesize(
                            graph_path=args.graph,
                            max_clusters=args.max_clusters,
                        )
                    case "harden":
                        cmd_semantic_harden(
                            graph_path=args.graph,
                            root=args.root,
                        )
                    case "brief":
                        cmd_semantic_brief(
                            graph_path=args.graph,
                            root=args.root,
                            max_briefs=args.max_briefs,
                            json_output=args.json_output,
                            markdown_output=args.markdown_output,
                            state_dir=args.state_dir,
                            campaign_path=args.campaign_path,
                        )
                    case "status":
                        cmd_semantic_status(graph_path=args.graph)
                    case "proof":
                        cmd_semantic_proof(root=args.root)
                    case _:
                        parser.parse_args(["semantic", "--help"])
            except Exception as e:
                print(f"Semantic command failed: {e}")
                raise SystemExit(2)
        case "bootstrap":
            cmd_bootstrap()
        case "field":
            try:
                match args.field_cmd:
                    case "scan":
                        cmd_field_scan()
                    case "gaps":
                        cmd_field_gaps()
                    case "position":
                        cmd_field_position()
                    case "unique":
                        cmd_field_unique()
                    case "summary":
                        cmd_field_summary()
                    case _:
                        parser.parse_args(["field", "--help"])
            except Exception as e:
                print(f"Field command failed: {e}")
                raise SystemExit(2)
        case "xray":
            cmd_xray(
                repo_path=args.repo_path,
                output=args.output,
                as_json=args.as_json,
            )
        case "review":
            cmd_review(
                hours=args.hours,
                skip_tests=args.skip_tests,
            )
        case "initiatives":
            cmd_initiatives(
                init_cmd=args.init_cmd,
                title=getattr(args, "title", ""),
                description=getattr(args, "description", ""),
                initiative_id=getattr(args, "initiative_id", ""),
                reason=getattr(args, "reason", ""),
            )
        case "cron":
            cmd_cron(
                cron_cmd=args.cron_cmd,
                prompt=getattr(args, "prompt", ""),
                schedule=getattr(args, "schedule", ""),
                name=getattr(args, "name", None),
                repeat=getattr(args, "repeat", None),
                deliver=getattr(args, "deliver", "local"),
                urgent=getattr(args, "urgent", False),
                job_id=getattr(args, "job_id", ""),
            )
        case "gateway":
            cmd_gateway(config_path=args.config)
        case _:
            parser.print_help()


if __name__ == "__main__":
    main()
