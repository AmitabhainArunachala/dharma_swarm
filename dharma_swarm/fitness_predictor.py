"""Fitness predictor for DHARMA SWARM evolution.

Estimates likely fitness of a proposed code change BEFORE expensive evaluation.
Learns from historical outcomes: group by (component, change_type), compute mean
fitness, apply heuristic bonuses/penalties for diff size and test coverage.

No ML frameworks, no numpy. Pure statistics from historical JSONL data.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


# === Models ===


class ProposalFeatures(BaseModel):
    """Feature vector describing a proposed code change."""

    component: str = Field(description="Which file or module is being changed")
    change_type: str = Field(description="mutation, crossover, or ablation")
    diff_size: int = Field(ge=0, description="Lines changed")
    complexity_delta: float = Field(
        default=0.0, description="Change in cyclomatic complexity"
    )
    test_coverage_exists: bool = Field(
        default=False, description="Whether tests exist for the component"
    )
    gates_likely_to_pass: int = Field(
        default=0, ge=0, description="Estimated gates that will pass (historical)"
    )


class PredictionOutcome(BaseModel):
    """A recorded outcome linking features to actual fitness."""

    features: ProposalFeatures
    actual_fitness: float = Field(ge=0.0, le=1.0)


# === Predictor ===


_NEUTRAL_PRIOR: float = 0.5
_SMALL_DIFF_THRESHOLD: int = 50
_LARGE_DIFF_THRESHOLD: int = 200
_SMALL_DIFF_BONUS: float = 0.05
_LARGE_DIFF_PENALTY: float = 0.1
_TEST_COVERAGE_BONUS: float = 0.05


class FitnessPredictor:
    """Lightweight fitness predictor based on historical evolution outcomes.

    Groups outcomes by (component, change_type) and computes running means.
    Applies heuristic adjustments for diff size and test coverage.
    Persists history to a JSONL file for cross-session learning.

    Attributes:
        history_path: Path to the JSONL file storing historical outcomes.
    """

    def __init__(self, history_path: Optional[Path] = None) -> None:
        if history_path is None:
            history_path = Path.home() / ".dharma" / "evolution" / "predictor_data.jsonl"
        self.history_path: Path = history_path
        self._outcomes: list[PredictionOutcome] = []
        self._group_means: dict[tuple[str, str], float] = {}
        self._group_counts: dict[tuple[str, str], int] = {}

    async def load(self) -> None:
        """Load historical outcomes from the JSONL file."""
        import asyncio

        self._outcomes.clear()
        if not self.history_path.exists():
            self._recompute_groups()
            return

        def _load_sync() -> list[PredictionOutcome]:
            outcomes: list[PredictionOutcome] = []
            with open(self.history_path, "r") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        outcome = PredictionOutcome.model_validate(data)
                        outcomes.append(outcome)
                    except (json.JSONDecodeError, ValueError):
                        continue
            return outcomes

        self._outcomes = await asyncio.to_thread(_load_sync)
        self._recompute_groups()

    async def record_outcome(
        self, features: ProposalFeatures, actual_fitness: float
    ) -> PredictionOutcome:
        """Append a new outcome to history and update group statistics.

        Args:
            features: The proposal features that were evaluated.
            actual_fitness: The actual fitness score (0.0 to 1.0).

        Returns:
            The recorded PredictionOutcome.
        """
        import asyncio

        outcome = PredictionOutcome(features=features, actual_fitness=actual_fitness)
        self._outcomes.append(outcome)

        def _write_sync() -> None:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.history_path, "a") as fh:
                fh.write(outcome.model_dump_json() + "\n")

        await asyncio.to_thread(_write_sync)

        self._recompute_groups()
        return outcome

    def predict(self, features: ProposalFeatures) -> float:
        """Estimate fitness of a proposal based on historical data.

        Strategy:
            1. Look up mean fitness for (component, change_type) group.
            2. If no history exists for this group, start with neutral prior (0.5).
            3. Apply bonus for small diffs (< 50 lines).
            4. Apply penalty for large diffs (> 200 lines).
            5. Apply bonus if test coverage exists.
            6. Clamp result to [0.0, 1.0].

        Args:
            features: The proposal to evaluate.

        Returns:
            Predicted fitness score between 0.0 and 1.0.
        """
        key = (features.component, features.change_type)
        base = self._group_means.get(key, _NEUTRAL_PRIOR)

        # Diff size adjustments
        if features.diff_size < _SMALL_DIFF_THRESHOLD:
            base += _SMALL_DIFF_BONUS
        elif features.diff_size > _LARGE_DIFF_THRESHOLD:
            base -= _LARGE_DIFF_PENALTY

        # Test coverage bonus
        if features.test_coverage_exists:
            base += _TEST_COVERAGE_BONUS

        return max(0.0, min(1.0, base))

    def should_attempt(
        self, features: ProposalFeatures, threshold: float = 0.3
    ) -> bool:
        """Decide whether a proposal is worth attempting.

        Args:
            features: The proposal to evaluate.
            threshold: Minimum predicted fitness to proceed.

        Returns:
            True if predicted fitness exceeds the threshold.
        """
        return self.predict(features) > threshold

    def _recompute_groups(self) -> None:
        """Rebuild group means and counts from current outcomes."""
        sums: dict[tuple[str, str], float] = defaultdict(float)
        counts: dict[tuple[str, str], int] = defaultdict(int)
        for outcome in self._outcomes:
            key = (outcome.features.component, outcome.features.change_type)
            sums[key] += outcome.actual_fitness
            counts[key] += 1
        self._group_means = {k: sums[k] / counts[k] for k in sums}
        self._group_counts = dict(counts)

    @property
    def outcome_count(self) -> int:
        """Total number of recorded outcomes."""
        return len(self._outcomes)

    @property
    def group_count(self) -> int:
        """Number of distinct (component, change_type) groups."""
        return len(self._group_means)

    def estimate_subtree_potential(
        self,
        entry_id: str,
        archive_entries: dict[str, Any],
    ) -> float:
        """Estimate the metaproductivity of an entry's subtree (HGM CMP pattern).

        Looks at all descendants and computes the max fitness achieved
        in the subtree. An entry with low personal fitness but high-fitness
        descendants has high metaproductivity.

        Args:
            entry_id: The root entry to evaluate.
            archive_entries: Dict mapping entry_id to entry objects
                (must have .parent_id and .fitness.weighted() attributes).

        Returns:
            Estimated subtree potential (0.0 to 1.0).
            Returns the entry's own fitness if no descendants exist.
        """
        # Find all descendants via BFS
        descendants: list[float] = []
        queue = [entry_id]
        visited: set[str] = {entry_id}

        while queue:
            current_id = queue.pop(0)
            for eid, entry in archive_entries.items():
                if eid in visited:
                    continue
                if getattr(entry, "parent_id", None) == current_id:
                    visited.add(eid)
                    queue.append(eid)
                    fitness = getattr(entry, "fitness", None)
                    if fitness and hasattr(fitness, "weighted"):
                        descendants.append(fitness.weighted())

        if not descendants:
            # No descendants — return own fitness or neutral
            own = archive_entries.get(entry_id)
            if own and hasattr(own, "fitness") and hasattr(own.fitness, "weighted"):
                return own.fitness.weighted()
            return _NEUTRAL_PRIOR

        # CMP = max descendant fitness (could also use mean or weighted)
        return max(descendants)
