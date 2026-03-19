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

            # Check fitness trend
            try:
                trend = engine.fitness_trend(window=5)
                if trend:
                    avg = sum(t.get("fitness", 0) for t in trend) / len(trend)
                    _log("evolution", f"Fitness trend (last {len(trend)}): avg={avg:.3f}")
            except Exception:
                pass  # fitness_trend may not exist

            # Bus metrics for observability
            try:
                stats = await _bus.event_stats()
                if stats.get("queued", 0) > 0:
                    _log("evolution", f"Bus: {stats['queued']} queued, {stats['consumed']} consumed")
            except Exception:
                pass

        except Exception as e:
            _log("evolution", f"Error: {e}")

        await asyncio.sleep(EVOLUTION_INTERVAL)


async def run_health_loop(shutdown_event: asyncio.Event) -> None:
    """Health monitoring — detect anomalies, report status."""
    _log("health", f"Starting (interval={HEALTH_INTERVAL}s)")
    await asyncio.sleep(15)  # Let swarm init first

    while not shutdown_event.is_set():
        try:
            from dharma_swarm.monitor import SystemMonitor
            from dharma_swarm.traces import TraceStore

            traces_dir = STATE_DIR / "traces"
            store = TraceStore(base_path=traces_dir)
            await store.init()
            monitor = SystemMonitor(trace_store=store)

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

    while not shutdown_event.is_set():
        try:
            from dharma_swarm.stigmergy import StigmergyStore
            from dharma_swarm.subconscious import SubconsciousStream
            from dharma_swarm.shakti import ShaktiLoop

            store = StigmergyStore()
            density = store.density()
            summary = [f"density={density}"]

            # Stigmergy decay (evaporate old marks)
            if density > 100:
                decayed = await store.decay(max_age_hours=168)
                if decayed:
                    summary.append(f"decayed={decayed}")

            # Subconscious dreams (trigger on density threshold)
            stream = SubconsciousStream(stigmergy=store)
            if await stream.should_wake():
                associations = await stream.dream()
                summary.append(f"dreams={len(associations)}")

            # Shakti perception
            loop = ShaktiLoop(stigmergy=store)
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


RECOGNITION_INTERVAL = 7200  # 2 hours between recognition synthesis


async def _run_recognition_loop(shutdown_event: asyncio.Event) -> None:
    """Periodic recognition synthesis — the strange loop's self-model.

    Every 2 hours, synthesizes signals from all subsystems into a recognition
    seed that feeds back into agent context via L9 META layer.
    """
    while not shutdown_event.is_set():
        try:
            from dharma_swarm.meta_daemon import RecognitionEngine
            engine = RecognitionEngine()
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

    # v0.3.0: Viveka architecture — perception-action loop + algedonic scanning
    from dharma_swarm.perception_action_loop import (
        PerceptionActionLoop, LoopConfig,
        stigmergy_sensor, health_sensor, signal_sensor,
    )
    from dharma_swarm.cost_ledger import CostLedger
    from dharma_swarm.loop_detector import LoopDetector
    from dharma_swarm.algedonic import AlgedonicChannel, AlgedonicSignal

    # Initialize the perception-action loop with real sensors + action dispatch
    from dharma_swarm.action_dispatch import ActionDispatcher, SwarmContext

    pal_config = LoopConfig(
        base_period_seconds=60.0,
        min_period_seconds=10.0,
        max_period_seconds=600.0,
    )

    # Shared loop detector with persistence
    loop_persist = STATE_DIR / "loops" / "session_actions.jsonl"
    shared_detector = LoopDetector(persist_path=loop_persist)
    shared_detector.load()

    # Build context — subsystems attached later when swarm initializes
    dispatch_ctx = SwarmContext(
        cost_ledger=CostLedger(),
        state_dir=STATE_DIR,
    )

    # Optional viveka gate and deliberation
    _viveka_gate = None
    _deliberation_tri = None
    try:
        from dharma_swarm.viveka import VivekaGate
        _viveka_gate = VivekaGate(precision=0.5)
    except ImportError:
        pass
    try:
        from dharma_swarm.deliberation import DeliberationTriangle
        _deliberation_tri = DeliberationTriangle()
    except ImportError:
        pass

    dispatcher = ActionDispatcher(
        context=dispatch_ctx,
        viveka=_viveka_gate,
        deliberation=_deliberation_tri,
    )

    pal = PerceptionActionLoop(
        config=pal_config,
        sensors=[stigmergy_sensor, health_sensor, signal_sensor],
        action_handler=dispatcher.handle,
        cost_ledger=dispatch_ctx.cost_ledger,
        loop_detector=shared_detector,
    )
    pal.load_state()  # Resume from crash if state exists

    # Initialize algedonic channel
    algedonic = AlgedonicChannel()

    async def run_perception_action(shutdown_event: asyncio.Event) -> None:
        """v0.3.0: Precision-gated perception-action cycle.

        Replaces fixed-interval health/living/evolution loops with
        adaptive endogenous timing. The system itself decides when
        to sense and when to act.
        """
        _log("viveka", f"Perception-action loop starting (precision={pal.precision:.2f})")
        await pal.run(shutdown_event)

    async def run_algedonic_scan(shutdown_event: asyncio.Event) -> None:
        """v0.3.0: Periodic algedonic emergency scanning.

        Checks for budget depletion, error spikes, coherence collapse.
        Escalates stale unacknowledged signals.
        """
        _log("algedonic", "Emergency scanner starting")
        await asyncio.sleep(30)  # Let other systems init

        while not shutdown_event.is_set():
            try:
                # Check for pending emergencies
                pending = algedonic.pending()
                if pending:
                    _log("algedonic", f"{len(pending)} pending signals")
                    # Escalate stale signals
                    escalated = algedonic.escalate_stale(max_age_seconds=300)
                    if escalated:
                        _log("algedonic", f"Escalated {len(escalated)} stale signals")

                # Run detector checks
                from dharma_swarm.algedonic import run_detectors
                signals = await run_detectors()
                if signals:
                    _log("algedonic", f"Detectors fired: {[s.category for s in signals]}")

            except Exception as e:
                _log("algedonic", f"Scan error: {e}")

            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=120)
                break
            except asyncio.TimeoutError:
                pass

    # v0.3.1: Evolution feedback loop — closes fitness→evolution circle
    async def run_evolution_feedback(shutdown_event: asyncio.Event) -> None:
        """Monitor agent fitness and trigger evolution proposals."""
        try:
            from dharma_swarm.evolution_feedback import start_feedback_loop
            feedback = await start_feedback_loop()
            _log("evolution-fb", "Feedback loop started")
            await shutdown_event.wait()
            await feedback.stop()
        except Exception as e:
            _log("evolution-fb", f"Error: {e}")

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
        # v0.3.0: Viveka architecture
        asyncio.create_task(run_perception_action(shutdown_event), name="viveka-pal"),
        asyncio.create_task(run_algedonic_scan(shutdown_event), name="algedonic"),
        # v0.3.1: Evolution feedback loop
        asyncio.create_task(run_evolution_feedback(shutdown_event), name="evolution-fb"),
    ]

    _log("orchestrator", f"All {len(tasks)} systems launched (v0.3.1 + evolution feedback)")

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
