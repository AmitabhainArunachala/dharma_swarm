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
  dgc up [--background]         Start the daemon
  dgc down                      Stop the daemon
  dgc daemon-status             Show daemon state
  dgc pulse                     Run one heartbeat pulse
  dgc swarm [plan]              Run orchestrator (build/research/deploy/maintenance)
  dgc swarm --status            Show orchestrator state
  dgc swarm live [N]            Persistent tmux swarm (N agents)
  dgc swarm overnight start [H] [--aggressive]
  dgc swarm overnight stop|status|report
  dgc swarm yolo                Aggressive overnight (10h)
  dgc context [domain]          Load context (research/content/ops/all)
  dgc memory                    Show memory status
  dgc witness "msg"             Record a witness observation
  dgc develop "what" "evidence" Record a development marker
  dgc gates "action"            Run telos gates on an action
  dgc health                    Ecosystem file health
  dgc health-check              Monitor-based system health (v0.2.0)
  dgc spawn --name X --role Y   Spawn a new agent
  dgc task create "title"       Create a task
  dgc task list [--status S]    List tasks
  dgc evolve propose COMP DESC  Run evolution pipeline
  dgc evolve trend [--component C]
  dgc run [--interval N]        Run orchestration loop
  dgc setup                     Install dependencies
  dgc migrate                   Migrate old DGC memory
  dgc agni "cmd"                Run command on AGNI VPS via SSH
"""

from __future__ import annotations

import argparse
import asyncio
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro: Any) -> Any:
    """Run an async coroutine synchronously."""
    return asyncio.run(coro)


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
        count = sum(1 for _ in open(gate_log))
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
    """Show memory status and recent entries."""
    async def _show():
        from dharma_swarm.memory import StrangeLoopMemory

        mem = StrangeLoopMemory(db_path=DHARMA_STATE / "db" / "memory.db")
        await mem.init_db()
        entries = await mem.recall(limit=10)
        await mem.close()
        if not entries:
            print("Memory: empty")
            return
        print(f"=== Strange Loop Memory ({len(entries)} recent) ===\n")
        for e in entries:
            ts = e.timestamp.isoformat()[:19] if hasattr(e.timestamp, "isoformat") else str(e.timestamp)[:19]
            print(f"  [{e.layer.value:>11}] {ts}  {e.content[:100]}")

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


def cmd_pulse() -> None:
    """Run one heartbeat pulse."""
    from dharma_swarm.pulse import pulse

    response = pulse()
    print(response)


def cmd_up(background: bool = False) -> None:
    """Start the daemon."""
    daemon_script = DGC_CORE / "daemon" / "dgc_daemon.py"
    args = ["python3", str(daemon_script)]
    if background:
        args.append("--background")
    os.execvp("python3", args)


def cmd_down() -> None:
    """Stop the daemon."""
    pid_file = DGC_CORE / "daemon" / "dgc.pid"
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
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
    state_file = DGC_CORE / "daemon" / "state.json"
    if state_file.exists():
        state = json.loads(state_file.read_text())
        for k, v in state.items():
            print(f"  {k}: {v}")
    else:
        print("Daemon: not running")


def cmd_agni(command: str) -> None:
    """Run command on AGNI VPS."""
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
    run_file = DHARMA_STATE / "overnight_run_dir.txt"
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

    # --- Dispatch subcommands ---

    if extra_args and extra_args[0] == "yolo":
        _overnight(["start", "10", "--aggressive"])
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
    parts: list[str] = []

    try:
        thread_file = DHARMA_STATE / "thread_state.json"
        if thread_file.exists():
            ts = json.loads(thread_file.read_text())
            parts.append(f"Active thread: {ts.get('current_thread', 'unknown')}")
    except Exception:
        pass

    try:
        from dharma_swarm.context import read_memory_context

        mem = read_memory_context()
        if mem and "No memory" not in mem:
            parts.append("Recent memory:")
            parts.append(mem)
    except Exception:
        pass

    try:
        manifest = HOME / ".dharma_manifest.json"
        if manifest.exists():
            data = json.loads(manifest.read_text())
            eco = data.get("ecosystem", {})
            alive = sum(1 for v in eco.values() if v.get("exists"))
            parts.append(f"Ecosystem: {alive}/{len(eco)} alive")
    except Exception:
        pass

    snapshot = "\n".join(parts).strip()
    if not snapshot:
        return ""
    return snapshot[:6000]


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

    # -- swarm (captures all remaining args) --
    p_swarm = sub.add_parser("swarm", help="Swarm orchestrator + overnight/live")
    p_swarm.add_argument("swarm_args", nargs="*", default=[])

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

    # -- setup --
    sub.add_parser("setup", help="Install dependencies")

    # -- migrate --
    sub.add_parser("migrate", help="Migrate old DGC memory")

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
        case "up":
            cmd_up(background=args.background)
        case "down":
            cmd_down()
        case "daemon-status":
            cmd_daemon_status()
        case "pulse":
            cmd_pulse()
        case "swarm":
            cmd_swarm(args.swarm_args)
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
        case "setup":
            cmd_setup()
        case "migrate":
            cmd_migrate()
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
                case _:
                    parser.parse_args(["evolve", "--help"])
        case "run":
            cmd_run(interval=args.interval)
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
        case _:
            parser.print_help()


if __name__ == "__main__":
    main()
