"""Tests for dharma_swarm.diversity_archive -- MAP-Elites diversity grid."""

import json

import pytest

from dharma_swarm.diversity_archive import (
    ArchiveCell,
    BehaviorDescriptor,
    DiversityArchive,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bd(**kwargs: float) -> BehaviorDescriptor:
    """Shorthand for creating a BehaviorDescriptor."""
    return BehaviorDescriptor(dimensions=kwargs)


# ---------------------------------------------------------------------------
# Archive creation
# ---------------------------------------------------------------------------


def test_create_archive():
    archive = DiversityArchive(
        dimensions=["speed", "risk"], bins_per_dimension=5, seed=42,
    )
    assert archive.dimensions == ["speed", "risk"]
    assert archive.bins_per_dimension == 5
    assert archive.coverage() == 0.0


def test_create_archive_no_dimensions():
    with pytest.raises(ValueError, match="At least one"):
        DiversityArchive(dimensions=[])


def test_create_archive_clamps_bins():
    archive = DiversityArchive(dimensions=["x"], bins_per_dimension=1)
    assert archive.bins_per_dimension >= 2


# ---------------------------------------------------------------------------
# add candidate
# ---------------------------------------------------------------------------


def test_add_candidate_to_empty_grid():
    archive = DiversityArchive(
        dimensions=["speed", "risk"], bins_per_dimension=5, seed=1,
    )
    inserted = archive.add(
        candidate_id="c1",
        candidate_payload={"code": "v1"},
        fitness=0.8,
        behavior=_bd(speed=0.5, risk=0.3),
    )
    assert inserted is True
    assert archive.coverage() > 0.0


def test_add_multiple_different_cells():
    archive = DiversityArchive(
        dimensions=["x", "y"], bins_per_dimension=5, seed=2,
    )
    archive.add("a", {}, 0.5, _bd(x=0.1, y=0.1))
    archive.add("b", {}, 0.6, _bd(x=0.9, y=0.9))
    assert archive.coverage() == pytest.approx(2.0 / 25.0)


# ---------------------------------------------------------------------------
# Replacement on fitter
# ---------------------------------------------------------------------------


def test_replacement_on_fitter():
    archive = DiversityArchive(
        dimensions=["x"], bins_per_dimension=5, seed=3,
    )
    archive.add("weak", {}, 0.3, _bd(x=0.5))
    archive.add("strong", {"upgraded": True}, 0.9, _bd(x=0.5))

    cell = archive.get_cell(_bd(x=0.5))
    assert cell is not None
    assert cell.candidate_id == "strong"
    assert cell.fitness == 0.9
    assert cell.candidate_payload == {"upgraded": True}


# ---------------------------------------------------------------------------
# No replacement on weaker
# ---------------------------------------------------------------------------


def test_no_replacement_on_weaker():
    archive = DiversityArchive(
        dimensions=["x"], bins_per_dimension=5, seed=4,
    )
    archive.add("strong", {}, 0.9, _bd(x=0.5))
    replaced = archive.add("weak", {}, 0.2, _bd(x=0.5))

    assert replaced is False
    cell = archive.get_cell(_bd(x=0.5))
    assert cell is not None
    assert cell.candidate_id == "strong"


def test_no_replacement_on_equal_fitness():
    archive = DiversityArchive(
        dimensions=["x"], bins_per_dimension=5, seed=5,
    )
    archive.add("first", {}, 0.5, _bd(x=0.5))
    replaced = archive.add("second", {}, 0.5, _bd(x=0.5))
    assert replaced is False
    cell = archive.get_cell(_bd(x=0.5))
    assert cell is not None
    assert cell.candidate_id == "first"


# ---------------------------------------------------------------------------
# sample_diverse
# ---------------------------------------------------------------------------


def test_sample_diverse_empty():
    archive = DiversityArchive(dimensions=["x", "y"], seed=6)
    assert archive.sample_diverse(5) == []


def test_sample_diverse_single_cell():
    archive = DiversityArchive(dimensions=["x"], bins_per_dimension=5, seed=7)
    archive.add("only", {}, 0.5, _bd(x=0.5))
    result = archive.sample_diverse(3)
    assert len(result) == 1
    assert result[0].candidate_id == "only"


def test_sample_diverse_maximizes_spread():
    archive = DiversityArchive(
        dimensions=["x", "y"], bins_per_dimension=10, seed=8,
    )
    # Place candidates at corners and center
    archive.add("corner_00", {}, 0.5, _bd(x=0.0, y=0.0))
    archive.add("corner_01", {}, 0.5, _bd(x=0.0, y=0.99))
    archive.add("corner_10", {}, 0.5, _bd(x=0.99, y=0.0))
    archive.add("corner_11", {}, 0.5, _bd(x=0.99, y=0.99))
    archive.add("center", {}, 0.9, _bd(x=0.5, y=0.5))  # Fittest

    # Sampling 3 should give the fittest + 2 farthest corners
    result = archive.sample_diverse(3)
    assert len(result) == 3
    # The fittest (center) should be picked first
    assert result[0].candidate_id == "center"
    # The next two should be from opposite corners
    ids = {r.candidate_id for r in result}
    assert "center" in ids


def test_sample_diverse_respects_n():
    archive = DiversityArchive(
        dimensions=["x"], bins_per_dimension=10, seed=9,
    )
    for i in range(8):
        archive.add(f"c{i}", {}, 0.1 * (i + 1), _bd(x=i / 10.0))
    result = archive.sample_diverse(3)
    assert len(result) == 3


# ---------------------------------------------------------------------------
# coverage
# ---------------------------------------------------------------------------


def test_coverage_empty():
    archive = DiversityArchive(dimensions=["a", "b"], bins_per_dimension=5)
    assert archive.coverage() == 0.0


def test_coverage_full_1d():
    archive = DiversityArchive(
        dimensions=["x"], bins_per_dimension=3, seed=10,
    )
    # Fill all 3 bins
    archive.add("a", {}, 0.5, _bd(x=0.0))   # bin 0
    archive.add("b", {}, 0.5, _bd(x=0.5))   # bin 1
    archive.add("c", {}, 0.5, _bd(x=0.99))  # bin 2
    assert archive.coverage() == pytest.approx(1.0)


def test_coverage_partial_2d():
    archive = DiversityArchive(
        dimensions=["x", "y"], bins_per_dimension=4, seed=11,
    )
    # 4x4 = 16 total cells, place in 4
    archive.add("a", {}, 0.5, _bd(x=0.0, y=0.0))
    archive.add("b", {}, 0.5, _bd(x=0.5, y=0.5))
    archive.add("c", {}, 0.5, _bd(x=0.99, y=0.99))
    archive.add("d", {}, 0.5, _bd(x=0.0, y=0.99))
    assert archive.coverage() == pytest.approx(4.0 / 16.0)


# ---------------------------------------------------------------------------
# best_per_dimension
# ---------------------------------------------------------------------------


def test_best_per_dimension():
    archive = DiversityArchive(
        dimensions=["speed", "risk"], bins_per_dimension=5, seed=12,
    )
    archive.add("slow_safe", {}, 0.3, _bd(speed=0.1, risk=0.1))
    archive.add("fast_risky", {}, 0.7, _bd(speed=0.99, risk=0.99))
    archive.add("fast_safe", {}, 0.9, _bd(speed=0.99, risk=0.1))

    best_speed = archive.best_per_dimension("speed")
    assert best_speed is not None
    # fast_safe has highest fitness among speed=max_bin
    assert best_speed.candidate_id == "fast_safe"


def test_best_per_dimension_unknown():
    archive = DiversityArchive(dimensions=["x"], seed=13)
    with pytest.raises(ValueError, match="Unknown dimension"):
        archive.best_per_dimension("nonexistent")


def test_best_per_dimension_fallback():
    archive = DiversityArchive(
        dimensions=["x"], bins_per_dimension=5, seed=14,
    )
    # Only populate low bins
    archive.add("low", {}, 0.5, _bd(x=0.1))
    best = archive.best_per_dimension("x")
    assert best is not None
    assert best.candidate_id == "low"


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


def test_stats_empty():
    archive = DiversityArchive(dimensions=["a", "b"], bins_per_dimension=3)
    s = archive.stats()
    assert s["occupied"] == 0
    assert s["coverage_pct"] == 0.0
    assert s["mean_fitness"] == 0.0
    assert s["total_cells"] == 9


def test_stats_populated():
    archive = DiversityArchive(
        dimensions=["x", "y"], bins_per_dimension=5, seed=15,
    )
    archive.add("a", {}, 0.4, _bd(x=0.1, y=0.1))
    archive.add("b", {}, 0.8, _bd(x=0.9, y=0.9))
    s = archive.stats()
    assert s["occupied"] == 2
    assert s["total_cells"] == 25
    assert s["coverage_pct"] == pytest.approx(8.0)
    assert s["mean_fitness"] == pytest.approx(0.6)
    assert s["max_fitness"] == pytest.approx(0.8)
    assert s["min_fitness"] == pytest.approx(0.4)
    assert s["diversity_score"] >= 0.0


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_serialization_roundtrip():
    archive = DiversityArchive(
        dimensions=["speed", "risk", "complexity"],
        bins_per_dimension=4,
        seed=16,
    )
    archive.add("a", {"code": "v1"}, 0.7, _bd(speed=0.3, risk=0.5, complexity=0.2))
    archive.add("b", {"code": "v2"}, 0.9, _bd(speed=0.8, risk=0.1, complexity=0.9))

    data = archive.to_dict()
    restored = DiversityArchive.from_dict(data, seed=16)

    assert restored.dimensions == archive.dimensions
    assert restored.bins_per_dimension == archive.bins_per_dimension
    assert len(restored._grid) == len(archive._grid)

    # Verify content matches
    original_stats = archive.stats()
    restored_stats = restored.stats()
    assert original_stats["occupied"] == restored_stats["occupied"]
    assert original_stats["mean_fitness"] == restored_stats["mean_fitness"]


def test_serialization_json_valid():
    archive = DiversityArchive(dimensions=["x"], bins_per_dimension=3, seed=17)
    archive.add("c1", {"data": 42}, 0.5, _bd(x=0.5))
    data = archive.to_dict()
    text = json.dumps(data)
    assert isinstance(json.loads(text), dict)


async def test_persist_and_load(tmp_path):
    path = tmp_path / "diversity.json"
    archive = DiversityArchive(
        dimensions=["a", "b"],
        bins_per_dimension=5,
        persist_path=path,
        seed=18,
    )
    archive.add("x", {"val": 1}, 0.6, _bd(a=0.2, b=0.8))
    archive.add("y", {"val": 2}, 0.9, _bd(a=0.7, b=0.3))

    saved_path = await archive.persist()
    assert saved_path.exists()

    loaded = await DiversityArchive.load(
        dimensions=["a", "b"],
        bins_per_dimension=5,
        persist_path=path,
        seed=18,
    )
    assert loaded.stats()["occupied"] == 2
    cell = loaded.get_cell(_bd(a=0.7, b=0.3))
    assert cell is not None
    assert cell.candidate_id == "y"


# ---------------------------------------------------------------------------
# BehaviorDescriptor
# ---------------------------------------------------------------------------


def test_behavior_descriptor_validate_dimensions():
    bd = _bd(x=0.5, y=0.3)
    assert bd.validate_dimensions(["x", "y"]) is True
    assert bd.validate_dimensions(["x", "y", "z"]) is False


def test_behavior_descriptor_out_of_range():
    bd = BehaviorDescriptor(dimensions={"x": 1.5})
    assert bd.validate_dimensions(["x"]) is False
