"""Parent selection strategies for the evolution engine.

Ported from ~/DHARMIC_GODEL_CLAW/src/dgm/selector.py into dharma_swarm
conventions: async functions, type hints, no singletons.

Four strategies balance exploration vs. exploitation when choosing
which archive entries to evolve from:

- **tournament**: random k-way tournament (default, good balance)
- **roulette**: fitness-proportional (exploitation-heavy)
- **rank**: rank-based probability (smoother than roulette)
- **elite**: top-n deterministic (pure exploitation)
"""

from __future__ import annotations

import random
from typing import Any

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _get_applied(archive: EvolutionArchive) -> list[ArchiveEntry]:
    """Return all entries with status ``"applied"``.

    Uses ``archive.get_best()`` with a very large *n* so the archive's own
    filtering logic is reused.  The result is sorted by descending fitness,
    which several strategies rely on.
    """
    return await archive.get_best(n=999_999)


async def _count_children(archive: EvolutionArchive) -> dict[str, int]:
    """Count direct children for each entry in the archive.

    Returns:
        Mapping from entry_id to number of direct children.
    """
    counts: dict[str, int] = {}
    for entry in archive._entries.values():
        if entry.parent_id:
            counts[entry.parent_id] = counts.get(entry.parent_id, 0) + 1
    return counts


def _novelty_weight(
    entry: ArchiveEntry,
    child_counts: dict[str, int],
    weights: dict[str, float] | None = None,
) -> float:
    """Compute DGM-style novelty-adjusted weight.

    Formula: fitness * (1.0 / (1.0 + n_children))
    Balances exploitation (fitness) with exploration (fewer children = higher weight).

    Args:
        entry: The archive entry to weight.
        child_counts: Mapping from entry_id to child count.

    Returns:
        Novelty-adjusted weight (always >= 0).
    """
    fitness = entry.fitness.weighted(weights=weights)
    n_children = child_counts.get(entry.id, 0)
    novelty = 1.0 / (1.0 + n_children)
    return fitness * novelty


# ---------------------------------------------------------------------------
# Selection strategies
# ---------------------------------------------------------------------------


async def tournament_select(
    archive: EvolutionArchive,
    k: int = 3,
    weights: dict[str, float] | None = None,
) -> ArchiveEntry | None:
    """Pick *k* random applied entries and return the fittest.

    If the archive has fewer than *k* applied entries, all available
    entries participate in the tournament.  Returns ``None`` when the
    archive contains no applied entries.

    Args:
        archive: The evolution archive to draw from.
        k: Tournament size.  Larger *k* increases selection pressure.

    Returns:
        The winning ``ArchiveEntry``, or ``None`` if no candidates exist.
    """
    candidates = await _get_applied(archive)
    if not candidates:
        return None

    pool_size = min(k, len(candidates))
    pool = random.sample(candidates, pool_size)
    child_counts = await _count_children(archive)
    return max(pool, key=lambda e: _novelty_weight(e, child_counts, weights=weights))


async def roulette_select(
    archive: EvolutionArchive,
    weights: dict[str, float] | None = None,
) -> ArchiveEntry | None:
    """Fitness-proportional (roulette wheel) selection.

    Each applied entry's probability of being selected equals its
    weighted fitness divided by the total fitness of all candidates.
    When all fitnesses are zero, falls back to uniform random choice.

    Args:
        archive: The evolution archive to draw from.

    Returns:
        A single ``ArchiveEntry``, or ``None`` if no candidates exist.
    """
    candidates = await _get_applied(archive)
    if not candidates:
        return None

    child_counts = await _count_children(archive)
    candidate_weights = [
        _novelty_weight(e, child_counts, weights=weights) for e in candidates
    ]
    total = sum(candidate_weights)

    if total == 0.0:
        return random.choice(candidates)

    return random.choices(candidates, weights=candidate_weights, k=1)[0]


async def rank_select(
    archive: EvolutionArchive,
    weights: dict[str, float] | None = None,
) -> ArchiveEntry | None:
    """Rank-based selection.

    Applied entries are sorted by ascending fitness and assigned integer
    rank weights (worst=1, best=N).  Selection uses rank-based
    probability, which compresses the fitness scale and avoids
    domination by a single super-fit individual.

    Args:
        archive: The evolution archive to draw from.

    Returns:
        A single ``ArchiveEntry``, or ``None`` if no candidates exist.
    """
    candidates = await _get_applied(archive)
    if not candidates:
        return None

    # Sort ascending so rank 1 = worst, rank N = best.
    child_counts = await _count_children(archive)
    sorted_asc = sorted(
        candidates,
        key=lambda e: _novelty_weight(e, child_counts, weights=weights),
    )
    rank_weights = list(range(1, len(sorted_asc) + 1))

    return random.choices(sorted_asc, weights=rank_weights, k=1)[0]


async def elite_select(
    archive: EvolutionArchive,
    n: int = 3,
    weights: dict[str, float] | None = None,
) -> list[ArchiveEntry]:
    """Return the top *n* entries by weighted fitness.

    This is a thin wrapper around ``archive.get_best(n)`` that provides
    a consistent interface with the other selectors.

    Args:
        archive: The evolution archive to draw from.
        n: How many elite entries to return.

    Returns:
        A list of up to *n* ``ArchiveEntry`` objects, sorted by
        descending fitness.  May be empty if no applied entries exist.
    """
    return await archive.get_best(n=n, weights=weights)


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_STRATEGIES: dict[str, str] = {
    "tournament": "tournament_select",
    "roulette": "roulette_select",
    "rank": "rank_select",
    "elite": "elite_select",
}


async def select_parent(
    archive: EvolutionArchive,
    strategy: str = "tournament",
    **kwargs: Any,
) -> ArchiveEntry | None:
    """Unified dispatch for parent selection.

    Args:
        archive: The evolution archive to draw from.
        strategy: One of ``"tournament"``, ``"roulette"``, ``"rank"``,
            or ``"elite"``.
        **kwargs: Forwarded to the chosen strategy function (e.g.
            ``k=5`` for tournament, ``n=3`` for elite).

    Returns:
        A single ``ArchiveEntry``, or ``None`` when the archive is empty.

    Raises:
        ValueError: If *strategy* is not recognised.
    """
    if strategy not in _STRATEGIES:
        raise ValueError(
            f"Unknown selection strategy {strategy!r}. "
            f"Choose from: {', '.join(sorted(_STRATEGIES))}"
        )

    if strategy == "elite":
        entries = await elite_select(archive, **kwargs)
        return entries[0] if entries else None

    if strategy == "tournament":
        return await tournament_select(archive, **kwargs)

    if strategy == "roulette":
        return await roulette_select(archive, **kwargs)

    # rank
    return await rank_select(archive, **kwargs)
