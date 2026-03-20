"""Organism — the integration layer that makes DHARMA SWARM breathe.

This module wires together all subsystems into a single living cycle:

    ontology ←→ agents ←→ gates ←→ evolution ←→ cascade
         ↕            ↕            ↕
     zeitgeist    message_bus    lineage
         ↕            ↕            ↕
      identity    stigmergy    amiros
              ↘      ↓      ↙
           vsm_channels (nervous system)
                    ↓
            algedonic → operator

The organism runs a heartbeat loop that:
1. Checks fleet viability (agent-internal VSM)
2. Runs zeitgeist scan (S4 intelligence)
3. Feeds gate patterns to zeitgeist (S3→S4)
4. Feeds zeitgeist signals back to gates (S4→S3)
5. Harvests agent outputs into AMIROS registries
6. Checks algedonic conditions (any→S5)
7. Updates identity coherence (S5)
8. Emits a pulse for observability

Ground: Varela (autopoiesis — cognition IS self-maintenance),
        Beer (VSM — recursive viability at every scale),
        Kauffman (autocatalytic closure — mutual enablement).
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.amiros import AMIROSRegistry
from dharma_swarm.identity import IdentityMonitor
from dharma_swarm.memory_palace import MemoryPalace
from dharma_swarm.model_routing import OrganismRouter
from dharma_swarm.traces import TraceEntry, TraceStore
from dharma_swarm.vsm_channels import (
    AgentViability,
    AlgedonicChannel,
    GatePattern,
    VSMCoordinator,
)
from dharma_swarm.zeitgeist import ZeitgeistScanner

logger = logging.getLogger(__name__)

# ── Singleton access ──────────────────────────────────────────────
_global_organism: Organism | None = None


def get_organism() -> Organism | None:
    """Return the global organism instance, or None if not booted."""
    return _global_organism


def set_organism(org: Organism) -> None:
    """Register the global organism instance (call once at startup)."""
    global _global_organism
    _global_organism = org


class OrganismPulse:
    """A single heartbeat of the organism.

    Captures the state of all subsystems at a point in time.
    Written to traces for full observability.
    """

    def __init__(self) -> None:
        self.timestamp = datetime.now(timezone.utc)
        self.cycle_number: int = 0
        self.fleet_health: float = 1.0
        self.zeitgeist_signals: int = 0
        self.anomalous_gate_patterns: int = 0
        self.algedonic_active: int = 0
        self.amiros_experiments_running: int = 0
        self.identity_coherence: float = 1.0
        self.audit_failure_rate: float = 0.0
        self.duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "cycle": self.cycle_number,
            "fleet_health": self.fleet_health,
            "zeitgeist_signals": self.zeitgeist_signals,
            "anomalous_patterns": self.anomalous_gate_patterns,
            "algedonic_active": self.algedonic_active,
            "experiments_running": self.amiros_experiments_running,
            "identity_coherence": self.identity_coherence,
            "audit_failure_rate": self.audit_failure_rate,
            "duration_ms": self.duration_ms,
        }

    @property
    def is_healthy(self) -> bool:
        return (
            self.fleet_health > 0.4
            and self.algedonic_active == 0
            and self.identity_coherence > 0.3
        )


class Organism:
    """The living integration layer.

    Composes all subsystems and runs the heartbeat that keeps
    the organism alive. This is the computational autopoiesis:
    the system maintaining itself through continuous self-monitoring.

    Usage:
        organism = Organism()
        await organism.boot()

        # Run a single heartbeat cycle
        pulse = await organism.heartbeat()

        # Or run continuous heartbeat
        await organism.run(interval_seconds=60)
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._cycle = 0
        self._running = False
        self._pulses: list[OrganismPulse] = []

        # === Subsystems ===
        self.vsm = VSMCoordinator(self._state_dir)
        self.amiros = AMIROSRegistry(self._state_dir)
        self.zeitgeist = ZeitgeistScanner(self._state_dir)
        self.identity = IdentityMonitor(state_dir=self._state_dir)
        self.palace = MemoryPalace(state_dir=self._state_dir)
        self.router = OrganismRouter(state_dir=self._state_dir)
        self.traces: TraceStore | None = None

        # Wiring: algedonic callbacks
        self.vsm.algedonic.register_callback(self._on_algedonic)

    async def boot(self) -> dict[str, Any]:
        """Initialize the organism — wake up all subsystems.

        Returns boot diagnostics.
        """
        diagnostics: dict[str, Any] = {"booted_at": datetime.now(timezone.utc).isoformat()}

        # Initialize trace store
        self.traces = TraceStore()
        await self.traces.init()
        diagnostics["traces"] = "initialized"

        # Run initial zeitgeist scan
        try:
            signals = await self.zeitgeist.scan()
            diagnostics["zeitgeist_signals"] = len(signals)
        except Exception as exc:
            diagnostics["zeitgeist_error"] = str(exc)

        # Check AMIROS state
        diagnostics["amiros"] = self.amiros.stats()

        # Log boot to traces
        if self.traces:
            await self.traces.log_entry(TraceEntry(
                agent="organism",
                action="boot",
                metadata=diagnostics,
            ))

        logger.info("Organism booted: %s", diagnostics)
        return diagnostics

    async def heartbeat(self) -> OrganismPulse:
        """Run a single heartbeat cycle.

        This is the autopoietic loop — the organism checking its own
        viability and adjusting.
        """
        t0 = time.monotonic()
        self._cycle += 1
        pulse = OrganismPulse()
        pulse.cycle_number = self._cycle

        # 1. Check fleet viability (agent-internal VSM)
        non_viable = await self.vsm.viability.check_all()
        pulse.fleet_health = self.vsm.viability.fleet_health()

        # 2. Run zeitgeist scan (S4)
        try:
            signals = await self.zeitgeist.scan()
            pulse.zeitgeist_signals = len(signals)

            # 3. Feed zeitgeist signals to gates (S4→S3)
            await self.vsm.run_zeitgeist_feedback(signals)
        except Exception as exc:
            logger.debug("Zeitgeist scan error: %s", exc)

        # 4. Check gate patterns (S3→S4)
        patterns = self.vsm.gate_patterns.get_all_patterns()
        pulse.anomalous_gate_patterns = sum(1 for p in patterns if p.is_anomalous)

        # 5. Check algedonic state
        pulse.algedonic_active = len(self.vsm.algedonic.active_signals)

        # 6. Check AMIROS state
        amiros_stats = self.amiros.stats()
        running = amiros_stats.get("experiments", {}).get("by_status", {})
        pulse.amiros_experiments_running = running.get("running", 0)

        # 7. Update identity coherence (S5)
        try:
            state = await self.identity.measure()
            pulse.identity_coherence = state.tcs
        except Exception:
            pulse.identity_coherence = -1.0

        # 8. Audit stats
        pulse.audit_failure_rate = self.vsm.auditor.failure_rate()

        # Record pulse
        pulse.duration_ms = (time.monotonic() - t0) * 1000
        self._pulses.append(pulse)

        # Keep last 1000 pulses in memory
        if len(self._pulses) > 1000:
            self._pulses = self._pulses[-1000:]

        # Log to traces
        if self.traces:
            await self.traces.log_entry(TraceEntry(
                agent="organism",
                action="heartbeat",
                metadata=pulse.to_dict(),
            ))

        level = logging.INFO if pulse.is_healthy else logging.WARNING
        logger.log(
            level,
            "♥ Cycle %d | health=%.2f | coherence=%.2f | algedonic=%d | %dms",
            pulse.cycle_number,
            pulse.fleet_health,
            pulse.identity_coherence,
            pulse.algedonic_active,
            pulse.duration_ms,
        )

        return pulse

    async def run(self, interval_seconds: float = 60.0) -> None:
        """Run continuous heartbeat loop.

        This is the daemon mode — the organism stays alive.
        """
        self._running = True
        logger.info("Organism heartbeat starting (interval=%ds)", interval_seconds)

        while self._running:
            try:
                pulse = await self.heartbeat()

                # Emergency: shorten interval if algedonic signals active
                if pulse.algedonic_active > 0:
                    await asyncio.sleep(min(interval_seconds, 10.0))
                else:
                    await asyncio.sleep(interval_seconds)

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("Heartbeat error: %s", exc)
                await asyncio.sleep(interval_seconds)

        logger.info("Organism heartbeat stopped after %d cycles", self._cycle)

    def stop(self) -> None:
        """Request graceful shutdown."""
        self._running = False

    # === Integration hooks — call these from agent_runner, evolution, etc. ===

    def on_gate_check(
        self,
        gate_name: str,
        result: str,
        action_description: str = "",
        agent_id: str = "",
    ) -> GatePattern | None:
        """Wire into telos_gates.py after every gate evaluation."""
        from dharma_swarm.models import GateResult
        gate_result = GateResult(result) if isinstance(result, str) else result
        return self.vsm.on_gate_check(
            gate_name, gate_result, action_description, agent_id,
        )

    async def on_agent_output(
        self,
        agent_id: str,
        task_description: str,
        output: str,
        gate_results: dict[str, str] | None = None,
    ) -> None:
        """Wire into agent_runner.py after agent produces output."""
        # VSM audit
        await self.vsm.on_agent_output(
            agent_id, task_description, output, gate_results,
        )

        # AMIROS harvest
        self.amiros.harvest(
            source="agent_output",
            agent_id=agent_id,
            raw_text=output[:2000],
        )

    def on_agent_viability(
        self,
        agent_id: str,
        s1: float = 1.0,
        s2: float = 1.0,
        s3: float = 1.0,
        s4: float = 1.0,
        s5: float = 1.0,
    ) -> None:
        """Wire into agent_runner.py for periodic self-assessment."""
        self.vsm.viability.update(AgentViability(
            agent_id=agent_id,
            s1_operations=s1,
            s2_coordination=s2,
            s3_control=s3,
            s4_intelligence=s4,
            s5_identity=s5,
        ))

    async def on_evolution_cycle(
        self,
        cycle_number: int,
        best_fitness: float,
        cycles_without_improvement: int,
        cost: float = 0.0,
    ) -> None:
        """Wire into evolution.py after each cycle."""
        # Check stagnation
        await self.vsm.algedonic.check_evolution_stagnation(
            cycles_without_improvement, best_fitness,
        )

        # Check cost spike
        if cost > 0:
            avg_costs = [p.to_dict().get("cost", 0) for p in self._pulses[-20:]]
            if avg_costs:
                avg = sum(avg_costs) / len(avg_costs)
                if avg > 0:
                    await self.vsm.algedonic.check_cost_spike(cost, avg)

    def _on_algedonic(self, signal: Any) -> None:
        """Callback when an algedonic signal fires.

        This is where we'd integrate with the operator bridge,
        notification system, or TUI alert.
        """
        logger.warning(
            "ALGEDONIC [%s]: %s — %s",
            signal.severity,
            signal.title,
            signal.recommended_action,
        )

    # === Status ===

    def status(self) -> dict[str, Any]:
        """Full organism status."""
        last_pulse = self._pulses[-1] if self._pulses else None
        return {
            "alive": self._running,
            "cycle": self._cycle,
            "last_pulse": last_pulse.to_dict() if last_pulse else None,
            "vsm": self.vsm.status(),
            "amiros": self.amiros.stats(),
            "palace": self.palace.stats(),
            "router": self.router.stats(),
        }

    @property
    def latest_pulse(self) -> OrganismPulse | None:
        return self._pulses[-1] if self._pulses else None
