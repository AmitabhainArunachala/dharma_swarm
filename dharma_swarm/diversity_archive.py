"""MAP-Elites style diversity archive for solution variants.

Maintains a grid of solutions indexed by behavioral properties, not just
performance. Each cell holds the best solution for that behavioral niche.

Inspired by:
  - QuantEvolve: multi-dimensional feature map (Sharpe x Frequency x Drawdown)
  - FunSearch: best-shot prompting from diverse high-quality pool
  - MAP-Elites: quality-diversity optimization

Grounded in:
  - Kauffman (Pillar 2): each cell is an adjacent possible state
  - Ashby: requisite variety requires diverse solutions

Differs from archive.MAPElitesGrid by supporting:
  - Arbitrary user-defined dimensions (not hard-coded 3)
  - Standalone candidates (not ArchiveEntry-coupled)
  - Diversity-aware sampling that maximizes behavioral spread
  - Full serialization/persistence lifecycle
"""

from __future__ import annotations

import itertools
import json
import logging
import math
import random
from pathlib import Path
from statistics import mean
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)

_DEFAULT_ARCHIVE_PATH = (
    Path.home() / ".dharma" / "evolution" / "diversity_archive.json"
)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class BehaviorDescriptor(BaseModel):
    """Multi-dimensional behavioral description of a solution.

    Each dimension is a float in [0.0, 1.0] representing a normalized
    behavioral property (e.g., complexity, speed, risk).
    """

    dimensions: dict[str, float] = Field(default_factory=dict)

    def validate_dimensions(self, expected: list[str]) -> bool:
        """Check that all expected dimension keys are present and in range."""
        for dim in expected:
            value = self.dimensions.get(dim)
            if value is None:
                return False
            if not (0.0 <= value <= 1.0):
                return False
        return True


class ArchiveCell(BaseModel):
    """A single cell in the diversity grid holding the best candidate for its niche."""

    candidate_id: str = Field(default_factory=_new_id)
    candidate_payload: dict[str, Any] = Field(default_factory=dict)
    fitness: float = 0.0
    generation: int = 0
    descriptor: BehaviorDescriptor = Field(default_factory=BehaviorDescriptor)
    inserted_at: str = Field(default_factory=lambda: _utc_now().isoformat())


# ---------------------------------------------------------------------------
# Diversity Archive
# ---------------------------------------------------------------------------


class DiversityArchive:
    """MAP-Elites grid with arbitrary behavioral dimensions.

    Solutions are placed into grid cells based on their behavioral descriptor.
    Each cell retains only the fittest solution for that behavioral niche,
    ensuring the archive maintains both quality and diversity.

    Args:
        dimensions: Names of behavioral dimensions that index the grid.
        bins_per_dimension: Number of bins along each dimension axis.
        persist_path: File path for JSON persistence.
        seed: Optional RNG seed for reproducible sampling.
    """

    def __init__(
        self,
        dimensions: list[str],
        bins_per_dimension: int = 5,
        persist_path: Path | None = None,
        seed: int | None = None,
    ) -> None:
        if not dimensions:
            raise ValueError("At least one behavioral dimension is required")
        self.dimensions = list(dimensions)
        self.bins_per_dimension = max(2, int(bins_per_dimension))
        self.persist_path = persist_path or _DEFAULT_ARCHIVE_PATH
        self._rng = random.Random(seed)

        # Grid maps bin-coordinate tuples to cells
        self._grid: dict[tuple[int, ...], ArchiveCell] = {}

    # -- Bin computation -----------------------------------------------------

    def _to_bin(self, value: float) -> int:
        """Map a [0, 1] value to a bin index."""
        clamped = max(0.0, min(1.0, float(value)))
        return min(int(clamped * self.bins_per_dimension), self.bins_per_dimension - 1)

    def _descriptor_to_key(self, behavior: BehaviorDescriptor) -> tuple[int, ...]:
        """Convert a behavior descriptor to a grid key."""
        return tuple(
            self._to_bin(behavior.dimensions.get(dim, 0.0))
            for dim in self.dimensions
        )

    # -- Core API ------------------------------------------------------------

    def add(
        self,
        candidate_id: str,
        candidate_payload: dict[str, Any],
        fitness: float,
        behavior: BehaviorDescriptor,
        generation: int = 0,
    ) -> bool:
        """Place a candidate in the grid. Replaces occupant only if fitter.

        Args:
            candidate_id: Unique identifier for the candidate.
            candidate_payload: Arbitrary data describing the solution.
            fitness: Scalar fitness score.
            behavior: Behavioral descriptor determining grid placement.
            generation: Evolution generation number.

        Returns:
            True if the candidate was inserted (new cell or higher fitness).
        """
        key = self._descriptor_to_key(behavior)
        existing = self._grid.get(key)

        if existing is not None and existing.fitness >= fitness:
            return False

        self._grid[key] = ArchiveCell(
            candidate_id=candidate_id,
            candidate_payload=candidate_payload,
            fitness=fitness,
            generation=generation,
            descriptor=behavior.model_copy(deep=True),
        )
        return True

    def get_cell(self, behavior: BehaviorDescriptor) -> ArchiveCell | None:
        """Look up the occupant of the cell matching a behavior descriptor."""
        key = self._descriptor_to_key(behavior)
        return self._grid.get(key)

    # -- Diversity-aware sampling --------------------------------------------

    def sample_diverse(self, n: int) -> list[ArchiveCell]:
        """Sample n candidates maximizing behavioral spread.

        Uses a greedy farthest-point strategy: start with the fittest cell,
        then iteratively pick the cell whose bin-coordinate is farthest
        from all already-selected cells.

        Args:
            n: Number of candidates to sample.

        Returns:
            List of ArchiveCells with maximally spread behavior descriptors.
        """
        if not self._grid:
            return []

        cells = list(self._grid.items())
        n = min(n, len(cells))

        if n <= 0:
            return []

        # Start with the fittest cell
        best_key, best_cell = max(cells, key=lambda kv: kv[1].fitness)
        selected_keys: list[tuple[int, ...]] = [best_key]
        selected_cells: list[ArchiveCell] = [best_cell]

        remaining = {k: cell for k, cell in cells if k != best_key}

        for _ in range(n - 1):
            if not remaining:
                break
            # Pick the remaining cell farthest from all selected
            farthest_key: tuple[int, ...] | None = None
            farthest_dist = -1.0

            for key in remaining:
                min_dist = min(
                    self._bin_distance(key, sk) for sk in selected_keys
                )
                if min_dist > farthest_dist:
                    farthest_dist = min_dist
                    farthest_key = key

            if farthest_key is None:
                break

            selected_keys.append(farthest_key)
            selected_cells.append(remaining.pop(farthest_key))

        return selected_cells

    @staticmethod
    def _bin_distance(a: tuple[int, ...], b: tuple[int, ...]) -> float:
        """Euclidean distance between two bin-coordinate tuples."""
        return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))

    # -- Queries -------------------------------------------------------------

    def coverage(self) -> float:
        """Fraction of grid cells that are occupied."""
        total = self.bins_per_dimension ** len(self.dimensions)
        if total == 0:
            return 0.0
        return len(self._grid) / total

    def best_per_dimension(self, dimension: str) -> ArchiveCell | None:
        """Return the cell with the highest value along one dimension.

        Among cells at the maximum bin for the given dimension, returns
        the one with the highest fitness.

        Args:
            dimension: Name of the behavioral dimension.

        Returns:
            The fittest cell at the maximum bin for this dimension, or None.
        """
        if dimension not in self.dimensions:
            raise ValueError(f"Unknown dimension: {dimension!r}")

        dim_index = self.dimensions.index(dimension)
        max_bin = self.bins_per_dimension - 1

        candidates = [
            cell
            for key, cell in self._grid.items()
            if key[dim_index] == max_bin
        ]
        if not candidates:
            # Fall back to highest bin that has occupants
            best_cell: ArchiveCell | None = None
            best_bin = -1
            for key, cell in self._grid.items():
                if key[dim_index] > best_bin or (
                    key[dim_index] == best_bin
                    and best_cell is not None
                    and cell.fitness > best_cell.fitness
                ):
                    best_bin = key[dim_index]
                    best_cell = cell
            return best_cell

        return max(candidates, key=lambda c: c.fitness)

    def stats(self) -> dict[str, Any]:
        """Summary statistics for the diversity archive."""
        cells = list(self._grid.values())
        total_possible = self.bins_per_dimension ** len(self.dimensions)
        occupied = len(cells)

        if not cells:
            return {
                "dimensions": self.dimensions,
                "bins_per_dimension": self.bins_per_dimension,
                "total_cells": total_possible,
                "occupied": 0,
                "coverage_pct": 0.0,
                "mean_fitness": 0.0,
                "max_fitness": 0.0,
                "min_fitness": 0.0,
                "diversity_score": 0.0,
            }

        fitnesses = [c.fitness for c in cells]
        # Diversity score: ratio of occupied cells weighted by spread
        # Higher is better -- more of the behavioral space is covered
        diversity = self._compute_diversity_score()

        return {
            "dimensions": self.dimensions,
            "bins_per_dimension": self.bins_per_dimension,
            "total_cells": total_possible,
            "occupied": occupied,
            "coverage_pct": round(100.0 * occupied / total_possible, 2),
            "mean_fitness": round(mean(fitnesses), 4),
            "max_fitness": round(max(fitnesses), 4),
            "min_fitness": round(min(fitnesses), 4),
            "diversity_score": round(diversity, 4),
        }

    def _compute_diversity_score(self) -> float:
        """Compute a diversity score combining coverage and spread.

        Score = coverage * mean_pairwise_distance_normalized
        Ranges from 0.0 (empty or single cell) to ~1.0 (full grid, well spread).
        """
        if len(self._grid) < 2:
            return 0.0

        keys = list(self._grid.keys())
        max_possible_dist = math.sqrt(
            len(self.dimensions) * (self.bins_per_dimension - 1) ** 2
        )
        if max_possible_dist == 0.0:
            return 0.0

        # Sample pairwise distances (cap at 100 pairs for large archives)
        if len(keys) <= 15:
            pairs = list(itertools.combinations(keys, 2))
        else:
            pairs = [
                (keys[i], keys[j])
                for i, j in {
                    tuple(sorted(self._rng.sample(range(len(keys)), 2)))
                    for _ in range(100)
                }
            ]

        if not pairs:
            return 0.0

        mean_dist = mean(self._bin_distance(a, b) for a, b in pairs)
        normalized_spread = mean_dist / max_possible_dist

        return self.coverage() * normalized_spread

    # -- Serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the archive state."""
        return {
            "dimensions": self.dimensions,
            "bins_per_dimension": self.bins_per_dimension,
            "grid": {
                ",".join(str(i) for i in key): cell.model_dump()
                for key, cell in self._grid.items()
            },
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        persist_path: Path | None = None,
        seed: int | None = None,
    ) -> DiversityArchive:
        """Restore an archive from serialized state."""
        archive = cls(
            dimensions=data["dimensions"],
            bins_per_dimension=data["bins_per_dimension"],
            persist_path=persist_path,
            seed=seed,
        )
        for key_str, cell_data in data.get("grid", {}).items():
            key = tuple(int(i) for i in key_str.split(","))
            archive._grid[key] = ArchiveCell.model_validate(cell_data)
        return archive

    async def persist(self) -> Path:
        """Save archive state to disk as JSON."""
        import aiofiles

        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(self.persist_path, "w") as f:
            await f.write(json.dumps(self.to_dict(), indent=2))
        return self.persist_path

    @classmethod
    async def load(
        cls,
        dimensions: list[str],
        bins_per_dimension: int = 5,
        persist_path: Path | None = None,
        seed: int | None = None,
    ) -> DiversityArchive:
        """Load archive from disk, or create empty if file does not exist."""
        import aiofiles

        path = persist_path or _DEFAULT_ARCHIVE_PATH
        if not path.exists():
            return cls(
                dimensions=dimensions,
                bins_per_dimension=bins_per_dimension,
                persist_path=path,
                seed=seed,
            )
        async with aiofiles.open(path, "r") as f:
            data = json.loads(await f.read())
        archive = cls.from_dict(data, persist_path=path, seed=seed)
        return archive
