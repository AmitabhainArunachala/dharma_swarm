"""DSE integration: wires monad, coalgebra, and sheaf into the live runtime.

This module is the seam between the theoretical DSE layers and the
operational swarm.  It:

1. Converts evolution observations into sheaf ``Discovery`` objects.
2. Publishes them into a ``CoordinationProtocol``.
3. Runs Čech cohomology to separate global truths from productive
   disagreements (H¹ obstructions backed by Anekanta).
4. Feeds coordination results back to the DarwinEngine so future
   cycles can incorporate collective intelligence.
5. Tracks the observation stream for fixed-point convergence (L5).

Usage::

    integrator = DSEIntegrator(engine, swarm_manager)
    await integrator.after_cycle(result, proposals)
    # Call this from evolution.py after each run_cycle().

All failures are non-fatal — the integrator never blocks the core pipeline.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.archive import ArchiveEntry
from dharma_swarm.coalgebra import EvolutionObservation, build_evolution_observation
from dharma_swarm.evolution import CycleResult, Proposal
from dharma_swarm.monad import SelfObservationMonad, is_idempotent
from dharma_swarm.rv import RVReading
from dharma_swarm.sheaf import (
    CoordinationProtocol,
    Discovery,
    InformationChannel,
    NoosphereSite,
)

logger = logging.getLogger(__name__)

_VIRTUAL_AGENT_PREFIX = "darwin:"

_EVOLUTION_TOPIC = "evolution_observation"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _virtual_agent_id(component: str) -> str:
    """Each component gets a virtual agent in the noosphere."""
    return f"{_VIRTUAL_AGENT_PREFIX}{component}"


class ObservationWindow(BaseModel):
    """Sliding window of recent cycle observations for convergence tracking."""

    max_size: int = 50
    observations: list[dict[str, Any]] = Field(default_factory=list)
    rv_trajectory: list[float] = Field(default_factory=list)
    fitness_trajectory: list[float] = Field(default_factory=list)

    def append(self, record: dict[str, Any]) -> None:
        self.observations.append(record)
        if rv := record.get("rv"):
            self.rv_trajectory.append(float(rv))
        if fitness := record.get("best_fitness"):
            self.fitness_trajectory.append(float(fitness))
        if len(self.observations) > self.max_size:
            self.observations = self.observations[-self.max_size:]
            self.rv_trajectory = self.rv_trajectory[-self.max_size:]
            self.fitness_trajectory = self.fitness_trajectory[-self.max_size:]

    @property
    def rv_trend(self) -> float | None:
        if len(self.rv_trajectory) < 2:
            return None
        diffs = [b - a for a, b in zip(self.rv_trajectory, self.rv_trajectory[1:])]
        return sum(diffs) / len(diffs)

    @property
    def fitness_trend(self) -> float | None:
        if len(self.fitness_trajectory) < 2:
            return None
        diffs = [b - a for a, b in zip(self.fitness_trajectory, self.fitness_trajectory[1:])]
        return sum(diffs) / len(diffs)


class CoordinationSnapshot(BaseModel):
    """Result of one DSE coordination pass."""

    timestamp: str = ""
    global_truths: int = 0
    productive_disagreements: int = 0
    cohomological_dimension: int = 0
    is_globally_coherent: bool = True
    global_truth_claims: list[str] = Field(default_factory=list)
    disagreement_claims: list[str] = Field(default_factory=list)
    rv_trend: float | None = None
    fitness_trend: float | None = None
    observation_count: int = 0
    approaching_fixed_point: bool = False


class DSEIntegrator:
    """Connects monad + coalgebra + sheaf to the live evolution runtime.

    Instantiate once per DarwinEngine, call ``after_cycle()`` at the end of
    each ``run_cycle()``.
    """

    def __init__(
        self,
        archive_path: Path | None = None,
        coordination_interval: int = 5,
    ) -> None:
        self._archive_path = archive_path or (
            Path.home() / ".dharma" / "evolution"
        )
        self._coordination_interval = max(1, coordination_interval)
        self._cycles_since_coordination = 0
        self._window = ObservationWindow()
        self._last_coordination: CoordinationSnapshot | None = None
        self._observation_log = self._archive_path / "observations" / "coalgebra_stream.jsonl"

        # Monad with proxy R_V observer (real R_V requires torch)
        self._monad: SelfObservationMonad[EvolutionObservation] = SelfObservationMonad(
            observer=self._proxy_rv_observer,
        )
        self._last_observed: Any = None  # ObservedState at varying nesting depths

    @staticmethod
    def _proxy_rv_observer(obs: Any) -> RVReading:
        """Proxy R_V from cycle metadata when torch is unavailable."""
        if isinstance(obs, EvolutionObservation):
            archived = obs.cycle_result.proposals_archived
        else:
            archived = 0
        contraction = 1.0 - min(archived, 5) * 0.1
        return RVReading(
            rv=contraction,
            pr_early=1.0,
            pr_late=contraction,
            model_name="evolution-proxy",
            early_layer=0,
            late_layer=0,
            prompt_hash="0" * 16,
            prompt_group="evolution_cycle",
        )

    async def after_cycle(
        self,
        result: CycleResult,
        proposals: list[Proposal],
        archive_entries: Sequence[ArchiveEntry] = (),
    ) -> CoordinationSnapshot | None:
        """Post-cycle hook: observe, publish to sheaf, optionally coordinate.

        Returns a CoordinationSnapshot every ``coordination_interval`` cycles,
        or None on intermediate cycles.
        """
        try:
            return await self._after_cycle_inner(result, proposals, archive_entries)
        except Exception as exc:
            logger.debug("DSE integration failed (non-fatal): %s", exc)
            return None

    async def _after_cycle_inner(
        self,
        result: CycleResult,
        proposals: list[Proposal],
        archive_entries: Sequence[ArchiveEntry],
    ) -> CoordinationSnapshot | None:
        # 1. Build an observation over the current cycle delta only.
        observation = build_evolution_observation(
            result,
            archive_entries,
            proposals,
        )

        # 2. Observe the current cycle, then probe one step deeper for stability.
        observed = self._monad.observe(observation)
        self._last_observed = observed

        # 3. Check for fixed-point convergence (L5 condition)
        double = self._monad.observe(observed)
        approaching_fp = is_idempotent(double, tolerance=0.05)

        next_state = observation.next_state
        component = (
            next_state.component
            if isinstance(next_state, (ArchiveEntry, Proposal))
            else None
        )

        # 4. Record to observation window + JSONL
        record = observed.to_dict(state_serializer=lambda state: state.to_dict())
        record.update(
            {
                "cycle_id": result.cycle_id,
                "rv": observed.rv_reading.rv if observed.rv_reading else None,
                "best_fitness": result.best_fitness,
                "proposals_archived": result.proposals_archived,
                "approaching_fixed_point": approaching_fp,
                "discoveries_count": len(observation.discoveries),
                "lessons": observation.discoveries[:5],
                "component": component,
                "archive_entry_id": observation.archive_entry_id,
                "timestamp": observed.timestamp.isoformat(),
            }
        )
        self._window.append(record)
        await self._persist_observation(record)

        # 5. Every N cycles, run sheaf coordination
        self._cycles_since_coordination += 1
        if self._cycles_since_coordination >= self._coordination_interval:
            self._cycles_since_coordination = 0
            snapshot = self._run_coordination()
            self._last_coordination = snapshot
            await self._persist_coordination(snapshot)
            return snapshot

        return None

    def _run_coordination(self) -> CoordinationSnapshot:
        """Build noosphere site from observations, run Čech cohomology."""
        # Group observations by component (each component = virtual agent)
        by_component: dict[str, list[dict[str, Any]]] = {}
        for obs in self._window.observations:
            comp = obs.get("component") or "unknown"
            by_component.setdefault(comp, []).append(obs)

        if len(by_component) < 2:
            return CoordinationSnapshot(
                timestamp=_utc_now().isoformat(),
                observation_count=len(self._window.observations),
                rv_trend=self._window.rv_trend,
                fitness_trend=self._window.fitness_trend,
                approaching_fixed_point=any(
                    o.get("approaching_fixed_point") for o in self._window.observations[-3:]
                ),
            )

        # Build virtual agents and channels (all-to-all within evolution)
        agent_ids = [_virtual_agent_id(c) for c in by_component]
        channels = []
        seen = set()
        for i, a in enumerate(agent_ids):
            for b in agent_ids[i + 1:]:
                key = (a, b)
                if key not in seen:
                    seen.add(key)
                    channels.append(InformationChannel(
                        source_agent=a,
                        target_agent=b,
                        topics=[_EVOLUTION_TOPIC],
                        weight=1.0,
                    ))

        site = NoosphereSite(agent_ids, channels=channels)
        protocol = CoordinationProtocol(site)

        # Publish discoveries from each component's observations
        for comp, observations in by_component.items():
            agent_id = _virtual_agent_id(comp)
            discoveries = []
            for obs in observations[-5:]:  # last 5 per component
                lessons = obs.get("lessons", [])
                for lesson in lessons:
                    if lesson.strip():
                        discoveries.append(Discovery(
                            agent_id=agent_id,
                            claim_key=lesson.strip().lower()[:80],
                            content=lesson.strip(),
                            confidence=min(1.0, obs.get("best_fitness", 0.5)),
                            evidence=[f"cycle:{obs.get('cycle_id', 'unknown')}"],
                            perspective=comp,
                        ))

                # Also publish fitness/rv trends as discoveries
                rv = obs.get("rv")
                fitness = obs.get("best_fitness")
                if rv is not None and fitness is not None:
                    trend_claim = f"rv={rv:.2f} fitness={fitness:.3f}"
                    discoveries.append(Discovery(
                        agent_id=agent_id,
                        claim_key=f"trend:{comp}",
                        content=trend_claim,
                        confidence=min(1.0, fitness),
                        evidence=[f"cycle:{obs.get('cycle_id', 'unknown')}"],
                        perspective=comp,
                    ))

            if discoveries:
                protocol.publish(agent_id, discoveries)

        # Run coordination
        coordination_result = protocol.coordinate()

        return CoordinationSnapshot(
            timestamp=_utc_now().isoformat(),
            global_truths=len(coordination_result.global_truths),
            productive_disagreements=len(coordination_result.productive_disagreements),
            cohomological_dimension=coordination_result.cohomological_dimension,
            is_globally_coherent=coordination_result.is_globally_coherent,
            global_truth_claims=[
                d.claim_key or d.canonical_claim_key
                for d in coordination_result.global_truths
            ],
            disagreement_claims=[
                o.claim_key for o in coordination_result.productive_disagreements
            ],
            rv_trend=self._window.rv_trend,
            fitness_trend=self._window.fitness_trend,
            observation_count=len(self._window.observations),
            approaching_fixed_point=any(
                o.get("approaching_fixed_point") for o in self._window.observations[-3:]
            ),
        )

    async def _persist_observation(self, record: dict[str, Any]) -> None:
        try:
            self._observation_log.parent.mkdir(parents=True, exist_ok=True)
            with open(self._observation_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception:
            pass

    async def _persist_coordination(self, snapshot: CoordinationSnapshot) -> None:
        try:
            coord_path = self._observation_log.parent / "coordination_log.jsonl"
            with open(coord_path, "a", encoding="utf-8") as f:
                f.write(snapshot.model_dump_json() + "\n")
        except Exception:
            pass

    def get_coordination_context(self) -> dict[str, Any]:
        """Return a context dict suitable for injection into agent prompts.

        This feeds sheaf results back into the engine: global truths become
        guidance, disagreements become exploration targets.
        """
        if self._last_coordination is None:
            return {}
        snap = self._last_coordination
        context: dict[str, Any] = {
            "globally_coherent": snap.is_globally_coherent,
            "global_truths": snap.global_truth_claims[:5],
            "productive_disagreements": snap.disagreement_claims[:5],
            "rv_trend": snap.rv_trend,
            "fitness_trend": snap.fitness_trend,
            "approaching_fixed_point": snap.approaching_fixed_point,
        }
        if snap.productive_disagreements > 0:
            context["exploration_hint"] = (
                f"H¹ ≠ 0: {snap.productive_disagreements} productive disagreements "
                f"across components. Consider exploring: {', '.join(snap.disagreement_claims[:3])}"
            )
        if snap.approaching_fixed_point:
            context["convergence_hint"] = (
                "System approaching observation fixed point (L5). "
                "Consider bolder mutations to escape or validate stability."
            )
        return context


__all__ = [
    "CoordinationSnapshot",
    "DSEIntegrator",
    "ObservationWindow",
]
