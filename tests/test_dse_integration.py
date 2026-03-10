from __future__ import annotations

import json

import pytest

from dharma_swarm.archive import ArchiveEntry, FitnessScore
from dharma_swarm.coalgebra import EvolutionObservation
from dharma_swarm.dse_integration import DSEIntegrator
from dharma_swarm.evolution import (
    CycleResult,
    DarwinEngine,
    EvolutionPlan,
    EvolutionStatus,
    Proposal,
)
from dharma_swarm.monad import ObservedState


@pytest.fixture
def engine_paths(tmp_path):
    return {
        "archive_path": tmp_path / "archive.jsonl",
        "traces_path": tmp_path / "traces",
        "predictor_path": tmp_path / "predictor.jsonl",
    }


def _proposal(component: str, description: str, *, parent_id: str | None = None) -> Proposal:
    return Proposal(
        component=component,
        change_type="mutation",
        description=description,
        parent_id=parent_id,
        diff="- old\n+ new\n",
        think_notes=(
            "Risk: low. Rollback: revert patch. "
            "Alternatives: no-op. Expected: small improvement."
        ),
    )


async def test_after_cycle_persists_replayable_current_cycle_observation(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )
    parent = ArchiveEntry(
        component="parent.py",
        change_type="mutation",
        description="historic parent",
        diff="- root\n+ parent\n",
        fitness=FitnessScore(correctness=0.9, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )
    current = ArchiveEntry(
        component="child.py",
        change_type="mutation",
        description="current child state",
        parent_id=parent.id,
        diff="- parent\n+ child\n",
        fitness=FitnessScore(correctness=0.4, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )
    result = CycleResult(
        cycle_id="cycle-1",
        proposals_submitted=1,
        proposals_archived=1,
        best_fitness=0.4,
        lessons_learned=["current lesson"],
    )

    snapshot = await integrator.after_cycle(
        result,
        [_proposal("child.py", "current child state", parent_id=parent.id)],
        [current],
    )

    assert snapshot is None

    obs_path = tmp_path / "evolution" / "observations" / "coalgebra_stream.jsonl"
    records = [
        json.loads(line)
        for line in obs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    observed = ObservedState.from_dict(
        records[-1],
        state_loader=EvolutionObservation.from_dict,
    )

    assert observed.state.cycle_id == "cycle-1"
    assert isinstance(observed.state.next_state, ArchiveEntry)
    assert observed.state.next_state.component == "child.py"
    assert observed.state.next_state.parent_id == parent.id
    assert observed.state.archive_entry_id == current.id
    assert "current lesson" in observed.state.discoveries
    assert records[-1]["component"] == "child.py"


async def test_after_cycle_replaces_last_observed_with_current_cycle(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )

    await integrator.after_cycle(
        CycleResult(
            cycle_id="cycle-1",
            proposals_submitted=1,
            proposals_archived=1,
            best_fitness=0.3,
            lessons_learned=["first lesson"],
        ),
        [_proposal("first.py", "first state")],
        [
            ArchiveEntry(
                component="first.py",
                change_type="mutation",
                description="first state",
                diff="- first\n+ first+\n",
                fitness=FitnessScore(correctness=0.3, dharmic_alignment=1.0, safety=1.0),
                status="applied",
            )
        ],
    )
    await integrator.after_cycle(
        CycleResult(
            cycle_id="cycle-2",
            proposals_submitted=1,
            proposals_archived=1,
            best_fitness=0.7,
            lessons_learned=["second lesson"],
        ),
        [_proposal("second.py", "second state")],
        [
            ArchiveEntry(
                component="second.py",
                change_type="mutation",
                description="second state",
                diff="- second\n+ second+\n",
                fitness=FitnessScore(correctness=0.7, dharmic_alignment=1.0, safety=1.0),
                status="applied",
            )
        ],
    )

    obs_path = tmp_path / "evolution" / "observations" / "coalgebra_stream.jsonl"
    records = [
        json.loads(line)
        for line in obs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    observed = ObservedState.from_dict(
        records[-1],
        state_loader=EvolutionObservation.from_dict,
    )

    assert len(records) == 2
    assert observed.state.cycle_id == "cycle-2"
    assert isinstance(observed.state.next_state, ArchiveEntry)
    assert observed.state.next_state.component == "second.py"
    assert records[-1]["observation_depth"] == 1
    assert records[-1]["archive_entry_id"] == observed.state.archive_entry_id


async def test_run_cycle_emits_only_current_cycle_archive_delta(engine_paths, monkeypatch):
    engine = DarwinEngine(**engine_paths)
    await engine.init()
    historic = ArchiveEntry(
        component="historic.py",
        change_type="mutation",
        description="historic best",
        diff="- old\n+ historic\n",
        fitness=FitnessScore(correctness=0.95, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )
    await engine.archive.add_entry(historic)

    proposal = _proposal("current.py", "current cycle state", parent_id=historic.id)
    captured: dict[str, list[str] | str] = {}

    async def fake_plan_cycle(proposals: list[Proposal]) -> EvolutionPlan:
        return EvolutionPlan(ordered_proposal_ids=[proposal.id])

    async def fake_gate_check(p: Proposal) -> Proposal:
        p.status = EvolutionStatus.GATED
        p.gate_decision = "allow"
        return p

    async def fake_evaluate(
        p: Proposal,
        test_results: dict[str, float] | None = None,
        code: str | None = None,
    ) -> Proposal:
        del test_results, code
        p.actual_fitness = FitnessScore(
            correctness=0.4,
            dharmic_alignment=1.0,
            safety=1.0,
        )
        p.status = EvolutionStatus.EVALUATED
        return p

    async def fake_archive_result(p: Proposal) -> str:
        entry = ArchiveEntry(
            component=p.component,
            change_type=p.change_type,
            description=p.description,
            parent_id=p.parent_id,
            diff=p.diff,
            fitness=p.actual_fitness or FitnessScore(),
            status="applied",
        )
        captured["archived_id"] = entry.id
        await engine.archive.add_entry(entry)
        p.status = EvolutionStatus.ARCHIVED
        return entry.id

    async def fake_emit(
        result: CycleResult,
        proposals: list[Proposal],
        new_entries: list[ArchiveEntry],
    ) -> None:
        del result, proposals
        captured["entry_ids"] = [entry.id for entry in new_entries]

    async def noop(*args, **kwargs) -> None:
        del args, kwargs
        return None

    monkeypatch.setattr(engine, "plan_cycle", fake_plan_cycle)
    monkeypatch.setattr(engine, "gate_check", fake_gate_check)
    monkeypatch.setattr(engine, "evaluate", fake_evaluate)
    monkeypatch.setattr(engine, "archive_result", fake_archive_result)
    monkeypatch.setattr(engine, "_update_cycle_dynamics", noop)
    monkeypatch.setattr(engine, "reflect_on_cycle", noop)
    monkeypatch.setattr(engine, "_maybe_run_meta_evolution", noop)
    monkeypatch.setattr(engine, "_emit_coalgebra_observation", fake_emit)

    await engine.run_cycle([proposal])

    assert captured["entry_ids"] == [captured["archived_id"]]
    assert historic.id not in captured["entry_ids"]
