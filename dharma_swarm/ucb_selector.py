"""UCB1-style parent selection for Darwin Engine."""

from __future__ import annotations

import math

from pydantic import BaseModel, Field

from dharma_swarm.archive import ArchiveEntry, EvolutionArchive


class UCBConfig(BaseModel):
    """Configuration for UCB parent selection."""

    exploration_coeff: float = 1.0
    min_pulls: int = 1
    annealing_rate: float = 0.99


class UCBState(BaseModel):
    """Mutable state for UCB selection across pulls."""

    total_pulls: int = 0
    child_counts: dict[str, int] = Field(default_factory=dict)
    exploration_coeff: float = 1.0


class UCBParentSelector:
    """Balance exploration and exploitation when choosing archive parents."""

    def __init__(self, config: UCBConfig | None = None) -> None:
        self.config = config or UCBConfig()
        self.state = UCBState(exploration_coeff=self.config.exploration_coeff)

    async def select_parent(
        self,
        archive: EvolutionArchive,
        weights: dict[str, float] | None = None,
    ) -> ArchiveEntry | None:
        """Select the next parent using a UCB1-style score."""
        entries = await archive.list_entries(status="applied")
        if not entries:
            return None

        unexplored = [
            entry
            for entry in entries
            if self.state.child_counts.get(entry.id, 0) < self.config.min_pulls
        ]
        if unexplored:
            min_count = min(self.state.child_counts.get(entry.id, 0) for entry in unexplored)
            candidates = [
                entry
                for entry in unexplored
                if self.state.child_counts.get(entry.id, 0) == min_count
            ]
            selected = max(
                candidates,
                key=lambda entry: (entry.fitness.weighted(weights=weights), entry.timestamp, entry.id),
            )
            return self._register_selection(selected)

        selected = max(
            entries,
            key=lambda entry: self._compute_ucb_score(entry, weights=weights),
        )
        return self._register_selection(selected)

    def _register_selection(self, entry: ArchiveEntry) -> ArchiveEntry:
        self.state.child_counts[entry.id] = self.state.child_counts.get(entry.id, 0) + 1
        self.state.total_pulls += 1
        self.state.exploration_coeff = max(
            0.01,
            self.state.exploration_coeff * self.config.annealing_rate,
        )
        return entry

    def _compute_ucb_score(
        self,
        entry: ArchiveEntry,
        weights: dict[str, float] | None = None,
    ) -> float:
        """Compute UCB1 score for a candidate parent."""
        mean_fitness = entry.fitness.weighted(weights=weights)
        n_i = max(1, self.state.child_counts.get(entry.id, 0))
        total = max(self.state.total_pulls, 1)
        exploration_bonus = math.sqrt((2.0 * math.log(total + 1.0)) / n_i)
        return mean_fitness + (self.state.exploration_coeff * exploration_bonus)

    def set_exploration_coeff(self, exploration_coeff: float) -> None:
        """Update the live exploration coefficient."""
        self.state.exploration_coeff = max(0.01, float(exploration_coeff))

    def get_exploration_ratio(self) -> float:
        """Return remaining exploration mass relative to the starting config."""
        baseline = max(self.config.exploration_coeff, 0.01)
        return max(0.0, min(1.0, self.state.exploration_coeff / baseline))
