"""Tests for dharma_swarm.island_evolution -- island-based parallel evolution."""

import json

import pytest

from dharma_swarm.island_evolution import (
    Candidate,
    Island,
    IslandEvolutionManager,
)


# ---------------------------------------------------------------------------
# Island creation
# ---------------------------------------------------------------------------


def test_create_islands_default():
    mgr = IslandEvolutionManager(seed=42)
    assert len(mgr.islands) == 4
    assert mgr.population_per_island == 10
    assert mgr.migration_rate == 0.1
    assert mgr.migration_interval == 5


def test_create_islands_custom():
    mgr = IslandEvolutionManager(
        num_islands=6,
        population_per_island=20,
        migration_rate=0.25,
        migration_interval=3,
        seed=99,
    )
    assert len(mgr.islands) == 6
    assert mgr.population_per_island == 20
    assert mgr.migration_rate == 0.25
    assert mgr.migration_interval == 3


def test_create_islands_clamps_minimums():
    mgr = IslandEvolutionManager(num_islands=1, population_per_island=1, seed=0)
    assert mgr.num_islands >= 2
    assert mgr.population_per_island >= 2


# ---------------------------------------------------------------------------
# add_candidate
# ---------------------------------------------------------------------------


def test_add_candidate_to_empty_island():
    mgr = IslandEvolutionManager(num_islands=2, population_per_island=5, seed=1)
    c = Candidate(payload={"x": 1.0}, fitness=0.5)
    assert mgr.add_candidate(0, c) is True
    assert len(mgr.islands[0].population) == 1
    assert mgr.islands[0].best_fitness == 0.5


def test_add_candidate_evicts_weakest():
    mgr = IslandEvolutionManager(num_islands=2, population_per_island=3, seed=2)
    for f in [0.1, 0.2, 0.3]:
        mgr.add_candidate(0, Candidate(fitness=f))
    assert len(mgr.islands[0].population) == 3

    # Adding a fitter candidate should evict the weakest (0.1)
    strong = Candidate(fitness=0.9)
    assert mgr.add_candidate(0, strong) is True
    assert len(mgr.islands[0].population) == 3
    fitnesses = {c.fitness for c in mgr.islands[0].population}
    assert 0.1 not in fitnesses
    assert 0.9 in fitnesses


def test_add_candidate_rejects_weaker():
    mgr = IslandEvolutionManager(num_islands=2, population_per_island=2, seed=3)
    mgr.add_candidate(0, Candidate(fitness=0.5))
    mgr.add_candidate(0, Candidate(fitness=0.6))
    weak = Candidate(fitness=0.1)
    assert mgr.add_candidate(0, weak) is False
    assert len(mgr.islands[0].population) == 2


def test_add_candidate_invalid_island():
    mgr = IslandEvolutionManager(num_islands=2, seed=4)
    with pytest.raises(ValueError, match="out of range"):
        mgr.add_candidate(5, Candidate(fitness=0.5))


# ---------------------------------------------------------------------------
# evolve_island
# ---------------------------------------------------------------------------


def test_evolve_island_produces_offspring():
    mgr = IslandEvolutionManager(
        num_islands=2, population_per_island=10, seed=42,
    )
    for i in range(5):
        mgr.add_candidate(0, Candidate(
            payload={"val": float(i)}, fitness=0.1 * (i + 1),
        ))

    offspring = mgr.evolve_island(0)
    assert len(offspring) > 0
    assert mgr.islands[0].generation_count == 1
    assert len(mgr.islands[0].fitness_history) == 1


def test_evolve_island_too_few_candidates():
    mgr = IslandEvolutionManager(num_islands=2, seed=5)
    mgr.add_candidate(0, Candidate(fitness=0.5))
    offspring = mgr.evolve_island(0)
    assert offspring == []


def test_evolve_island_invalid_id():
    mgr = IslandEvolutionManager(num_islands=2, seed=6)
    with pytest.raises(ValueError, match="out of range"):
        mgr.evolve_island(99)


def test_evolve_island_offspring_have_parent_ids():
    mgr = IslandEvolutionManager(
        num_islands=2, population_per_island=10, seed=7,
    )
    for i in range(4):
        mgr.add_candidate(0, Candidate(
            payload={"v": float(i)}, fitness=0.2 * (i + 1),
        ))

    offspring = mgr.evolve_island(0)
    for child in offspring:
        assert len(child.parent_ids) == 2


# ---------------------------------------------------------------------------
# migrate
# ---------------------------------------------------------------------------


def test_migrate_ring_topology():
    mgr = IslandEvolutionManager(
        num_islands=3, population_per_island=10, migration_rate=0.5, seed=10,
    )
    # Populate each island with distinct fitness ranges
    for island_id in range(3):
        for j in range(4):
            fitness = (island_id + 1) * 0.1 + j * 0.01
            mgr.add_candidate(island_id, Candidate(fitness=fitness))

    pop_before = [len(i.population) for i in mgr.islands]
    n_migrated = mgr.migrate()
    assert n_migrated > 0

    # After migration, islands should have gained some candidates
    total_after = sum(len(i.population) for i in mgr.islands)
    total_before = sum(pop_before)
    assert total_after >= total_before  # Copies, so total can grow


def test_migrate_empty_islands():
    mgr = IslandEvolutionManager(num_islands=3, seed=11)
    n = mgr.migrate()
    assert n == 0


def test_should_migrate():
    mgr = IslandEvolutionManager(
        num_islands=2, migration_interval=3, seed=12,
    )
    assert mgr.should_migrate() is False
    mgr._global_generation = 3
    assert mgr.should_migrate() is True
    mgr._global_generation = 4
    assert mgr.should_migrate() is False
    mgr._global_generation = 6
    assert mgr.should_migrate() is True


# ---------------------------------------------------------------------------
# best_overall
# ---------------------------------------------------------------------------


def test_best_overall_empty():
    mgr = IslandEvolutionManager(num_islands=2, seed=13)
    assert mgr.best_overall() is None


def test_best_overall_across_islands():
    mgr = IslandEvolutionManager(num_islands=3, seed=14)
    mgr.add_candidate(0, Candidate(fitness=0.3))
    mgr.add_candidate(1, Candidate(fitness=0.9))
    mgr.add_candidate(2, Candidate(fitness=0.5))
    best = mgr.best_overall()
    assert best is not None
    assert best.fitness == 0.9


# ---------------------------------------------------------------------------
# diversity_score
# ---------------------------------------------------------------------------


def test_diversity_score_empty():
    mgr = IslandEvolutionManager(num_islands=3, seed=15)
    assert mgr.diversity_score() == 0.0


def test_diversity_score_identical_islands():
    mgr = IslandEvolutionManager(num_islands=3, population_per_island=5, seed=16)
    for island_id in range(3):
        for _ in range(3):
            mgr.add_candidate(island_id, Candidate(fitness=0.5))
    # All islands have the same mean fitness -> CV = 0
    assert mgr.diversity_score() == 0.0


def test_diversity_score_divergent_islands():
    mgr = IslandEvolutionManager(num_islands=3, population_per_island=5, seed=17)
    mgr.add_candidate(0, Candidate(fitness=0.1))
    mgr.add_candidate(1, Candidate(fitness=0.5))
    mgr.add_candidate(2, Candidate(fitness=0.9))
    score = mgr.diversity_score()
    assert score > 0.0


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_serialization_roundtrip():
    mgr = IslandEvolutionManager(
        num_islands=3, population_per_island=5, migration_rate=0.2,
        migration_interval=4, seed=18,
    )
    mgr.add_candidate(0, Candidate(payload={"a": 1}, fitness=0.7))
    mgr.add_candidate(1, Candidate(payload={"b": 2}, fitness=0.3))
    mgr.evolve_island(0)

    data = mgr.to_dict()
    restored = IslandEvolutionManager.from_dict(data, seed=18)

    assert restored.num_islands == mgr.num_islands
    assert restored.population_per_island == mgr.population_per_island
    assert restored.migration_rate == mgr.migration_rate
    assert restored.migration_interval == mgr.migration_interval
    assert len(restored.islands[0].population) == len(mgr.islands[0].population)
    assert restored.islands[0].generation_count == mgr.islands[0].generation_count


def test_serialization_json_valid():
    mgr = IslandEvolutionManager(num_islands=2, seed=19)
    mgr.add_candidate(0, Candidate(fitness=0.5))
    data = mgr.to_dict()
    # Must be JSON-serializable
    text = json.dumps(data)
    assert isinstance(json.loads(text), dict)


async def test_persist_and_load(tmp_path):
    persist_dir = tmp_path / "islands"
    mgr = IslandEvolutionManager(
        num_islands=3, population_per_island=5,
        seed=20, persist_dir=persist_dir,
    )
    mgr.add_candidate(0, Candidate(payload={"x": 42}, fitness=0.8))
    mgr.add_candidate(2, Candidate(payload={"y": 99}, fitness=0.6))

    path = await mgr.persist()
    assert path.exists()

    loaded = await IslandEvolutionManager.load(persist_dir=persist_dir, seed=20)
    assert loaded.num_islands == 3
    assert len(loaded.islands[0].population) == 1
    assert loaded.islands[0].population[0].fitness == 0.8


# ---------------------------------------------------------------------------
# island_summary
# ---------------------------------------------------------------------------


def test_island_summary():
    mgr = IslandEvolutionManager(num_islands=2, seed=21)
    mgr.add_candidate(0, Candidate(fitness=0.4))
    mgr.add_candidate(0, Candidate(fitness=0.6))
    summary = mgr.island_summary()
    assert len(summary) == 2
    assert summary[0]["population_size"] == 2
    assert summary[0]["best_fitness"] == 0.6
    assert summary[0]["mean_fitness"] == pytest.approx(0.5)
    assert summary[1]["population_size"] == 0
