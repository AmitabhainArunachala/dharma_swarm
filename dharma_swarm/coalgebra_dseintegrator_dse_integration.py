"""Coalgebra-facing bridge for the live DSE integration runtime.

This cluster module gives the campaign ledger a stable import target at the
intersection of `coalgebra`, `monad`, and `sheaf` without duplicating the core
`DSEIntegrator` implementation. It re-exports the canonical runtime types from
`dse_integration.py` and adds a compact artifact model that summarizes one DSE
cycle in thesis terms.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field

from dharma_swarm.archive import ArchiveEntry
from dharma_swarm.coalgebra import EvolutionObservation, build_evolution_observation
from dharma_swarm.dse_integration import (
    CoordinationSnapshot,
    DSEIntegrator,
    ObservationWindow,
)
from dharma_swarm.evolution import CycleResult, Proposal

_FORMAL_STRUCTURES = ("coalgebra", "monad", "sheaf")


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _clean_discoveries(values: Sequence[Any]) -> list[str]:
    discoveries: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        discoveries.append(text)
    return discoveries


def _coordination_context(snapshot: CoordinationSnapshot) -> dict[str, Any]:
    context: dict[str, Any] = {
        "globally_coherent": snapshot.is_globally_coherent,
        "global_truths": list(snapshot.global_truth_claims[:5]),
        "productive_disagreements": list(snapshot.disagreement_claims[:5]),
        "rv_trend": snapshot.rv_trend,
        "fitness_trend": snapshot.fitness_trend,
        "approaching_fixed_point": snapshot.approaching_fixed_point,
    }
    if snapshot.productive_disagreements > 0:
        context["exploration_hint"] = (
            f"H^1 != 0: {snapshot.productive_disagreements} productive disagreements "
            f"across components. Consider exploring: "
            f"{', '.join(snapshot.disagreement_claims[:3])}"
        )
    if snapshot.approaching_fixed_point:
        context["convergence_hint"] = (
            "System approaching observation fixed point (L5). "
            "Consider bolder mutations to escape or validate stability."
        )
    return context


def _resolve_component(
    archive_entries: Sequence[ArchiveEntry],
    proposals: Sequence[Proposal],
) -> str:
    for entry in archive_entries:
        component = _clean_text(getattr(entry, "component", ""))
        if component:
            return component
    for proposal in proposals:
        component = _clean_text(getattr(proposal, "component", ""))
        if component:
            return component
    return ""


class DSECycleBridge(BaseModel):
    """Portable summary of one cycle at the coalgebra/monad/sheaf seam."""

    cycle_id: str = ""
    component: str = ""
    next_state_type: str = ""
    fitness: float = 0.0
    rv: float = 0.0
    discoveries: list[str] = Field(default_factory=list)
    discovery_count: int = 0
    observation_depth: int = 1
    has_monadic_observation: bool = False
    coordination_available: bool = False
    global_truths: int = 0
    productive_disagreements: int = 0
    global_truth_claims: list[str] = Field(default_factory=list)
    disagreement_claims: list[str] = Field(default_factory=list)
    approaching_fixed_point: bool = False
    context: dict[str, Any] = Field(default_factory=dict)
    formal_structures: list[str] = Field(
        default_factory=lambda: list(_FORMAL_STRUCTURES),
    )


def build_dse_cycle_bridge(
    observation: EvolutionObservation,
    *,
    component: str = "",
    observation_depth: int = 1,
    coordination_snapshot: CoordinationSnapshot | None = None,
    coordination_context: Mapping[str, Any] | None = None,
    approaching_fixed_point: bool | None = None,
) -> DSECycleBridge:
    """Summarize one coalgebra observation in DSE-integrator terms."""

    next_state = observation.next_state
    cycle_id = _clean_text(getattr(next_state, "cycle_id", ""))
    discoveries = _clean_discoveries(observation.discoveries)
    resolved_approaching_fixed_point = (
        coordination_snapshot.approaching_fixed_point
        if approaching_fixed_point is None and coordination_snapshot is not None
        else bool(approaching_fixed_point)
    )
    context = (
        dict(coordination_context)
        if coordination_context is not None
        else (
            _coordination_context(coordination_snapshot)
            if coordination_snapshot is not None
            else {}
        )
    )

    return DSECycleBridge(
        cycle_id=cycle_id,
        component=_clean_text(component),
        next_state_type=type(next_state).__name__,
        fitness=float(observation.fitness),
        rv=float(observation.rv),
        discoveries=discoveries,
        discovery_count=len(discoveries),
        observation_depth=max(0, int(observation_depth)),
        has_monadic_observation=int(observation_depth) > 0,
        coordination_available=coordination_snapshot is not None,
        global_truths=(
            coordination_snapshot.global_truths if coordination_snapshot is not None else 0
        ),
        productive_disagreements=(
            coordination_snapshot.productive_disagreements
            if coordination_snapshot is not None
            else 0
        ),
        global_truth_claims=(
            list(coordination_snapshot.global_truth_claims)
            if coordination_snapshot is not None
            else []
        ),
        disagreement_claims=(
            list(coordination_snapshot.disagreement_claims)
            if coordination_snapshot is not None
            else []
        ),
        approaching_fixed_point=resolved_approaching_fixed_point,
        context=context,
    )


def build_dse_cycle_bridge_from_cycle(
    result: CycleResult,
    archive_entries: Sequence[ArchiveEntry] = (),
    proposals: Sequence[Proposal] = (),
    *,
    component: str = "",
    observation_depth: int = 1,
    coordination_snapshot: CoordinationSnapshot | None = None,
    coordination_context: Mapping[str, Any] | None = None,
    approaching_fixed_point: bool | None = None,
) -> DSECycleBridge:
    """Build the bridge artifact directly from one Darwin cycle result."""

    resolved_archive_entries = list(archive_entries)
    resolved_proposals = list(proposals)
    observation = build_evolution_observation(
        result,
        resolved_archive_entries,
        resolved_proposals,
    )
    return build_dse_cycle_bridge(
        observation,
        component=component or _resolve_component(resolved_archive_entries, resolved_proposals),
        observation_depth=observation_depth,
        coordination_snapshot=coordination_snapshot,
        coordination_context=coordination_context,
        approaching_fixed_point=approaching_fixed_point,
    )


__all__ = [
    "CoordinationSnapshot",
    "DSECycleBridge",
    "DSEIntegrator",
    "EvolutionObservation",
    "ObservationWindow",
    "build_dse_cycle_bridge",
    "build_dse_cycle_bridge_from_cycle",
    "build_evolution_observation",
]
