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


def _log(system: str, msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    line = f"[{ts}] [{system}] {msg}"
    print(line, flush=True)
    logger.info("[%s] %s", system, msg)


async def run_swarm_loop(
    shutdown_event: asyncio.Event,
    signal_bus: "Any | None" = None,
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

    # MessageBus for instinct signal consumption
    from dharma_swarm.message_bus import MessageBus as _MBus
    _instinct_bus = _MBus(STATE_DIR / "db" / "messages.db")
    await _instinct_bus.init_db()

    agents = await swarm.list_agents()
    _log("swarm", f"Ready: {len(agents)} agents, thread={swarm.current_thread}")

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
                    instinct_events = await _instinct_bus.consume_events(
                        "ECC_INSTINCT_SIGNAL", limit=10,
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
                lifecycle_msgs = await _bus.receive("evolution_loop", limit=20)
                completions = sum(
                    1 for m in lifecycle_msgs
                    if m.metadata.get("event") == "task_completed"
                )
                if completions:
                    _log("evolution", f"Lifecycle: {completions} task completion(s) since last cycle")
                # Mark consumed so they don't pile up
                for m in lifecycle_msgs:
                    await _bus.mark_read(m.id)
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

            # Extract live fitness from AGENT_FITNESS event payloads
            live_fitness_scores: list[float] = []
            for ev in fitness_events:
                payload = ev.get("payload") if isinstance(ev, dict) else {}
                if isinstance(payload, dict):
                    score = payload.get("fitness_score") or payload.get("composite")
                    if isinstance(score, (int, float)) and score > 0:
                        live_fitness_scores.append(float(score))
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
                pulse_log = STATE_DIR / "pulse.log"
                status_parts = []
                if pid_file.exists():
                    try:
                        pid = int(pid_file.read_text().strip())
                        os.kill(pid, 0)
                        status_parts.append(f"daemon=PID:{pid}")
                    except (ValueError, OSError):
                        status_parts.append("daemon=dead")
                if pulse_log.exists():
                    lines = pulse_log.read_text().split("--- PULSE @")
                    status_parts.append(f"pulses={len(lines)-1}")
                _log("health", f"OK ({', '.join(status_parts) or 'nominal'})")

        except Exception as e:
            _log("health", f"Error: {e}")

        await asyncio.sleep(HEALTH_INTERVAL)


async def run_living_layers(shutdown_event: asyncio.Event) -> None:
    """Living layers — stigmergy decay, shakti perception, subconscious dreams."""
    _log("living", f"Starting (interval={LIVING_INTERVAL}s)")
    await asyncio.sleep(45)  # Let other systems init first

    # Hoist heavy objects out of the loop
    from dharma_swarm.stigmergy import StigmergyStore
    from dharma_swarm.subconscious import SubconsciousStream
    from dharma_swarm.shakti import ShaktiLoop

    store = StigmergyStore()
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


CONSOLIDATION_INTERVAL = _ll.consolidation_interval_seconds

WITNESS_INTERVAL = 3600  # 60 minutes between S3* sporadic audits

ZEITGEIST_INTERVAL = 300  # 5 minutes between S4 environmental scans

REPLICATION_INTERVAL = _ll.replication_check_interval_seconds

RECOGNITION_INTERVAL = 7200  # 2 hours between recognition synthesis


async def _run_recognition_loop(shutdown_event: asyncio.Event) -> None:
    """Periodic recognition synthesis — the strange loop's self-model.

    Every 2 hours, synthesizes signals from all subsystems into a recognition
    seed that feeds back into agent context via L9 META layer.
    """
    from dharma_swarm.meta_daemon import RecognitionEngine
    engine = RecognitionEngine()

    while not shutdown_event.is_set():
        try:
            seed = await engine.synthesize("light")
            _log("recognition", f"Seed updated ({len(seed)} chars)")
        except Exception as e:
            _log("recognition", f"Synthesis failed: {e}")

        # Wait for next cycle or shutdown
        try:
            await asyncio.wait_for(
                shutdown_event.wait(), timeout=RECOGNITION_INTERVAL
            )
            break
        except asyncio.TimeoutError:
            pass


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
                                role=outcome.child_spec.get("role", "worker"),
                                provider_type=outcome.child_spec.get(
                                    "default_provider", "openrouter_free"
                                ),
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


async def orchestrate(background: bool = False) -> None:
    """Main entry point — run all systems concurrently."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Stop any existing daemon to avoid DB conflicts
    _stop_old_daemon()

    # Write PID -- use daemon.pid for consistency with _stop_old_daemon()
    pid_file = STATE_DIR / "daemon.pid"
    pid_file.write_text(str(os.getpid()))

    shutdown_event = asyncio.Event()

    def _signal_handler(signum, frame):
        _log("orchestrator", f"Signal {signum} received, shutting down...")
        shutdown_event.set()

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

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

    tasks = [
        asyncio.create_task(run_swarm_loop(shutdown_event, signal_bus=bus), name="swarm"),
        asyncio.create_task(run_pulse_loop(shutdown_event), name="pulse"),
        asyncio.create_task(
            _run_recognition_loop(shutdown_event), name="recognition"
        ),
        asyncio.create_task(run_conductor_loop(shutdown_event), name="conductors"),
        asyncio.create_task(
            run_context_agent_loop(shutdown_event, signal_bus=bus), name="context-agent"
        ),
        asyncio.create_task(
            _run_zeitgeist_loop(shutdown_event), name="zeitgeist"
        ),
        asyncio.create_task(
            _run_witness_loop(shutdown_event), name="witness"
        ),
        asyncio.create_task(
            _run_consolidation_loop(shutdown_event), name="consolidation"
        ),
        asyncio.create_task(
            _run_replication_monitor_loop(shutdown_event), name="replication"
        ),
        asyncio.create_task(
            run_training_flywheel_loop(shutdown_event), name="flywheel"
        ),
        asyncio.create_task(
            run_health_loop(shutdown_event), name="health"
        ),
        asyncio.create_task(
            run_self_improvement_loop(shutdown_event, interval=3600),
            name="self-improve"
        ),
    ]

    _log("orchestrator", f"All {len(tasks)} systems launched ({len(tasks)} loops incl. self-improve)")

    try:
        # Wait for shutdown or first failure
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        for t in done:
            if t.exception():
                _log("orchestrator", f"System {t.get_name()} failed: {t.exception()}")
    except asyncio.CancelledError:
        pass
    finally:
        shutdown_event.set()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        pid_file.unlink(missing_ok=True)
        _log("orchestrator", "All systems stopped")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s [%(levelname)s] %(message)s",
    )
    bg = "--background" in sys.argv or "--bg" in sys.argv
    asyncio.run(orchestrate(background=bg))
