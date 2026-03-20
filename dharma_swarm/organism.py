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

        # Dynamic scaling state
        self._stigmergy_seen: set[str] = set()

        # Phase 4: Organism developmental memory
        try:
            from dharma_swarm.organism_memory import OrganismMemory
            self.memory = OrganismMemory(state_dir=self._state_dir)
        except Exception:
            self.memory = None
            logger.debug("OrganismMemory init failed (non-fatal)")

        # Phase 4: Algedonic activation (pain → behavioral change)
        try:
            from dharma_swarm.algedonic_activation import AlgedonicActivation
            self.algedonic_activation = AlgedonicActivation(self)
        except Exception:
            self.algedonic_activation = None
            logger.debug("AlgedonicActivation init failed (non-fatal)")

        # Phase 4: Gnani field
        try:
            from dharma_swarm.dharma_attractor import DharmaAttractor
            self.attractor = DharmaAttractor(state_dir=self._state_dir)
        except Exception:
            self.attractor = None
            logger.debug("DharmaAttractor init failed (non-fatal)")

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

        # 5b. Harvest high-salience stigmergy → task recommendations
        stigmergy_tasks = await self._harvest_stigmergy_tasks()

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

        # Phase 4: Algedonic activation — pain causes behavioral change
        pulse_extra: dict[str, Any] = {}
        try:
            if self.algedonic_activation is not None:
                actions = self.algedonic_activation.evaluate(pulse)
                for act in actions:
                    self.algedonic_activation.apply(act)
                if actions:
                    pulse_extra["algedonic_actions"] = [a.signal_type for a in actions]
        except Exception as exc:
            logger.debug("Algedonic activation failed (non-fatal): %s", exc)

        # Phase 4: Record pulse to organism developmental memory
        try:
            if self.memory is not None:
                self.memory.record_event(
                    entity_type="decision",
                    description=(
                        f"Heartbeat cycle {pulse.cycle_number}: "
                        f"health={pulse.fleet_health:.2f}, "
                        f"coherence={pulse.identity_coherence:.2f}"
                    ),
                    metadata=pulse.to_dict(),
                )
        except Exception as exc:
            logger.debug("Organism memory record failed (non-fatal): %s", exc)

        # Dynamic crew scaling check
        scaling_rec = self._check_scaling_needs(pulse)
        if scaling_rec is not None:
            logger.warning(
                "SCALING: %s — %s (urgency=%s)",
                scaling_rec["action"], scaling_rec["reason"], scaling_rec["urgency"],
            )

        # Log to traces
        if self.traces:
            await self.traces.log_entry(TraceEntry(
                agent="organism",
                action="heartbeat",
                metadata={**pulse.to_dict(), **({
                    "scaling": scaling_rec} if scaling_rec else {})},
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

        # Memory Palace ingestion — index output for future recall
        try:
            await self.palace.ingest(
                content=output[:2000],
                source=f"agent:{agent_id}",
                layer="working",
                metadata={
                    "agent_id": agent_id,
                    "task": task_description[:200],
                    "gate_results": gate_results or {},
                },
            )
        except Exception as exc:
            logger.debug("Palace ingestion failed (non-fatal): %s", exc)

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

        # Phase 4: Gnani checkpoint on evolution events
        try:
            if self.attractor is not None and cycles_without_improvement > 5:
                proposal = (
                    f"Evolution cycle {cycle_number}: best_fitness={best_fitness}, "
                    f"stagnant for {cycles_without_improvement} cycles"
                )
                verdict = self.attractor.gnani_checkpoint(
                    proposal,
                    {"fitness": best_fitness, "stagnation": cycles_without_improvement},
                )
                if self.memory is not None:
                    self.memory.record_event(
                        entity_type="gnani_verdict",
                        description=(
                            f"{'PROCEED' if verdict.proceed else 'HOLD'} on evolution cycle "
                            f"{cycle_number}"
                        ),
                        metadata={
                            "proposal": proposal,
                            "proceed": verdict.proceed,
                        },
                    )
        except Exception as exc:
            logger.debug("Gnani checkpoint failed (non-fatal): %s", exc)

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

    def _check_scaling_needs(self, pulse: OrganismPulse) -> dict[str, Any] | None:
        """Check if dynamic crew scaling is needed.

        Returns a scaling recommendation, or None.
        Triggers on:
        - 3+ consecutive unhealthy pulses
        - Algedonic signals active for 2+ cycles
        - Fleet health below 0.3
        """
        if len(self._pulses) < 3:
            return None

        recent = self._pulses[-3:]

        # Check consecutive unhealthy
        all_unhealthy = all(not p.is_healthy for p in recent)

        # Check persistent algedonic
        persistent_algedonic = sum(1 for p in recent if p.algedonic_active > 0) >= 2

        # Check critical fleet health
        critical_health = pulse.fleet_health < 0.3

        if not (all_unhealthy or persistent_algedonic or critical_health):
            return None

        # Determine what kind of specialist to recommend
        if pulse.audit_failure_rate > 0.5:
            return {
                "action": "spawn_specialist",
                "role": "validator",
                "reason": f"Audit failure rate {pulse.audit_failure_rate:.0%} — need validation specialist",
                "urgency": "high",
            }
        elif pulse.algedonic_active > 0:
            return {
                "action": "spawn_specialist",
                "role": "surgeon",
                "reason": f"{pulse.algedonic_active} algedonic signals active — need surgical intervention",
                "urgency": "high",
            }
        elif pulse.identity_coherence < 0.3:
            return {
                "action": "spawn_specialist",
                "role": "architect",
                "reason": f"Identity coherence at {pulse.identity_coherence:.2f} — need architectural review",
                "urgency": "medium",
            }
        else:
            return {
                "action": "spawn_specialist",
                "role": "cartographer",
                "reason": "Sustained unhealthy state — need ecosystem scan",
                "urgency": "medium",
            }

    async def _harvest_stigmergy_tasks(self) -> int:
        """Read high-salience stigmergy marks and create tasks from them.

        Returns number of tasks created.
        """
        try:
            from dharma_swarm.stigmergy import StigmergyStore
            store = StigmergyStore(base_path=self._state_dir / "stigmergy")
            marks = await store.read_marks(limit=20)

            high_salience = [m for m in marks if m.salience >= 0.8]
            if not high_salience:
                return 0

            # Check which marks have already been converted to tasks
            created = 0
            for mark in high_salience[:3]:  # Cap at 3 per heartbeat
                mark_key = f"stig:{mark.id}"
                if mark_key in self._stigmergy_seen:
                    continue
                self._stigmergy_seen.add(mark_key)

                logger.info(
                    "STIGMERGY→TASK: [%s] %s (salience=%.2f, agent=%s)",
                    mark.action, mark.observation, mark.salience, mark.agent,
                )
                created += 1

            # Trim seen set
            if len(self._stigmergy_seen) > 500:
                self._stigmergy_seen = set(list(self._stigmergy_seen)[-200:])

            return created
        except Exception as exc:
            logger.debug("Stigmergy harvest failed (non-fatal): %s", exc)
            return 0

    @property
    def scaling_recommendations(self) -> list[dict[str, Any]]:
        """Recent scaling recommendations from heartbeat checks."""
        recs = []
        for pulse in self._pulses[-10:]:
            rec = self._check_scaling_needs(pulse)
            if rec:
                recs.append(rec)
        return recs

    # === Status ===

    def status(self) -> dict[str, Any]:
        """Full organism status."""
        last_pulse = self._pulses[-1] if self._pulses else None
        result: dict[str, Any] = {
            "alive": self._running,
            "cycle": self._cycle,
            "last_pulse": last_pulse.to_dict() if last_pulse else None,
            "vsm": self.vsm.status(),
            "amiros": self.amiros.stats(),
            "palace": self.palace.stats(),
            "router": self.router.stats(),
        }
        # Phase 4: memory, attractor, algedonic stats
        try:
            result["memory"] = self.memory.stats() if self.memory else {}
            result["attractor"] = "active" if self.attractor else "inactive"
            result["algedonic_activations"] = (
                len(self.algedonic_activation.recent_activations)
                if self.algedonic_activation
                else 0
            )
        except Exception:
            pass
        return result

    @property
    def latest_pulse(self) -> OrganismPulse | None:
        return self._pulses[-1] if self._pulses else None
