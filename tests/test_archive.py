"""Tests for dharma_swarm.archive -- EvolutionArchive + FitnessScore."""

import pytest

from dharma_swarm.archive import (
    ArchiveEntry,
    EvolutionArchive,
    FitnessScore,
    _DEFAULT_WEIGHTS,
)


# ---------------------------------------------------------------------------
# FitnessScore
# ---------------------------------------------------------------------------


def test_fitness_defaults_zero():
    f = FitnessScore()
    assert f.correctness == 0.0
    assert f.weighted() == 0.0


def test_fitness_weighted_default_weights():
    f = FitnessScore(
        correctness=1.0,
        dharmic_alignment=1.0,
        elegance=1.0,
        efficiency=1.0,
        safety=1.0,
    )
    # All 1.0 with weights summing to 1.0 should give 1.0
    assert f.weighted() == pytest.approx(1.0)


def test_fitness_weighted_custom_weights():
    f = FitnessScore(correctness=0.8, safety=1.0)
    custom = {"correctness": 1.0, "safety": 0.0}
    assert f.weighted(custom) == pytest.approx(0.8)


def test_fitness_weighted_partial_custom():
    f = FitnessScore(correctness=0.5, elegance=0.5)
    custom = {"correctness": 0.5, "elegance": 0.5}
    assert f.weighted(custom) == pytest.approx(0.5)


def test_fitness_json_roundtrip():
    f = FitnessScore(correctness=0.9, dharmic_alignment=0.85)
    data = f.model_dump_json()
    f2 = FitnessScore.model_validate_json(data)
    assert f2.correctness == f.correctness
    assert f2.dharmic_alignment == f.dharmic_alignment


# ---------------------------------------------------------------------------
# ArchiveEntry
# ---------------------------------------------------------------------------


def test_entry_defaults():
    e = ArchiveEntry()
    assert len(e.id) == 16
    assert e.status == "proposed"
    assert e.parent_id is None
    assert e.gates_passed == []
    assert e.tokens_used == 0


def test_entry_json_roundtrip():
    e = ArchiveEntry(
        component="test.py",
        change_type="mutation",
        description="test entry",
        fitness=FitnessScore(correctness=0.9, safety=1.0),
        gates_passed=["AHIMSA", "SATYA"],
    )
    data = e.model_dump_json()
    e2 = ArchiveEntry.model_validate_json(data)
    assert e2.id == e.id
    assert e2.component == "test.py"
    assert e2.fitness.correctness == 0.9
    assert e2.gates_passed == ["AHIMSA", "SATYA"]


# ---------------------------------------------------------------------------
# EvolutionArchive -- helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def archive_path(tmp_path):
    return tmp_path / "archive.jsonl"


@pytest.fixture
async def archive(archive_path):
    a = EvolutionArchive(path=archive_path)
    await a.load()
    return a


def _make_entry(**kw) -> ArchiveEntry:
    """Shorthand for building test entries."""
    return ArchiveEntry(**kw)


# ---------------------------------------------------------------------------
# EvolutionArchive -- core operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_and_get_entry(archive):
    entry = _make_entry(component="a.py", description="first")
    eid = await archive.add_entry(entry)
    got = await archive.get_entry(eid)
    assert got is not None
    assert got.component == "a.py"
    assert got.description == "first"


@pytest.mark.asyncio
async def test_get_entry_missing(archive):
    got = await archive.get_entry("nonexistent")
    assert got is None


@pytest.mark.asyncio
async def test_add_persists_to_disk(archive_path):
    archive = EvolutionArchive(path=archive_path)
    await archive.load()
    entry = _make_entry(component="b.py")
    eid = await archive.add_entry(entry)

    # Load a fresh instance from the same file
    archive2 = EvolutionArchive(path=archive_path)
    await archive2.load()
    got = await archive2.get_entry(eid)
    assert got is not None
    assert got.component == "b.py"


# ---------------------------------------------------------------------------
# Lineage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_lineage_three_generations(archive):
    grandparent = _make_entry(component="g.py", description="gen0")
    parent = _make_entry(
        component="g.py", description="gen1", parent_id=grandparent.id
    )
    child = _make_entry(
        component="g.py", description="gen2", parent_id=parent.id
    )

    await archive.add_entry(grandparent)
    await archive.add_entry(parent)
    await archive.add_entry(child)

    lineage = await archive.get_lineage(child.id)
    assert len(lineage) == 3
    assert lineage[0].id == child.id
    assert lineage[1].id == parent.id
    assert lineage[2].id == grandparent.id


@pytest.mark.asyncio
async def test_get_lineage_single(archive):
    entry = _make_entry(description="lone")
    await archive.add_entry(entry)
    lineage = await archive.get_lineage(entry.id)
    assert len(lineage) == 1


@pytest.mark.asyncio
async def test_get_lineage_missing_id(archive):
    lineage = await archive.get_lineage("nope")
    assert lineage == []


# ---------------------------------------------------------------------------
# Children
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_children(archive):
    parent = _make_entry(description="parent")
    c1 = _make_entry(parent_id=parent.id, description="child1")
    c2 = _make_entry(parent_id=parent.id, description="child2")
    unrelated = _make_entry(description="other")

    for e in (parent, c1, c2, unrelated):
        await archive.add_entry(e)

    children = await archive.get_children(parent.id)
    assert len(children) == 2
    child_ids = {c.id for c in children}
    assert c1.id in child_ids
    assert c2.id in child_ids


# ---------------------------------------------------------------------------
# get_best
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_best_sorted_by_fitness(archive):
    low = _make_entry(
        fitness=FitnessScore(correctness=0.1), status="applied"
    )
    mid = _make_entry(
        fitness=FitnessScore(correctness=0.5), status="applied"
    )
    high = _make_entry(
        fitness=FitnessScore(correctness=0.9), status="applied"
    )
    # proposed -- should be excluded
    proposed = _make_entry(
        fitness=FitnessScore(correctness=1.0), status="proposed"
    )

    for e in (low, mid, high, proposed):
        await archive.add_entry(e)

    best = await archive.get_best(n=3)
    assert len(best) == 3
    assert best[0].id == high.id
    assert best[1].id == mid.id
    assert best[2].id == low.id


@pytest.mark.asyncio
async def test_get_best_filtered_by_component(archive):
    a = _make_entry(
        component="x.py",
        fitness=FitnessScore(correctness=0.9),
        status="applied",
    )
    b = _make_entry(
        component="y.py",
        fitness=FitnessScore(correctness=0.8),
        status="applied",
    )

    for e in (a, b):
        await archive.add_entry(e)

    best = await archive.get_best(n=5, component="x.py")
    assert len(best) == 1
    assert best[0].id == a.id


@pytest.mark.asyncio
async def test_get_best_empty(archive):
    best = await archive.get_best(n=5)
    assert best == []


# ---------------------------------------------------------------------------
# get_latest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_latest_ordered(archive):
    e1 = _make_entry(description="old")
    e1.timestamp = "2025-01-01T00:00:00"
    e2 = _make_entry(description="new")
    e2.timestamp = "2025-12-01T00:00:00"
    e3 = _make_entry(description="mid")
    e3.timestamp = "2025-06-01T00:00:00"

    for e in (e1, e2, e3):
        await archive.add_entry(e)

    latest = await archive.get_latest(n=3)
    assert latest[0].id == e2.id
    assert latest[1].id == e3.id
    assert latest[2].id == e1.id


@pytest.mark.asyncio
async def test_get_latest_limited(archive):
    for i in range(10):
        await archive.add_entry(_make_entry(description=f"entry-{i}"))
    latest = await archive.get_latest(n=3)
    assert len(latest) == 3


# ---------------------------------------------------------------------------
# update_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_status_persists(archive_path):
    archive = EvolutionArchive(path=archive_path)
    await archive.load()
    entry = _make_entry(description="to update")
    eid = await archive.add_entry(entry)

    await archive.update_status(eid, "applied")
    got = await archive.get_entry(eid)
    assert got is not None
    assert got.status == "applied"

    # Reload from disk and verify persistence
    archive2 = EvolutionArchive(path=archive_path)
    await archive2.load()
    got2 = await archive2.get_entry(eid)
    assert got2 is not None
    assert got2.status == "applied"


@pytest.mark.asyncio
async def test_update_status_with_reason(archive):
    entry = _make_entry(description="will rollback")
    eid = await archive.add_entry(entry)

    await archive.update_status(eid, "rolled_back", reason="tests failed")
    got = await archive.get_entry(eid)
    assert got is not None
    assert got.status == "rolled_back"
    assert got.rollback_reason == "tests failed"


@pytest.mark.asyncio
async def test_update_status_missing_id(archive):
    # Should not raise
    await archive.update_status("nonexistent", "applied")


# ---------------------------------------------------------------------------
# fitness_over_time
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fitness_over_time(archive):
    e1 = _make_entry(
        fitness=FitnessScore(correctness=0.3), status="applied"
    )
    e1.timestamp = "2025-01-01T00:00:00"
    e2 = _make_entry(
        fitness=FitnessScore(correctness=0.9), status="applied"
    )
    e2.timestamp = "2025-06-01T00:00:00"
    # proposed -- excluded
    e3 = _make_entry(
        fitness=FitnessScore(correctness=1.0), status="proposed"
    )
    e3.timestamp = "2025-12-01T00:00:00"

    for e in (e1, e2, e3):
        await archive.add_entry(e)

    trajectory = archive.fitness_over_time()
    assert len(trajectory) == 2
    assert trajectory[0][0] == "2025-01-01T00:00:00"
    assert trajectory[1][0] == "2025-06-01T00:00:00"
    # Second entry has higher fitness
    assert trajectory[1][1] > trajectory[0][1]


@pytest.mark.asyncio
async def test_fitness_over_time_by_component(archive):
    a = _make_entry(component="x.py", fitness=FitnessScore(correctness=0.5), status="applied")
    b = _make_entry(component="y.py", fitness=FitnessScore(correctness=0.8), status="applied")

    for e in (a, b):
        await archive.add_entry(e)

    traj = archive.fitness_over_time(component="x.py")
    assert len(traj) == 1


# ---------------------------------------------------------------------------
# Empty archive edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_archive_operations(archive):
    assert await archive.get_entry("anything") is None
    assert await archive.get_lineage("anything") == []
    assert await archive.get_children("anything") == []
    assert await archive.get_best(5) == []
    assert await archive.get_latest(5) == []
    assert archive.fitness_over_time() == []


@pytest.mark.asyncio
async def test_load_nonexistent_file(tmp_path):
    archive = EvolutionArchive(path=tmp_path / "does_not_exist.jsonl")
    await archive.load()
    assert await archive.get_latest(5) == []
