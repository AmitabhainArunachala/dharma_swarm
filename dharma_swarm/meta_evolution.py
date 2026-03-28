"""Persisted meta-evolution for Darwin Engine hyperparameters."""

from __future__ import annotations

import math
import random
from pathlib import Path
from statistics import mean, pvariance
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field, field_validator

from dharma_swarm.archive import FITNESS_DIMENSIONS, normalize_fitness_weights
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
    coordination_pressure: float = 0.0
    coordination_summary: dict[str, Any] = Field(default_factory=dict)


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
        poor_meta_fitness_threshold: float = 0.7,
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
        self._coordination_history: list[dict[str, Any]] = []
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

    def observe_coordination_summary(
        self,
        summary: Mapping[str, Any] | None,
    ) -> None:
        """Record live coordination uncertainty for later meta updates."""
        if not summary:
            return
        payload = {
            "observed_at": str(summary.get("observed_at", "")),
            "global_truths": self._coordination_int(
                summary.get("global_truths"),
            ),
            "productive_disagreements": self._coordination_int(
                summary.get("productive_disagreements"),
            ),
            "cohomological_dimension": self._coordination_int(
                summary.get("cohomological_dimension"),
            ),
            "is_globally_coherent": self._coordination_bool(
                summary.get("is_globally_coherent"),
                default=True,
            ),
            "global_truth_claim_keys": self._coordination_string_list(
                summary.get("global_truth_claim_keys"),
            ),
            "productive_disagreement_claim_keys": self._coordination_string_list(
                summary.get("productive_disagreement_claim_keys"),
            ),
            "rv_trend": self._coordination_float(summary.get("rv_trend")),
            "fitness_trend": self._coordination_float(summary.get("fitness_trend")),
            "observation_count": self._coordination_int(
                summary.get("observation_count"),
            ),
            "approaching_fixed_point": self._coordination_bool(
                summary.get("approaching_fixed_point"),
                default=False,
            ),
        }
        self._coordination_history.append(payload)
        if len(self._coordination_history) > self.n_object_cycles:
            self._coordination_history = self._coordination_history[-self.n_object_cycles :]

    @staticmethod
    def _coordination_int(value: Any, default: int = 0) -> int:
        if value is None or isinstance(value, bool):
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            try:
                parsed_float = float(value)
            except (TypeError, ValueError):
                return default
            if not math.isfinite(parsed_float):
                return default
            parsed = int(parsed_float)
        return max(default, parsed)

    @staticmethod
    def _coordination_float(value: Any, default: float = 0.0) -> float:
        if value is None or isinstance(value, bool):
            return default
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return default
        if not math.isfinite(parsed):
            return default
        return parsed

    @staticmethod
    def _coordination_bool(value: Any, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        return default

    @staticmethod
    def _coordination_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        items: list[str] = []
        for raw in value:
            item = str(raw).strip()
            if item and item not in items:
                items.append(item)
        return items

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

    def get_meta_parameter_theta(self) -> list[float]:
        """Export current meta-parameters onto the information-geometry surface."""
        from dharma_swarm.info_geometry import meta_parameters_to_theta

        return meta_parameters_to_theta(self.meta_params)

    def apply_meta_parameter_theta(
        self,
        theta: Sequence[float],
        *,
        auto_apply: bool | None = None,
        bounded: bool = True,
    ) -> MetaParameters:
        """Load manifold coordinates back into bounded meta-parameters."""
        from dharma_swarm.info_geometry import theta_to_meta_parameters

        candidate = theta_to_meta_parameters(theta)
        if bounded:
            candidate = self._bound_meta_params(candidate, baseline=self.meta_params)
        self.meta_params = candidate
        should_apply = self.auto_apply if auto_apply is None else bool(auto_apply)
        if should_apply:
            self.darwin.apply_meta_parameters(self.meta_params)
        return self.meta_params.model_copy(deep=True)

    def propose_natural_gradient_update(
        self,
        loss_grad: Sequence[float],
        *,
        step_size: float = 0.1,
        auto_apply: bool = False,
        bounded: bool = True,
    ) -> MetaParameters:
        """Generate a natural-gradient meta-parameter update from the current point."""
        from dharma_swarm.info_geometry import natural_meta_step

        candidate = natural_meta_step(
            self.meta_params,
            loss_grad,
            step_size=step_size,
        )
        if bounded:
            candidate = self._bound_meta_params(candidate, baseline=self.meta_params)
        if auto_apply:
            self.meta_params = candidate
            self.darwin.apply_meta_parameters(self.meta_params)
            return self.meta_params.model_copy(deep=True)
        return candidate

    def _trajectory_loss_gradient(self, fitness_trajectory: list[float]) -> list[float]:
        """Estimate a loss gradient from the recent fitness trajectory."""
        theta_dim = len(self.get_meta_parameter_theta())
        if not fitness_trajectory:
            return [0.0] * theta_dim

        final = max(0.0, min(1.0, fitness_trajectory[-1]))
        trend = self._mean_diff(fitness_trajectory)
        variance = pvariance(fitness_trajectory) if len(fitness_trajectory) > 1 else 0.0
        fitness_gap = max(0.0, 1.0 - final)
        stagnation = max(0.0, 0.05 - abs(trend)) / 0.05
        coordination_pressure = self._coordination_uncertainty_pressure()
        instability = max(0.0, min(1.0, variance + (0.35 * coordination_pressure)))
        pressure = min(
            1.0,
            fitness_gap + (0.5 * stagnation) + (0.45 * coordination_pressure),
        )

        gradients: list[float] = []
        for key in FITNESS_DIMENSIONS:
            if key in {"correctness", "dharmic_alignment", "safety", "economic_value"}:
                gradients.append(
                    (-0.60 * pressure) - (0.20 * coordination_pressure)
                )
            elif key in {"performance", "utilization", "efficiency"}:
                gradients.append(-0.45 * pressure)
            else:
                gradients.append((-0.25 * pressure) + (0.10 * instability))

        gradients.extend(
            [
                -0.90 * (pressure + stagnation + coordination_pressure),  # mutation_rate
                -0.70 * (pressure + stagnation + coordination_pressure),  # exploration_coeff
                (0.30 * instability)
                + (0.20 * coordination_pressure)
                - (0.10 * fitness_gap),  # circuit_breaker_limit
                -0.50 * (pressure + stagnation + (0.5 * coordination_pressure)),  # map_elites_n_bins
            ]
        )
        return gradients

    def _coordination_uncertainty_pressure(self) -> float:
        """Estimate pressure from recent productive disagreement history."""
        if not self._coordination_history:
            return 0.0
        recent = self._coordination_history[-min(4, len(self._coordination_history)) :]
        disagreement_levels = [
            min(1.0, float(item.get("productive_disagreements", 0)) / 2.0)
            for item in recent
        ]
        incoherence = [
            0.0 if bool(item.get("is_globally_coherent", True)) else 1.0
            for item in recent
        ]
        dimensionality = [
            min(1.0, float(item.get("cohomological_dimension", 0)))
            for item in recent
        ]
        truth_scarcity = [
            1.0
            if (
                int(item.get("global_truths", 0) or 0) == 0
                and int(item.get("productive_disagreements", 0) or 0) > 0
            )
            else 0.0
            for item in recent
        ]
        trend_regression = [
            min(
                1.0,
                max(0.0, -float(item.get("rv_trend", 0.0) or 0.0))
                + max(0.0, -float(item.get("fitness_trend", 0.0) or 0.0)),
            )
            for item in recent
        ]
        fixed_point_stall = [
            1.0
            if bool(item.get("approaching_fixed_point")) and (
                not bool(item.get("is_globally_coherent", True))
                or float(item.get("rv_trend", 0.0) or 0.0) <= 0.0
                or float(item.get("fitness_trend", 0.0) or 0.0) <= 0.0
            )
            else 0.0
            for item in recent
        ]
        counts: dict[str, int] = {}
        for item in recent:
            for claim_key in item.get("productive_disagreement_claim_keys", []):
                counts[claim_key] = counts.get(claim_key, 0) + 1
        repeated_claims = (
            min(1.0, sum(1 for count in counts.values() if count > 1) / 2.0)
            if counts
            else 0.0
        )
        return min(
            1.0,
            (0.32 * mean(disagreement_levels))
            + (0.24 * mean(incoherence))
            + (0.12 * mean(dimensionality))
            + (0.10 * repeated_claims)
            + (0.08 * mean(truth_scarcity))
            + (0.08 * mean(trend_regression))
            + (0.06 * mean(fixed_point_stall)),
        )

    def _current_coordination_summary(self) -> dict[str, Any]:
        if not self._coordination_history:
            return {}
        return dict(self._coordination_history[-1])

    def _natural_gradient_step_size(self, fitness_trajectory: list[float]) -> float:
        """Scale natural-gradient updates with recent fitness quality."""
        if not fitness_trajectory:
            return max(0.05, min(0.35, 0.10 + (0.10 * self._coordination_uncertainty_pressure())))
        final = max(0.0, min(1.0, fitness_trajectory[-1]))
        fitness_gap = 1.0 - final
        return max(
            0.05,
            min(
                0.35,
                0.10
                + (0.20 * fitness_gap)
                + (0.10 * self._coordination_uncertainty_pressure()),
            ),
        )

    def _blend_meta_params(
        self,
        primary: MetaParameters,
        secondary: MetaParameters,
        *,
        primary_weight: float = 0.65,
    ) -> MetaParameters:
        """Blend geometric and exploratory candidates into one bounded proposal."""
        w = max(0.0, min(1.0, float(primary_weight)))
        inverse = 1.0 - w
        blended_weights = {
            key: (
                (primary.fitness_weights[key] * w)
                + (secondary.fitness_weights[key] * inverse)
            )
            for key in primary.fitness_weights
        }
        return MetaParameters(
            fitness_weights=normalize_fitness_weights(blended_weights),
            mutation_rate=(
                (primary.mutation_rate * w)
                + (secondary.mutation_rate * inverse)
            ),
            exploration_coeff=(
                (primary.exploration_coeff * w)
                + (secondary.exploration_coeff * inverse)
            ),
            circuit_breaker_limit=max(
                1,
                round(
                    (primary.circuit_breaker_limit * w)
                    + (secondary.circuit_breaker_limit * inverse)
                ),
            ),
            map_elites_n_bins=max(
                3,
                round(
                    (primary.map_elites_n_bins * w)
                    + (secondary.map_elites_n_bins * inverse)
                ),
            ),
        )

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
        coordination_pressure = self._coordination_uncertainty_pressure()
        if meta_fitness < self.poor_meta_fitness_threshold:
            loss_grad = self._trajectory_loss_gradient(fitness_trajectory)
            geometric_candidate = self.propose_natural_gradient_update(
                loss_grad,
                step_size=self._natural_gradient_step_size(fitness_trajectory),
                auto_apply=False,
                bounded=False,
            )
            exploratory_candidate = self._evolve_meta_params()
            candidate = self._bound_meta_params(
                self._blend_meta_params(
                    geometric_candidate,
                    exploratory_candidate,
                ),
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
            coordination_pressure=coordination_pressure,
            coordination_summary=self._current_coordination_summary(),
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
