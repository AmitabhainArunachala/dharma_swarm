from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.coalgebra import (
    DistributiveLaw,
    EvolutionCoalgebra,
    EvolutionObservation,
    SelfObservedEvolution,
    bisimilar,
)
from dharma_swarm.evolution import CycleResult, DarwinEngine, Proposal
from dharma_swarm.monad import ObservedState, SelfObservationMonad
from dharma_swarm.rv import RVReading


def _ts(second: int) -> datetime:
    return datetime(2026, 3, 10, 0, 0, second, tzinfo=timezone.utc)


def _reading(rv: float) -> RVReading:
    return RVReading(
        rv=rv,
        pr_early=1.0,
        pr_late=rv,
        model_name="coalgebra-test",
        early_layer=1,
        late_layer=2,
        prompt_hash=f"{int(rv * 1000):016d}"[:16],
        prompt_group="coalgebra",
        timestamp=_ts(0),
    )


def _proposal(component: str, description: str) -> Proposal:
    return Proposal(
        component=component,
        change_type="mutation",
        description=description,
        diff="- old\n+ new\n",
        think_notes=(
            "Risk: low. Rollback: revert patch. "
            "Alternatives: no-op. Expected: small improvement."
        ),
    )


class FakeDarwinEngine:
    def __init__(self, archive_path, cycles):
        self.archive = EvolutionArchive(path=archive_path)
        self._cycles = list(cycles)

    async def init(self) -> None:
        await self.archive.load()

    def score_fitness(self, fitness: FitnessScore | None) -> float:
        return 0.0 if fitness is None else fitness.correctness

    async def run_cycle(self, proposals: list[Proposal]) -> CycleResult:
        spec = self._cycles.pop(0)
        scores = list(spec.get("scores", []))
        descriptions = spec.get("descriptions")
        archived = 0
        for index, score in enumerate(scores):
            proposal = proposals[index]
            entry = ArchiveEntry(
                component=proposal.component,
                change_type=proposal.change_type,
                description=(
                    descriptions[index]
                    if descriptions is not None
                    else proposal.description
                ),
                parent_id=proposal.parent_id,
                diff=proposal.diff,
                fitness=FitnessScore(
                    correctness=score,
                    dharmic_alignment=1.0,
                    safety=1.0,
                ),
                status="applied",
            )
            await self.archive.add_entry(entry)
            archived += 1

        return CycleResult(
            cycle_id=spec.get("cycle_id", f"cycle-{len(scores)}"),
            proposals_submitted=len(proposals),
            proposals_gated=archived,
            proposals_tested=archived,
            proposals_archived=archived,
            best_fitness=max(scores, default=0.0),
            lessons_learned=list(spec.get("lessons", [])),
        )


@pytest.fixture
def engine_paths(tmp_path):
    return {
        "archive_path": tmp_path / "archive.jsonl",
        "traces_path": tmp_path / "traces",
        "predictor_path": tmp_path / "predictor.jsonl",
    }


async def test_step_selects_best_new_archive_entry(tmp_path):
    engine = FakeDarwinEngine(
        tmp_path / "archive.jsonl",
        [
            {
                "cycle_id": "cycle-a",
                "scores": [0.4, 0.9],
                "lessons": ["prefer smaller diff"],
            }
        ],
    )
    await engine.init()
    coalgebra = EvolutionCoalgebra(
        engine,
        rv_observer=lambda result, entries, proposals: _reading(float(len(entries)) / 10.0),
    )

    observation = await coalgebra.step(
        [
            _proposal("a.py", "first change"),
            _proposal("b.py", "second change"),
        ]
    )

    assert observation.cycle_id == "cycle-a"
    assert isinstance(observation.next_state, ArchiveEntry)
    assert observation.next_state.component == "b.py"
    assert observation.fitness.correctness == pytest.approx(0.9)
    assert observation.rv == _reading(0.2)
    assert "prefer smaller diff" in observation.discoveries
    assert "first change" in observation.discoveries
    assert "second change" in observation.discoveries


async def test_trajectory_emits_ordered_observations(tmp_path):
    engine = FakeDarwinEngine(
        tmp_path / "archive.jsonl",
        [
            {"cycle_id": "cycle-1", "scores": [0.3]},
            {"cycle_id": "cycle-2", "scores": [0.8]},
        ],
    )
    await engine.init()
    coalgebra = EvolutionCoalgebra(engine)

    observations = await coalgebra.trajectory(
        [
            [_proposal("one.py", "first")],
            [_proposal("two.py", "second")],
        ]
    )

    assert [obs.cycle_id for obs in observations] == ["cycle-1", "cycle-2"]
    assert isinstance(observations[0].next_state, ArchiveEntry)
    assert observations[0].next_state.component == "one.py"
    assert observations[1].next_state.component == "two.py"


async def test_bisimilar_true_for_equivalent_streams(tmp_path):
    left_engine = FakeDarwinEngine(
        tmp_path / "left.jsonl",
        [
            {"cycle_id": "left-1", "scores": [0.5], "lessons": ["steady"]},
            {"cycle_id": "left-2", "scores": [0.7], "lessons": ["improve"]},
        ],
    )
    right_engine = FakeDarwinEngine(
        tmp_path / "right.jsonl",
        [
            {"cycle_id": "right-1", "scores": [0.5], "lessons": ["steady"]},
            {"cycle_id": "right-2", "scores": [0.7], "lessons": ["improve"]},
        ],
    )
    await left_engine.init()
    await right_engine.init()

    left = EvolutionCoalgebra(left_engine)
    right = EvolutionCoalgebra(right_engine)

    assert await bisimilar(
        left,
        right,
        [
            [_proposal("x.py", "steady")],
            [_proposal("y.py", "improve")],
        ],
    ) is True


async def test_bisimilar_false_when_behavior_changes(tmp_path):
    left_engine = FakeDarwinEngine(
        tmp_path / "left.jsonl",
        [{"cycle_id": "left-1", "scores": [0.5], "lessons": ["steady"]}],
    )
    right_engine = FakeDarwinEngine(
        tmp_path / "right.jsonl",
        [{"cycle_id": "right-1", "scores": [0.1], "lessons": ["steady"]}],
    )
    await left_engine.init()
    await right_engine.init()

    left = EvolutionCoalgebra(left_engine)
    right = EvolutionCoalgebra(right_engine)

    assert await bisimilar(
        left,
        right,
        [[_proposal("x.py", "steady")]],
    ) is False


async def test_step_wraps_real_darwin_engine_archive(engine_paths, monkeypatch):
    engine = DarwinEngine(**engine_paths)
    await engine.init()

    async def fake_run_cycle(proposals: list[Proposal]) -> CycleResult:
        for proposal in proposals:
            await engine.archive.add_entry(
                ArchiveEntry(
                    component=proposal.component,
                    change_type=proposal.change_type,
                    description=proposal.description,
                    diff=proposal.diff,
                    fitness=FitnessScore(
                        correctness=0.9,
                        dharmic_alignment=1.0,
                        safety=1.0,
                    ),
                    status="applied",
                )
            )
        return CycleResult(
            cycle_id="real-cycle",
            proposals_submitted=len(proposals),
            proposals_gated=len(proposals),
            proposals_tested=len(proposals),
            proposals_archived=len(proposals),
            best_fitness=0.9,
            lessons_learned=["wrapped real engine"],
        )

    monkeypatch.setattr(engine, "run_cycle", fake_run_cycle)
    coalgebra = EvolutionCoalgebra(engine)

    observation = await coalgebra.step([_proposal("real.py", "real step")])

    assert observation.cycle_id == "real-cycle"
    assert isinstance(observation.next_state, ArchiveEntry)
    assert observation.next_state.component == "real.py"
    assert observation.archive_entry_id is not None
    assert observation.fitness.correctness == pytest.approx(0.9)
    assert "wrapped real engine" in observation.discoveries


async def test_distributive_law_wraps_observation_with_introspection(tmp_path):
    engine = FakeDarwinEngine(
        tmp_path / "archive.jsonl",
        [{"cycle_id": "cycle-law", "scores": [0.6], "lessons": ["watch drift"]}],
    )
    await engine.init()
    coalgebra = EvolutionCoalgebra(
        engine,
        rv_observer=lambda result, entries, proposals: _reading(0.6),
    )
    monad = SelfObservationMonad[EvolutionObservation](observer=lambda observation: observation.rv)
    law = DistributiveLaw(monad)

    observed = law.distribute(await coalgebra.step([_proposal("law.py", "law step")]))

    assert isinstance(observed, ObservedState)
    assert observed.observation_depth == 1
    assert observed.rv_reading == _reading(0.6)
    assert observed.introspection["cycle_id"] == "cycle-law"
    assert observed.introspection["discoveries"] >= 1


async def test_distributive_law_lift_creates_self_observed_evolution(tmp_path):
    engine = FakeDarwinEngine(
        tmp_path / "archive.jsonl",
        [{"cycle_id": "cycle-lift", "scores": [0.8], "lessons": ["lifted"]}],
    )
    await engine.init()
    coalgebra = EvolutionCoalgebra(
        engine,
        rv_observer=lambda result, entries, proposals: _reading(0.8),
    )
    monad = SelfObservationMonad[EvolutionObservation](observer=lambda observation: observation.rv)
    observed_evolution = DistributiveLaw(monad).lift(coalgebra)

    assert isinstance(observed_evolution, SelfObservedEvolution)

    observed = await observed_evolution.step([_proposal("lift.py", "lift step")])

    assert observed.state.cycle_id == "cycle-lift"
    assert observed.rv_reading == _reading(0.8)
    assert observed.introspection["archive_entry_id"] is not None
