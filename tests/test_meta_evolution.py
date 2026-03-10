"""Tests for persisted Darwin meta-evolution."""

import pytest

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
