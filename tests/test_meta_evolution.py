"""Tests for persisted Darwin meta-evolution."""

import pytest

from dharma_swarm.archive import FITNESS_DIMENSIONS
from dharma_swarm.evolution import CycleResult, DarwinEngine
from dharma_swarm.meta_evolution import MetaEvolutionEngine, MetaParameters


@pytest.fixture
def engine_paths(tmp_path):
    return {
        "archive_path": tmp_path / "archive.jsonl",
        "traces_path": tmp_path / "traces",
        "predictor_path": tmp_path / "predictor.jsonl",
    }


@pytest.mark.asyncio
async def test_meta_fitness_correlates_with_trend(engine_paths):
    engine = DarwinEngine(**engine_paths)
    meta = MetaEvolutionEngine(engine, n_object_cycles_per_meta=5)

    up = meta._compute_meta_fitness([0.1, 0.2, 0.3, 0.4, 0.5])
    down = meta._compute_meta_fitness([0.5, 0.4, 0.3, 0.2, 0.1])

    assert up > down


@pytest.mark.asyncio
async def test_meta_cycle_archives_and_evolves_when_poor(engine_paths, tmp_path, monkeypatch):
    engine = DarwinEngine(**engine_paths)
    await engine.init()
    archive_path = tmp_path / "meta_archive.jsonl"
    meta = MetaEvolutionEngine(
        engine,
        meta_archive_path=archive_path,
        n_object_cycles_per_meta=3,
        poor_meta_fitness_threshold=0.5,
        seed=4,
    )
    initial = meta.meta_params.model_copy(deep=True)

    async def fake_run_cycle(proposals):
        del proposals
        return CycleResult(best_fitness=0.0)

    monkeypatch.setattr(engine, "run_cycle", fake_run_cycle)
    result = await meta.run_meta_cycle([])

    assert result.object_cycles_completed == 3
    assert result.meta_fitness < 0.5
    assert result.evolved_parameters is True
    assert archive_path.exists()
    assert len(meta.meta_archive) == 1
    assert meta.meta_params != initial
    assert engine.get_fitness_weights() == meta.meta_params.fitness_weights


@pytest.mark.asyncio
async def test_meta_cycle_keeps_parameters_when_strong(engine_paths, tmp_path, monkeypatch):
    engine = DarwinEngine(**engine_paths)
    await engine.init()
    meta = MetaEvolutionEngine(
        engine,
        meta_archive_path=tmp_path / "meta_archive_strong.jsonl",
        n_object_cycles_per_meta=3,
        poor_meta_fitness_threshold=0.5,
        seed=4,
    )
    initial = meta.meta_params.model_copy(deep=True)
    scores = iter([0.4, 0.6, 0.8])

    async def fake_run_cycle(proposals):
        del proposals
        return CycleResult(best_fitness=next(scores))

    monkeypatch.setattr(engine, "run_cycle", fake_run_cycle)
    result = await meta.run_meta_cycle([])

    assert result.meta_fitness >= 0.5
    assert result.evolved_parameters is False
    assert meta.meta_params == initial


@pytest.mark.asyncio
async def test_observe_cycle_result_applies_bounded_update(
    engine_paths,
    tmp_path,
    monkeypatch,
):
    engine = DarwinEngine(**engine_paths)
    await engine.init()
    meta = MetaEvolutionEngine(
        engine,
        meta_archive_path=tmp_path / "meta_archive_periodic.jsonl",
        n_object_cycles_per_meta=2,
        poor_meta_fitness_threshold=1.1,
        max_weight_shift=0.02,
        max_mutation_delta=0.03,
        max_exploration_delta=0.1,
        max_circuit_breaker_delta=1,
        max_grid_delta=1,
        seed=7,
    )
    baseline = meta.meta_params.model_copy(deep=True)

    def fake_evolve():
        return MetaParameters(
            fitness_weights={"correctness": 1.0, "safety": 0.0},
            mutation_rate=0.9,
            exploration_coeff=3.0,
            circuit_breaker_limit=10,
            map_elites_n_bins=12,
        )

    monkeypatch.setattr(meta, "_evolve_meta_params", fake_evolve)

    first = meta.observe_cycle_result(CycleResult(cycle_id="cycle-1", best_fitness=0.1))
    second = meta.observe_cycle_result(CycleResult(cycle_id="cycle-2", best_fitness=0.1))

    assert first is None
    assert second is not None
    assert second.trigger == "periodic"
    assert second.applied_parameters is True
    assert second.evolved_parameters is True
    assert second.source_cycle_ids == ["cycle-1", "cycle-2"]
    assert len(meta.meta_archive) == 1
    assert abs(second.meta_parameters.mutation_rate - baseline.mutation_rate) <= 0.031
    assert (
        abs(
            second.meta_parameters.exploration_coeff - baseline.exploration_coeff
        )
        <= 0.101
    )
    assert (
        second.meta_parameters.circuit_breaker_limit
        <= baseline.circuit_breaker_limit + 1
    )
    assert second.meta_parameters.map_elites_n_bins <= baseline.map_elites_n_bins + 1


@pytest.mark.asyncio
async def test_meta_parameter_theta_roundtrip(engine_paths):
    engine = DarwinEngine(**engine_paths)
    await engine.init()
    meta = MetaEvolutionEngine(engine, n_object_cycles_per_meta=2)

    theta = meta.get_meta_parameter_theta()
    restored = meta.apply_meta_parameter_theta(theta, auto_apply=False, bounded=False)

    assert restored == meta.meta_params
    assert abs(sum(restored.fitness_weights.values()) - 1.0) < 1e-9


@pytest.mark.asyncio
async def test_propose_natural_gradient_update_is_bounded(engine_paths):
    engine = DarwinEngine(**engine_paths)
    await engine.init()
    meta = MetaEvolutionEngine(
        engine,
        n_object_cycles_per_meta=2,
        max_weight_shift=0.02,
        max_mutation_delta=0.03,
        max_exploration_delta=0.1,
        max_circuit_breaker_delta=1,
        max_grid_delta=1,
    )
    baseline = meta.meta_params.model_copy(deep=True)
    gradient = [0.05] * len(meta.get_meta_parameter_theta())

    candidate = meta.propose_natural_gradient_update(gradient, step_size=0.4)

    assert candidate != baseline
    assert abs(candidate.mutation_rate - baseline.mutation_rate) <= 0.031
    assert abs(candidate.exploration_coeff - baseline.exploration_coeff) <= 0.101
    assert candidate.circuit_breaker_limit <= baseline.circuit_breaker_limit + 1
    assert candidate.map_elites_n_bins <= baseline.map_elites_n_bins + 1


@pytest.mark.asyncio
async def test_poor_meta_cycle_uses_natural_gradient_and_exploration(
    engine_paths,
    tmp_path,
    monkeypatch,
):
    engine = DarwinEngine(**engine_paths)
    await engine.init()
    meta = MetaEvolutionEngine(
        engine,
        meta_archive_path=tmp_path / "meta_archive_ng.jsonl",
        n_object_cycles_per_meta=2,
        poor_meta_fitness_threshold=0.9,
    )
    called: dict[str, bool] = {"natural": False, "explore": False}

    async def fake_run_cycle(proposals):
        del proposals
        return CycleResult(best_fitness=0.0)

    def fake_natural(*args, **kwargs):
        called["natural"] = True
        return MetaParameters(
            fitness_weights={"correctness": 1.0, "safety": 0.0},
            mutation_rate=0.2,
            exploration_coeff=1.2,
            circuit_breaker_limit=2,
            map_elites_n_bins=6,
        )

    def fake_explore():
        called["explore"] = True
        return MetaParameters(
            fitness_weights={"correctness": 0.0, "safety": 1.0},
            mutation_rate=0.3,
            exploration_coeff=1.4,
            circuit_breaker_limit=4,
            map_elites_n_bins=7,
        )

    monkeypatch.setattr(engine, "run_cycle", fake_run_cycle)
    monkeypatch.setattr(meta, "propose_natural_gradient_update", fake_natural)
    monkeypatch.setattr(meta, "_evolve_meta_params", fake_explore)

    result = await meta.run_meta_cycle([])

    assert result.evolved_parameters is True
    assert called == {"natural": True, "explore": True}


@pytest.mark.asyncio
async def test_coordination_uncertainty_pressure_biases_gradients(engine_paths):
    engine = DarwinEngine(**engine_paths)
    await engine.init()
    meta = MetaEvolutionEngine(engine, n_object_cycles_per_meta=2)

    baseline = meta._trajectory_loss_gradient([0.4, 0.4])
    summary = {
        "observed_at": "2026-03-10T00:00:00+00:00",
        "productive_disagreements": 2,
        "cohomological_dimension": 1,
        "is_globally_coherent": False,
        "productive_disagreement_claim_keys": ["route-policy"],
    }
    meta.observe_coordination_summary(summary)
    meta.observe_coordination_summary(summary)
    pressured = meta._trajectory_loss_gradient([0.4, 0.4])

    safety_idx = FITNESS_DIMENSIONS.index("safety")
    exploration_idx = len(FITNESS_DIMENSIONS) + 1
    circuit_idx = len(FITNESS_DIMENSIONS) + 2

    assert meta._coordination_uncertainty_pressure() > 0.0
    assert pressured[safety_idx] < baseline[safety_idx]
    assert pressured[exploration_idx] < baseline[exploration_idx]
    assert pressured[circuit_idx] > baseline[circuit_idx]


@pytest.mark.asyncio
async def test_stalled_fixed_point_increases_coordination_pressure(engine_paths):
    stable_engine = DarwinEngine(**engine_paths)
    await stable_engine.init()
    stable = MetaEvolutionEngine(stable_engine, n_object_cycles_per_meta=2)
    stable.observe_coordination_summary(
        {
            "observed_at": "2026-03-10T00:00:00+00:00",
            "productive_disagreements": 0,
            "cohomological_dimension": 0,
            "is_globally_coherent": True,
            "rv_trend": 0.1,
            "fitness_trend": 0.05,
            "approaching_fixed_point": False,
        }
    )

    stalled_engine = DarwinEngine(**engine_paths)
    await stalled_engine.init()
    stalled = MetaEvolutionEngine(stalled_engine, n_object_cycles_per_meta=2)
    stalled.observe_coordination_summary(
        {
            "observed_at": "2026-03-10T01:00:00+00:00",
            "productive_disagreements": 0,
            "cohomological_dimension": 0,
            "is_globally_coherent": True,
            "rv_trend": -0.2,
            "fitness_trend": -0.05,
            "approaching_fixed_point": True,
        }
    )

    assert stable._coordination_uncertainty_pressure() == 0.0
    assert stalled._coordination_uncertainty_pressure() > stable._coordination_uncertainty_pressure()


@pytest.mark.asyncio
async def test_meta_cycle_reports_coordination_pressure(engine_paths, tmp_path, monkeypatch):
    engine = DarwinEngine(**engine_paths)
    await engine.init()
    meta = MetaEvolutionEngine(
        engine,
        meta_archive_path=tmp_path / "meta_archive_coordination.jsonl",
        n_object_cycles_per_meta=2,
        poor_meta_fitness_threshold=0.9,
    )
    meta.observe_coordination_summary(
        {
            "observed_at": "2026-03-10T00:00:00+00:00",
            "global_truths": 0,
            "productive_disagreements": 1,
            "cohomological_dimension": 1,
            "is_globally_coherent": False,
            "global_truth_claim_keys": ["shared-route"],
            "productive_disagreement_claim_keys": ["route-policy"],
            "rv_trend": -0.2,
            "fitness_trend": -0.05,
            "observation_count": 4,
            "approaching_fixed_point": True,
        }
    )

    async def fake_run_cycle(proposals):
        del proposals
        return CycleResult(best_fitness=0.0)

    monkeypatch.setattr(engine, "run_cycle", fake_run_cycle)

    result = await meta.run_meta_cycle([])

    assert result.coordination_pressure > 0.0
    assert result.coordination_summary["productive_disagreements"] == 1
    assert result.coordination_summary["global_truth_claim_keys"] == ["shared-route"]
    assert result.coordination_summary["rv_trend"] == -0.2
    assert result.coordination_summary["fitness_trend"] == -0.05
    assert result.coordination_summary["observation_count"] == 4
    assert result.coordination_summary["approaching_fixed_point"] is True
