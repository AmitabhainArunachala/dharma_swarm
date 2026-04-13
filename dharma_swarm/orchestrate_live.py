"""Live Orchestrator — runs all DGC systems concurrently.

Boots SwarmManager + concurrent pulse heartbeat + evolution cycles + health
monitoring in a single asyncio event loop. Uses `claude -p` (authenticated)
as the execution engine — no API keys required.

Usage:
    dgc orchestrate                     # interactive (60s tick)
    dgc orchestrate --background        # background daemon
    python3 -m dharma_swarm.orchestrate_live  # direct

Systems run concurrently:
    1. Swarm loop — agent pool, task dispatch, coordination synthesis
    2. Pulse loop — claude -p heartbeat with thread rotation + telos gates
    3. Evolution loop — periodic Darwin Engine cycles
    4. Living layers — stigmergy decay, shakti perception, subconscious dreams
    5. Health monitor — anomaly detection, auto-healing
    6. Zeitgeist (S4) — environmental scanning, gate pressure feedback
    7. Witness (S3*) — sporadic random audit of agent behavior
    8. Training flywheel — trajectory scoring, strategy reinforcement, dataset building
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from dharma_swarm.config import DEFAULT_CONFIG
from dharma_swarm.pending_proposals import append_pending_proposals
from dharma_swarm.runtime_artifacts import (
    freshest_pulse_log_path,
    write_dgc_health_snapshot,
)

HOME = Path.home()
STATE_DIR = HOME / ".dharma"
LOG_DIR = STATE_DIR / "logs"

# Orchestrator defaults — sourced from central config (env overrides baked in)
_ll = DEFAULT_CONFIG.live_loop
SWARM_TICK = _ll.swarm_tick_seconds
PULSE_INTERVAL = _ll.pulse_interval_seconds
EVOLUTION_INTERVAL = _ll.evolution_interval_seconds
HEALTH_INTERVAL = _ll.health_interval_seconds
LIVING_INTERVAL = _ll.living_interval_seconds
MAX_DAILY = _ll.max_daily_tasks
_RUNTIME_HEALTH_STATE: dict[str, int] = {
    "agent_count": 0,
    "task_count": 0,
}


def _update_runtime_health_state(*, agent_count: int | None = None, task_count: int | None = None) -> None:
    if agent_count is not None:
        _RUNTIME_HEALTH_STATE["agent_count"] = max(0, int(agent_count))
    if task_count is not None:
        _RUNTIME_HEALTH_STATE["task_count"] = max(0, int(task_count))


def _log(system: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] [{system}] {msg}"
    print(line, flush=True)
    logger.info("[%s] %s", system, msg)


def _enqueue_shakti_escalations(
    perceptions: list[Any],
    *,
    proposals_path: Path | None = None,
) -> int:
    """Durably hand Shakti escalations to Darwin through the shared queue."""
    payloads: list[dict[str, Any]] = []
    for perception in perceptions:
        impact_level = str(getattr(perception, "impact_level", "") or "").strip().lower()
        if impact_level not in {"module", "system"}:
            continue
        connection = str(getattr(perception, "connection", "") or "system").strip() or "system"
        observation = str(
            getattr(perception, "proposal", "") or getattr(perception, "observation", "") or ""
        ).strip()
        energy = getattr(getattr(perception, "energy", None), "value", None) or str(
            getattr(perception, "energy", "unknown")
        )
        salience = float(getattr(perception, "salience", 0.0) or 0.0)
        payloads.append(
            {
                "component": connection,
                "change_type": "shakti_escalation",
                "description": f"[shakti:{energy}] {observation}",
                "diff": "",
                "spec_ref": "shakti_loop",
                "metadata": {
                    "source": "living_layers",
                    "impact_level": impact_level,
                    "salience": salience,
                    "energy": str(energy),
                },
            }
        )
    return append_pending_proposals(payloads, path=proposals_path)


async def _wait_or_shutdown(shutdown_event: asyncio.Event, delay: float) -> bool:
    """Sleep for a backoff window unless shutdown is requested first."""
    if delay <= 0:
        return shutdown_event.is_set()
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=delay)
        return True
    except asyncio.TimeoutError:
        return shutdown_event.is_set()


async def run_swarm_loop(
    shutdown_event: asyncio.Event,
    signal_bus: "Any | None" = None,
    supervisor: "Any | None" = None,
) -> None:
    """Primary loop: SwarmManager.tick() -- the ONE control path.

    Strange Loop Phase 0: unified tick. No more split brain.
    """
    from dharma_swarm.daemon_config import DaemonConfig
    from dharma_swarm.swarm import SwarmManager

    _log("swarm", f"Initializing (tick={SWARM_TICK}s, max_daily={MAX_DAILY})...")

    cfg = DaemonConfig()
    cfg.heartbeat_interval = float(SWARM_TICK)
    cfg.max_daily_contributions = MAX_DAILY

    swarm = SwarmManager(state_dir=str(STATE_DIR), daemon_config=cfg)
    await swarm.init()
    try:
        from dharma_swarm.startup_crew import spawn_cybernetics_crew

        cyber_crew = await spawn_cybernetics_crew(swarm)
        if cyber_crew:
            _log("swarm", f"Cybernetics crew asserted: {len(cyber_crew)} seats")
    except Exception as exc:
        _log("swarm", f"Cybernetics crew assertion failed: {exc}")

    # MessageBus for instinct signal consumption
    from dharma_swarm.message_bus import MessageBus as _MBus
    _instinct_bus = _MBus(STATE_DIR / "db" / "messages.db")
    await _instinct_bus.init_db()

    agents = await swarm.list_agents()
    swarm_state = await swarm.status()
    _update_runtime_health_state(
        agent_count=len(swarm_state.agents),
        task_count=(
            swarm_state.tasks_pending
            + swarm_state.tasks_running
            + swarm_state.tasks_completed
            + swarm_state.tasks_failed
        ),
    )
    _log("swarm", f"Ready: {len(agents)} agents, thread={swarm.current_thread}")

    # Auto-seed missions from ThinkodynamicDirector if task board is empty.
    # The director derives missions from TelosGraph + recognition_seed + ecosystem.
    # This replaces static SEED_TASKS with telos-derived, philosophically grounded work.
    try:
        _board = swarm._orchestrator._board
        _board_stats = await _board.stats()
        _pending = _board_stats.get("pending", 0) + _board_stats.get("running", 0)
        if _pending == 0:
            from dharma_swarm.mission_contract import load_latest_mission
            from pathlib import Path
            _handoff = STATE_DIR / "shared" / "thinkodynamic_director_handoff.md"
            _contract_path = STATE_DIR / "logs" / "thinkodynamic_director" / "latest.json"
            if _contract_path.exists():
                try:
                    mission = load_latest_mission(_contract_path)
                    if mission and hasattr(mission, 'task_titles') and mission.task_titles:
                        _log("swarm", f"Seeding {len(mission.task_titles)} tasks from director: '{mission.mission_title}'")
                        for title in mission.task_titles[:10]:  # cap at 10 per mission
                            await _board.create(
                                title=title,
                                description=(
                                    f"Mission: {mission.mission_title}.\n"
                                    f"Use web_search, fetch_url, read_file, and write_file "
                                    f"to complete this task. Write results to "
                                    f"~/.dharma/shared/ with a descriptive filename."
                                ),
                                priority="high",
                            )
                except Exception as e:
                    _log("swarm", f"Director mission seeding failed (non-fatal): {e}")
            else:
                _log("swarm", "No director mission found — using default SEED_TASKS")
    except Exception as e:
        _log("swarm", f"Mission auto-seed check failed (non-fatal): {e}")

    try:
        while not shutdown_event.is_set():
            try:
                # Drain signal bus before tick -- respond to inter-loop signals
                if signal_bus is not None:
                    anomaly_signals = signal_bus.drain(["ANOMALY_DETECTED"])
                    if anomaly_signals:
                        _log("swarm", f"Signal bus: {len(anomaly_signals)} anomaly signal(s)")

                # Drain skill bridge inbox — route Claude Code skill outputs to swarm
                try:
                    from dharma_swarm.skill_bridge import SkillBridge
                    _bridge = SkillBridge()
                    _bridge_entries = _bridge.drain_inbox()
                    if _bridge_entries:
                        _bridge_counts = _bridge.process_entries(_bridge_entries)
                        _log("swarm", f"Skill bridge: processed {sum(_bridge_counts.values())} entries ({_bridge_counts})")
                except Exception:
                    pass  # Skill bridge is best-effort

                # Drain instinct signals — negative patterns inform task quality
                try:
                    from dharma_swarm.signal_bus import SIGNAL_ECC_INSTINCT
                    instinct_events = await _instinct_bus.consume_events(
                        SIGNAL_ECC_INSTINCT, limit=10,
                    )
                    negatives = [
                        e for e in instinct_events
                        if e.get("payload", {}).get("signal") == "negative"
                    ]
                    if negatives:
                        _log("swarm", f"Instinct: {len(negatives)} negative pattern(s) detected")
                        for neg in negatives[:3]:
                            p = neg.get("payload", {})
                            _log("swarm", f"  ↳ {p.get('pattern_type', '?')}: {p.get('detail', '')[:60]}")
                except Exception:
                    logger.debug("Swarm: instinct drain failed", exc_info=True)

                activity = await swarm.tick()

                # Liveness watchdog: record healthy tick + check all loops
                if supervisor is not None:
                    supervisor.record_tick("swarm")
                    alerts = supervisor.tick()
                    for alert in alerts:
                        _log("watchdog", f"{alert.severity.upper()} [{alert.loop_name}]: "
                             f"{alert.message} → {alert.intervention}")

                swarm_state = await swarm.status()
                _update_runtime_health_state(
                    agent_count=len(swarm_state.agents),
                    task_count=(
                        swarm_state.tasks_pending
                        + swarm_state.tasks_running
                        + swarm_state.tasks_completed
                        + swarm_state.tasks_failed
                    ),
                )

                if activity.get("paused"):
                    _log("swarm", "Paused (.PAUSE file)")
                    await asyncio.sleep(30)
                    continue
                if activity.get("circuit_broken"):
                    _log("swarm", "Circuit breaker tripped, waiting...")
                    await asyncio.sleep(60)
                    continue

                dispatched = activity.get("dispatched", 0)
                settled = activity.get("settled", 0)
                rescued = activity.get("rescued", 0)
                if dispatched or settled or rescued:
                    _log("swarm", f"tick: dispatched={dispatched} settled={settled} rescued={rescued}")

                cfg.circuit_breaker.record_success()

            except Exception as e:
                _log("swarm", f"tick error: {e}")
                cfg.circuit_breaker.record_failure()

            await asyncio.sleep(SWARM_TICK)
    finally:
        await swarm.shutdown()
        _log("swarm", "Shutdown complete")


async def run_pulse_loop(shutdown_event: asyncio.Event) -> None:
    """Pulse heartbeat — runs claude -p with thread rotation.

    Skips if running inside a Claude Code session (nested sessions not allowed).
    """
    if os.environ.get("CLAUDECODE"):
        _log("pulse", "Skipping — running inside Claude Code session (nested not allowed)")
        return

    from dharma_swarm.pulse import pulse
    from dharma_swarm.daemon_config import DaemonConfig

    _log("pulse", f"Starting (interval={PULSE_INTERVAL}s)")

    cfg = DaemonConfig()
    cfg.heartbeat_interval = float(PULSE_INTERVAL)
    cfg.max_daily_contributions = MAX_DAILY
    daily_count = 0

    while not shutdown_event.is_set():
        if daily_count >= MAX_DAILY:
            _log("pulse", f"Daily limit ({MAX_DAILY}) reached")
            await asyncio.sleep(3600)
            continue

        try:
            _log("pulse", f"Pulsing... (#{daily_count + 1})")
            # Run pulse in thread to not block event loop (it calls subprocess)
            result = await asyncio.to_thread(pulse, cfg)
            short = result[:120].replace("\n", " ")
            _log("pulse", f"Result: {short}")

            if not result.startswith(("PAUSED", "QUIET", "CIRCUIT", "TELOS")):
                daily_count += 1
        except Exception as e:
            _log("pulse", f"Error: {e}")

        await asyncio.sleep(PULSE_INTERVAL)


async def run_evolution_loop(shutdown_event: asyncio.Event) -> None:
    """Periodic evolution cycles — propose, gate, evaluate, archive."""
    from dharma_swarm.evolution import DarwinEngine, CycleResult
    from dharma_swarm.meta_evolution import MetaEvolutionEngine

    _log("evolution", f"Starting (interval={EVOLUTION_INTERVAL}s)")
    await asyncio.sleep(30)  # Let swarm init first

    evo_dir = STATE_DIR / "evolution"
    traces_dir = STATE_DIR / "traces"

    engine = DarwinEngine(
        archive_path=evo_dir / "archive.jsonl",
        traces_path=traces_dir,
        predictor_path=evo_dir / "predictor_data.jsonl",
    )
    await engine.init()

    # Meta-evolution: adapts hyperparameters when object-level fitness stalls
    meta_engine = MetaEvolutionEngine(
        engine,
        meta_archive_path=evo_dir / "meta_archive.jsonl",
        n_object_cycles_per_meta=2,
        auto_apply=True,
    )

    # Connect to MessageBus for durable fitness event consumption
    from dharma_swarm.message_bus import MessageBus as _MBus
    db_dir = STATE_DIR / "db"
    _bus = _MBus(db_dir / "messages.db")
    await _bus.init_db()

    # Subscribe to orchestrator.lifecycle — track task throughput for fitness context
    try:
        await _bus.subscribe("evolution_loop", "orchestrator.lifecycle")
    except Exception:
        logger.debug("Evolution: lifecycle subscription failed", exc_info=True)

    # Source files for evolution proposals — core modules only
    _src_root = Path(__file__).resolve().parent
    _EVOLUTION_TARGETS = [
        "swarm.py", "orchestrator.py", "agent_runner.py", "providers.py",
        "evolution.py", "dharma_kernel.py", "telos_gates.py",
        "thinkodynamic_director.py",
    ]
    cycle_count = 0

    while not shutdown_event.is_set():
        try:
            count = len(engine.archive._entries) if engine.archive else 0
            _log("evolution", f"Archive: {count} entries")

            # Consume durable fitness events from MessageBus
            fitness_events = []
            try:
                fitness_events = await _bus.consume_events("AGENT_FITNESS", limit=50)
                if fitness_events:
                    _log("evolution", f"Consumed {len(fitness_events)} fitness events from bus")
            except Exception as exc:
                _log("evolution", f"Bus consume error: {exc}")

            # Drain lifecycle events — task completion throughput for fitness context
            completions = 0
            try:
                lifecycle_events = await _bus.consume_events(
                    "AGENT_LIFECYCLE_COMPLETED", limit=20,
                )
                completions = len(lifecycle_events)
                if completions:
                    _log("evolution", f"Lifecycle: {completions} task completion(s) since last cycle")
            except Exception:
                logger.debug("Evolution: lifecycle drain failed", exc_info=True)

            # Check fitness trend
            avg_fitness = 0.0
            try:
                trend = await engine.get_fitness_trend(limit=5)
                if trend:
                    avg_fitness = sum(f for _, f in trend) / len(trend)
                    _log("evolution", f"Fitness trend (last {len(trend)}): avg={avg_fitness:.3f}")
            except Exception:
                logger.debug("Fitness trend read failed", exc_info=True)

            # ── ACTIVE EVOLUTION: run cycle + meta-adaptation ──
            cycle_count += 1

            # Extract live fitness from AGENT_FITNESS event payloads and persist
            live_fitness_scores: list[float] = []
            for ev in fitness_events:
                payload = ev.get("payload") if isinstance(ev, dict) else {}
                if isinstance(payload, dict):
                    # agent_runner emits swabhaav_ratio as the primary score
                    score = (
                        payload.get("swabhaav_ratio")
                        or payload.get("fitness_score")
                        or payload.get("composite")
                    )
                    if isinstance(score, (int, float)) and score > 0:
                        live_fitness_scores.append(float(score))
                        # Persist to archive so get_fitness_trend() works
                        try:
                            await engine.record_fitness_observation(
                                agent_name=payload.get("agent", "unknown"),
                                fitness_score=float(score),
                                task_id=payload.get("task_id"),
                            )
                        except Exception:
                            logger.debug("Fitness archival failed", exc_info=True)
            if live_fitness_scores:
                _log("evolution", f"Live fitness from {len(live_fitness_scores)} agents: "
                     f"avg={sum(live_fitness_scores)/len(live_fitness_scores):.3f} "
                     f"max={max(live_fitness_scores):.3f}")

            # Feed meta-evolution with observed fitness
            # Prefer live agent fitness; fall back to historical archive average
            if avg_fitness > 0 or fitness_events:
                if live_fitness_scores:
                    best_fitness = max(live_fitness_scores)
                else:
                    best_fitness = avg_fitness if avg_fitness > 0 else 0.0
                synthetic_result = CycleResult(
                    cycle_id=f"orch-evo-{cycle_count}",
                    best_fitness=best_fitness,
                    proposals_submitted=len(fitness_events),
                )
                meta_result = meta_engine.observe_cycle_result(synthetic_result)
                if meta_result is not None:
                    if meta_result.evolved_parameters:
                        _log(
                            "evolution",
                            f"Meta-evolution adapted parameters "
                            f"(meta_fitness={meta_result.meta_fitness:.3f}, "
                            f"applied={meta_result.applied_parameters})",
                        )
                    else:
                        _log(
                            "evolution",
                            f"Meta-evolution: no adaptation needed "
                            f"(meta_fitness={meta_result.meta_fitness:.3f})",
                        )

            # Drain active inference prediction errors — bias evolution toward high-error areas
            try:
                from dharma_swarm.signal_bus import SignalBus as _EvSB
                _ev_bus = _EvSB.get()
                pe_signals = _ev_bus.drain(["ACTIVE_INFERENCE_PREDICTION_ERROR"])
                if pe_signals:
                    high_error = sorted(pe_signals, key=lambda s: abs(s.get("error", 0)), reverse=True)[:3]
                    error_summary = ", ".join(f"{s.get('agent', '?')}:{s.get('error', 0):.3f}" for s in high_error)
                    _log("evolution", f"Prediction errors from {len(pe_signals)} observations: {error_summary}")
            except Exception:
                pass

            # Read health anomalies from file (written by health loop, avoids signal bus contention)
            try:
                import json as _ej
                _anomaly_file = STATE_DIR / "health" / "latest_anomalies.json"
                if _anomaly_file.exists():
                    _anomaly_data = _ej.loads(_anomaly_file.read_text())
                    if _anomaly_data:
                        _anomaly_types = [a.get("type", "?") for a in _anomaly_data]
                        _log("evolution", f"Health context: {', '.join(_anomaly_types)}")
            except Exception:
                pass

            # --- EVAL VERDICT GATE: check overnight verdict before evolving ---
            _evo_allowed = True
            try:
                import json as _vj
                _verdict_dir = STATE_DIR / "overnight" / datetime.now(timezone.utc).strftime("%Y-%m-%d")
                _verdict_file = _verdict_dir / "verdict.json"
                if _verdict_file.exists():
                    _vdata = _vj.loads(_verdict_file.read_text())
                    _v = _vdata.get("verdict", "")
                    if _v == "rollback":
                        _evo_allowed = False
                        _log("evolution", "PAUSED: overnight ROLLBACK verdict — skipping auto_evolve")
                    elif _v == "hold":
                        # On HOLD, only allow shadow mode
                        _log("evolution", "CONSTRAINED: overnight HOLD verdict — forcing shadow mode")
            except Exception:
                pass

            # Auto-evolve: propose improvements via LLM every 3rd cycle
            # Shadow mode controlled by env var (default: ON for safety)
            # Set DHARMA_EVOLUTION_SHADOW=0 + DGC_AUTONOMY_LEVEL>=2 for real mutation
            if cycle_count % 3 == 0 and _evo_allowed:
                try:
                    from dharma_swarm.providers import OpenRouterProvider
                    import os as _evo_os
                    if _evo_os.environ.get("OPENROUTER_API_KEY"):
                        provider = OpenRouterProvider()
                        # Pick 2 random source files per cycle to limit LLM cost
                        import random as _evo_rng
                        targets = [
                            _src_root / f for f in _EVOLUTION_TARGETS
                            if (_src_root / f).exists()
                        ]
                        if targets:
                            selected = _evo_rng.sample(targets, min(2, len(targets)))

                            # Determine shadow mode: real mutation requires explicit opt-in
                            _shadow = _evo_os.environ.get("DHARMA_EVOLUTION_SHADOW", "1") != "0"
                            _autonomy = int(_evo_os.environ.get("DGC_AUTONOMY_LEVEL", "1"))
                            if not _shadow and _autonomy < 2:
                                _shadow = True  # Autonomy too low for real mutation
                                _log("evolution", "Shadow forced: DGC_AUTONOMY_LEVEL < 2")

                            # Eval verdict override: HOLD forces shadow mode
                            try:
                                if _verdict_file.exists():
                                    _vd2 = _vj.loads(_verdict_file.read_text())
                                    if _vd2.get("verdict") == "hold" and not _shadow:
                                        _shadow = True
                                        _log("evolution", "Shadow forced: overnight HOLD verdict")
                            except Exception:
                                pass

                            # Merge any pending proposals from consolidation/skill bridge
                            _pending = engine.load_pending_proposals()
                            if _pending:
                                _log("evolution", f"Loaded {len(_pending)} pending proposals from consolidation/bridge")

                            mode_label = "shadow" if _shadow else "LIVE"
                            _log("evolution", f"Auto-evolve ({mode_label}): {[s.name for s in selected]}")

                            # Create darwin branch for live mutation
                            if not _shadow:
                                _branch = f"darwin/cycle-{cycle_count}"
                                _br_proc = await asyncio.create_subprocess_exec(
                                    "git", "checkout", "-b", _branch,
                                    cwd=str(_src_root.parent),
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.PIPE,
                                )
                                await _br_proc.communicate()
                                _log("evolution", f"Created branch {_branch}")

                            result = await engine.auto_evolve(
                                provider=provider,
                                source_files=selected,
                                shadow=_shadow,
                                timeout=30.0,
                                context=f"Fitness avg={avg_fitness:.3f}, completions={completions}",
                            )
                            _log(
                                "evolution",
                                f"Auto-evolve result ({mode_label}): fitness={result.best_fitness:.3f}, "
                                f"submitted={result.proposals_submitted}, "
                                f"gated={result.proposals_gated}",
                            )

                            # For live mode: commit worthy proposals, then return to main branch
                            if not _shadow and result.proposals_archived > 0:
                                _committed = 0
                                _best_entries = await engine.archive.get_best(n=3)
                                for entry in _best_entries:
                                    # Build a Proposal from ArchiveEntry for commit_if_worthy
                                    from dharma_swarm.evolution import Proposal
                                    _p = Proposal(
                                        id=entry.id,
                                        component=entry.component,
                                        change_type=entry.change_type,
                                        description=entry.description,
                                        diff=entry.diff,
                                        actual_fitness=entry.fitness,
                                    )
                                    sha = await engine.commit_if_worthy(_p)
                                    if sha:
                                        _committed += 1
                                        _log("evolution", f"Committed {sha[:8]} for {entry.component}")
                                if _committed == 0:
                                    # No commits — delete the branch
                                    _del_proc = await asyncio.create_subprocess_exec(
                                        "git", "checkout", "-",
                                        cwd=str(_src_root.parent),
                                        stdout=asyncio.subprocess.PIPE,
                                        stderr=asyncio.subprocess.PIPE,
                                    )
                                    await _del_proc.communicate()
                                    await asyncio.create_subprocess_exec(
                                        "git", "branch", "-D", _branch,
                                        cwd=str(_src_root.parent),
                                        stdout=asyncio.subprocess.PIPE,
                                        stderr=asyncio.subprocess.PIPE,
                                    )
                                else:
                                    # Return to previous branch, keep darwin branch
                                    await asyncio.create_subprocess_exec(
                                        "git", "checkout", "-",
                                        cwd=str(_src_root.parent),
                                        stdout=asyncio.subprocess.PIPE,
                                        stderr=asyncio.subprocess.PIPE,
                                    )
                                _log("evolution", f"Live cycle: {_committed} commits on {_branch}")

                            # Feed result to meta-evolution
                            meta_engine.observe_cycle_result(result)
                    else:
                        _log("evolution", "Auto-evolve skipped: OPENROUTER_API_KEY not set")
                except Exception as exc:
                    _log("evolution", f"Auto-evolve error: {exc}")

            # Bus metrics for observability
            try:
                stats = await _bus.event_stats()
                if stats.get("queued", 0) > 0:
                    _log("evolution", f"Bus: {stats['queued']} queued, {stats['consumed']} consumed")
            except Exception:
                logger.debug("Bus event stats failed", exc_info=True)

        except Exception as e:
            _log("evolution", f"Error: {e}")

        await asyncio.sleep(EVOLUTION_INTERVAL)


async def run_health_loop(shutdown_event: asyncio.Event) -> None:
    """Health monitoring — detect anomalies, report status."""
    _log("health", f"Starting (interval={HEALTH_INTERVAL}s)")
    await asyncio.sleep(15)  # Let swarm init first

    # Hoist heavy objects out of the loop
    from dharma_swarm.monitor import SystemMonitor
    from dharma_swarm.traces import TraceStore

    traces_dir = STATE_DIR / "traces"
    store = TraceStore(base_path=traces_dir)
    await store.init()
    monitor = SystemMonitor(trace_store=store)

    # Import signal bus for WITNESS_AUDIT drain
    from dharma_swarm.signal_bus import SignalBus
    signal_bus = SignalBus.get()

    while not shutdown_event.is_set():
        try:
            # Drain WITNESS_AUDIT signals — close the S3* feedback loop
            witness_signals = signal_bus.drain(["WITNESS_AUDIT"])
            for ws in witness_signals:
                criticals = ws.get("severities", {}).get("critical", 0)
                warnings = ws.get("severities", {}).get("warning", 0)
                total = ws.get("total_findings", 0)
                if criticals:
                    _log("health", f"WITNESS: {criticals} critical finding(s) in audit cycle {ws.get('cycle', '?')}")
                elif warnings:
                    _log("health", f"WITNESS: {warnings} warning(s), {total} total in cycle {ws.get('cycle', '?')}")

            anomalies = await monitor.detect_anomalies()
            if anomalies:
                for a in anomalies[:3]:
                    _log("health", f"ANOMALY: {a.anomaly_type} severity={a.severity} — {a.description[:80]}")
                # Emit to signal bus so swarm loop can drain
                for a in anomalies[:5]:
                    signal_bus.emit({
                        "type": "ANOMALY_DETECTED",
                        "anomaly_type": a.anomaly_type,
                        "severity": a.severity,
                        "description": a.description[:200],
                    })
                # Write anomaly file for evolution loop (avoids signal bus contention)
                anomaly_dir = STATE_DIR / "health"
                anomaly_dir.mkdir(parents=True, exist_ok=True)
                import json as _hj
                summary = [{"type": a.anomaly_type, "severity": a.severity} for a in anomalies[:10]]
                (anomaly_dir / "latest_anomalies.json").write_text(_hj.dumps(summary))
            else:
                # Quick summary
                pid_file = STATE_DIR / "daemon.pid"
                pulse_log = freshest_pulse_log_path(STATE_DIR)
                status_parts = []
                if pid_file.exists():
                    try:
                        pid = int(pid_file.read_text().strip())
                        os.kill(pid, 0)
                        status_parts.append(f"daemon=PID:{pid}")
                    except (ValueError, OSError):
                        status_parts.append("daemon=dead")
                if pulse_log is not None and pulse_log.exists():
                    lines = pulse_log.read_text().split("--- PULSE @")
                    status_parts.append(f"pulses={len(lines)-1}")
                _log("health", f"OK ({', '.join(status_parts) or 'nominal'})")

            write_dgc_health_snapshot(
                STATE_DIR,
                daemon_pid=os.getpid(),
                agent_count=_RUNTIME_HEALTH_STATE.get("agent_count", 0),
                task_count=_RUNTIME_HEALTH_STATE.get("task_count", 0),
                anomaly_count=len(anomalies),
                source="orchestrate_live",
            )

        except Exception as e:
            _log("health", f"Error: {e}")

        await asyncio.sleep(HEALTH_INTERVAL)


async def run_living_layers(
    shutdown_event: asyncio.Event,
    stigmergy_store: "StigmergyStore | None" = None,
) -> None:
    """Living layers — stigmergy decay, shakti perception, subconscious dreams."""
    _log("living", f"Starting (interval={LIVING_INTERVAL}s)")
    await asyncio.sleep(45)  # Let other systems init first

    # Hoist heavy objects out of the loop
    from dharma_swarm.stigmergy import StigmergyStore
    from dharma_swarm.subconscious import SubconsciousStream
    from dharma_swarm.shakti import ShaktiLoop

    store = stigmergy_store or StigmergyStore()
    stream = SubconsciousStream(stigmergy=store)
    loop = ShaktiLoop(stigmergy=store)

    while not shutdown_event.is_set():
        try:
            density = store.density()
            summary = [f"density={density}"]

            # Stigmergy decay (evaporate old marks)
            if density > 100:
                decayed = await store.decay(max_age_hours=168)
                if decayed:
                    summary.append(f"decayed={decayed}")

            # Sync stigmergy marks → catalytic graph edges
            try:
                from dharma_swarm.catalytic_graph import CatalyticGraph
                cg = CatalyticGraph()
                cg.load()
                pre_edges = len(cg._edges)
                recent = await store.read_marks(limit=50)
                agent_topics: dict[str, set[str]] = {}
                for mark in recent:
                    agent = mark.agent or "unknown"
                    topic = (mark.observation or mark.action or "")[:40]
                    if agent and topic:
                        agent_topics.setdefault(agent, set()).add(topic)
                        cg.add_node(f"agent:{agent}", type="agent")
                        cg.add_node(f"obs:{topic}", type="observation")
                # Connect agents that share topics (mutual catalysis)
                agents = list(agent_topics.keys())
                for i, a1 in enumerate(agents):
                    for a2 in agents[i+1:]:
                        shared = agent_topics[a1] & agent_topics[a2]
                        if shared:
                            cg.add_edge(f"agent:{a1}", f"agent:{a2}", "validates",
                                        strength=min(1.0, len(shared) * 0.2),
                                        evidence=f"Shared topics: {len(shared)}")
                            cg.add_edge(f"agent:{a2}", f"agent:{a1}", "validates",
                                        strength=min(1.0, len(shared) * 0.2),
                                        evidence=f"Shared topics: {len(shared)}")
                new_edges = len(cg._edges) - pre_edges
                if new_edges > 0:
                    cg.save()
                    summary.append(f"graph_edges=+{new_edges}")
            except Exception as e:
                logger.debug("Stigmergy→graph sync failed: %s", e)

            # Subconscious dreams (trigger on density threshold)
            if await stream.should_wake():
                associations = await stream.dream()
                summary.append(f"dreams={len(associations)}")

            # Shakti perception
            perceptions = await loop.perceive(
                current_context="orchestrator living-layer tick",
                agent_role="orchestrator",
            )
            if perceptions:
                summary.append(f"perceptions={len(perceptions)}")
                high = [p for p in perceptions if p.salience >= 0.7]
                if high:
                    summary.append(f"high_salience={len(high)}")

                    # Route high-salience escalations to Darwin Engine
                    try:
                        queued = _enqueue_shakti_escalations(high)
                        if queued:
                            summary.append(f"darwin_proposals={queued}")
                    except Exception as e:
                        logger.debug("Shakti→Darwin routing failed: %s", e, exc_info=True)

            _log("living", " ".join(summary))

        except Exception as e:
            _log("living", f"Error: {e}")

        await asyncio.sleep(LIVING_INTERVAL)


def _stop_old_daemon() -> None:
    """Stop existing daemon if running, to avoid DB conflicts."""
    pid_file = STATE_DIR / "daemon.pid"
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # Check alive
        _log("orchestrator", f"Stopping old daemon (PID {pid})...")
        os.kill(pid, signal.SIGTERM)
        # Wait up to 5 seconds for clean exit
        for _ in range(10):
            try:
                os.kill(pid, 0)
                import time
                time.sleep(0.5)
            except OSError:
                break
        _log("orchestrator", "Old daemon stopped")
    except (ValueError, OSError):
        pass
    pid_file.unlink(missing_ok=True)


def _reap_stale_pid_files() -> None:
    """Remove PID files that point to dead processes."""
    for pid_file in STATE_DIR.glob("*.pid"):
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Still alive — leave it
        except (ValueError, OSError):
            _log("orchestrator", f"Reaped stale PID file: {pid_file.name}")
            pid_file.unlink(missing_ok=True)


CONSOLIDATION_INTERVAL = _ll.consolidation_interval_seconds

WITNESS_INTERVAL = 3600  # 60 minutes between S3* sporadic audits

ZEITGEIST_INTERVAL = 600  # 10 minutes between S4 environmental scans

REPLICATION_INTERVAL = 3600  # 1 hour between replication checks

RECOGNITION_INTERVAL = 7200  # 2 hours between recognition synthesis


async def _run_recognition_loop(shutdown_event: asyncio.Event) -> None:
    """Periodic recognition synthesis — the strange loop's self-model.

    Every 2 hours, synthesizes signals from all subsystems into a recognition
    seed that feeds back into agent context via L9 META layer.

    On first run: generates an immediate seed so agents have self-model context
    from the very first task, not after 2 hours of blind operation.
    """
    import time  # required for _seed_stale calculation below
    from dharma_swarm.meta_daemon import RecognitionEngine
    engine = RecognitionEngine()

    # First-run: generate seed immediately if it doesn't exist or is stale (>12h)
    _seed_path = STATE_DIR / "meta" / "recognition_seed.md"
    _seed_stale = (
        not _seed_path.exists() or
        (time.time() - _seed_path.stat().st_mtime) > 43200  # 12 hours
    )
    if _seed_stale:
        _log("recognition", "Generating first-run recognition seed...")
        await asyncio.sleep(30)  # Let other systems init first
        try:
            seed = await asyncio.wait_for(engine.synthesize("light"), timeout=60)
            _log("recognition", f"First-run seed generated ({len(seed)} chars)")
        except Exception as e:
            _log("recognition", f"First-run synthesis failed (non-fatal): {e}")
    else:
        _log("recognition", f"Existing seed is fresh ({_seed_path.stat().st_size}b)")

    # Then run on the normal 2-hour cycle
    while not shutdown_event.is_set():
        await asyncio.sleep(RECOGNITION_INTERVAL)
        if shutdown_event.is_set():
            break
        try:
            seed = await asyncio.wait_for(engine.synthesize("light"), timeout=120)
            _log("recognition", f"Seed updated ({len(seed)} chars)")
        except Exception as e:
            _log("recognition", f"Synthesis failed: {e}")

    # Exit the loop cleanly (original code had the wait at the bottom)
    return


async def _run_recognition_loop_UNUSED(shutdown_event: asyncio.Event) -> None:
    # Keep for reference — original simple loop
    from dharma_swarm.meta_daemon import RecognitionEngine
    engine = RecognitionEngine()

    while not shutdown_event.is_set():
        try:
            seed = await engine.synthesize("light")
            _log("recognition", f"Seed updated ({len(seed)} chars)")
        except Exception as e:
            _log("recognition", f"Synthesis failed: {e}")
    return  # pragma: no cover


async def _run_witness_loop(shutdown_event: asyncio.Event) -> None:
    """S3* Sporadic Audit — random direct audit of agent behavior.

    Implements Beer's S3* function: the Witness samples recent traces,
    evaluates telos alignment, detects mimicry, and publishes findings
    to stigmergy governance channel + signal bus. Closes VSM Gap #2.
    """
    # Let other systems produce traces first
    await asyncio.sleep(120)
    _log("witness", f"S3* Witness auditor starting (cycle={WITNESS_INTERVAL}s)")

    from dharma_swarm.witness import WitnessAuditor

    auditor = WitnessAuditor(cycle_seconds=WITNESS_INTERVAL)

    while not shutdown_event.is_set():
        try:
            findings = await auditor.run_cycle()
            actionable = [f for f in findings if f.is_actionable]
            stats = auditor.get_stats()
            _log(
                "witness",
                f"S3* audit cycle {stats['cycles_completed']}: "
                f"{len(findings)} findings, {len(actionable)} actionable",
            )
            if actionable:
                for f in actionable[:3]:
                    _log("witness", f"  [{f.severity}] {f.agent}/{f.action}: {f.observation[:100]}")
        except Exception as e:
            _log("witness", f"S3* audit failed: {e}")

        try:
            await asyncio.wait_for(
                shutdown_event.wait(), timeout=WITNESS_INTERVAL
            )
            break
        except asyncio.TimeoutError:
            pass

    auditor.stop()
    _log("witness", "S3* Witness auditor stopped")


async def _run_consolidation_loop(shutdown_event: asyncio.Event) -> None:
    """Consolidation Cycle — system-wide sleep/backpropagation.

    Two consolidator agents (Alpha/Beta) read ALL agents' state, have a
    structured contrarian debate, and modify behavioral DNA based on
    observed "loss". Mirrors sleep consolidation in the brain.
    """
    # Wait 2 hours after boot to let other systems produce traces
    await asyncio.sleep(7200)
    _log("consolidation", f"Sleep cycle starting (interval={CONSOLIDATION_INTERVAL}s)")

    from dharma_swarm.consolidation import ConsolidationCycle

    cycle = ConsolidationCycle(state_dir=STATE_DIR)

    # Neural consolidator: algorithmic forward-pass + loss detection + corrections
    # Runs BEFORE the LLM debate cycle — no LLM cost, identifies losses fast
    try:
        from dharma_swarm.neural_consolidator import NeuralConsolidator
        _neural = NeuralConsolidator(
            provider=None,  # Algorithmic mode, no LLM calls
            base_path=STATE_DIR,
        )
    except Exception as _ne:
        _neural = None
        _log("consolidation", f"Neural consolidator init failed: {_ne}")

    while not shutdown_event.is_set():
        # Neural pass first (algorithmic, fast, no LLM cost)
        if _neural is not None:
            try:
                _nr = await _neural.consolidation_cycle()
                _log(
                    "consolidation",
                    f"Neural pass: losses={_nr.losses_found} "
                    f"corrections={_nr.corrections_applied} "
                    f"divisions={_nr.division_proposals}",
                )
            except Exception as _ne:
                _log("consolidation", f"Neural pass error: {_ne}")

        # LLM-based contrarian debate cycle
        try:
            outcome = await cycle.run()
            _log(
                "consolidation",
                f"Cycle {outcome.cycle_number}: loss={outcome.system_loss_score:.3f} "
                f"corrections={outcome.corrections_applied}/{outcome.corrections_proposed} "
                f"({outcome.duration_seconds:.1f}s)",
            )
            # Export capability/fitness gap corrections as evolution proposals
            try:
                exported = cycle.export_evolution_proposals(outcome)
                if exported:
                    _log("consolidation", f"Exported {exported} proposals to evolution pipeline")
            except Exception as _ep_err:
                _log("consolidation", f"Proposal export failed: {_ep_err}")
        except Exception as e:
            _log("consolidation", f"Cycle failed: {e}")

        try:
            await asyncio.wait_for(
                shutdown_event.wait(), timeout=CONSOLIDATION_INTERVAL
            )
            break
        except asyncio.TimeoutError:
            pass

    _log("consolidation", "Sleep cycle stopped")


# ---------------------------------------------------------------------------
# Loop 13: Free Evolution Grind — nonstop free-tier evolution with hunger signal
# ---------------------------------------------------------------------------

# Hunger thresholds: when hunger > HIGH, run fast. When < LOW, run slow.
_GRIND_HUNGER_HIGH = 0.7
_GRIND_HUNGER_LOW = 0.3
_GRIND_INTERVAL_FAST = 60      # seconds — when hungry
_GRIND_INTERVAL_SLOW = 300     # seconds — when satisfied
_GRIND_STAGNATION_WINDOW = 10  # meta-archive entries to check for plateau

# Free-tier providers only — zero cost, can run 24/7
_FREE_PROVIDER_TYPES = ("ollama", "nvidia_nim", "openrouter_free", "groq", "siliconflow")

# Free coding-capable models on OpenRouter for evolution proposals
_FREE_CODING_MODELS = (
    "qwen/qwen3-coder:free",
    "qwen/qwen3-next-80b-a3b-instruct:free",
    "qwen/qwen3-4b:free",
    "meta-llama/llama-3.3-70b-instruct:free",
    "deepseek/deepseek-chat-v3-0324:free",
)

# Core Python modules to target for evolution — actual testable source
_GRIND_EVOLUTION_TARGETS = (
    "swarm.py", "orchestrator.py", "agent_runner.py", "providers.py",
    "evolution.py", "thinkodynamic_director.py", "consolidation.py",
    "stigmergy.py", "monitor.py", "auto_proposer.py", "self_improve.py",
    "fitness_predictor.py", "training_flywheel.py", "overnight_evaluator.py",
)


def _compute_hunger(meta_archive_path: Path, last_improvement_time: float) -> float:
    """Hunger = how badly the system wants to evolve right now.

    Inputs:
        - meta_fitness plateau (are recent meta-fitness values flat?)
        - time since last real improvement
        - gap between current fitness and 1.0

    Returns 0.0 (satisfied) to 1.0 (starving).
    """
    import json as _hj
    import time as _ht

    if not meta_archive_path.exists():
        return 0.5  # neutral

    # Read last N meta-archive entries
    try:
        lines = meta_archive_path.read_text().strip().split("\n")
        recent = []
        for line in lines[-_GRIND_STAGNATION_WINDOW:]:
            if line.strip():
                recent.append(_hj.loads(line))
    except Exception:
        return 0.5

    if len(recent) < 3:
        return 0.6  # slight hunger — need more data

    # Component 1: fitness gap (how far from 1.0)
    latest_mf = recent[-1].get("meta_fitness", 0.5)
    fitness_gap = max(0.0, 1.0 - latest_mf)

    # Component 2: stagnation (are recent values flat?)
    mf_values = [e.get("meta_fitness", 0.5) for e in recent]
    if len(mf_values) >= 2:
        diffs = [abs(b - a) for a, b in zip(mf_values, mf_values[1:])]
        avg_diff = sum(diffs) / len(diffs)
        stagnation = max(0.0, 1.0 - (avg_diff * 20))  # flat = high stagnation
    else:
        stagnation = 0.5

    # Component 3: time since last improvement (decays every hour)
    time_since = _ht.time() - last_improvement_time
    time_pressure = min(1.0, time_since / 7200.0)  # maxes at 2 hours

    hunger = (0.4 * fitness_gap) + (0.35 * stagnation) + (0.25 * time_pressure)
    return max(0.0, min(1.0, hunger))


def _hunger_to_interval(hunger: float) -> float:
    """Map hunger to sleep interval: high hunger = short interval."""
    if hunger >= _GRIND_HUNGER_HIGH:
        return _GRIND_INTERVAL_FAST
    if hunger <= _GRIND_HUNGER_LOW:
        return _GRIND_INTERVAL_SLOW
    # Linear interpolation
    ratio = (hunger - _GRIND_HUNGER_LOW) / (_GRIND_HUNGER_HIGH - _GRIND_HUNGER_LOW)
    return _GRIND_INTERVAL_SLOW - (ratio * (_GRIND_INTERVAL_SLOW - _GRIND_INTERVAL_FAST))


async def run_free_evolution_grind(shutdown_event: asyncio.Event) -> None:
    """Nonstop free-tier evolution loop with adaptive hunger signal.

    Runs AutoProposer → DarwinEngine → MetaEvolution using ONLY free providers.
    Adjusts its own cadence: runs every 60s when hungry, every 300s when satisfied.
    Cost: $0. Runs 24/7.

    This is loop #13 in the orchestrator — the system's metabolic drive.
    """
    await asyncio.sleep(90)  # Let swarm + evolution init first

    _log("grind", "Free Evolution Grind starting (loop #13)")
    _log("grind", f"  Free providers: {_FREE_PROVIDER_TYPES}")
    _log("grind", f"  Interval range: {_GRIND_INTERVAL_FAST}s (hungry) → {_GRIND_INTERVAL_SLOW}s (satisfied)")

    # Init DarwinEngine (separate instance, reads same archive)
    from dharma_swarm.evolution import DarwinEngine, Proposal
    from dharma_swarm.meta_evolution import MetaEvolutionEngine

    evo_dir = STATE_DIR / "evolution"
    traces_dir = STATE_DIR / "traces"
    meta_archive_path = evo_dir / "meta_archive.jsonl"

    engine = DarwinEngine(
        archive_path=evo_dir / "archive.jsonl",
        traces_path=traces_dir,
        predictor_path=evo_dir / "predictor_data.jsonl",
    )
    await engine.init()

    meta_engine = MetaEvolutionEngine(
        engine,
        meta_archive_path=meta_archive_path,
        n_object_cycles_per_meta=2,
        auto_apply=True,
    )

    cycle_count = 0
    last_improvement_time = __import__("time").time()
    last_best_fitness = 0.0

    while not shutdown_event.is_set():
        cycle_count += 1

        # Compute hunger
        hunger = _compute_hunger(meta_archive_path, last_improvement_time)
        interval = _hunger_to_interval(hunger)

        try:
            import random as _grng
            _src_root = Path(__file__).resolve().parent
            proposals: list[Proposal] = []

            # Phase 1: Read pending proposals from consolidation bridge
            try:
                pending = engine.load_pending_proposals()
                if pending:
                    # Filter to only Python source targets
                    for p in pending[:3]:
                        comp = p.component
                        if comp.endswith(".py") or "/" not in comp:
                            proposals.append(p)
                    if proposals:
                        _log("grind", f"Loaded {len(proposals)} pending proposals from consolidation")
            except Exception:
                pass

            # Phase 2: AutoProposer observations (only those targeting .py files)
            if len(proposals) < 3:
                try:
                    import json as _gj
                    obs_file = STATE_DIR / "auto_proposer" / "observations.jsonl"
                    if obs_file.exists():
                        obs_lines = obs_file.read_text().strip().split("\n")
                        for line in obs_lines[-5:]:
                            if not line.strip():
                                continue
                            obs = _gj.loads(line)
                            fp = obs.get("source_data", {}).get("file_path", "")
                            # Only accept Python file paths
                            if fp.endswith(".py"):
                                proposals.append(Proposal(
                                    component=fp,
                                    change_type="mutation",
                                    description=obs.get("description", "auto-observation"),
                                    spec_ref=f"auto_proposer:{obs.get('observation_type', '?')}",
                                ))
                except Exception as exc:
                    _log("grind", f"Observation read error: {exc}")

            # Phase 3: Always include a random core Python module target
            # This ensures every cycle has at least one testable proposal
            available_targets = [
                t for t in _GRIND_EVOLUTION_TARGETS
                if (_src_root / t).exists()
            ]
            if available_targets:
                target = _grng.choice(available_targets)
                proposals.append(Proposal(
                    component=target,
                    change_type="mutation",
                    description=f"Grind probe: evolve {target} (hunger={hunger:.2f})",
                    spec_ref="grind_probe",
                ))

            # Phase 4: Run evolution cycle via DarwinEngine.run_cycle
            # (takes proposals directly — no LLM needed for proposal gen)
            result = await engine.run_cycle(proposals)

            # Phase 4b: LLM-powered evolution via Qwen3-coder:free (every 5th cycle)
            # This uses auto_evolve with free coding models for deeper mutations
            if cycle_count % 5 == 0 and hunger > 0.4:
                try:
                    import os as _gos
                    if _gos.environ.get("OPENROUTER_API_KEY"):
                        from dharma_swarm.providers import OpenRouterProvider
                        _free_provider = OpenRouterProvider()
                        _llm_targets = _grng.sample(available_targets, min(2, len(available_targets)))
                        _llm_files = [_src_root / t for t in _llm_targets]
                        _model = _grng.choice(_FREE_CODING_MODELS)
                        _log("grind", f"LLM evolve via {_model}: {_llm_targets}")
                        llm_result = await engine.auto_evolve(
                            provider=_free_provider,
                            source_files=_llm_files,
                            model=_model,
                            shadow=False,  # Real mode — apply diffs, run tests, roll back on failure
                            timeout=30.0,
                            context=f"Grind cycle {cycle_count}, hunger={hunger:.2f}",
                        )
                        if llm_result.best_fitness > result.best_fitness:
                            result = llm_result  # Use the better result
                            _log("grind", f"LLM result: fitness={llm_result.best_fitness:.3f} (better)")
                except Exception as _llm_err:
                    _log("grind", f"LLM evolve error: {_llm_err}")

            # Phase 5: Feed to meta-evolution
            meta_result = meta_engine.observe_cycle_result(result)

            # Track improvement
            if result.best_fitness > last_best_fitness + 0.01:
                last_best_fitness = result.best_fitness
                last_improvement_time = __import__("time").time()

            # Phase 5: Log
            meta_note = ""
            if meta_result is not None:
                if meta_result.evolved_parameters:
                    meta_note = f" | META EVOLVED (mf={meta_result.meta_fitness:.3f})"
                else:
                    meta_note = f" | meta ok (mf={meta_result.meta_fitness:.3f})"

            _log(
                "grind",
                f"Cycle {cycle_count}: hunger={hunger:.2f} interval={interval:.0f}s "
                f"proposals={len(proposals)} fitness={result.best_fitness:.3f} "
                f"archived={result.proposals_archived}{meta_note}",
            )

        except Exception as exc:
            _log("grind", f"Cycle {cycle_count} error: {exc}")

        # Adaptive sleep — hunger controls the pace
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
            break
        except asyncio.TimeoutError:
            pass

    _log("grind", f"Free Evolution Grind stopped after {cycle_count} cycles")


async def _run_replication_monitor_loop(shutdown_event: asyncio.Event) -> None:
    """Loop 9: Replication monitor -- process proposals, manage child lifecycles.

    Waits for consolidation to run first (initial delay = consolidation interval
    + 1 hour), then periodically drains pending proposals from
    ``~/.dharma/replication/proposals.jsonl`` and runs each through the
    checkpoint-gated ReplicationProtocol pipeline.

    Successful materialization creates a PersistentAgent whose ``run_loop``
    is spawned as a new asyncio task. Probation and apoptosis checks run
    on every tick for all tracked agents.
    """
    # Let consolidation produce proposals before we start consuming them
    initial_delay = CONSOLIDATION_INTERVAL + 3600
    _log("replication", f"Waiting {initial_delay}s for consolidation to run first...")
    try:
        await asyncio.wait_for(shutdown_event.wait(), timeout=initial_delay)
        _log("replication", "Shutdown during initial delay, exiting")
        return
    except asyncio.TimeoutError:
        pass

    _log("replication", f"Replication monitor starting (interval={REPLICATION_INTERVAL}s)")

    # Lazy imports to avoid circular deps and startup cost
    from dharma_swarm.replication_protocol import ReplicationProtocol

    protocol = ReplicationProtocol(state_dir=STATE_DIR)

    # Track spawned child tasks so we can cancel on shutdown
    child_tasks: list[asyncio.Task[None]] = []

    while not shutdown_event.is_set():
        try:
            pending = protocol.get_pending_proposals()
            if pending:
                _log("replication", f"Processing {len(pending)} pending proposal(s)")

            for proposal_data in pending:
                try:
                    outcome = await protocol.run(proposal_data.model_dump())
                    status = "SUCCESS" if outcome.success else "FAILED"
                    _log(
                        "replication",
                        f"Proposal '{proposal_data.proposed_role}': {status} "
                        f"({outcome.duration_seconds:.1f}s)"
                        + (f" -- {outcome.error}" if outcome.error else ""),
                    )

                    # On success, spawn PersistentAgent for the child
                    if outcome.success and outcome.child_agent_name and outcome.child_spec:
                        try:
                            from dharma_swarm.persistent_agent import PersistentAgent
                            from dharma_swarm.models import AgentRole, ProviderType as PT

                            child = PersistentAgent(
                                name=outcome.child_agent_name,
                                role=AgentRole(outcome.child_spec.get("role", "general")),
                                provider_type=PT(outcome.child_spec.get(
                                    "default_provider", "openrouter_free"
                                )),
                                model=outcome.child_spec.get("default_model", ""),
                                state_dir=STATE_DIR,
                                wake_interval_seconds=float(
                                    outcome.child_spec.get("wake_interval", 3600)
                                ),
                                system_prompt=outcome.child_spec.get("system_prompt", ""),
                            )
                            task = asyncio.create_task(
                                child.run_loop(shutdown_event),
                                name=f"child-{outcome.child_agent_name}",
                            )
                            child_tasks.append(task)
                            _log(
                                "replication",
                                f"Spawned child agent '{outcome.child_agent_name}' as asyncio task",
                            )
                        except Exception as spawn_exc:
                            _log(
                                "replication",
                                f"Failed to spawn child '{outcome.child_agent_name}': {spawn_exc}",
                            )
                except Exception as run_exc:
                    _log(
                        "replication",
                        f"Pipeline error for '{proposal_data.proposed_role}': {run_exc}",
                    )

            # Probation + apoptosis checks
            try:
                from dharma_swarm.population_control import PopulationController
                pop_ctrl = PopulationController(state_dir=STATE_DIR)
                probation_map = pop_ctrl.get_all_probation()
                for name, status in probation_map.items():
                    if not status.is_complete:
                        _log("replication", f"Probation active: '{name}' ({status.cycles_remaining} cycles left)")
            except Exception as pc_exc:
                _log("replication", f"Population check error: {pc_exc}")

        except Exception as e:
            _log("replication", f"Monitor error: {e}")

        # Clean up completed child tasks
        child_tasks = [t for t in child_tasks if not t.done()]

        try:
            await asyncio.wait_for(
                shutdown_event.wait(), timeout=REPLICATION_INTERVAL
            )
            break
        except asyncio.TimeoutError:
            pass

    # Cancel child tasks on shutdown
    for t in child_tasks:
        t.cancel()
    if child_tasks:
        await asyncio.gather(*child_tasks, return_exceptions=True)

    _log("replication", "Replication monitor stopped")


async def _run_zeitgeist_loop(shutdown_event: asyncio.Event) -> None:
    """S4 Environmental Intelligence — periodic zeitgeist scanning.

    Scans witness logs, shared notes, and external signals. When high gate
    block rates are detected, writes gate_pressure.json to tighten S3 trust
    mode. This closes VSM Gap #1: S3<->S4 bidirectional feedback.
    """
    # Initial delay to let other systems boot first
    await asyncio.sleep(30)

    from dharma_swarm.zeitgeist import ZeitgeistScanner
    scanner = ZeitgeistScanner(state_dir=STATE_DIR)

    while not shutdown_event.is_set():
        try:
            signals = await scanner.scan()
            threats = [s for s in signals if s.category == "threat"]
            _log("zeitgeist", f"S4 scan: {len(signals)} signals, {len(threats)} threats")
        except Exception as e:
            _log("zeitgeist", f"S4 scan failed: {e}")

        try:
            await asyncio.wait_for(
                shutdown_event.wait(), timeout=ZEITGEIST_INTERVAL
            )
            break
        except asyncio.TimeoutError:
            pass


async def run_conductor_loop(shutdown_event: asyncio.Event) -> None:
    """Run persistent conductor agents alongside the orchestrator.

    Each conductor has its own wake interval and restart logic.
    If one crashes, the other keeps running.
    """
    from dharma_swarm.persistent_agent import PersistentAgent
    from dharma_swarm.conductors import CONDUCTOR_CONFIGS

    _log("conductors", f"Initializing {len(CONDUCTOR_CONFIGS)} conductors...")

    conductors: list[PersistentAgent] = []
    for cfg in CONDUCTOR_CONFIGS:
        agent = PersistentAgent(
            name=cfg["name"],
            role=cfg["role"],
            provider_type=cfg["provider_type"],
            model=cfg["model"],
            state_dir=STATE_DIR,
            wake_interval_seconds=cfg["wake_interval_seconds"],
            system_prompt=cfg["system_prompt"],
            max_turns=cfg.get("max_turns", 25),
        )
        conductors.append(agent)
        _log("conductors", f"  {cfg['name']}: {cfg['model']} every {cfg['wake_interval_seconds']}s")

    async def _run_with_restart(conductor: PersistentAgent, delay: float) -> None:
        await asyncio.sleep(delay)
        while not shutdown_event.is_set():
            try:
                await conductor.run_loop(shutdown_event)
            except Exception as e:
                _log("conductors", f"{conductor.name} crashed: {e}. Restarting in 60s")
                try:
                    await asyncio.wait_for(shutdown_event.wait(), timeout=60)
                    break
                except asyncio.TimeoutError:
                    pass

    await asyncio.gather(
        _run_with_restart(conductors[0], 10),   # Claude starts +10s
        _run_with_restart(conductors[1], 30),   # Codex starts +30s
    )


async def _run_world_model_loop(shutdown_event: asyncio.Event) -> None:
    """World Model: living Forrester-style world state, updated every 6h by research agents.

    Seeded with 15 stocks (CO2, biodiversity, AI capability, institutional trust...),
    8 flows, 6 feedback loops. Each cycle: update stocks via web_search, assess
    telos pressure, emit algedonic signal if any stock crosses critical threshold.
    """
    try:
        from dharma_swarm.world_model import WorldModelAgent
        agent = WorldModelAgent(state_dir=STATE_DIR)
        # Seed on first boot
        try:
            await asyncio.wait_for(agent.initialize(), timeout=60.0)
            _log("world-model", "World model initialized and seeded")
        except Exception as exc:
            _log("world-model", f"World model init failed (non-fatal): {exc}")
        # Run update loop every 6 hours
        while not shutdown_event.is_set():
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=21600)
                break
            except asyncio.TimeoutError:
                pass
            if shutdown_event.is_set():
                break
            try:
                await asyncio.wait_for(agent.run_cycle(), timeout=300.0)
                _log("world-model", "World model cycle complete")
            except Exception as exc:
                _log("world-model", f"World model cycle error: {exc}")
    except Exception as exc:
        _log("world-model", f"World model loop crashed: {exc}")


async def _run_gauntlet_loop(shutdown_event: asyncio.Event) -> None:
    """Gauntlet: run adversarial eval pressure on a schedule, feed scores into DGM.

    Tier 1+2 (correctness + research): every 2 hours.
    Tier 3 (self-modification): every 6 hours.
    Tier 4+5 (adversarial + emergent): every 12 hours.
    Scores written to ~/.dharma/gauntlet/ and fed back to BenchmarkRegistry.
    """
    import random as _random
    _log("gauntlet", "Gauntlet loop starting")
    _cycle = 0
    while not shutdown_event.is_set():
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=7200)
            break
        except asyncio.TimeoutError:
            pass
        if shutdown_event.is_set():
            break

        _cycle += 1
        tiers = [1, 2]
        if _cycle % 3 == 0:
            tiers.append(3)
        if _cycle % 6 == 0:
            tiers += [4, 5]

        try:
            from benchmarks.gauntlet import run_gauntlet
            _log("gauntlet", f"Running tiers {tiers} (cycle {_cycle})")
            report = await asyncio.wait_for(run_gauntlet(tiers=tiers), timeout=1800)
            _log("gauntlet",
                 f"Score: {report.gauntlet_score:.3f} (Δ{report.delta:+.3f}) | "
                 f"DGM targets: {report.dgm_targets}")
            # Feed DGM targets into evolution loop via signal bus
            if report.dgm_targets and report.delta < 0:
                try:
                    from dharma_swarm.signal_bus import SignalBus
                    SignalBus.get().emit("GAUNTLET_REGRESSION", {
                        "score": report.gauntlet_score,
                        "delta": report.delta,
                        "dgm_targets": report.dgm_targets,
                    })
                except Exception:
                    pass
        except asyncio.TimeoutError:
            _log("gauntlet", "Gauntlet cycle timed out (1800s)")
        except Exception as exc:
            _log("gauntlet", f"Gauntlet cycle failed: {exc}")


async def _run_health_api(shutdown_event: asyncio.Event) -> None:
    """Health API: serves http://localhost:7433/health|metrics|loops|providers|telos"""
    try:
        from dharma_swarm.swarm_health_api import run_health_api
        await run_health_api(shutdown_event)
    except Exception as exc:
        _log("health-api", f"Health API crashed: {exc}")


async def _run_guardian_loop(shutdown_event: asyncio.Event) -> None:
    """Guardian Crew: continuous interface + loop + router health checking.

    Three specialist agents running every 4 hours:
      AUDITOR        — import chains, method existence, syntax errors
      LOOP_WATCHER   — cybernetic loop health, evolution archive freshness
      ROUTER_PROBE   — circuit breaker state, dead providers, missing keys

    Writes GUARDIAN_REPORT.md to repo root and ~/.dharma/guardian/.
    Creates GitHub issues for BLOCKER-severity findings.
    """
    try:
        from dharma_swarm.guardian_crew import start_guardian_loop
        await start_guardian_loop(
            state_dir=STATE_DIR,
            github_repo="AmitabhainArunachala/dharma_swarm",
            shutdown_event=shutdown_event,
        )
    except Exception as exc:
        _log("guardian", f"Guardian loop crashed: {exc}")


async def _run_archaeology_loop(shutdown_event: asyncio.Event) -> None:
    """Fang 7: Self-Reading Archaeology loop.

    Runs ArchaeologyIngestionDaemon on a 30-minute cycle.
    Ingests: evolution archive, shared research, stigmergy marks, task completions.
    Produces: ~/.dharma/meta/lessons_learned.md (anti-amnesia context prefix).
    Agents gain query_archaeology tool access to all ingested institutional memory.
    """
    _log("archaeology", "Starting archaeology ingestion loop (interval=1800s)")
    try:
        from dharma_swarm.archaeology_ingestion import ArchaeologyIngestionDaemon
        daemon = ArchaeologyIngestionDaemon(state_dir=STATE_DIR, interval_seconds=1800)

        # Run once immediately at boot
        try:
            counts = await asyncio.wait_for(daemon.run_once(), timeout=120.0)
            _log("archaeology", f"Boot ingestion complete: {counts}")
        except asyncio.TimeoutError:
            _log("archaeology", "Boot ingestion timed out (120s) — continuing")
        except Exception as exc:
            _log("archaeology", f"Boot ingestion failed (non-fatal): {exc}")

        # Then loop every 30 minutes
        while not shutdown_event.is_set():
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=1800)
                break  # shutdown
            except asyncio.TimeoutError:
                pass  # interval elapsed, run ingestion
            if shutdown_event.is_set():
                break
            try:
                counts = await asyncio.wait_for(daemon.run_once(), timeout=120.0)
                _log("archaeology", f"Ingestion cycle complete: {counts}")
            except asyncio.TimeoutError:
                _log("archaeology", "Ingestion cycle timed out (120s) — continuing")
            except Exception as exc:
                _log("archaeology", f"Ingestion cycle error: {exc}")

    except Exception as exc:
        _log("archaeology", f"Archaeology loop crashed: {exc}")


async def orchestrate(background: bool = False) -> None:
    """Main entry point — run all systems concurrently."""
    # Ensure Python logging is configured so module-level logger.info() calls
    # (from orchestrator.py, swarm.py, agent_runner.py etc.) are visible.
    # Rotating file logs: 10MB × 5 files → ~/.dharma/logs/swarm.log
    _log_dir = STATE_DIR / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _root = logging.getLogger()
    if not _root.handlers:
        _root.setLevel(logging.INFO)
        _fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        _ch = logging.StreamHandler()
        _ch.setFormatter(_fmt)
        _root.addHandler(_ch)
        from logging.handlers import RotatingFileHandler as _RFH
        _fh = _RFH(_log_dir / "swarm.log", maxBytes=10 * 1024 * 1024, backupCount=5)
        _fh.setFormatter(_fmt)
        _root.addHandler(_fh)
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Stop any existing daemon to avoid DB conflicts
    _stop_old_daemon()
    _reap_stale_pid_files()

    # Write PID -- use daemon.pid for consistency with _stop_old_daemon()
    pid_file = STATE_DIR / "daemon.pid"
    pid_file.write_text(str(os.getpid()))

    shutdown_event = asyncio.Event()

    def _signal_handler(signum, frame):
        _log("orchestrator", f"Signal {signum} received, shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # Enable subscription auth for Claude when not nested inside Claude Code
    if "CLAUDECODE" not in os.environ:
        os.environ.setdefault("DHARMA_CLAUDE_AUTH_MODE", "subscription")
        _log("orchestrator", "Claude auth: subscription (Max/Pro plan)")
    else:
        _log("orchestrator", "Claude auth: skipped (nested in Claude Code)")

    # Phase 2: Create shared signal bus for inter-loop temporal coherence
    from dharma_swarm.signal_bus import SignalBus
    bus = SignalBus.get()

    _log("orchestrator", "=" * 60)
    _log("orchestrator", "DGC Live Orchestrator starting (Strange Loop v1)")
    _log("orchestrator", f"  PID: {os.getpid()}")
    _log("orchestrator", f"  State: {STATE_DIR}")
    _log("orchestrator", f"  Swarm tick: {SWARM_TICK}s")
    _log("orchestrator", f"  Pulse interval: {PULSE_INTERVAL}s")
    _log("orchestrator", f"  Max daily: {MAX_DAILY}")
    _log("orchestrator", f"  Signal bus: active")
    _log("orchestrator", "=" * 60)

    # Constitutional size check (Power Prompt Commandment #3)
    try:
        from dharma_swarm.constitutional_size_check import enforce_constitutional_size
        enforce_constitutional_size()
    except RuntimeError as e:
        _log("orchestrator", f"FATAL: {e}")
        raise
    except Exception as e:
        _log("orchestrator", f"Constitutional size check failed (non-fatal): {e}")

    # Strange Loop Phase 0: unified swarm tick handles evolution + living layers + health
    # Only genuinely independent loops remain as separate tasks
    from dharma_swarm.context_agent import run_context_agent_loop
    from dharma_swarm.training_flywheel import run_training_flywheel_loop
    from dharma_swarm.self_improve import run_self_improvement_loop

    # Auto-enable self-improvement when autonomy >= 1
    _auto_level = int(os.environ.get("DGC_AUTONOMY_LEVEL", "1"))
    if _auto_level >= 1 and not os.environ.get("DHARMA_SELF_IMPROVE"):
        os.environ["DHARMA_SELF_IMPROVE"] = "1"
        _log("orchestrator", "Auto-enabled DHARMA_SELF_IMPROVE (autonomy >= 1)")

    # Liveness watchdog — the #1 convergent finding from the 20-agent audit.
    # Detects "alive but not progressing" loops before they compound.
    from dharma_swarm.loop_supervisor import LoopSupervisor
    _supervisor = LoopSupervisor()
    _loop_intervals = {
        "swarm": SWARM_TICK, "pulse": PULSE_INTERVAL, "health": 120,
        "zeitgeist": ZEITGEIST_INTERVAL, "witness": WITNESS_INTERVAL,
        "consolidation": CONSOLIDATION_INTERVAL, "recognition": 7200,
        "replication": 3600, "self-improve": 3600, "free-grind": 600,
        "flywheel": 300, "conductors": 120, "context-agent": 60,
    }
    for loop_name, interval in _loop_intervals.items():
        _supervisor.register_loop(loop_name, expected_interval=float(interval))

    task_factories: dict[str, Any] = {
        "swarm": lambda: run_swarm_loop(shutdown_event, signal_bus=bus, supervisor=_supervisor),
        "pulse": lambda: run_pulse_loop(shutdown_event),
        "recognition": lambda: _run_recognition_loop(shutdown_event),
        "conductors": lambda: run_conductor_loop(shutdown_event),
        "context-agent": lambda: run_context_agent_loop(shutdown_event, signal_bus=bus),
        "zeitgeist": lambda: _run_zeitgeist_loop(shutdown_event),
        "witness": lambda: _run_witness_loop(shutdown_event),
        "consolidation": lambda: _run_consolidation_loop(shutdown_event),
        "replication": lambda: _run_replication_monitor_loop(shutdown_event),
        "flywheel": lambda: run_training_flywheel_loop(shutdown_event),
        "health": lambda: run_health_loop(shutdown_event),
        "self-improve": lambda: run_self_improvement_loop(shutdown_event, interval=3600),
        "free-grind": lambda: run_free_evolution_grind(shutdown_event),
        # ── Fang 7: Self-Reading Archaeology ──
        # Ingests evolution archive, shared research, stigmergy marks, task
        # completions into MemoryPalace every 30 minutes. Produces
        # lessons_learned.md at ~/.dharma/meta/ — the anti-amnesia mechanism.
        "archaeology": lambda: _run_archaeology_loop(shutdown_event),
        # ── Guardian Crew: continuous interface + loop + router health checks ──
        # Runs at boot + every 4 hours. Writes GUARDIAN_REPORT.md.
        # Creates GitHub issues for BLOCKER-severity findings.
        "guardian": lambda: _run_guardian_loop(shutdown_event),
        # ── Health API: curl http://localhost:7433/health ──
        "health-api": lambda: _run_health_api(shutdown_event),
        # ── Gauntlet: adversarial eval pressure + DGM feedback loop ──
        "gauntlet": lambda: _run_gauntlet_loop(shutdown_event),
        # ── World Model: living Forrester-style world state updated by research ──
        "world-model": lambda: _run_world_model_loop(shutdown_event),
    }
    optional_clean_exit = {"pulse"}
    tasks = {
        name: asyncio.create_task(factory(), name=name)
        for name, factory in task_factories.items()
    }

    _log("orchestrator", f"All {len(tasks)} systems launched ({len(tasks)} loops incl. free-grind)")

    try:
        # Resilient loop: restart failed tasks instead of dying on first error.
        # Transient failures (e.g. "database is locked") should not kill all
        # 13 loops — just log, wait a beat, and let the system heal.
        max_restarts = 5
        restart_counts: dict[str, int] = {}

        while tasks and not shutdown_event.is_set():
            done, pending = await asyncio.wait(
                list(tasks.values()), return_when=asyncio.FIRST_COMPLETED, timeout=60.0,
            )
            if not done:
                continue  # timeout, check shutdown flag

            restart_queue: list[str] = []
            for t in done:
                name = t.get_name() or "unknown"
                tasks.pop(name, None)
                if t.cancelled():
                    if shutdown_event.is_set():
                        _log("orchestrator", f"System {name} cancelled during shutdown")
                    else:
                        _log("orchestrator", f"System {name} cancelled unexpectedly")
                        if name not in optional_clean_exit:
                            restart_queue.append(name)
                    continue

                exc = t.exception()
                if exc is not None:
                    _log("orchestrator", f"System {name} failed: {exc}")
                    restart_queue.append(name)
                    continue

                if shutdown_event.is_set() or name in optional_clean_exit:
                    _log("orchestrator", f"System {name} exited cleanly")
                else:
                    _log("orchestrator", f"System {name} exited unexpectedly; scheduling restart")
                    restart_queue.append(name)

            for name in restart_queue:
                count = restart_counts.get(name, 0) + 1
                restart_counts[name] = count
                if count <= max_restarts:
                    _log("orchestrator", f"Restarting {name} (attempt {count}/{max_restarts})")
                    if await _wait_or_shutdown(shutdown_event, min(count * 5, 30)):
                        break
                    tasks[name] = asyncio.create_task(task_factories[name](), name=name)
                else:
                    _log("orchestrator", f"System {name} exceeded max restarts, abandoning")

    except asyncio.CancelledError:
        pass
    finally:
        shutdown_event.set()
        for t in tasks.values():
            t.cancel()
        await asyncio.gather(*tasks.values(), return_exceptions=True)
        pid_file.unlink(missing_ok=True)
        _log("orchestrator", "All systems stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )
    bg = "--background" in sys.argv or "--bg" in sys.argv
    asyncio.run(orchestrate(background=bg))
