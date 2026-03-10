"""Persisted meta-evolution for Darwin Engine hyperparameters."""

from __future__ import annotations

import random
from pathlib import Path
from statistics import mean, pvariance

from pydantic import BaseModel, Field, field_validator

from dharma_swarm.archive import normalize_fitness_weights
from dharma_swarm.evolution import CycleResult, DarwinEngine, Proposal
from dharma_swarm.models import _new_id, _utc_now


class MetaParameters(BaseModel):
    """Evolution hyperparameters that can be adapted over time."""

    fitness_weights: dict[str, float] = Field(
        default_factory=normalize_fitness_weights,
    )
    mutation_rate: float = 0.1
    exploration_coeff: float = 1.0
    circuit_breaker_limit: int = 3
    map_elites_n_bins: int = 5

    @field_validator("fitness_weights", mode="before")
    @classmethod
    def _normalize_weights(cls, value: dict[str, float] | None) -> dict[str, float]:
        return normalize_fitness_weights(value)


class MetaEvolutionResult(BaseModel):
    """Outcome of one meta-evolution cycle."""

    id: str = Field(default_factory=_new_id)
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())
    meta_parameters: MetaParameters
    object_cycles_completed: int = 0
    avg_fitness_trend: float = 0.0
    meta_fitness: float = 0.0
    improvement_over_baseline: float = 0.0
    fitness_trajectory: list[float] = Field(default_factory=list)
    trigger: str = "manual"
    source_cycle_ids: list[str] = Field(default_factory=list)
    evolved_parameters: bool = False
    applied_parameters: bool = False


class MetaArchiveEntry(BaseModel):
    """Archived meta-configuration with its observed performance."""

    id: str = Field(default_factory=_new_id)
    meta_parameters: MetaParameters
    meta_fitness: float
    n_object_cycles: int
    fitness_trajectory: list[float]
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())


class MetaEvolutionEngine:
    """Run object-level Darwin cycles and evolve the hyperparameters above them."""

    def __init__(
        self,
        darwin_engine: DarwinEngine,
        meta_archive_path: Path | None = None,
        n_object_cycles_per_meta: int = 10,
        poor_meta_fitness_threshold: float = 0.5,
        auto_apply: bool = True,
        max_weight_shift: float = 0.08,
        max_mutation_delta: float = 0.05,
        max_exploration_delta: float = 0.25,
        max_circuit_breaker_delta: int = 1,
        max_grid_delta: int = 1,
        seed: int | None = None,
    ) -> None:
        self.darwin = darwin_engine
        self.n_object_cycles = max(1, int(n_object_cycles_per_meta))
        self.poor_meta_fitness_threshold = float(poor_meta_fitness_threshold)
        self.auto_apply = bool(auto_apply)
        self.max_weight_shift = max(0.0, float(max_weight_shift))
        self.max_mutation_delta = max(0.0, float(max_mutation_delta))
        self.max_exploration_delta = max(0.0, float(max_exploration_delta))
        self.max_circuit_breaker_delta = max(0, int(max_circuit_breaker_delta))
        self.max_grid_delta = max(0, int(max_grid_delta))
        self.meta_archive_path = meta_archive_path or (
            Path.home() / ".dharma" / "evolution" / "meta_archive.jsonl"
        )
        self._rng = random.Random(seed)
        self.meta_archive: list[MetaArchiveEntry] = []
        self._observed_cycle_results: list[CycleResult] = []
        self._observed_cycles = 0
        self._load_meta_archive()
        self.meta_params = MetaParameters(**self.darwin.get_meta_parameter_state())
        self.darwin.apply_meta_parameters(self.meta_params)

    async def run_meta_cycle(self, proposals: list[Proposal]) -> MetaEvolutionResult:
        """Run object cycles, score them, archive the result, then adapt if needed."""
        self.darwin.apply_meta_parameters(self.meta_params)
        fitness_trajectory: list[float] = []
        source_cycle_ids: list[str] = []

        for _ in range(self.n_object_cycles):
            cycle_inputs = [proposal.model_copy(deep=True) for proposal in proposals]
            cycle_result: CycleResult = await self.darwin.run_cycle(cycle_inputs)
            fitness_trajectory.append(cycle_result.best_fitness)
            source_cycle_ids.append(cycle_result.cycle_id)

        return self._finalize_meta_cycle(
            fitness_trajectory,
            trigger="manual",
            source_cycle_ids=source_cycle_ids,
        )

    def observe_cycle_result(
        self,
        cycle_result: CycleResult,
    ) -> MetaEvolutionResult | None:
        """Periodically adapt hyperparameters from recent object-level cycles."""
        self._observed_cycles += 1
        self._observed_cycle_results.append(cycle_result.model_copy(deep=True))
        if len(self._observed_cycle_results) > self.n_object_cycles:
            self._observed_cycle_results = self._observed_cycle_results[
                -self.n_object_cycles :
            ]

        if self._observed_cycles % self.n_object_cycles != 0:
            return None

        window = self._observed_cycle_results[-self.n_object_cycles :]
        return self._finalize_meta_cycle(
            [cycle.best_fitness for cycle in window],
            trigger="periodic",
            source_cycle_ids=[cycle.cycle_id for cycle in window],
        )

    def _load_meta_archive(self) -> None:
        """Load historical meta-configurations from JSONL."""
        if not self.meta_archive_path.exists():
            return
        with self.meta_archive_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                self.meta_archive.append(MetaArchiveEntry.model_validate_json(stripped))

    def _archive_meta_entry(self, entry: MetaArchiveEntry) -> None:
        """Append a meta result to the JSONL archive."""
        self.meta_archive.append(entry)
        self.meta_archive_path.parent.mkdir(parents=True, exist_ok=True)
        with self.meta_archive_path.open("a", encoding="utf-8") as handle:
            handle.write(entry.model_dump_json() + "\n")

    def _compute_meta_fitness(self, fitness_trajectory: list[float]) -> float:
        """Score how well the object-level cycles improved."""
        if not fitness_trajectory:
            return 0.0
        if len(fitness_trajectory) == 1:
            return max(0.0, min(1.0, fitness_trajectory[0]))

        gradient = self._mean_diff(fitness_trajectory)
        variance = pvariance(fitness_trajectory) if len(fitness_trajectory) > 1 else 0.0
        final = fitness_trajectory[-1]

        gradient_component = max(0.0, min(1.0, 0.5 + gradient))
        stability_component = max(0.0, 1.0 - min(variance, 1.0))
        meta_fitness = (
            0.5 * gradient_component
            + 0.3 * max(0.0, min(1.0, final))
            + 0.2 * stability_component
        )
        return max(0.0, min(1.0, meta_fitness))

    def _evolve_meta_params(self) -> MetaParameters:
        """Mutate or crossover hyperparameters based on archive history."""
        if not self.meta_archive:
            return self._mutate_meta_params(self.meta_params)

        parents = sorted(
            self.meta_archive,
            key=lambda entry: entry.meta_fitness,
            reverse=True,
        )[:3]
        if len(parents) == 1:
            return self._mutate_meta_params(parents[0].meta_parameters)
        return self._crossover_meta_params([entry.meta_parameters for entry in parents])

    def _mutate_meta_params(self, params: MetaParameters) -> MetaParameters:
        """Apply bounded random perturbations to a parameter set."""
        mutated_weights = {
            key: max(0.001, value + self._rng.uniform(-0.05, 0.05))
            for key, value in params.fitness_weights.items()
        }
        return MetaParameters(
            fitness_weights=mutated_weights,
            mutation_rate=max(0.01, params.mutation_rate * self._rng.uniform(0.8, 1.2)),
            exploration_coeff=max(
                0.1,
                params.exploration_coeff * self._rng.uniform(0.8, 1.2),
            ),
            circuit_breaker_limit=max(
                1,
                params.circuit_breaker_limit + self._rng.randint(-1, 1),
            ),
            map_elites_n_bins=max(
                3,
                params.map_elites_n_bins + self._rng.randint(-1, 1),
            ),
        )

    def _crossover_meta_params(
        self,
        parent_params: list[MetaParameters],
    ) -> MetaParameters:
        """Average several high-performing parameter sets and lightly perturb them."""
        avg_weights = {
            key: mean(param.fitness_weights[key] for param in parent_params)
            for key in parent_params[0].fitness_weights
        }
        blended = MetaParameters(
            fitness_weights=avg_weights,
            mutation_rate=mean(param.mutation_rate for param in parent_params),
            exploration_coeff=mean(param.exploration_coeff for param in parent_params),
            circuit_breaker_limit=max(
                1,
                round(mean(param.circuit_breaker_limit for param in parent_params)),
            ),
            map_elites_n_bins=max(
                3,
                round(mean(param.map_elites_n_bins for param in parent_params)),
            ),
        )
        return self._mutate_meta_params(blended)

    def _finalize_meta_cycle(
        self,
        fitness_trajectory: list[float],
        *,
        trigger: str,
        source_cycle_ids: list[str],
    ) -> MetaEvolutionResult:
        """Archive one meta-evaluation window and optionally adapt parameters."""
        meta_fitness = self._compute_meta_fitness(fitness_trajectory)
        avg_trend = self._mean_diff(fitness_trajectory)
        improvement = (
            (fitness_trajectory[-1] - fitness_trajectory[0])
            if len(fitness_trajectory) > 1
            else 0.0
        )
        archive_entry = MetaArchiveEntry(
            meta_parameters=self.meta_params.model_copy(deep=True),
            meta_fitness=meta_fitness,
            n_object_cycles=len(fitness_trajectory),
            fitness_trajectory=fitness_trajectory,
        )
        self._archive_meta_entry(archive_entry)

        evolved = False
        applied = False
        if meta_fitness < self.poor_meta_fitness_threshold:
            candidate = self._bound_meta_params(
                self._evolve_meta_params(),
                baseline=self.meta_params,
            )
            evolved = candidate != self.meta_params
            if evolved:
                self.meta_params = candidate
                if self.auto_apply:
                    self.darwin.apply_meta_parameters(self.meta_params)
                    applied = True

        return MetaEvolutionResult(
            meta_parameters=self.meta_params.model_copy(deep=True),
            object_cycles_completed=len(fitness_trajectory),
            avg_fitness_trend=avg_trend,
            meta_fitness=meta_fitness,
            improvement_over_baseline=improvement,
            fitness_trajectory=fitness_trajectory,
            trigger=trigger,
            source_cycle_ids=source_cycle_ids,
            evolved_parameters=evolved,
            applied_parameters=applied,
        )

    def _bound_meta_params(
        self,
        candidate: MetaParameters,
        *,
        baseline: MetaParameters,
    ) -> MetaParameters:
        """Clamp proposed parameter changes to bounded per-cycle deltas."""
        bounded_weights = {
            key: self._clamp_float(
                candidate.fitness_weights.get(key, baseline.fitness_weights[key]),
                baseline.fitness_weights[key] - self.max_weight_shift,
                baseline.fitness_weights[key] + self.max_weight_shift,
            )
            for key in baseline.fitness_weights
        }
        return MetaParameters(
            fitness_weights=normalize_fitness_weights(bounded_weights),
            mutation_rate=self._clamp_float(
                candidate.mutation_rate,
                baseline.mutation_rate - self.max_mutation_delta,
                baseline.mutation_rate + self.max_mutation_delta,
            ),
            exploration_coeff=self._clamp_float(
                candidate.exploration_coeff,
                baseline.exploration_coeff - self.max_exploration_delta,
                baseline.exploration_coeff + self.max_exploration_delta,
            ),
            circuit_breaker_limit=int(
                round(
                    self._clamp_float(
                        float(candidate.circuit_breaker_limit),
                        float(
                            baseline.circuit_breaker_limit
                            - self.max_circuit_breaker_delta
                        ),
                        float(
                            baseline.circuit_breaker_limit
                            + self.max_circuit_breaker_delta
                        ),
                    )
                )
            ),
            map_elites_n_bins=int(
                round(
                    self._clamp_float(
                        float(candidate.map_elites_n_bins),
                        float(baseline.map_elites_n_bins - self.max_grid_delta),
                        float(baseline.map_elites_n_bins + self.max_grid_delta),
                    )
                )
            ),
        )

    @staticmethod
    def _mean_diff(values: list[float]) -> float:
        if len(values) < 2:
            return 0.0
        diffs = [curr - prev for prev, curr in zip(values, values[1:])]
        return mean(diffs)

    @staticmethod
    def _clamp_float(value: float, lower: float, upper: float) -> float:
        if lower > upper:
            lower, upper = upper, lower
        return max(lower, min(upper, float(value)))
