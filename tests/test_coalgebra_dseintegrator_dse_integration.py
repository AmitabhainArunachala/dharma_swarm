from __future__ import annotations

import importlib

import pytest

from dharma_swarm.archive import ArchiveEntry, FitnessScore
from dharma_swarm.coalgebra import EvolutionObservation
from dharma_swarm.dse_integration import (
    CoordinationSnapshot as CanonicalCoordinationSnapshot,
    DSEIntegrator as CanonicalDSEIntegrator,
    ObservationWindow as CanonicalObservationWindow,
)
from dharma_swarm.evolution import CycleResult


def _load_module():
    try:
        return importlib.import_module("dharma_swarm.coalgebra_dseintegrator_dse_integration")
    except ModuleNotFoundError as exc:
        pytest.fail(f"cluster bridge module is missing: {exc}")


def test_module_re_exports_canonical_dse_runtime_types():
    module = _load_module()

    assert module.DSEIntegrator is CanonicalDSEIntegrator
    assert module.ObservationWindow is CanonicalObservationWindow
    assert module.CoordinationSnapshot is CanonicalCoordinationSnapshot


def test_build_dse_cycle_bridge_summarizes_coalgebra_monad_and_sheaf_state():
    module = _load_module()
    result = CycleResult(
        cycle_id="cycle-bridge-1",
        best_fitness=0.61,
        proposals_archived=1,
        lessons_learned=["theta discovered"],
        reflection="sheaf disagreement remains productive",
    )
    observation = EvolutionObservation(
        next_state=result,
        fitness=0.61,
        rv=0.72,
        discoveries=["theta discovered", "coalgebra stream stable"],
    )
    snapshot = module.CoordinationSnapshot(
        timestamp="2026-03-20T00:00:00+00:00",
        global_truths=1,
        productive_disagreements=1,
        cohomological_dimension=1,
        is_globally_coherent=False,
        global_truth_claims=["theta discovered"],
        disagreement_claims=["trend:worker.py"],
        observation_count=3,
        approaching_fixed_point=True,
    )

    bridge = module.build_dse_cycle_bridge(
        observation,
        component="worker.py",
        observation_depth=2,
        coordination_snapshot=snapshot,
        coordination_context={"exploration_hint": "investigate trend:worker.py"},
        approaching_fixed_point=True,
    )

    assert bridge.cycle_id == "cycle-bridge-1"
    assert bridge.component == "worker.py"
    assert bridge.next_state_type == "CycleResult"
    assert bridge.fitness == pytest.approx(0.61)
    assert bridge.rv == pytest.approx(0.72)
    assert bridge.discovery_count == 2
    assert bridge.has_monadic_observation is True
    assert bridge.coordination_available is True
    assert bridge.global_truth_claims == ["theta discovered"]
    assert bridge.disagreement_claims == ["trend:worker.py"]
    assert bridge.approaching_fixed_point is True
    assert bridge.context["exploration_hint"] == "investigate trend:worker.py"


def test_build_dse_cycle_bridge_from_cycle_uses_coalgebra_factory():
    module = _load_module()
    result = CycleResult(
        cycle_id="cycle-bridge-2",
        best_fitness=0.44,
        proposals_archived=1,
        lessons_learned=["archive delta emitted"],
    )
    archive_entry = ArchiveEntry(
        component="archive.py",
        change_type="mutation",
        description="archive delta emitted",
        diff="- old\n+ new\n",
        fitness=FitnessScore(correctness=0.44, dharmic_alignment=1.0, safety=1.0),
        status="applied",
    )

    bridge = module.build_dse_cycle_bridge_from_cycle(
        result,
        [archive_entry],
        component="archive.py",
    )

    assert bridge.cycle_id == "cycle-bridge-2"
    assert bridge.component == "archive.py"
    assert bridge.discovery_count >= 1
    assert "archive delta emitted" in bridge.discoveries


def test_build_dse_cycle_bridge_uses_snapshot_fixed_point_pressure_by_default():
    module = _load_module()
    result = CycleResult(
        cycle_id="cycle-bridge-3",
        best_fitness=0.73,
        proposals_archived=2,
        lessons_learned=["fixed point pressure rising"],
    )
    observation = EvolutionObservation(
        next_state=result,
        fitness=0.73,
        rv=0.81,
        discoveries=["fixed point pressure rising"],
    )
    snapshot = module.CoordinationSnapshot(
        timestamp="2026-03-20T00:00:00+00:00",
        global_truths=2,
        productive_disagreements=0,
        cohomological_dimension=0,
        is_globally_coherent=True,
        global_truth_claims=["fixed point pressure rising"],
        disagreement_claims=[],
        observation_count=8,
        approaching_fixed_point=True,
    )

    bridge = module.build_dse_cycle_bridge(
        observation,
        component="runtime.py",
        coordination_snapshot=snapshot,
    )

    assert bridge.approaching_fixed_point is True
    assert bridge.context["approaching_fixed_point"] is True
    assert "convergence_hint" in bridge.context
