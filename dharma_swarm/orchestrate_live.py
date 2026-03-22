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
    from dharma_swarm.evolution import DarwinEngine

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

    while not shutdown_event.is_set():
        try:
            count = len(engine.archive._entries) if engine.archive else 0
            _log("evolution", f"Archive: {count} entries")

            # Consume durable fitness events from MessageBus
            try:
                events = await _bus.consume_events("AGENT_FITNESS", limit=50)
                if events:
                    _log("evolution", f"Consumed {len(events)} fitness events from bus")
            except Exception as exc:
                _log("evolution", f"Bus consume error: {exc}")

            # Drain lifecycle events — task completion throughput for fitness context
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
            try:
                trend = await engine.get_fitness_trend(limit=5)
                if trend:
                    avg = sum(f for _, f in trend) / len(trend)
                    _log("evolution", f"Fitness trend (last {len(trend)}): avg={avg:.3f}")
            except Exception:
                logger.debug("Fitness trend read failed", exc_info=True)

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

    while not shutdown_event.is_set():
        try:
            outcome = await cycle.run()
            _log(
                "consolidation",
                f"Cycle {outcome.cycle_number}: loss={outcome.system_loss_score:.3f} "
                f"corrections={outcome.corrections_applied}/{outcome.corrections_proposed} "
                f"({outcome.duration_seconds:.1f}s)",
            )
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
    ]

    _log("orchestrator", f"All {len(tasks)} systems launched (incl. conductors + context-agent + witness)")

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
