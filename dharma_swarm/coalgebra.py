"""Coalgebraic wrapper over Darwin evolution.

This module exposes evolution as an explicit stream of observations without
rewriting ``evolution.py``. The wrapper treats one Darwin cycle as one
observable transition and reconstructs the emitted state from archive deltas.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Callable, Mapping, Protocol

from pydantic import BaseModel, Field

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.evolution import CycleResult, Proposal
from dharma_swarm.monad import ObservedState, SelfObservationMonad
from dharma_swarm.rv import RVReading

RVObserver = Callable[[CycleResult, list[ArchiveEntry], list[Proposal]], RVReading | None]
DiscoveriesExtractor = Callable[
    [CycleResult, list[ArchiveEntry], list[Proposal]],
    list[str],
]


class DarwinLike(Protocol):
    """Minimal Darwin interface needed by the coalgebra wrapper."""

    archive: EvolutionArchive

    async def run_cycle(self, proposals: list[Proposal]) -> CycleResult:
        ...

    def score_fitness(self, fitness: FitnessScore | None) -> float:
        ...


class EvolutionObservation(BaseModel):
    """Observable output of one evolution step."""

    cycle_id: str = ""
    next_state: ArchiveEntry | dict[str, Any] | None = None
    fitness: FitnessScore = Field(default_factory=FitnessScore)
    rv: RVReading | None = None
    discoveries: list[str] = Field(default_factory=list)
    archive_entry_id: str | None = None
    proposal_ids: list[str] = Field(default_factory=list)
    cycle_result: CycleResult = Field(default_factory=CycleResult)


ObservationIntrospectionBuilder = Callable[[EvolutionObservation], Mapping[str, Any]]


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        text = str(item).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        ordered.append(text)
    return ordered


def _clone_batches(
    proposal_batches: Iterable[Sequence[Proposal]],
    *,
    depth: int | None = None,
) -> list[list[Proposal]]:
    cloned: list[list[Proposal]] = []
    for index, batch in enumerate(proposal_batches):
        if depth is not None and index >= depth:
            break
        cloned.append([proposal.model_copy(deep=True) for proposal in batch])
    return cloned


def normalize_observation(observation: EvolutionObservation) -> dict[str, Any]:
    """Project an observation into a behavior-only comparison shape."""
    next_state = observation.next_state
    if isinstance(next_state, ArchiveEntry):
        normalized_state: dict[str, Any] | None = {
            "component": next_state.component,
            "change_type": next_state.change_type,
            "description": next_state.description,
            "status": next_state.status,
            "parent_id": next_state.parent_id,
        }
    else:
        normalized_state = next_state

    return {
        "next_state": normalized_state,
        "fitness": observation.fitness.model_dump(),
        "rv": (
            None
            if observation.rv is None
            else {
                "rv": observation.rv.rv,
                "pr_early": observation.rv.pr_early,
                "pr_late": observation.rv.pr_late,
                "model_name": observation.rv.model_name,
                "early_layer": observation.rv.early_layer,
                "late_layer": observation.rv.late_layer,
                "prompt_hash": observation.rv.prompt_hash,
                "prompt_group": observation.rv.prompt_group,
            }
        ),
        "discoveries": list(observation.discoveries),
        "proposals_submitted": observation.cycle_result.proposals_submitted,
        "proposals_archived": observation.cycle_result.proposals_archived,
        "best_fitness": observation.cycle_result.best_fitness,
    }


class EvolutionCoalgebra:
    """Expose Darwin cycles as explicit observations."""

    def __init__(
        self,
        engine: DarwinLike,
        *,
        rv_observer: RVObserver | None = None,
        discoveries_extractor: DiscoveriesExtractor | None = None,
    ) -> None:
        self._engine = engine
        self._rv_observer = rv_observer
        self._discoveries_extractor = (
            discoveries_extractor or self._default_discoveries
        )

    @staticmethod
    def _default_discoveries(
        result: CycleResult,
        entries: list[ArchiveEntry],
        proposals: list[Proposal],
    ) -> list[str]:
        return _dedupe_preserve_order(
            [
                *result.lessons_learned,
                *(entry.description for entry in entries),
                *(proposal.description for proposal in proposals),
            ]
        )

    def _score_entry(self, entry: ArchiveEntry) -> float:
        scorer = getattr(self._engine, "score_fitness", None)
        if callable(scorer):
            return float(scorer(entry.fitness))
        return float(entry.fitness.weighted())

    async def _capture_new_entries(
        self,
        proposals: list[Proposal],
    ) -> tuple[CycleResult, list[ArchiveEntry]]:
        before = await self._engine.archive.list_entries()
        before_ids = {entry.id for entry in before}
        result = await self._engine.run_cycle(proposals)
        after = await self._engine.archive.list_entries()
        new_entries = [entry for entry in after if entry.id not in before_ids]
        return result, new_entries

    def _select_next_state(
        self,
        result: CycleResult,
        entries: list[ArchiveEntry],
    ) -> ArchiveEntry | dict[str, Any]:
        if entries:
            return max(entries, key=self._score_entry)
        return {
            "kind": "empty_cycle",
            "cycle_id": result.cycle_id,
            "proposals_submitted": result.proposals_submitted,
            "proposals_archived": result.proposals_archived,
        }

    async def step(self, proposals: Sequence[Proposal]) -> EvolutionObservation:
        batch = [proposal.model_copy(deep=True) for proposal in proposals]
        result, new_entries = await self._capture_new_entries(batch)
        next_state = self._select_next_state(result, new_entries)
        selected_entry = next_state if isinstance(next_state, ArchiveEntry) else None
        rv = (
            self._rv_observer(result, new_entries, batch)
            if self._rv_observer is not None
            else None
        )
        return EvolutionObservation(
            cycle_id=result.cycle_id,
            next_state=next_state,
            fitness=selected_entry.fitness if selected_entry else FitnessScore(),
            rv=rv,
            discoveries=self._discoveries_extractor(result, new_entries, batch),
            archive_entry_id=selected_entry.id if selected_entry else None,
            proposal_ids=[proposal.id for proposal in batch],
            cycle_result=result,
        )

    async def trajectory(
        self,
        proposal_batches: Iterable[Sequence[Proposal]],
        n: int | None = None,
    ) -> list[EvolutionObservation]:
        observations: list[EvolutionObservation] = []
        for index, batch in enumerate(proposal_batches):
            if n is not None and index >= n:
                break
            observations.append(await self.step(batch))
        return observations


class SelfObservedEvolution:
    """Lift an evolution coalgebra into observed evolution steps."""

    def __init__(
        self,
        coalgebra: EvolutionCoalgebra,
        law: "DistributiveLaw",
    ) -> None:
        self._coalgebra = coalgebra
        self._law = law

    async def step(self, proposals: Sequence[Proposal]) -> ObservedState[EvolutionObservation]:
        observation = await self._coalgebra.step(proposals)
        return self._law.distribute(observation)

    async def trajectory(
        self,
        proposal_batches: Iterable[Sequence[Proposal]],
        n: int | None = None,
    ) -> list[ObservedState[EvolutionObservation]]:
        observed: list[ObservedState[EvolutionObservation]] = []
        for index, batch in enumerate(proposal_batches):
            if n is not None and index >= n:
                break
            observed.append(await self.step(batch))
        return observed


class DistributiveLaw:
    """First-pass distributive law TF => FT for observed evolution."""

    def __init__(
        self,
        monad: SelfObservationMonad[EvolutionObservation],
        *,
        introspection_builder: ObservationIntrospectionBuilder | None = None,
    ) -> None:
        self._monad = monad
        self._introspection_builder = (
            introspection_builder or self._default_introspection
        )

    @staticmethod
    def _default_introspection(
        observation: EvolutionObservation,
    ) -> Mapping[str, Any]:
        return {
            "cycle_id": observation.cycle_id,
            "archive_entry_id": observation.archive_entry_id,
            "discoveries": len(observation.discoveries),
            "proposals_archived": observation.cycle_result.proposals_archived,
        }

    def distribute(
        self,
        observation: EvolutionObservation,
    ) -> ObservedState[EvolutionObservation]:
        return self._monad.observe(
            observation,
            introspection=self._introspection_builder(observation),
        )

    def lift(self, coalgebra: EvolutionCoalgebra) -> SelfObservedEvolution:
        return SelfObservedEvolution(coalgebra, self)


async def bisimilar(
    left: EvolutionCoalgebra,
    right: EvolutionCoalgebra,
    proposal_batches: Iterable[Sequence[Proposal]],
    *,
    depth: int = 100,
) -> bool:
    """Compare two coalgebras by their normalized observation streams."""
    batches = _clone_batches(proposal_batches, depth=depth)
    left_observations = await left.trajectory(_clone_batches(batches), n=depth)
    right_observations = await right.trajectory(_clone_batches(batches), n=depth)
    return [normalize_observation(obs) for obs in left_observations] == [
        normalize_observation(obs) for obs in right_observations
    ]


__all__ = [
    "DistributiveLaw",
    "DarwinLike",
    "DiscoveriesExtractor",
    "EvolutionCoalgebra",
    "EvolutionObservation",
    "ObservationIntrospectionBuilder",
    "RVObserver",
    "SelfObservedEvolution",
    "bisimilar",
    "normalize_observation",
]
