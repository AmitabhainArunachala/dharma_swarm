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
ObservationScorer = Callable[[ArchiveEntry], float]
NextState = ArchiveEntry | Proposal | dict[str, Any] | None


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
    next_state: NextState = None
    fitness: FitnessScore = Field(default_factory=FitnessScore)
    rv: RVReading | None = None
    discoveries: list[str] = Field(default_factory=list)
    archive_entry_id: str | None = None
    proposal_ids: list[str] = Field(default_factory=list)
    cycle_result: CycleResult = Field(default_factory=CycleResult)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation of the observation."""
        return {
            "cycle_id": self.cycle_id,
            "next_state": _serialize_next_state(self.next_state),
            "fitness": self.fitness.model_dump(mode="json"),
            "rv": None if self.rv is None else self.rv.model_dump(mode="json"),
            "discoveries": list(self.discoveries),
            "archive_entry_id": self.archive_entry_id,
            "proposal_ids": list(self.proposal_ids),
            "cycle_result": self.cycle_result.model_dump(mode="json"),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvolutionObservation":
        """Rebuild an observation from ``to_dict`` output."""
        raw_fitness = data.get("fitness")
        raw_cycle_result = data.get("cycle_result")
        raw_rv = data.get("rv")
        return cls(
            cycle_id=str(data.get("cycle_id", "")),
            next_state=_deserialize_next_state(data.get("next_state")),
            fitness=(
                FitnessScore()
                if raw_fitness is None
                else FitnessScore.model_validate(raw_fitness)
            ),
            rv=None if raw_rv is None else RVReading.model_validate(raw_rv),
            discoveries=list(data.get("discoveries", [])),
            archive_entry_id=data.get("archive_entry_id"),
            proposal_ids=list(data.get("proposal_ids", [])),
            cycle_result=(
                CycleResult()
                if raw_cycle_result is None
                else CycleResult.model_validate(raw_cycle_result)
            ),
        )


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


def _serialize_next_state(next_state: NextState) -> dict[str, Any] | None:
    if next_state is None:
        return None
    if isinstance(next_state, ArchiveEntry):
        return {
            "kind": "archive_entry",
            "value": next_state.model_dump(mode="json"),
        }
    if isinstance(next_state, Proposal):
        return {
            "kind": "proposal",
            "value": next_state.model_dump(mode="json"),
        }
    if isinstance(next_state, Mapping):
        return {
            "kind": "mapping",
            "value": dict(next_state),
        }
    raise TypeError(f"Unsupported evolution next_state: {type(next_state)!r}")


def _deserialize_next_state(data: Any) -> NextState:
    if data is None:
        return None
    if not isinstance(data, Mapping):
        raise TypeError(f"Serialized next_state must be a mapping, got {type(data)!r}")
    kind = data.get("kind")
    if kind is None:
        return dict(data)
    value = data.get("value")
    if kind == "archive_entry":
        return ArchiveEntry.model_validate(value or {})
    if kind == "proposal":
        return Proposal.model_validate(value or {})
    if kind == "mapping":
        return dict(value or {})
    raise ValueError(f"Unknown serialized next_state kind: {kind}")


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


def _select_next_state(
    result: CycleResult,
    entries: Sequence[ArchiveEntry],
    *,
    score_entry: ObservationScorer,
) -> ArchiveEntry | dict[str, Any]:
    if entries:
        return max(entries, key=score_entry)
    return {
        "kind": "empty_cycle",
        "cycle_id": result.cycle_id,
        "proposals_submitted": result.proposals_submitted,
        "proposals_archived": result.proposals_archived,
    }


def build_evolution_observation(
    result: CycleResult,
    entries: Sequence[ArchiveEntry],
    proposals: Sequence[Proposal],
    *,
    score_entry: ObservationScorer | None = None,
    rv_observer: RVObserver | None = None,
    discoveries_extractor: DiscoveriesExtractor | None = None,
) -> EvolutionObservation:
    """Construct a typed observation from one completed evolution cycle."""
    captured_entries = [entry.model_copy(deep=True) for entry in entries]
    captured_proposals = [proposal.model_copy(deep=True) for proposal in proposals]
    scorer = score_entry or (lambda entry: float(entry.fitness.weighted()))
    next_state = _select_next_state(result, captured_entries, score_entry=scorer)
    selected_entry = next_state if isinstance(next_state, ArchiveEntry) else None
    extractor = discoveries_extractor or _default_discoveries
    return EvolutionObservation(
        cycle_id=result.cycle_id,
        next_state=next_state,
        fitness=selected_entry.fitness if selected_entry else FitnessScore(),
        rv=(
            rv_observer(result, captured_entries, captured_proposals)
            if rv_observer is not None
            else None
        ),
        discoveries=extractor(result, captured_entries, captured_proposals),
        archive_entry_id=selected_entry.id if selected_entry else None,
        proposal_ids=[proposal.id for proposal in captured_proposals],
        cycle_result=result.model_copy(deep=True),
    )


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
    elif isinstance(next_state, Proposal):
        normalized_state = {
            "component": next_state.component,
            "change_type": next_state.change_type,
            "description": next_state.description,
            "parent_id": next_state.parent_id,
            "status": next_state.status.value,
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
        return _select_next_state(result, entries, score_entry=self._score_entry)

    async def step(self, proposals: Sequence[Proposal]) -> EvolutionObservation:
        batch = [proposal.model_copy(deep=True) for proposal in proposals]
        result, new_entries = await self._capture_new_entries(batch)
        return build_evolution_observation(
            result,
            new_entries,
            batch,
            score_entry=self._score_entry,
            rv_observer=self._rv_observer,
            discoveries_extractor=self._discoveries_extractor,
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
    "build_evolution_observation",
    "RVObserver",
    "SelfObservedEvolution",
    "bisimilar",
    "normalize_observation",
]
