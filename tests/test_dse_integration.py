from __future__ import annotations

import json

import pytest

from dharma_swarm.archive import ArchiveEntry, FitnessScore
from dharma_swarm.bridge import ResearchBridge
from dharma_swarm.coalgebra import EvolutionObservation
from dharma_swarm.dse_integration import (
    CoordinationSnapshot,
    DSEIntegrator,
    ObservationWindow,
)
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


def test_observation_window_preserves_zero_metric_values():
    window = ObservationWindow(max_size=5)

    window.append({"cycle_id": "c1", "rv": 0.0, "best_fitness": 0.0})
    window.append({"cycle_id": "c2", "rv": 0.2, "best_fitness": 0.4})

    assert window.rv_trajectory == [0.0, 0.2]
    assert window.fitness_trajectory == [0.0, 0.4]
    assert window.rv_trend == pytest.approx(0.2)
    assert window.fitness_trend == pytest.approx(0.4)


def test_observation_window_trim_drops_stale_metrics_from_trimmed_records():
    window = ObservationWindow(max_size=2)

    window.append({"cycle_id": "c1", "rv": 0.9, "best_fitness": 0.8})
    window.append({"cycle_id": "c2"})
    window.append({"cycle_id": "c3", "rv": 0.0, "best_fitness": 0.0})

    assert [record["cycle_id"] for record in window.observations] == ["c2", "c3"]
    assert window.rv_trajectory == [0.0]
    assert window.fitness_trajectory == [0.0]
    assert window.rv_trend is None
    assert window.fitness_trend is None


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
    record = records[-1]

    assert record["cycle_id"] == "cycle-1"
    assert record["best_fitness"] == 0.4
    assert "current lesson" in record.get("lessons", [])
    assert record["observation_depth"] == 1
    assert record.get("rv_measurement") is not None


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

    assert len(records) == 2
    assert records[-1]["cycle_id"] == "cycle-2"
    assert records[-1]["best_fitness"] == 0.7
    assert records[-1]["observation_depth"] == 1


def test_compose_cycle_text_dedupes_repeated_discoveries_and_lessons():
    result = CycleResult(
        cycle_id="cycle-compose",
        reflection="Reflection on the cycle",
        lessons_learned=["current lesson", "proposal description"],
    )
    observation = EvolutionObservation(
        next_state=result,
        fitness=0.5,
        rv=0.8,
        discoveries=[
            "current lesson",
            "child archive state",
            "proposal description",
            "Reflection on the cycle",
        ],
    )

    assert DSEIntegrator._compose_cycle_text(result, observation) == (
        "current lesson\nchild archive state\nproposal description\n"
        "Reflection on the cycle"
    )


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


async def test_after_cycle_persists_ouroboros_summary_to_observation_log(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )

    class _FakeOuroboros:
        def __init__(self) -> None:
            self.calls: list[dict[str, str]] = []

        def observe_cycle_text(
            self,
            text: str,
            *,
            cycle_id: str = "",
            source: str = "evolution",
        ) -> dict[str, object]:
            self.calls.append(
                {
                    "text": text,
                    "cycle_id": cycle_id,
                    "source": source,
                }
            )
            return {
                "signature": {
                    "recognition_type": "genuine",
                    "swabhaav_ratio": 0.72,
                },
                "is_mimicry": False,
                "is_genuine": True,
            }

    fake_ouroboros = _FakeOuroboros()
    integrator._ouroboros = fake_ouroboros

    current = ArchiveEntry(
        component="child.py",
        change_type="mutation",
        description="child archive state",
        diff="- parent\n+ child\n",
        fitness=FitnessScore(correctness=0.4, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )
    result = CycleResult(
        cycle_id="cycle-ouroboros",
        proposals_submitted=1,
        proposals_archived=1,
        best_fitness=0.4,
        reflection="Reflection on the cycle",
        lessons_learned=["current lesson"],
    )

    await integrator.after_cycle(
        result,
        [_proposal("child.py", "proposal description")],
        [current],
    )

    assert fake_ouroboros.calls == [
        {
            "text": (
                "current lesson\nchild archive state\nproposal description\n"
                "Reflection on the cycle"
            ),
            "cycle_id": "cycle-ouroboros",
            "source": "dse_integration",
        }
    ]
    assert integrator._window.observations[-1]["ouroboros"] == {
        "recognition_type": "genuine",
        "swabhaav_ratio": 0.72,
        "is_mimicry": False,
        "is_genuine": True,
    }

    obs_path = tmp_path / "evolution" / "observations" / "coalgebra_stream.jsonl"
    persisted = [
        json.loads(line)
        for line in obs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert persisted[-1]["ouroboros"] == {
        "recognition_type": "genuine",
        "swabhaav_ratio": 0.72,
        "is_mimicry": False,
        "is_genuine": True,
    }


async def test_after_cycle_persists_l4_bridge_measurement(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )

    class _FakeOuroboros:
        def observe_cycle_text(
            self,
            text: str,
            *,
            cycle_id: str = "",
            source: str = "evolution",
        ) -> dict[str, object]:
            del text, cycle_id, source
            return {
                "signature": {
                    "recognition_type": "GENUINE",
                    "swabhaav_ratio": 0.72,
                },
                "is_mimicry": False,
                "is_genuine": True,
            }

    integrator._ouroboros = _FakeOuroboros()

    current = ArchiveEntry(
        component="child.py",
        change_type="mutation",
        description="child archive state",
        diff="- parent\n+ child\n",
        fitness=FitnessScore(correctness=0.4, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )
    result = CycleResult(
        cycle_id="cycle-bridge",
        proposals_submitted=1,
        proposals_archived=1,
        best_fitness=0.4,
        reflection="Reflection on the cycle",
        lessons_learned=["current lesson"],
    )

    await integrator.after_cycle(
        result,
        [_proposal("child.py", "proposal description")],
        [current],
    )

    assert integrator._window.observations[-1]["l4_correlation"] == {
        "swabhaav_ratio": 0.72,
        "recognition_type": "GENUINE",
        "is_l4_like": True,
        "bridge_group": "dse_l4_like",
    }

    bridge_path = tmp_path / "evolution" / "observations" / "bridge_data.jsonl"
    measurements = [
        json.loads(line)
        for line in bridge_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert len(measurements) == 1
    assert measurements[0]["prompt_text"] == "dse_cycle:cycle-bridge:child.py"
    assert measurements[0]["prompt_group"] == "dse_l4_like"
    assert measurements[0]["generated_text"] == (
        "current lesson\nchild archive state\nproposal description\n"
        "Reflection on the cycle"
    )
    assert measurements[0]["rv_reading"]["rv"] == pytest.approx(0.9)


async def test_after_cycle_persists_reciprocity_summary_to_observation_log(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )
    integrator._reciprocity_enabled = True

    class _FakeReciprocity:
        def __init__(self) -> None:
            self.calls = 0

        async def ledger_summary(self) -> dict[str, object]:
            self.calls += 1
            return {
                "service": "reciprocity_commons",
                "summary_type": "ledger_summary",
                "actors": 2,
                "activities": 1,
                "projects": 1,
                "obligations": 3,
                "active_obligations": 2,
                "challenged_claims": 1,
                "invariant_issues": 2,
                "chain_valid": False,
                "total_obligation_usd": 25000,
                "total_routed_usd": 5000,
                "issues": [
                    {"code": "routing_missing_project"},
                    {"code": "verified_ecology_missing_audit"},
                ],
            }

    fake_reciprocity = _FakeReciprocity()
    integrator._reciprocity = fake_reciprocity

    current = ArchiveEntry(
        component="child.py",
        change_type="mutation",
        description="child archive state",
        diff="- parent\n+ child\n",
        fitness=FitnessScore(correctness=0.4, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )

    await integrator.after_cycle(
        CycleResult(
            cycle_id="cycle-reciprocity",
            proposals_submitted=1,
            proposals_archived=1,
            best_fitness=0.4,
            reflection="Reflection on the cycle",
            lessons_learned=["current lesson"],
        ),
        [_proposal("child.py", "proposal description")],
        [current],
    )

    assert fake_reciprocity.calls == 1
    assert integrator._window.observations[-1]["reciprocity"] == {
        "source": "reciprocity_commons",
        "summary_type": "ledger_summary",
        "actors": 2,
        "activities": 1,
        "projects": 1,
        "obligations": 3,
        "active_obligations": 2,
        "challenged_claims": 1,
        "invariant_issues": 2,
        "chain_valid": False,
        "total_obligation_usd": 25000.0,
        "total_routed_usd": 5000.0,
        "issue_codes": [
            "routing_missing_project",
            "verified_ecology_missing_audit",
        ],
    }

    obs_path = tmp_path / "evolution" / "observations" / "coalgebra_stream.jsonl"
    persisted = [
        json.loads(line)
        for line in obs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert persisted[-1]["reciprocity"] == integrator._window.observations[-1]["reciprocity"]


async def test_after_cycle_omits_invalid_reciprocity_summary_from_observation_log(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )
    integrator._reciprocity_enabled = True

    class _BadReciprocity:
        async def ledger_summary(self) -> dict[str, object]:
            return {
                "service": "reciprocity_commons",
                "summary_type": "ledger_summary",
                "actors": 2,
                "activities": 1,
                "projects": 1,
                "obligations": 3,
                "active_obligations": 2,
                "challenged_claims": 0,
                "invariant_issues": 0,
                "chain_valid": "true",
                "total_obligation_usd": 25000,
                "total_routed_usd": 5000,
            }

    integrator._reciprocity = _BadReciprocity()

    current = ArchiveEntry(
        component="child.py",
        change_type="mutation",
        description="child archive state",
        diff="- parent\n+ child\n",
        fitness=FitnessScore(correctness=0.4, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )

    await integrator.after_cycle(
        CycleResult(
            cycle_id="cycle-invalid-reciprocity",
            proposals_submitted=1,
            proposals_archived=1,
            best_fitness=0.4,
            reflection="Reflection on the cycle",
            lessons_learned=["current lesson"],
        ),
        [_proposal("child.py", "proposal description")],
        [current],
    )

    assert "reciprocity" not in integrator._window.observations[-1]
    assert integrator._last_reciprocity_summary is None
    assert integrator._last_reciprocity_error == "chain_valid must be a boolean"

    obs_path = tmp_path / "evolution" / "observations" / "coalgebra_stream.jsonl"
    persisted = [
        json.loads(line)
        for line in obs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "reciprocity" not in persisted[-1]


async def test_after_cycle_marks_reciprocity_summary_stale_when_refresh_is_invalid(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
        reciprocity_interval=1,
    )
    integrator._reciprocity_enabled = True

    class _FlakyReciprocity:
        def __init__(self) -> None:
            self.calls = 0

        async def ledger_summary(self) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                return {
                    "service": "reciprocity_commons",
                    "summary_type": "ledger_summary",
                    "actors": 2,
                    "activities": 1,
                    "projects": 1,
                    "obligations": 3,
                    "active_obligations": 2,
                    "challenged_claims": 1,
                    "invariant_issues": 0,
                    "chain_valid": True,
                    "total_obligation_usd": 25000,
                    "total_routed_usd": 5000,
                    "issues": [],
                }
            return {
                "service": "reciprocity_commons",
                "summary_type": "ledger_summary",
                "actors": 2,
                "activities": 1,
                "projects": 1,
                "obligations": 3,
                "active_obligations": 2,
                "challenged_claims": 1,
                "invariant_issues": 0,
                "chain_valid": True,
                "total_obligation_usd": 25000,
                "total_routed_usd": "nan",
                "issues": [],
            }

    flaky = _FlakyReciprocity()
    integrator._reciprocity = flaky

    current = ArchiveEntry(
        component="child.py",
        change_type="mutation",
        description="child archive state",
        diff="- parent\n+ child\n",
        fitness=FitnessScore(correctness=0.4, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )
    proposal = _proposal("child.py", "proposal description")

    await integrator.after_cycle(
        CycleResult(
            cycle_id="cycle-reciprocity-valid",
            proposals_submitted=1,
            proposals_archived=1,
            best_fitness=0.4,
            reflection="Reflection on the cycle",
            lessons_learned=["current lesson"],
        ),
        [proposal],
        [current],
    )
    await integrator.after_cycle(
        CycleResult(
            cycle_id="cycle-reciprocity-stale",
            proposals_submitted=1,
            proposals_archived=1,
            best_fitness=0.45,
            reflection="Reflection on the cycle again",
            lessons_learned=["current lesson again"],
        ),
        [proposal],
        [current],
    )

    assert flaky.calls == 2
    assert integrator._last_reciprocity_summary == {
        "source": "reciprocity_commons",
        "summary_type": "ledger_summary",
        "actors": 2,
        "activities": 1,
        "projects": 1,
        "obligations": 3,
        "active_obligations": 2,
        "challenged_claims": 1,
        "invariant_issues": 0,
        "chain_valid": True,
        "total_obligation_usd": 25000.0,
        "total_routed_usd": 5000.0,
        "issue_codes": [],
    }
    assert integrator._last_reciprocity_error == "total_routed_usd must be a finite number >= 0"
    assert integrator._window.observations[-1]["reciprocity"] == {
        "source": "reciprocity_commons",
        "summary_type": "ledger_summary",
        "actors": 2,
        "activities": 1,
        "projects": 1,
        "obligations": 3,
        "active_obligations": 2,
        "challenged_claims": 1,
        "invariant_issues": 0,
        "chain_valid": True,
        "total_obligation_usd": 25000.0,
        "total_routed_usd": 5000.0,
        "issue_codes": [],
        "stale": True,
    }

    obs_path = tmp_path / "evolution" / "observations" / "coalgebra_stream.jsonl"
    persisted = [
        json.loads(line)
        for line in obs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert persisted[-1]["reciprocity"] == integrator._window.observations[-1]["reciprocity"]


async def test_after_cycle_records_canonical_evaluations_when_binding_available(tmp_path):
    class _FakeOuroboros:
        def observe_cycle_text(
            self,
            text: str,
            *,
            cycle_id: str = "",
            source: str = "evolution",
        ) -> dict[str, object]:
            del text, source
            return {
                "cycle_id": cycle_id,
                "source": "dse_integration",
                "signature": {
                    "recognition_type": "GENUINE",
                    "swabhaav_ratio": 0.81,
                    "entropy": 0.93,
                    "complexity": 0.58,
                    "self_reference_density": 0.04,
                    "identity_stability": 0.71,
                    "paradox_tolerance": 0.64,
                    "word_count": 24,
                },
                "modifiers": {
                    "quality": 0.91,
                    "mimicry_penalty": 1.0,
                    "recognition_bonus": 1.15,
                    "witness_score": 0.81,
                },
                "is_mimicry": False,
                "is_genuine": True,
            }

    class _FakeReciprocity:
        async def ledger_summary(self) -> dict[str, object]:
            return {
                "service": "reciprocity_commons",
                "summary_type": "ledger_summary",
                "actors": 2,
                "activities": 1,
                "projects": 1,
                "obligations": 3,
                "active_obligations": 2,
                "challenged_claims": 1,
                "invariant_issues": 0,
                "chain_valid": True,
                "total_obligation_usd": 25000,
                "total_routed_usd": 5000,
                "issues": [],
            }

    class _FakeArtifact:
        def __init__(self, artifact_id: str) -> None:
            self.artifact_id = artifact_id

    class _FakeFact:
        def __init__(self, fact_id: str) -> None:
            self.fact_id = fact_id

    class _FakeResult:
        def __init__(self, artifact_id: str, event_id: str, summary: dict[str, object]) -> None:
            self.artifact = _FakeArtifact(artifact_id)
            self.facts = [_FakeFact(f"fact-{artifact_id}")]
            self.receipt = {"event_id": event_id}
            self.summary = summary

    class _FakeRegistry:
        def __init__(self) -> None:
            self.ouroboros_calls: list[dict[str, object]] = []
            self.reciprocity_calls: list[dict[str, object]] = []

        async def record_ouroboros_observation(self, payload, **kwargs):
            self.ouroboros_calls.append({"payload": payload, "kwargs": kwargs})
            return _FakeResult(
                "art-ouro",
                "evt-ouro",
                {"cycle_id": payload["cycle_id"], "recognition_type": "GENUINE"},
            )

        async def record_reciprocity_summary(self, payload, **kwargs):
            self.reciprocity_calls.append({"payload": payload, "kwargs": kwargs})
            return _FakeResult(
                "art-recip",
                "evt-recip",
                {"source": payload["source"], "summary_type": payload["summary_type"]},
            )

    registry = _FakeRegistry()
    integrator = DSEIntegrator(
        archive_path=tmp_path / "runtime-root" / "evolution",
        coordination_interval=10,
        evaluation_registry=registry,
    )
    integrator._ouroboros = _FakeOuroboros()
    integrator._reciprocity_enabled = True
    integrator._reciprocity = _FakeReciprocity()

    proposal = _proposal("child.py", "proposal description")
    proposal.metadata = {
        "session_id": "sess-canonical",
        "task_id": "task-canonical",
        "trace_id": "trace-canonical",
    }
    current = ArchiveEntry(
        component="child.py",
        change_type="mutation",
        description="child archive state",
        diff="- parent\n+ child\n",
        fitness=FitnessScore(correctness=0.4, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )

    await integrator.after_cycle(
        CycleResult(
            cycle_id="cycle-canonical",
            proposals_submitted=1,
            proposals_archived=1,
            best_fitness=0.4,
            reflection="Reflection on the cycle",
            lessons_learned=["current lesson"],
        ),
        [proposal],
        [current],
    )

    assert registry.ouroboros_calls == [
        {
            "payload": {
                "cycle_id": "cycle-canonical",
                "source": "dse_integration",
                "signature": {
                    "recognition_type": "GENUINE",
                    "swabhaav_ratio": 0.81,
                    "entropy": 0.93,
                    "complexity": 0.58,
                    "self_reference_density": 0.04,
                    "identity_stability": 0.71,
                    "paradox_tolerance": 0.64,
                    "word_count": 24,
                },
                "modifiers": {
                    "quality": 0.91,
                    "mimicry_penalty": 1.0,
                    "recognition_bonus": 1.15,
                    "witness_score": 0.81,
                },
                "is_mimicry": False,
                "is_genuine": True,
            },
            "kwargs": {
                "run_id": "",
                "session_id": "sess-canonical",
                "task_id": "task-canonical",
                "trace_id": "trace-canonical",
                "created_by": "dse.integration",
            },
        }
    ]
    assert registry.reciprocity_calls == [
        {
            "payload": {
                "source": "reciprocity_commons",
                "summary_type": "ledger_summary",
                "actors": 2,
                "activities": 1,
                "projects": 1,
                "obligations": 3,
                "active_obligations": 2,
                "challenged_claims": 1,
                "invariant_issues": 0,
                "chain_valid": True,
                "total_obligation_usd": 25000.0,
                "total_routed_usd": 5000.0,
                "issue_codes": [],
            },
            "kwargs": {
                "run_id": "",
                "session_id": "sess-canonical",
                "task_id": "task-canonical",
                "trace_id": "trace-canonical",
                "created_by": "dse.integration",
            },
        }
    ]
    assert integrator._window.observations[-1]["canonical_evaluations"] == {
        "binding": {
            "run_id": "",
            "session_id": "sess-canonical",
            "task_id": "task-canonical",
            "trace_id": "trace-canonical",
        },
        "ouroboros": {
            "artifact_id": "art-ouro",
            "fact_ids": ["fact-art-ouro"],
            "receipt_event_id": "evt-ouro",
            "summary": {
                "cycle_id": "cycle-canonical",
                "recognition_type": "GENUINE",
            },
        },
        "reciprocity": {
            "artifact_id": "art-recip",
            "fact_ids": ["fact-art-recip"],
            "receipt_event_id": "evt-recip",
            "summary": {
                "source": "reciprocity_commons",
                "summary_type": "ledger_summary",
            },
        },
    }

    obs_path = (
        tmp_path
        / "runtime-root"
        / "evolution"
        / "observations"
        / "coalgebra_stream.jsonl"
    )
    persisted = [
        json.loads(line)
        for line in obs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert persisted[-1]["canonical_evaluations"] == (
        integrator._window.observations[-1]["canonical_evaluations"]
    )


async def test_after_cycle_builds_lazy_registry_paths_from_archive_root(tmp_path, monkeypatch):
    seen: dict[str, object] = {}

    class _FakeRuntimeState:
        def __init__(self, db_path):
            seen["runtime_db_path"] = db_path
            self.db_path = db_path

    class _FakeMemoryLattice:
        def __init__(self, *, db_path, event_log_dir=None):
            seen["memory_db_path"] = db_path
            seen["event_log_dir"] = event_log_dir

    class _FakeRegistry:
        def __init__(
            self,
            *,
            runtime_state,
            memory_lattice,
            workspace_root=None,
            provenance_root=None,
        ):
            seen["runtime_state"] = runtime_state
            seen["memory_lattice"] = memory_lattice
            seen["workspace_root"] = workspace_root
            seen["provenance_root"] = provenance_root

        async def record_ouroboros_observation(self, payload, **kwargs):
            seen["record_payload"] = payload
            seen["record_kwargs"] = kwargs

            class _Artifact:
                artifact_id = "art-lazy"

            class _Fact:
                fact_id = "fact-lazy"

            class _Result:
                artifact = _Artifact()
                facts = [_Fact()]
                receipt = {"event_id": "evt-lazy"}
                summary = {"cycle_id": payload["cycle_id"]}

            return _Result()

    class _FakeOuroboros:
        def observe_cycle_text(
            self,
            text: str,
            *,
            cycle_id: str = "",
            source: str = "evolution",
        ) -> dict[str, object]:
            del text, source
            return {
                "cycle_id": cycle_id,
                "source": "dse_integration",
                "signature": {
                    "recognition_type": "GENUINE",
                    "swabhaav_ratio": 0.7,
                    "entropy": 0.9,
                    "complexity": 0.5,
                    "self_reference_density": 0.03,
                    "identity_stability": 0.6,
                    "paradox_tolerance": 0.5,
                    "word_count": 12,
                },
                "modifiers": {
                    "quality": 0.88,
                    "mimicry_penalty": 1.0,
                    "recognition_bonus": 1.15,
                    "witness_score": 0.7,
                },
                "is_mimicry": False,
                "is_genuine": True,
            }

    monkeypatch.setattr("dharma_swarm.runtime_state.RuntimeStateStore", _FakeRuntimeState)
    monkeypatch.setattr("dharma_swarm.memory_lattice.MemoryLattice", _FakeMemoryLattice)
    monkeypatch.setattr("dharma_swarm.evaluation_registry.EvaluationRegistry", _FakeRegistry)

    integrator = DSEIntegrator(
        archive_path=tmp_path / "runtime-root" / "evolution",
        coordination_interval=10,
    )
    integrator._ouroboros = _FakeOuroboros()

    proposal = _proposal("child.py", "proposal description")
    proposal.metadata = {"session_id": "sess-lazy"}
    current = ArchiveEntry(
        component="child.py",
        change_type="mutation",
        description="child archive state",
        diff="- parent\n+ child\n",
        fitness=FitnessScore(correctness=0.4, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )

    await integrator.after_cycle(
        CycleResult(
            cycle_id="cycle-lazy",
            proposals_submitted=1,
            proposals_archived=1,
            best_fitness=0.4,
            reflection="Reflection on the cycle",
            lessons_learned=["current lesson"],
        ),
        [proposal],
        [current],
    )

    expected_root = tmp_path / "runtime-root"
    assert seen["runtime_db_path"] == expected_root / "state" / "runtime.db"
    assert seen["memory_db_path"] == expected_root / "state" / "runtime.db"
    assert seen["event_log_dir"] == expected_root / "events"
    assert seen["workspace_root"] == expected_root / "workspace" / "sessions"
    assert seen["provenance_root"] == expected_root / "workspace" / "sessions"
    assert seen["record_kwargs"] == {
        "run_id": "",
        "session_id": "sess-lazy",
        "task_id": "",
        "trace_id": None,
        "created_by": "dse.integration",
    }


async def test_after_cycle_skips_canonical_recording_for_ambiguous_binding(tmp_path):
    class _FakeRegistry:
        def __init__(self) -> None:
            self.calls = 0

        async def record_ouroboros_observation(self, payload, **kwargs):
            del payload, kwargs
            self.calls += 1
            raise AssertionError("registry should not be called")

    class _FakeOuroboros:
        def observe_cycle_text(
            self,
            text: str,
            *,
            cycle_id: str = "",
            source: str = "evolution",
        ) -> dict[str, object]:
            del text, cycle_id, source
            return {
                "signature": {
                    "recognition_type": "GENUINE",
                    "swabhaav_ratio": 0.72,
                },
                "modifiers": {
                    "quality": 0.9,
                    "mimicry_penalty": 1.0,
                    "recognition_bonus": 1.15,
                    "witness_score": 0.72,
                },
                "is_mimicry": False,
                "is_genuine": True,
            }

    registry = _FakeRegistry()
    integrator = DSEIntegrator(
        archive_path=tmp_path / "runtime-root" / "evolution",
        coordination_interval=10,
        evaluation_registry=registry,
    )
    integrator._ouroboros = _FakeOuroboros()

    first = _proposal("child.py", "proposal description")
    first.metadata = {"session_id": "sess-a"}
    second = _proposal("child.py", "proposal description 2")
    second.metadata = {"session_id": "sess-b"}
    current = ArchiveEntry(
        component="child.py",
        change_type="mutation",
        description="child archive state",
        diff="- parent\n+ child\n",
        fitness=FitnessScore(correctness=0.4, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )

    await integrator.after_cycle(
        CycleResult(
            cycle_id="cycle-ambiguous",
            proposals_submitted=2,
            proposals_archived=1,
            best_fitness=0.4,
            reflection="Reflection on the cycle",
            lessons_learned=["current lesson"],
        ),
        [first, second],
        [current],
    )

    assert registry.calls == 0
    assert "canonical_evaluations" not in integrator._window.observations[-1]


async def test_after_cycle_appends_to_existing_bridge_history(tmp_path):
    bridge_path = tmp_path / "evolution" / "observations" / "bridge_data.jsonl"
    seed_bridge = ResearchBridge(data_path=bridge_path)
    await seed_bridge.add_measurement(
        prompt_text="seed prompt",
        prompt_group="seed",
        generated_text="seed output",
    )

    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )

    class _FakeOuroboros:
        def observe_cycle_text(
            self,
            text: str,
            *,
            cycle_id: str = "",
            source: str = "evolution",
        ) -> dict[str, object]:
            del text, cycle_id, source
            return {
                "signature": {
                    "recognition_type": "GENUINE",
                    "swabhaav_ratio": 0.81,
                },
                "is_mimicry": False,
                "is_genuine": True,
            }

    integrator._ouroboros = _FakeOuroboros()

    current = ArchiveEntry(
        component="child.py",
        change_type="mutation",
        description="child archive state",
        diff="- parent\n+ child\n",
        fitness=FitnessScore(correctness=0.4, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )

    await integrator.after_cycle(
        CycleResult(
            cycle_id="cycle-append",
            proposals_submitted=1,
            proposals_archived=1,
            best_fitness=0.4,
            reflection="Reflection on the cycle",
            lessons_learned=["current lesson"],
        ),
        [_proposal("child.py", "proposal description")],
        [current],
    )

    measurements = [
        json.loads(line)
        for line in bridge_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert [measurement["prompt_text"] for measurement in measurements] == [
        "seed prompt",
        "dse_cycle:cycle-append:child.py",
    ]


def test_get_coordination_context_includes_ouroboros_warning(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )
    integrator._last_coordination = CoordinationSnapshot(
        timestamp="2026-03-11T00:00:00+00:00",
        global_truths=1,
        productive_disagreements=0,
        is_globally_coherent=True,
        global_truth_claims=["shared truth"],
        disagreement_claims=[],
        rv_trend=-0.1,
        fitness_trend=0.2,
        observation_count=4,
        approaching_fixed_point=False,
    )

    class _FakeOuroboros:
        def detect_cycle_drift(self) -> dict[str, object]:
            return {
                "drifting": True,
                "reason": "high_mimicry",
                "mimicry_rate": 0.4,
                "avg_witness_stance": 0.2,
            }

    integrator._ouroboros = _FakeOuroboros()

    context = integrator.get_coordination_context()

    assert context["global_truths"] == ["shared truth"]
    assert context["ouroboros_warning"] == (
        "Behavioral drift detected: high_mimicry. "
        "Mimicry rate: 40.0%, witness stance: 0.20"
    )
    assert context["ouroboros_health"] == {
        "mimicry_rate": 0.4,
        "witness_stance": 0.2,
        "drifting": True,
    }


def test_get_coordination_summary_returns_canonical_snapshot_shape(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )
    integrator._last_coordination = CoordinationSnapshot(
        timestamp="2026-03-11T00:00:00+00:00",
        global_truths=2,
        productive_disagreements=1,
        cohomological_dimension=1,
        is_globally_coherent=False,
        global_truth_claims=["shared truth", "shared route"],
        disagreement_claims=["route-policy"],
        rv_trend=-0.1,
        fitness_trend=0.2,
        observation_count=4,
        approaching_fixed_point=True,
    )

    assert integrator.get_coordination_summary() == {
        "observed_at": "2026-03-11T00:00:00+00:00",
        "global_truths": 2,
        "productive_disagreements": 1,
        "cohomological_dimension": 1,
        "is_globally_coherent": False,
        "global_truth_claim_keys": ["shared truth", "shared route"],
        "productive_disagreement_claim_keys": ["route-policy"],
        "rv_trend": -0.1,
        "fitness_trend": 0.2,
        "observation_count": 4,
        "approaching_fixed_point": True,
    }


def test_get_coordination_context_includes_reciprocity_warning(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )
    integrator._last_coordination = CoordinationSnapshot(
        timestamp="2026-03-11T00:00:00+00:00",
        global_truths=1,
        productive_disagreements=0,
        is_globally_coherent=True,
        global_truth_claims=["shared truth"],
        disagreement_claims=[],
        rv_trend=-0.1,
        fitness_trend=0.2,
        observation_count=4,
        approaching_fixed_point=False,
    )
    integrator._last_reciprocity_summary = {
        "source": "reciprocity_commons",
        "summary_type": "ledger_summary",
        "actors": 2,
        "activities": 1,
        "projects": 1,
        "obligations": 3,
        "active_obligations": 2,
        "challenged_claims": 1,
        "invariant_issues": 2,
        "chain_valid": False,
        "total_obligation_usd": 25000.0,
        "total_routed_usd": 5000.0,
        "issue_codes": [
            "routing_missing_project",
            "verified_ecology_missing_audit",
        ],
    }

    context = integrator.get_coordination_context()

    assert context["reciprocity_warning"] == (
        "Reciprocity integrity pressure: chain_valid=False, "
        "invariant_issues=2, challenged_claims=1, "
        "issue_codes=routing_missing_project,verified_ecology_missing_audit"
    )
    assert context["reciprocity_health"] == {
        "chain_valid": False,
        "invariant_issues": 2,
        "challenged_claims": 1,
        "issue_codes": [
            "routing_missing_project",
            "verified_ecology_missing_audit",
        ],
        "stale": False,
    }


def test_get_coordination_context_exposes_health_without_coordination_snapshot(tmp_path):
    integrator = DSEIntegrator(
        archive_path=tmp_path / "evolution",
        coordination_interval=10,
    )

    class _FakeOuroboros:
        def detect_cycle_drift(self) -> dict[str, object]:
            return {
                "drifting": True,
                "reason": "high_mimicry",
                "mimicry_rate": 0.25,
                "avg_witness_stance": 0.4,
            }

    integrator._ouroboros = _FakeOuroboros()
    integrator._last_reciprocity_summary = {
        "source": "reciprocity_commons",
        "summary_type": "ledger_summary",
        "actors": 2,
        "activities": 1,
        "projects": 1,
        "obligations": 3,
        "active_obligations": 2,
        "challenged_claims": 0,
        "invariant_issues": 1,
        "chain_valid": False,
        "total_obligation_usd": 25000.0,
        "total_routed_usd": 5000.0,
        "issue_codes": ["routing_missing_project"],
    }
    integrator._last_reciprocity_error = "refresh failed"

    context = integrator.get_coordination_context()

    assert "global_truths" not in context
    assert context["ouroboros_warning"] == (
        "Behavioral drift detected: high_mimicry. "
        "Mimicry rate: 25.0%, witness stance: 0.40"
    )
    assert context["ouroboros_health"] == {
        "mimicry_rate": 0.25,
        "witness_stance": 0.4,
        "drifting": True,
    }
    assert context["reciprocity_warning"] == (
        "Reciprocity integrity pressure (stale): chain_valid=False, "
        "invariant_issues=1, challenged_claims=0, "
        "issue_codes=routing_missing_project"
    )
    assert context["reciprocity_health"] == {
        "chain_valid": False,
        "invariant_issues": 1,
        "challenged_claims": 0,
        "issue_codes": ["routing_missing_project"],
        "stale": True,
    }
