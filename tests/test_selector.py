"""Tests for dharma_swarm.selector -- parent selection strategies."""

import pytest

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive, FitnessScore
from dharma_swarm.selector import (
    _count_children,
    _novelty_weight,
    elite_select,
    rank_select,
    roulette_select,
    select_parent,
    tournament_select,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _entry(correctness: float, **kw) -> ArchiveEntry:
    """Build an applied entry with a given correctness score."""
    return ArchiveEntry(
        fitness=FitnessScore(correctness=correctness),
        status="applied",
        **kw,
    )


@pytest.fixture
async def archive(tmp_path):
    """Archive pre-loaded with 7 entries of varying fitness."""
    path = tmp_path / "selector_archive.jsonl"
    a = EvolutionArchive(path=path)
    await a.load()

    for score in [0.1, 0.2, 0.3, 0.5, 0.6, 0.8, 1.0]:
        await a.add_entry(_entry(score))

    return a


@pytest.fixture
async def empty_archive(tmp_path):
    """Archive with no entries at all."""
    path = tmp_path / "empty_archive.jsonl"
    a = EvolutionArchive(path=path)
    await a.load()
    return a


@pytest.fixture
async def single_archive(tmp_path):
    """Archive with exactly one applied entry."""
    path = tmp_path / "single_archive.jsonl"
    a = EvolutionArchive(path=path)
    await a.load()
    await a.add_entry(_entry(0.7, component="solo.py"))
    return a


@pytest.fixture
async def proposed_only_archive(tmp_path):
    """Archive where all entries are proposed (none applied)."""
    path = tmp_path / "proposed_archive.jsonl"
    a = EvolutionArchive(path=path)
    await a.load()
    for score in [0.3, 0.5, 0.9]:
        await a.add_entry(
            ArchiveEntry(
                fitness=FitnessScore(correctness=score),
                status="proposed",
            )
        )
    return a


# ---------------------------------------------------------------------------
# tournament_select
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tournament_returns_entry(archive):
    result = await tournament_select(archive, k=3)
    assert result is not None
    assert isinstance(result, ArchiveEntry)
    assert result.status == "applied"


@pytest.mark.asyncio
async def test_tournament_biases_toward_high_fitness(archive):
    """Run 50 tournaments and check that the top entry wins often."""
    wins: dict[str, int] = {}
    for _ in range(50):
        winner = await tournament_select(archive, k=3)
        assert winner is not None
        wins[winner.id] = wins.get(winner.id, 0) + 1

    # The entry with correctness=1.0 should win at least sometimes.
    best = await archive.get_best(n=1)
    best_id = best[0].id
    assert best_id in wins, "Top-fitness entry never won in 50 trials"


@pytest.mark.asyncio
async def test_tournament_k_larger_than_pool(archive):
    """When k exceeds candidate count, all entries participate."""
    result = await tournament_select(archive, k=100)
    assert result is not None
    # With all 7 entries in the pool the fittest must win.
    best = await archive.get_best(n=1)
    assert result.id == best[0].id


@pytest.mark.asyncio
async def test_tournament_empty(empty_archive):
    result = await tournament_select(empty_archive, k=3)
    assert result is None


@pytest.mark.asyncio
async def test_tournament_single(single_archive):
    result = await tournament_select(single_archive, k=3)
    assert result is not None
    assert result.component == "solo.py"


# ---------------------------------------------------------------------------
# roulette_select
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_roulette_returns_entry(archive):
    result = await roulette_select(archive)
    assert result is not None
    assert isinstance(result, ArchiveEntry)


@pytest.mark.asyncio
async def test_roulette_biases_toward_high_fitness(archive):
    """Higher fitness entries should be selected more often."""
    counts: dict[float, int] = {}
    for _ in range(200):
        winner = await roulette_select(archive)
        assert winner is not None
        score = winner.fitness.correctness
        counts[score] = counts.get(score, 0) + 1

    # The 1.0-correctness entry should appear more than the 0.1 entry.
    assert counts.get(1.0, 0) > counts.get(0.1, 0)


@pytest.mark.asyncio
async def test_roulette_empty(empty_archive):
    result = await roulette_select(empty_archive)
    assert result is None


@pytest.mark.asyncio
async def test_roulette_single(single_archive):
    result = await roulette_select(single_archive)
    assert result is not None
    assert result.component == "solo.py"


@pytest.mark.asyncio
async def test_roulette_all_zero_fitness(tmp_path):
    """When all fitnesses are zero, falls back to uniform random."""
    path = tmp_path / "zero_archive.jsonl"
    a = EvolutionArchive(path=path)
    await a.load()
    for _ in range(5):
        await a.add_entry(_entry(0.0))

    result = await roulette_select(a)
    assert result is not None


# ---------------------------------------------------------------------------
# rank_select
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rank_returns_entry(archive):
    result = await rank_select(archive)
    assert result is not None
    assert isinstance(result, ArchiveEntry)


@pytest.mark.asyncio
async def test_rank_biases_toward_high_fitness(archive):
    """Rank selection should favour higher-ranked entries."""
    counts: dict[float, int] = {}
    for _ in range(200):
        winner = await rank_select(archive)
        assert winner is not None
        score = winner.fitness.correctness
        counts[score] = counts.get(score, 0) + 1

    # Top rank (correctness=1.0) should appear more than bottom (0.1).
    assert counts.get(1.0, 0) > counts.get(0.1, 0)


@pytest.mark.asyncio
async def test_rank_empty(empty_archive):
    result = await rank_select(empty_archive)
    assert result is None


@pytest.mark.asyncio
async def test_rank_single(single_archive):
    result = await rank_select(single_archive)
    assert result is not None


# ---------------------------------------------------------------------------
# elite_select
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_elite_returns_sorted_top_n(archive):
    top3 = await elite_select(archive, n=3)
    assert len(top3) == 3
    # Must be sorted descending by weighted fitness.
    fitnesses = [e.fitness.weighted() for e in top3]
    assert fitnesses == sorted(fitnesses, reverse=True)
    # The first entry should have the highest correctness.
    assert top3[0].fitness.correctness == 1.0


@pytest.mark.asyncio
async def test_elite_returns_all_when_n_exceeds_count(archive):
    """Requesting more than available returns everything."""
    top100 = await elite_select(archive, n=100)
    assert len(top100) == 7


@pytest.mark.asyncio
async def test_elite_empty(empty_archive):
    result = await elite_select(empty_archive, n=3)
    assert result == []


@pytest.mark.asyncio
async def test_elite_single(single_archive):
    result = await elite_select(single_archive, n=3)
    assert len(result) == 1
    assert result[0].component == "solo.py"


# ---------------------------------------------------------------------------
# select_parent dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_select_parent_tournament(archive):
    result = await select_parent(archive, strategy="tournament", k=3)
    assert result is not None


@pytest.mark.asyncio
async def test_select_parent_roulette(archive):
    result = await select_parent(archive, strategy="roulette")
    assert result is not None


@pytest.mark.asyncio
async def test_select_parent_rank(archive):
    result = await select_parent(archive, strategy="rank")
    assert result is not None


@pytest.mark.asyncio
async def test_select_parent_elite(archive):
    result = await select_parent(archive, strategy="elite", n=2)
    assert result is not None
    # Should return the single best entry.
    best = await archive.get_best(n=1)
    assert result.id == best[0].id


@pytest.mark.asyncio
async def test_select_parent_unknown_strategy(archive):
    with pytest.raises(ValueError, match="Unknown selection strategy"):
        await select_parent(archive, strategy="bogus")


@pytest.mark.asyncio
async def test_select_parent_default_is_tournament(archive):
    """Default strategy (no arg) should work and return an entry."""
    result = await select_parent(archive)
    assert result is not None


@pytest.mark.asyncio
async def test_select_parent_empty_all_strategies(empty_archive):
    """Every strategy returns None on an empty archive."""
    for strat in ("tournament", "roulette", "rank", "elite"):
        result = await select_parent(empty_archive, strategy=strat)
        assert result is None, f"Strategy {strat!r} should return None"


@pytest.mark.asyncio
async def test_select_parent_proposed_only(proposed_only_archive):
    """Entries that are 'proposed' (not 'applied') should be invisible."""
    for strat in ("tournament", "roulette", "rank", "elite"):
        result = await select_parent(proposed_only_archive, strategy=strat)
        assert result is None, f"Strategy {strat!r} should skip proposed"


# ---------------------------------------------------------------------------
# Novelty bonus (Change 0A tests)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_novelty_bonus_reduces_overexploited_parent(tmp_path):
    """TEST 1: Entry B (fewer children) selected more often than pure fitness predicts."""
    path = tmp_path / "novelty_archive.jsonl"
    a = EvolutionArchive(path=path)
    await a.load()

    # A: high fitness (0.8), 10 children -> novelty_weight = 0.24 * (1/11) ≈ 0.022
    entry_a = ArchiveEntry(
        fitness=FitnessScore(correctness=0.8),
        status="applied",
        component="a.py",
    )
    await a.add_entry(entry_a)

    # Create 10 children of A
    for i in range(10):
        child = ArchiveEntry(
            parent_id=entry_a.id,
            fitness=FitnessScore(correctness=0.1),
            status="applied",
            component=f"child{i}.py",
        )
        await a.add_entry(child)

    # B: medium fitness (0.6), 0 children -> novelty_weight = 0.18 * 1.0 = 0.18
    entry_b = ArchiveEntry(
        fitness=FitnessScore(correctness=0.6),
        status="applied",
        component="b.py",
    )
    await a.add_entry(entry_b)

    # C: high fitness (0.7), 2 children
    entry_c = ArchiveEntry(
        fitness=FitnessScore(correctness=0.7),
        status="applied",
        component="c.py",
    )
    await a.add_entry(entry_c)
    for i in range(2):
        child = ArchiveEntry(
            parent_id=entry_c.id,
            fitness=FitnessScore(correctness=0.1),
            status="applied",
            component=f"c_child{i}.py",
        )
        await a.add_entry(child)

    # Run tournament 100 times with k=3
    wins: dict[str, int] = {}
    for _ in range(100):
        winner = await tournament_select(a, k=3)
        assert winner is not None
        wins[winner.id] = wins.get(winner.id, 0) + 1

    # B should win >20% despite lower fitness (novelty compensates)
    b_wins = wins.get(entry_b.id, 0)
    a_wins = wins.get(entry_a.id, 0)
    # A has 10 children, so its novelty weight is very low
    # B should be selected more than A
    assert b_wins > a_wins, (
        f"B (0 children) should beat A (10 children): B={b_wins}, A={a_wins}"
    )


def test_novelty_weight_formula():
    """Verify the novelty weight formula: fitness * (1 / (1 + n_children))."""
    entry = ArchiveEntry(
        fitness=FitnessScore(correctness=0.8, safety=1.0),
        status="applied",
    )
    # No children
    assert _novelty_weight(entry, {}) == entry.fitness.weighted()

    # 1 child
    w1 = _novelty_weight(entry, {entry.id: 1})
    assert w1 == pytest.approx(entry.fitness.weighted() * 0.5)

    # 9 children
    w9 = _novelty_weight(entry, {entry.id: 9})
    assert w9 == pytest.approx(entry.fitness.weighted() * 0.1)


@pytest.mark.asyncio
async def test_count_children(tmp_path):
    """_count_children correctly counts direct offspring."""
    path = tmp_path / "count_archive.jsonl"
    a = EvolutionArchive(path=path)
    await a.load()

    parent = ArchiveEntry(status="applied")
    await a.add_entry(parent)
    for _ in range(3):
        child = ArchiveEntry(parent_id=parent.id, status="applied")
        await a.add_entry(child)

    counts = await _count_children(a)
    assert counts[parent.id] == 3
