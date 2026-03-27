"""Organism integration surfaces.

This module intentionally exports two organism APIs:

1. ``Organism`` and ``OrganismPulse``: the legacy integration layer that wires
   together VSM, AMIROS, memory, routing, and phase 3-6 lifecycle hooks.
2. ``OrganismRuntime`` and ``HeartbeatResult``: the newer heartbeat runtime
   focused on Gnani/Samvara hold-processing.

The merge branch needs both. ``origin/main`` still relies on the legacy
organism surface across a large integration-test slice, while the newer swarm
runtime imports ``OrganismRuntime`` directly.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from dharma_swarm.amiros import AMIROSRegistry
from dharma_swarm.identity import IdentityMonitor, LiveCoherenceSensor
from dharma_swarm.memory_palace import MemoryPalace
from dharma_swarm.model_routing import OrganismRouter
from dharma_swarm.samvara import DiagnosticResult, SamvaraEngine
from dharma_swarm.traces import TraceEntry, TraceStore
from dharma_swarm.vsm_channels import AgentViability, GatePattern, VSMCoordinator
from dharma_swarm.zeitgeist import ZeitgeistScanner

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Legacy organism surface
# ---------------------------------------------------------------------------

_global_organism: Organism | None = None
_global_graph_store: Any = None  # GraphStore | None


def get_organism() -> Organism | None:
    """Return the global organism instance, or None if not booted."""
    return _global_organism


def get_graph_store() -> Any:
    """Return the global GraphStore instance, or None if not initialized."""
    return _global_graph_store


def set_organism(org: Organism | None) -> None:
    """Register or clear the global organism instance."""
    global _global_organism, _global_graph_store
    _global_organism = org
    _global_graph_store = getattr(org, "graph_store", None) if org else None


class OrganismPulse:
    """A single heartbeat of the legacy organism integration layer."""

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
        # Phase 7b: concept graph stats
        self.concept_stats: dict[str, Any] = {}
        self.top_fragile_concepts: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        d = {
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
        if self.concept_stats:
            d["concept_stats"] = self.concept_stats
        if self.top_fragile_concepts:
            d["top_fragile_concepts"] = self.top_fragile_concepts
        return d

    @property
    def is_healthy(self) -> bool:
        return (
            self.fleet_health > 0.4
            and self.algedonic_active == 0
            and self.identity_coherence > 0.3
        )


class Organism:
    """The legacy organism integration layer."""

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._cycle = 0
        self._running = False
        self._pulses: list[OrganismPulse] = []

        self.vsm = VSMCoordinator(self._state_dir)
        self.amiros = AMIROSRegistry(self._state_dir)
        self.zeitgeist = ZeitgeistScanner(self._state_dir)
        self.identity = IdentityMonitor(state_dir=self._state_dir)
        self.palace = MemoryPalace(state_dir=self._state_dir)
        self.router = OrganismRouter(state_dir=self._state_dir)
        self.traces: TraceStore | None = None

        self._stigmergy_seen: set[str] = set()
        self._last_gnani_verdict: bool | None = None

        try:
            from dharma_swarm.organism_memory import OrganismMemory

            self.memory = OrganismMemory(state_dir=self._state_dir)
        except Exception:
            self.memory = None
            logger.debug("OrganismMemory init failed (non-fatal)")

        try:
            from dharma_swarm.algedonic_activation import AlgedonicActivation

            self.algedonic_activation = AlgedonicActivation(self)
        except Exception:
            self.algedonic_activation = None
            logger.debug("AlgedonicActivation init failed (non-fatal)")

        try:
            from dharma_swarm.dharma_attractor import DharmaAttractor

            self.attractor = DharmaAttractor(state_dir=self._state_dir)
        except Exception:
            self.attractor = None
            logger.debug("DharmaAttractor init failed (non-fatal)")

        try:
            from dharma_swarm.strange_loop import StrangeLoop

            self.strange_loop = StrangeLoop(self)
        except Exception:
            self.strange_loop = None
            logger.debug("StrangeLoop init failed (non-fatal)")

        try:
            from dharma_swarm.sleep_time_agent import SleepTimeAgent

            self.sleep_time_agent = SleepTimeAgent(tick_interval=5)
        except Exception:
            self.sleep_time_agent = None
            logger.debug("SleepTimeAgent init failed (non-fatal)")

        # ── Phase 7b: Semantic Graph integration ──────────────────────
        self.graph_store = None
        self._concept_registry = None
        self._concept_parser = None
        self._concept_indexer = None
        self._last_index_cycle: int = 0
        self._indexed_files: dict[str, float] = {}  # path -> mtime
        self._concept_stats: dict[str, Any] = {}
        self._last_index_time: str | None = None
        self._top_fragile_concepts: list[dict[str, Any]] = []

        try:
            from dharma_swarm.graph_store import SQLiteGraphStore

            db_path = self._state_dir / "data" / "dharma_graphs.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.graph_store = SQLiteGraphStore(str(db_path))
            logger.info("GraphStore initialized: %s", db_path)
        except Exception as exc:
            logger.debug("GraphStore init failed (non-fatal): %s", exc)

        try:
            from dharma_swarm.concept_parser import (
                ConceptIndexer,
                ConceptParser,
                ConceptRegistry,
            )

            self._concept_registry = ConceptRegistry()
            self._concept_parser = ConceptParser(self._concept_registry)
            if self.graph_store is not None:
                self._concept_indexer = ConceptIndexer(
                    self.graph_store, self._concept_registry
                )
                # Pre-populate semantic graph with known concepts on first boot
                self._concept_indexer.index_concepts()
        except Exception as exc:
            self._concept_parser = None
            logger.debug("ConceptParser init failed (non-fatal): %s", exc)

        self.vsm.algedonic.register_callback(self._on_algedonic)

    async def boot(self) -> dict[str, Any]:
        """Initialize the organism and return boot diagnostics."""
        diagnostics: dict[str, Any] = {"booted_at": datetime.now(timezone.utc).isoformat()}

        self.traces = TraceStore()
        await self.traces.init()
        diagnostics["traces"] = "initialized"

        try:
            signals = await self.zeitgeist.scan()
            diagnostics["zeitgeist_signals"] = len(signals)
        except Exception as exc:
            diagnostics["zeitgeist_error"] = str(exc)

        diagnostics["amiros"] = self.amiros.stats()

        if self.traces:
            await self.traces.log_entry(
                TraceEntry(agent="organism", action="boot", metadata=diagnostics)
            )

        logger.info("Organism booted: %s", diagnostics)
        return diagnostics

    async def heartbeat(self) -> OrganismPulse:
        """Run a single heartbeat cycle for the legacy organism layer."""
        t0 = time.monotonic()
        self._cycle += 1
        pulse = OrganismPulse()
        pulse.cycle_number = self._cycle

        await self.vsm.viability.check_all()
        pulse.fleet_health = self.vsm.viability.fleet_health()

        try:
            signals = await self.zeitgeist.scan()
            pulse.zeitgeist_signals = len(signals)
            await self.vsm.run_zeitgeist_feedback(signals)
        except Exception as exc:
            logger.debug("Zeitgeist scan error: %s", exc)

        patterns = self.vsm.gate_patterns.get_all_patterns()
        pulse.anomalous_gate_patterns = sum(1 for p in patterns if p.is_anomalous)
        pulse.algedonic_active = len(self.vsm.algedonic.active_signals)

        await self._harvest_stigmergy_tasks()

        amiros_stats = self.amiros.stats()
        running = amiros_stats.get("experiments", {}).get("by_status", {})
        pulse.amiros_experiments_running = running.get("running", 0)

        try:
            state = await self.identity.measure()
            pulse.identity_coherence = state.tcs
        except Exception:
            pulse.identity_coherence = -1.0

        pulse.audit_failure_rate = self.vsm.auditor.failure_rate()

        pulse.duration_ms = (time.monotonic() - t0) * 1000
        self._pulses.append(pulse)
        if len(self._pulses) > 1000:
            self._pulses = self._pulses[-1000:]

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

        if pulse_extra.get("algedonic_actions"):
            try:
                if self.algedonic_activation is not None:
                    all_actions = self.algedonic_activation.evaluate(pulse)
                    for act in all_actions:
                        try:
                            if act.action == "recalibrate_routing" and self.router is not None:
                                self.router._routing_bias = min(
                                    getattr(self.router, "_routing_bias", 0.0) + 0.1,
                                    0.5,
                                )
                                logger.info(
                                    "ALGEDONIC→ROUTING: bias increased to %.2f",
                                    self.router._routing_bias,
                                )
                            elif act.action == "gnani_checkpoint" and self.attractor is not None:
                                verdict = self.attractor.gnani_checkpoint(
                                    f"Algedonic telos drift: {act.description}",
                                    {"pulse_cycle": pulse.cycle_number},
                                )
                                if self.memory is not None:
                                    self.memory.record_event(
                                        entity_type="gnani_verdict",
                                        description=(
                                            f"{'PROCEED' if verdict.proceed else 'HOLD'} "
                                            "on telos drift alarm"
                                        ),
                                        metadata={
                                            "trigger": "algedonic_telos_drift",
                                            "proceed": verdict.proceed,
                                        },
                                    )
                                logger.info(
                                    "ALGEDONIC→GNANI: %s",
                                    "PROCEED" if verdict.proceed else "HOLD",
                                )
                        except Exception as exc:
                            logger.debug(
                                "Algedonic action %s failed (non-fatal): %s",
                                act.action,
                                exc,
                            )
            except Exception as exc:
                logger.debug("Algedonic action wiring failed (non-fatal): %s", exc)

        try:
            if self.strange_loop is not None:
                strange_loop_status = self.strange_loop.tick(self._cycle, self._pulses)
                if strange_loop_status not in ("idle", "testing", ""):
                    logger.info("STRANGE LOOP: %s (cycle %d)", strange_loop_status, self._cycle)
        except Exception as exc:
            logger.debug("Strange loop tick failed (non-fatal): %s", exc)

        try:
            if self.sleep_time_agent is not None:
                sleep_stats = self.sleep_time_agent.tick(self._cycle, self)
                if not sleep_stats.get("skipped") and sleep_stats.get("phases"):
                    logger.debug(
                        "SLEEP-TIME tick %d: %s",
                        self._cycle,
                        sleep_stats.get("phases", {}),
                    )
        except Exception as exc:
            logger.debug("SleepTimeAgent tick failed (non-fatal): %s", exc)

        # ── Phase 7b: Semantic Graph heartbeat integration ────────────
        try:
            if self._concept_indexer is not None and self.graph_store is not None:
                indexing_interval = 10  # run every 10th heartbeat cycle
                if self._cycle - self._last_index_cycle >= indexing_interval:
                    self._last_index_cycle = self._cycle
                    indexed = self._run_incremental_indexing()
                    if indexed > 0:
                        logger.info(
                            "CONCEPT-INDEX: indexed %d files (cycle %d)",
                            indexed,
                            self._cycle,
                        )
                # Always collect stats for the pulse
                try:
                    node_count = self.graph_store.count_nodes("semantic")
                    edge_count = self.graph_store.count_edges("semantic")
                except Exception:
                    node_count, edge_count = 0, 0
                self._concept_stats = {
                    "concept_nodes": node_count,
                    "concept_edges": edge_count,
                    "last_index_cycle": self._last_index_cycle,
                    "indexed_files": len(self._indexed_files),
                }
                pulse.concept_stats = dict(self._concept_stats)
        except Exception as exc:
            logger.debug("Concept indexing heartbeat failed (non-fatal): %s", exc)

        # ── Phase 7b: Blast radius for top concepts ──────────────────
        try:
            if self.graph_store is not None:
                fragile = await self._compute_top_fragile_concepts(limit=3)
                if fragile:
                    pulse.top_fragile_concepts = fragile
        except Exception as exc:
            logger.debug("Blast radius heartbeat failed (non-fatal): %s", exc)

        scaling_rec = self._check_scaling_needs(pulse)

        try:
            should_record = False
            if len(self._pulses) >= 2:
                prev = self._pulses[-2]
                if prev.is_healthy != pulse.is_healthy:
                    should_record = True
                if pulse_extra.get("algedonic_actions"):
                    should_record = True
                if scaling_rec is not None:
                    should_record = True
            else:
                should_record = True

            if should_record and self.memory is not None:
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

        if scaling_rec is not None:
            logger.warning(
                "SCALING: %s — %s (urgency=%s)",
                scaling_rec["action"],
                scaling_rec["reason"],
                scaling_rec["urgency"],
            )

        if self.traces:
            await self.traces.log_entry(
                TraceEntry(
                    agent="organism",
                    action="heartbeat",
                    metadata={**pulse.to_dict(), **({"scaling": scaling_rec} if scaling_rec else {})},
                )
            )

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
        """Run a continuous legacy heartbeat loop."""
        self._running = True
        logger.info("Organism heartbeat starting (interval=%ds)", interval_seconds)

        while self._running:
            try:
                pulse = await self.heartbeat()
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

    # ── Phase 7b: Semantic Graph helpers ──────────────────────────────

    def _run_incremental_indexing(self) -> int:
        """Scan for changed files and index new concept references.

        Returns the number of files indexed in this pass.
        Uses mtime tracking to avoid re-scanning unchanged files.
        The flow: ConceptParser.parse_file() → extractions → ConceptIndexer.index_extractions()
        """
        if (
            self._concept_indexer is None
            or self.graph_store is None
            or getattr(self, "_concept_parser", None) is None
        ):
            return 0

        import os

        scan_root = Path.cwd()
        indexed_count = 0
        all_extractions: list = []
        try:
            for py_file in scan_root.rglob("*.py"):
                if "__pycache__" in str(py_file) or ".git" in str(py_file):
                    continue
                try:
                    fpath = str(py_file)
                    mtime = os.path.getmtime(fpath)
                    prev_mtime = self._indexed_files.get(fpath, 0.0)
                    if mtime <= prev_mtime:
                        continue
                    extractions = self._concept_parser.parse_file(
                        fpath, repo_root=scan_root
                    )
                    all_extractions.extend(extractions)
                    self._indexed_files[fpath] = mtime
                    indexed_count += 1
                except Exception:
                    continue  # individual file failures are silently skipped

            if all_extractions:
                self._concept_indexer.index_extractions(all_extractions)
        except Exception as exc:
            logger.debug("Incremental indexing scan failed: %s", exc)

        return indexed_count

    async def _compute_top_fragile_concepts(
        self, limit: int = 3
    ) -> list[dict[str, Any]]:
        """Compute blast radius for the most-connected semantic concepts.

        Returns a list of dicts with concept name and total_impact for
        the top N most-fragile concepts (highest blast radius).
        """
        if self.graph_store is None:
            return []

        try:
            from dharma_swarm.concept_blast_radius import ConceptBlastRadius

            br = ConceptBlastRadius(state_dir=self._state_dir)

            # Get the most-connected concepts from the semantic graph
            # by querying for nodes with the highest edge count.
            top_nodes = self.graph_store.search_nodes(
                "semantic", "*", limit=limit * 2
            )
            if not top_nodes:
                return []

            fragile: list[dict[str, Any]] = []
            for node in top_nodes[:limit * 2]:
                node_id = node.get("id", "")
                node_name = node.get("name", "")
                if not node_id:
                    continue
                try:
                    report = await br.compute(node_id)
                    fragile.append({
                        "concept": report.concept_name or node_name,
                        "total_impact": report.total_impact,
                        "affected_files": len(report.affected_code_files),
                        "affected_concepts": len(report.affected_concepts),
                    })
                except Exception:
                    continue

            # Sort by total_impact descending, return top N
            fragile.sort(key=lambda x: x["total_impact"], reverse=True)
            return fragile[:limit]
        except ImportError:
            return []
        except Exception as exc:
            logger.debug("Top fragile concepts failed: %s", exc)
            return []

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
        return self.vsm.on_gate_check(gate_name, gate_result, action_description, agent_id)

    async def on_agent_output(
        self,
        agent_id: str,
        task_description: str,
        output: str,
        gate_results: dict[str, str] | None = None,
    ) -> None:
        """Wire into agent_runner.py after agent produces output."""
        await self.vsm.on_agent_output(agent_id, task_description, output, gate_results)
        self.amiros.harvest(source="agent_output", agent_id=agent_id, raw_text=output[:2000])

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
        self.vsm.viability.update(
            AgentViability(
                agent_id=agent_id,
                s1_operations=s1,
                s2_coordination=s2,
                s3_control=s3,
                s4_intelligence=s4,
                s5_identity=s5,
            )
        )

    async def on_evolution_cycle(
        self,
        cycle_number: int,
        best_fitness: float,
        cycles_without_improvement: int,
        cost: float = 0.0,
    ) -> None:
        """Wire into evolution.py after each cycle."""
        await self.vsm.algedonic.check_evolution_stagnation(
            cycles_without_improvement, best_fitness
        )

        if cost > 0:
            if not hasattr(self, "_evolution_costs"):
                self._evolution_costs: list[float] = []
            self._evolution_costs.append(cost)
            if len(self._evolution_costs) > 20:
                self._evolution_costs = self._evolution_costs[-20:]
            if len(self._evolution_costs) >= 3:
                avg = sum(self._evolution_costs[:-1]) / len(self._evolution_costs[:-1])
                if avg > 0:
                    await self.vsm.algedonic.check_cost_spike(cost, avg)

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
                self._last_gnani_verdict = verdict.proceed
                if self.memory is not None:
                    self.memory.record_event(
                        entity_type="gnani_verdict",
                        description=(
                            f"{'PROCEED' if verdict.proceed else 'HOLD'} on evolution cycle "
                            f"{cycle_number}"
                        ),
                        metadata={"proposal": proposal, "proceed": verdict.proceed},
                    )
        except Exception as exc:
            logger.debug("Gnani checkpoint failed (non-fatal): %s", exc)

    @property
    def last_gnani_verdict(self) -> bool | None:
        """Most recent Gnani checkpoint verdict."""
        return self._last_gnani_verdict

    def _on_algedonic(self, signal: Any) -> None:
        """Record and surface algedonic notifications."""
        logger.warning(
            "ALGEDONIC [%s]: %s — %s",
            signal.severity,
            signal.title,
            signal.recommended_action,
        )
        try:
            if self.memory is not None:
                self.memory.record_event(
                    entity_type="algedonic_event",
                    description=f"[{signal.severity}] {signal.title}: {signal.recommended_action}",
                    metadata={"severity": signal.severity, "title": signal.title},
                )
        except Exception:
            pass

    def _check_scaling_needs(self, pulse: OrganismPulse) -> dict[str, Any] | None:
        """Check whether the legacy organism should recommend crew scaling."""
        if len(self._pulses) < 3:
            return None

        recent = self._pulses[-3:]
        all_unhealthy = all(not p.is_healthy for p in recent)
        persistent_algedonic = sum(1 for p in recent if p.algedonic_active > 0) >= 2
        critical_health = pulse.fleet_health < 0.3

        if not (all_unhealthy or persistent_algedonic or critical_health):
            return None

        if pulse.audit_failure_rate > 0.5:
            return {
                "action": "spawn_specialist",
                "role": "validator",
                "reason": (
                    f"Audit failure rate {pulse.audit_failure_rate:.0%} — "
                    "need validation specialist"
                ),
                "urgency": "high",
            }
        if pulse.algedonic_active > 0:
            return {
                "action": "spawn_specialist",
                "role": "surgeon",
                "reason": (
                    f"{pulse.algedonic_active} algedonic signals active — "
                    "need surgical intervention"
                ),
                "urgency": "high",
            }
        if pulse.identity_coherence < 0.3:
            return {
                "action": "spawn_specialist",
                "role": "architect",
                "reason": (
                    f"Identity coherence at {pulse.identity_coherence:.2f} — "
                    "need architectural review"
                ),
                "urgency": "medium",
            }
        return {
            "action": "spawn_specialist",
            "role": "cartographer",
            "reason": "Sustained unhealthy state — need ecosystem scan",
            "urgency": "medium",
        }

    async def _harvest_stigmergy_tasks(self) -> int:
        """Read high-salience stigmergy marks and create tasks from them."""
        try:
            from dharma_swarm.stigmergy import StigmergyStore

            store = StigmergyStore(base_path=self._state_dir / "stigmergy")
            marks = await store.read_marks(limit=20)

            high_salience = [m for m in marks if m.salience >= 0.8]
            if not high_salience:
                return 0

            created = 0
            for mark in high_salience[:3]:
                mark_key = f"stig:{mark.id}"
                if mark_key in self._stigmergy_seen:
                    continue
                self._stigmergy_seen.add(mark_key)

                logger.info(
                    "STIGMERGY→TASK: [%s] %s (salience=%.2f, agent=%s)",
                    mark.action,
                    mark.observation,
                    mark.salience,
                    mark.agent,
                )
                created += 1

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

    def status(self) -> dict[str, Any]:
        """Full organism status."""
        pulse = self.latest_pulse
        result: dict[str, Any] = {
            "alive": self._running,
            "cycle": self._cycle,
            "last_pulse": pulse.to_dict() if pulse else None,
            "vsm": self.vsm.status(),
            "amiros": self.amiros.stats(),
            "palace": self.palace.stats(),
            "router": self.router.stats(),
        }
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
        try:
            result["strange_loop"] = self.strange_loop.stats if self.strange_loop else {}
        except Exception:
            pass
        try:
            result["sleep_time"] = self.sleep_time_agent.stats() if self.sleep_time_agent else {}
        except Exception:
            pass
        # Phase 7b: graph store stats
        try:
            if self.graph_store is not None:
                result["graph_store"] = {
                    "semantic_nodes": self.graph_store.count_nodes("semantic"),
                    "semantic_edges": self.graph_store.count_edges("semantic"),
                    "code_nodes": self.graph_store.count_nodes("code"),
                    "last_index_time": getattr(self, "_last_index_time", None),
                }
            fragile = getattr(self, "_top_fragile_concepts", [])
            if fragile:
                result["top_fragile_concepts"] = fragile
        except Exception:
            pass
        return result

    @property
    def latest_pulse(self) -> OrganismPulse | None:
        return self._pulses[-1] if self._pulses else None


# ---------------------------------------------------------------------------
# Algedonic signals
# ---------------------------------------------------------------------------

@dataclass
class AlgedonicSignal:
    """A pain/pleasure signal that bypasses S1-S4 and reaches S5 directly."""
    kind: str          # telos_drift, omega_divergence, failure_rate, ontological_drift
    severity: str      # info, medium, critical
    action: str        # what the system should do
    value: float = 0.0
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Gnani verdict
# ---------------------------------------------------------------------------

@dataclass
class GnaniVerdict:
    """The witness's binary decision: HOLD or PROCEED."""
    decision: str  # "HOLD" or "PROCEED"
    reason: str
    coherence: float
    hold_count: int
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Heartbeat result
# ---------------------------------------------------------------------------

@dataclass
class HeartbeatResult:
    """Everything that happened in one heartbeat cycle."""
    cycle: int
    tcs: float
    live_score: float
    blended: float
    regime: str
    algedonic_signals: list[AlgedonicSignal] = field(default_factory=list)
    gnani_verdict: Optional[GnaniVerdict] = None
    samvara_diagnostic: Optional[DiagnosticResult] = None
    elapsed_ms: float = 0.0


# ---------------------------------------------------------------------------
# OrganismRuntime
# ---------------------------------------------------------------------------

class OrganismRuntime:
    """The living heartbeat loop.

    Ties together IdentityMonitor (trailing), LiveCoherenceSensor
    (present-moment), algedonic channel (pain signals), Gnani (witness
    verdict), and SamvaraEngine (transformation on HOLD).

    Usage:
        org = OrganismRuntime(state_dir)
        result = await org.heartbeat()
        # or
        results = await org.run(n_cycles=15)
    """

    # Algedonic thresholds
    TELOS_DRIFT_THRESHOLD: float = 0.4
    OMEGA_DIVERGENCE_THRESHOLD: float = 0.4

    # Blend weights: present-moment vs trailing
    LIVE_WEIGHT: float = 0.4
    TRAILING_WEIGHT: float = 0.6

    def __init__(
        self,
        state_dir: Optional[Path] = None,
        on_algedonic: Optional[Callable[[AlgedonicSignal], None]] = None,
        on_gnani: Optional[Callable[[GnaniVerdict], None]] = None,
    ) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._identity = IdentityMonitor(self._state_dir)
        self._live_sensor = LiveCoherenceSensor(self._state_dir)
        self._samvara = SamvaraEngine(self._state_dir)
        self._on_algedonic = on_algedonic
        self._on_gnani = on_gnani
        self._cycle = 0
        self._consecutive_holds = 0
        self._history: deque[HeartbeatResult] = deque(maxlen=1000)

    @property
    def cycle(self) -> int:
        return self._cycle

    @property
    def samvara(self) -> SamvaraEngine:
        return self._samvara

    @property
    def history(self) -> list[HeartbeatResult]:
        return list(self._history)

    async def heartbeat(self) -> HeartbeatResult:
        """Execute one heartbeat cycle. The organism processes itself."""
        t0 = time.monotonic()
        self._cycle += 1

        # 1. Trailing measurement (TCS from filesystem artifacts)
        identity_state = await self._identity.measure()
        tcs = identity_state.tcs

        # 2. Present-moment measurement
        live = self._live_sensor.measure()
        live_score = live["score"]

        # 3. Blend
        blended = self.LIVE_WEIGHT * live_score + self.TRAILING_WEIGHT * tcs

        # 4. Algedonic channel — fire pain signals if thresholds crossed
        signals = self._check_algedonic(blended, live_score, tcs)

        # 4b. Check hibernating jobs for wake conditions
        try:
            hibernation_woken = await self._check_hibernating_jobs()
            if hibernation_woken > 0:
                logger.info(
                    "Reawakened %d hibernating job(s) (cycle %d)",
                    hibernation_woken,
                    self._cycle,
                )
        except Exception as exc:
            logger.debug("Hibernation check failed (non-fatal): %s", exc)

        # 5. Gnani verdict
        verdict = self._gnani_verdict(blended, signals)

        # 6. Samvara engine — transform on HOLD
        diagnostic = None
        if verdict.decision == "HOLD":
            self._consecutive_holds += 1
            diagnostic = await self._samvara.on_hold(
                coherence=blended,
                live_metrics={
                    "daemon_alive": live.get("daemon_alive", False),
                    "freshness_ratio": live.get("freshness_ratio", 0.0),
                    "tcs": tcs,
                    "live_score": live_score,
                },
            )
        else:
            if self._consecutive_holds > 0:
                self._samvara.on_proceed()
            self._consecutive_holds = 0

        elapsed = (time.monotonic() - t0) * 1000

        result = HeartbeatResult(
            cycle=self._cycle,
            tcs=round(tcs, 4),
            live_score=round(live_score, 4),
            blended=round(blended, 4),
            regime=identity_state.regime,
            algedonic_signals=signals,
            gnani_verdict=verdict,
            samvara_diagnostic=diagnostic,
            elapsed_ms=round(elapsed, 2),
        )
        self._history.append(result)

        logger.info(
            "♥ Cycle %d | tcs=%.2f live=%.2f blended=%.2f | %s | %s | %.0fms",
            self._cycle, tcs, live_score, blended,
            verdict.decision,
            self._samvara.current_power.value if self._samvara.active else "—",
            elapsed,
        )

        return result

    async def run(self, n_cycles: int = 15) -> list[HeartbeatResult]:
        """Run n heartbeat cycles and return all results."""
        results = []
        for _ in range(n_cycles):
            results.append(await self.heartbeat())
        return results

    # -- Algedonic channel --------------------------------------------------

    def _check_algedonic(
        self, blended: float, live_score: float, tcs: float,
    ) -> list[AlgedonicSignal]:
        """Fire pain signals when the organism is incoherent."""
        signals: list[AlgedonicSignal] = []

        # Telos drift: blended coherence below threshold
        if blended < self.TELOS_DRIFT_THRESHOLD:
            sig = AlgedonicSignal(
                kind="telos_drift",
                severity="critical",
                action="gnani_checkpoint",
                value=blended,
            )
            signals.append(sig)
            if self._on_algedonic:
                self._on_algedonic(sig)

        # Omega divergence: live and trailing disagree strongly
        divergence = abs(live_score - tcs)
        if divergence > self.OMEGA_DIVERGENCE_THRESHOLD:
            sig = AlgedonicSignal(
                kind="omega_divergence",
                severity="medium",
                action="rebalance_priorities",
                value=divergence,
            )
            signals.append(sig)
            if self._on_algedonic:
                self._on_algedonic(sig)

        return signals

    # -- Gnani (witness) ----------------------------------------------------

    def _gnani_verdict(
        self, blended: float, signals: list[AlgedonicSignal],
    ) -> GnaniVerdict:
        """The witness observes and issues a binary verdict."""
        has_critical = any(s.severity == "critical" for s in signals)

        if has_critical or blended < self.TELOS_DRIFT_THRESHOLD:
            verdict = GnaniVerdict(
                decision="HOLD",
                reason=(
                    f"blended coherence {blended:.3f} below drift threshold "
                    f"{self.TELOS_DRIFT_THRESHOLD}"
                ),
                coherence=blended,
                hold_count=self._consecutive_holds + 1,
            )
        else:
            verdict = GnaniVerdict(
                decision="PROCEED",
                reason=f"blended coherence {blended:.3f} is stable",
                coherence=blended,
                hold_count=0,
            )

        if self._on_gnani:
            self._on_gnani(verdict)

        return verdict

    # -- Hibernation integration --------------------------------------------

    async def _check_hibernating_jobs(self) -> int:
        """Check hibernating jobs for wake conditions.

        Delegates to the HibernationManager if available.  Returns the
        number of jobs woken (0 if no manager is configured).
        """
        mgr = getattr(self, "_hibernation_manager", None)
        if mgr is None:
            return 0
        woken = await mgr.check_conditions()
        timed_out = await mgr.timeout_check()
        if timed_out > 0:
            logger.warning(
                "Timed out %d hibernating job(s) (cycle %d)",
                timed_out,
                self._cycle,
            )
        return woken

    def set_hibernation_manager(self, manager: Any) -> None:
        """Attach a HibernationManager for heartbeat-driven condition checks."""
        self._hibernation_manager = manager

    # -- Status -------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Full organism status snapshot."""
        return {
            "cycle": self._cycle,
            "consecutive_holds": self._consecutive_holds,
            "samvara_active": self._samvara.active,
            "samvara_power": self._samvara.current_power.value,
            "total_heartbeats": len(self._history),
            "last_blended": self._history[-1].blended if self._history else None,
            "last_verdict": (
                self._history[-1].gnani_verdict.decision
                if self._history and self._history[-1].gnani_verdict
                else None
            ),
        }
