"""Island-based evolution with periodic migration.

Inspired by:
  - AlphaEvolve (Google DeepMind): island populations prevent premature convergence
  - FunSearch (Nature 2024): 15 samplers + 150 evaluators, island model
  - QuantEvolve: quality-diversity feature map with island migration

Multiple independent populations ("islands") evolve in parallel. Periodically,
the top performers migrate between islands, preventing convergence collapse
while maintaining diverse search trajectories.

Grounded in:
  - Kauffman (Pillar 2): adjacent possible -- islands explore different regions
  - Beer (Pillar 8): requisite variety -- diversity is necessary for resilience
"""

from __future__ import annotations

import json
import logging
import math
import random
from pathlib import Path
from statistics import mean, pvariance
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)

_DEFAULT_ISLANDS_DIR = Path.home() / ".dharma" / "evolution" / "islands"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class Candidate(BaseModel):
    """A solution candidate living on an island."""

    id: str = Field(default_factory=_new_id)
    payload: dict[str, Any] = Field(default_factory=dict)
    fitness: float = 0.0
    generation: int = 0
    parent_ids: list[str] = Field(default_factory=list)
    origin_island: int = 0
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


class Island(BaseModel):
    """An independent population evolving in isolation."""

    id: int = 0
    population: list[Candidate] = Field(default_factory=list)
    fitness_history: list[float] = Field(default_factory=list)
    generation_count: int = 0
    best_fitness: float = 0.0


# ---------------------------------------------------------------------------
# Island Evolution Manager
# ---------------------------------------------------------------------------


class IslandEvolutionManager:
    """Manage multiple island populations with periodic migration.

    Ring topology: island i migrates top candidates to island (i+1) % n.
    Each island maintains its own population and fitness history.

    Args:
        num_islands: Number of independent populations.
        population_per_island: Maximum candidates per island.
        migration_rate: Fraction of top candidates that migrate each interval.
        migration_interval: Generations between migration events.
        seed: Optional RNG seed for reproducibility.
        persist_dir: Directory for island state persistence.
    """

    def __init__(
        self,
        num_islands: int = 4,
        population_per_island: int = 10,
        migration_rate: float = 0.1,
        migration_interval: int = 5,
        seed: int | None = None,
        persist_dir: Path | None = None,
    ) -> None:
        self.num_islands = max(2, int(num_islands))
        self.population_per_island = max(2, int(population_per_island))
        self.migration_rate = max(0.0, min(1.0, float(migration_rate)))
        self.migration_interval = max(1, int(migration_interval))
        self.persist_dir = persist_dir or _DEFAULT_ISLANDS_DIR
        self._rng = random.Random(seed)
        self._global_generation = 0

        self.islands: list[Island] = [
            Island(id=i) for i in range(self.num_islands)
        ]

    # -- Population management -----------------------------------------------

    def add_candidate(
        self,
        island_id: int,
        candidate: Candidate,
    ) -> bool:
        """Add a candidate to a specific island.

        If the island is at capacity, the weakest candidate is evicted
        only if the new candidate is fitter.

        Returns:
            True if the candidate was added, False if rejected.
        """
        if island_id < 0 or island_id >= self.num_islands:
            raise ValueError(
                f"Island {island_id} out of range [0, {self.num_islands})"
            )

        island = self.islands[island_id]
        candidate.origin_island = island_id

        if len(island.population) < self.population_per_island:
            island.population.append(candidate)
            island.best_fitness = max(island.best_fitness, candidate.fitness)
            return True

        # Evict weakest if new candidate is fitter
        weakest = min(island.population, key=lambda c: c.fitness)
        if candidate.fitness > weakest.fitness:
            island.population.remove(weakest)
            island.population.append(candidate)
            island.best_fitness = max(
                c.fitness for c in island.population
            )
            return True

        return False

    # -- Evolution -----------------------------------------------------------

    def evolve_island(self, island_id: int) -> list[Candidate]:
        """Run one generation on a single island.

        Selects parents via tournament selection, creates offspring through
        crossover and mutation of payload keys. Returns the new offspring.

        Args:
            island_id: Which island to evolve.

        Returns:
            List of newly created offspring candidates.
        """
        if island_id < 0 or island_id >= self.num_islands:
            raise ValueError(
                f"Island {island_id} out of range [0, {self.num_islands})"
            )

        island = self.islands[island_id]
        if len(island.population) < 2:
            return []

        island.generation_count += 1
        self._global_generation = max(
            self._global_generation, island.generation_count
        )

        offspring: list[Candidate] = []
        n_offspring = max(1, len(island.population) // 2)

        for _ in range(n_offspring):
            parent_a = self._tournament_select(island)
            parent_b = self._tournament_select(island)
            child = self._crossover_and_mutate(parent_a, parent_b, island_id)
            offspring.append(child)

        # Add offspring (will evict weaker candidates if at capacity)
        for child in offspring:
            self.add_candidate(island_id, child)

        # Record fitness history
        if island.population:
            best = max(c.fitness for c in island.population)
            island.best_fitness = best
            island.fitness_history.append(best)

        return offspring

    def _tournament_select(
        self, island: Island, tournament_size: int = 3,
    ) -> Candidate:
        """Select a parent via tournament selection."""
        k = min(tournament_size, len(island.population))
        competitors = self._rng.sample(island.population, k)
        return max(competitors, key=lambda c: c.fitness)

    def _crossover_and_mutate(
        self,
        parent_a: Candidate,
        parent_b: Candidate,
        island_id: int,
    ) -> Candidate:
        """Create an offspring by merging parent payloads with mutation.

        Payload keys are inherited from either parent with equal probability.
        A small mutation perturbs numeric values.
        """
        child_payload: dict[str, Any] = {}
        all_keys = set(parent_a.payload) | set(parent_b.payload)

        for key in all_keys:
            source = parent_a if self._rng.random() < 0.5 else parent_b
            value = source.payload.get(key)
            if value is None:
                other = parent_b if source is parent_a else parent_a
                value = other.payload.get(key)
            # Mutate numeric values
            if isinstance(value, (int, float)):
                if self._rng.random() < 0.2:
                    value = value * self._rng.uniform(0.8, 1.2)
            child_payload[key] = value

        # Fitness is not inherited -- must be evaluated externally.
        # We assign a blended estimate so the candidate can compete for a slot.
        estimated_fitness = (parent_a.fitness + parent_b.fitness) / 2.0

        return Candidate(
            payload=child_payload,
            fitness=estimated_fitness,
            generation=max(parent_a.generation, parent_b.generation) + 1,
            parent_ids=[parent_a.id, parent_b.id],
            origin_island=island_id,
        )

    # -- Migration -----------------------------------------------------------

    def migrate(self) -> int:
        """Migrate top candidates between islands using ring topology.

        Island i sends its top `migration_rate` fraction to island (i+1) % n.

        Returns:
            Total number of candidates migrated.
        """
        n_migrated = 0
        migrants_per_island: list[list[Candidate]] = []

        for island in self.islands:
            if not island.population:
                migrants_per_island.append([])
                continue
            k = max(1, int(len(island.population) * self.migration_rate))
            sorted_pop = sorted(
                island.population, key=lambda c: c.fitness, reverse=True,
            )
            # Copy candidates for migration (they stay on source island too)
            migrants = [
                c.model_copy(deep=True) for c in sorted_pop[:k]
            ]
            migrants_per_island.append(migrants)

        # Ring topology: island i -> island (i+1) % n
        for i, migrants in enumerate(migrants_per_island):
            target_id = (i + 1) % self.num_islands
            for migrant in migrants:
                migrant.origin_island = target_id
                if self.add_candidate(target_id, migrant):
                    n_migrated += 1

        if n_migrated > 0:
            logger.info(
                "Migration: %d candidates moved across %d islands",
                n_migrated,
                self.num_islands,
            )

        return n_migrated

    def should_migrate(self) -> bool:
        """Check if a migration is due based on global generation count."""
        return (
            self._global_generation > 0
            and self._global_generation % self.migration_interval == 0
        )

    # -- Queries -------------------------------------------------------------

    def best_overall(self) -> Candidate | None:
        """Return the single best candidate across all islands."""
        all_candidates = [
            c for island in self.islands for c in island.population
        ]
        if not all_candidates:
            return None
        return max(all_candidates, key=lambda c: c.fitness)

    def diversity_score(self) -> float:
        """Measure behavioral diversity across islands.

        Computes the coefficient of variation of mean fitness across islands.
        Higher values indicate greater inter-island divergence (more diversity).
        Returns 0.0 when all islands have identical populations or are empty.
        """
        means = [
            mean(c.fitness for c in island.population)
            for island in self.islands
            if island.population
        ]
        if len(means) < 2:
            return 0.0
        mu = mean(means)
        if mu == 0.0:
            return 0.0
        variance = pvariance(means)
        return math.sqrt(variance) / abs(mu)

    def island_summary(self) -> list[dict[str, Any]]:
        """Return a summary dict for each island."""
        return [
            {
                "id": island.id,
                "population_size": len(island.population),
                "generation_count": island.generation_count,
                "best_fitness": island.best_fitness,
                "mean_fitness": (
                    mean(c.fitness for c in island.population)
                    if island.population
                    else 0.0
                ),
            }
            for island in self.islands
        ]

    # -- Serialization -------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full island manager state."""
        return {
            "num_islands": self.num_islands,
            "population_per_island": self.population_per_island,
            "migration_rate": self.migration_rate,
            "migration_interval": self.migration_interval,
            "global_generation": self._global_generation,
            "islands": [island.model_dump() for island in self.islands],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any], seed: int | None = None) -> IslandEvolutionManager:
        """Restore an island manager from serialized state."""
        manager = cls(
            num_islands=data["num_islands"],
            population_per_island=data["population_per_island"],
            migration_rate=data["migration_rate"],
            migration_interval=data["migration_interval"],
            seed=seed,
        )
        manager._global_generation = data.get("global_generation", 0)
        manager.islands = [
            Island.model_validate(island_data)
            for island_data in data["islands"]
        ]
        return manager

    async def persist(self) -> Path:
        """Save island state to disk as JSON."""
        import aiofiles

        self.persist_dir.mkdir(parents=True, exist_ok=True)
        path = self.persist_dir / "island_state.json"
        async with aiofiles.open(path, "w") as f:
            await f.write(json.dumps(self.to_dict(), indent=2))
        return path

    @classmethod
    async def load(
        cls,
        persist_dir: Path | None = None,
        seed: int | None = None,
    ) -> IslandEvolutionManager:
        """Load island state from disk."""
        import aiofiles

        directory = persist_dir or _DEFAULT_ISLANDS_DIR
        path = directory / "island_state.json"
        if not path.exists():
            return cls(persist_dir=directory, seed=seed)
        async with aiofiles.open(path, "r") as f:
            data = json.loads(await f.read())
        manager = cls.from_dict(data, seed=seed)
        manager.persist_dir = directory
        return manager
