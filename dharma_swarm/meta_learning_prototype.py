"""Minimal meta-learning loop for Darwin Engine fitness weights.

This is intentionally small: it searches over fitness-weight configurations
without introducing full meta-archives, convergence detectors, or new storage
surfaces. The goal is to turn the current Darwin Engine weight-tuning idea into
real code that can be exercised and tested now.
"""

from __future__ import annotations

import inspect
import random
from statistics import mean
from typing import Any, Awaitable, Callable, TypeAlias

from pydantic import BaseModel, Field

from dharma_swarm.archive import FITNESS_DIMENSIONS, normalize_fitness_weights
from dharma_swarm.evolution import DarwinEngine, Proposal

MetaScorer: TypeAlias = Callable[
    [dict[str, float], list[Proposal]],
    float | Awaitable[float],
]


class MetaCycleResult(BaseModel):
    """Single meta-cycle outcome."""

    cycle_index: int
    baseline_score: float
    selected_score: float
    improved: bool = False
    weights: dict[str, float] = Field(default_factory=dict)
    candidate_scores: list[float] = Field(default_factory=list)


class MetaExperimentResult(BaseModel):
    """Summary of a meta-learning run."""

    baseline_score: float = 0.0
    final_score: float = 0.0
    fitness_improvement: float = 0.0
    weight_history: list[dict[str, float]] = Field(default_factory=list)
    cycles: list[MetaCycleResult] = Field(default_factory=list)


class MetaLearningPrototype:
    """Search over Darwin Engine fitness weights with a lightweight loop."""

    def __init__(
        self,
        darwin_engine: DarwinEngine,
        mutation_scale: float = 0.35,
        seed: int | None = None,
    ) -> None:
        self.darwin = darwin_engine
        self.mutation_scale = min(1.0, max(0.05, float(mutation_scale)))
        self._rng = random.Random(seed)
        self.fitness_weights = self.darwin.get_fitness_weights()
        self.meta_history: list[dict[str, Any]] = []

    async def run_meta_experiment(
        self,
        proposals: list[Proposal],
        n_meta_cycles: int = 3,
        candidates_per_cycle: int = 4,
        scorer: MetaScorer | None = None,
    ) -> MetaExperimentResult:
        """Run a small search over fitness-weight configurations."""
        if n_meta_cycles < 1:
            raise ValueError("n_meta_cycles must be >= 1")
        if candidates_per_cycle < 1:
            raise ValueError("candidates_per_cycle must be >= 1")

        current_weights = normalize_fitness_weights(self.fitness_weights)
        current_score = await self.evaluate_weights(
            proposals,
            current_weights,
            scorer=scorer,
        )

        result = MetaExperimentResult(
            baseline_score=current_score,
            final_score=current_score,
            weight_history=[dict(current_weights)],
        )

        for cycle_index in range(n_meta_cycles):
            candidate_scores: list[float] = []
            selected_weights = current_weights
            selected_score = current_score

            for _ in range(candidates_per_cycle):
                candidate_weights = self._evolve_weights(current_weights)
                candidate_score = await self.evaluate_weights(
                    proposals,
                    candidate_weights,
                    scorer=scorer,
                )
                candidate_scores.append(candidate_score)
                if candidate_score > selected_score:
                    selected_score = candidate_score
                    selected_weights = candidate_weights

            improved = selected_score > current_score
            current_weights = selected_weights
            current_score = selected_score
            result.weight_history.append(dict(current_weights))
            result.cycles.append(
                MetaCycleResult(
                    cycle_index=cycle_index,
                    baseline_score=result.baseline_score,
                    selected_score=current_score,
                    improved=improved,
                    weights=dict(current_weights),
                    candidate_scores=candidate_scores,
                )
            )

        self.fitness_weights = dict(current_weights)
        self.darwin.set_fitness_weights(current_weights)
        result.final_score = current_score
        result.fitness_improvement = current_score - result.baseline_score
        self.meta_history = [cycle.model_dump(mode="json") for cycle in result.cycles]
        return result

    async def evaluate_weights(
        self,
        proposals: list[Proposal],
        weights: dict[str, float],
        scorer: MetaScorer | None = None,
    ) -> float:
        """Score a weight configuration against a proposal set."""
        normalized = normalize_fitness_weights(weights)
        if scorer is not None:
            score = scorer(normalized, [p.model_copy(deep=True) for p in proposals])
            if inspect.isawaitable(score):
                score = await score
            return float(score)

        original_weights = self.darwin.get_fitness_weights()
        self.darwin.set_fitness_weights(normalized)
        try:
            trial_scores: list[float] = []
            for proposal in proposals:
                candidate = proposal.model_copy(deep=True)
                await self.darwin.gate_check(candidate)
                await self.darwin.evaluate(candidate)
                trial_scores.append(self.darwin.score_fitness(candidate.actual_fitness))
            return mean(trial_scores) if trial_scores else 0.0
        finally:
            self.darwin.set_fitness_weights(original_weights)

    def _evolve_weights(
        self,
        weights: dict[str, float],
    ) -> dict[str, float]:
        """Blend the current weights with a random distribution."""
        evolved: dict[str, float] = {}
        for dimension in FITNESS_DIMENSIONS:
            current = weights[dimension]
            random_mass = self._rng.random()
            evolved[dimension] = (
                (1.0 - self.mutation_scale) * current
                + self.mutation_scale * random_mass
            )
        return normalize_fitness_weights(evolved)

    @staticmethod
    def format_weights(weights: dict[str, float]) -> str:
        """Pretty-print a weight configuration in canonical dimension order."""
        ordered = [f"{name[:3]}={weights[name]:.2f}" for name in FITNESS_DIMENSIONS]
        return ", ".join(ordered)
