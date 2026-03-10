"""Information geometry helpers for Darwin meta-evolution.

This is a practical first pass: it keeps the geometry layer small, typed, and
compatible with the current ``MetaParameters`` surface instead of assuming a
full differentiable numeric stack.
"""

from __future__ import annotations

import math
from typing import Callable, Sequence

from dharma_swarm.archive import FITNESS_DIMENSIONS, normalize_fitness_weights
from dharma_swarm.meta_evolution import MetaParameters

Vector = Sequence[float]
Matrix = list[list[float]]
DharmicConstraint = Callable[[Vector], bool]

_META_PARAMETER_ORDER: tuple[str, ...] = FITNESS_DIMENSIONS + (
    "mutation_rate",
    "exploration_coeff",
    "circuit_breaker_limit",
    "map_elites_n_bins",
)


def _as_vector(theta: Vector, *, expected_dim: int | None = None) -> list[float]:
    values = [float(value) for value in theta]
    if expected_dim is not None and len(values) != expected_dim:
        raise ValueError(f"Expected vector of length {expected_dim}, got {len(values)}")
    if not values:
        raise ValueError("theta must not be empty")
    return values


def _positive_projection(theta: Vector, epsilon: float) -> list[float]:
    values = [max(float(value), epsilon) for value in theta]
    total = sum(values)
    if total <= 0.0:
        return [1.0 / len(values)] * len(values)
    return [value / total for value in values]


class StatisticalManifold:
    """Finite-dimensional statistical manifold with Fisher-style geometry."""

    def __init__(self, param_dim: int, epsilon: float = 1e-9) -> None:
        if param_dim <= 0:
            raise ValueError("param_dim must be positive")
        self.dim = int(param_dim)
        self.epsilon = float(epsilon)

    def fisher_metric(self, theta: Vector) -> Matrix:
        """Compute a diagonal Fisher-style metric on the positive simplex."""
        probs = _positive_projection(_as_vector(theta, expected_dim=self.dim), self.epsilon)
        metric: Matrix = []
        for index, probability in enumerate(probs):
            row = [0.0] * self.dim
            row[index] = 1.0 / max(probability, self.epsilon)
            metric.append(row)
        return metric

    def geodesic_distance(self, theta1: Vector, theta2: Vector) -> float:
        """Approximate Fisher-Rao distance on the simplex."""
        probs1 = _positive_projection(_as_vector(theta1, expected_dim=self.dim), self.epsilon)
        probs2 = _positive_projection(_as_vector(theta2, expected_dim=self.dim), self.epsilon)
        inner = sum(math.sqrt(a * b) for a, b in zip(probs1, probs2))
        inner = max(-1.0, min(1.0, inner))
        return 2.0 * math.acos(inner)

    def kl_divergence(self, theta1: Vector, theta2: Vector) -> float:
        """KL(p_theta1 || p_theta2) on the positive simplex projection."""
        probs1 = _positive_projection(_as_vector(theta1, expected_dim=self.dim), self.epsilon)
        probs2 = _positive_projection(_as_vector(theta2, expected_dim=self.dim), self.epsilon)
        return sum(p * math.log(p / q) for p, q in zip(probs1, probs2))


class NaturalGradientOptimizer:
    """Natural-gradient descent over a statistical manifold."""

    def __init__(
        self,
        manifold: StatisticalManifold,
        *,
        step_size: float = 0.1,
        damping: float = 1e-9,
    ) -> None:
        self.manifold = manifold
        self.step_size = float(step_size)
        self.damping = float(damping)

    def natural_gradient(self, loss_grad: Vector, theta: Vector) -> list[float]:
        """Return G(theta)^-1 * grad(L) using the manifold's diagonal metric."""
        grad = _as_vector(loss_grad, expected_dim=self.manifold.dim)
        probs = _positive_projection(_as_vector(theta, expected_dim=self.manifold.dim), self.manifold.epsilon)
        return [p * g / (1.0 + self.damping) for p, g in zip(probs, grad)]

    def step(
        self,
        theta: Vector,
        loss_grad: Vector,
        *,
        dharmic_pressure: Vector | None = None,
    ) -> list[float]:
        """Take one natural-gradient step with optional dharmic pressure."""
        current = _as_vector(theta, expected_dim=self.manifold.dim)
        natural_grad = self.natural_gradient(loss_grad, current)
        pressure = (
            [0.0] * self.manifold.dim
            if dharmic_pressure is None
            else _as_vector(dharmic_pressure, expected_dim=self.manifold.dim)
        )
        return [
            value - (self.step_size * grad) + (self.step_size * push)
            for value, grad, push in zip(current, natural_grad, pressure)
        ]


class DharmicAttractor:
    """Constraint-aware pull toward a designated dharmic target point."""

    def __init__(
        self,
        dharmic_constraints: list[DharmicConstraint],
        *,
        target_point: Vector,
        manifold: StatisticalManifold | None = None,
    ) -> None:
        self.constraints = list(dharmic_constraints)
        self.target_point = _as_vector(target_point)
        self.manifold = manifold or StatisticalManifold(len(self.target_point))

    def _violations(self, theta: Vector) -> int:
        values = _as_vector(theta, expected_dim=len(self.target_point))
        return sum(0 if constraint(values) else 1 for constraint in self.constraints)

    def distance_to_dharma(self, theta: Vector) -> float:
        if not self.constraints:
            return 0.0
        violations = self._violations(theta)
        if violations == 0:
            return 0.0
        ratio = violations / len(self.constraints)
        return ratio * self.manifold.geodesic_distance(theta, self.target_point)

    def dharmic_pressure(self, theta: Vector) -> list[float]:
        values = _as_vector(theta, expected_dim=len(self.target_point))
        if self._violations(values) == 0:
            return [0.0] * len(values)
        return [target - value for value, target in zip(values, self.target_point)]

    def is_geodesically_convex(self, samples: Sequence[Vector] | None = None) -> bool:
        if not self.constraints:
            return True

        probe_points = [
            _as_vector(sample, expected_dim=len(self.target_point))
            for sample in (samples or [self.target_point])
        ]
        satisfied = [
            point
            for point in probe_points
            if all(constraint(point) for constraint in self.constraints)
        ]
        if len(satisfied) < 2:
            return False

        for left_index, left in enumerate(satisfied):
            for right in satisfied[left_index + 1 :]:
                midpoint = [(l + r) / 2.0 for l, r in zip(left, right)]
                if not all(constraint(midpoint) for constraint in self.constraints):
                    return False
        return True


def rv_as_manifold_collapse(covariance: Sequence[Sequence[float]]) -> dict[str, float | int | bool]:
    """Measure effective dimensionality collapse via participation ratio."""
    matrix = [[float(value) for value in row] for row in covariance]
    if not matrix or any(len(row) != len(matrix) for row in matrix):
        raise ValueError("covariance must be a non-empty square matrix")

    trace = sum(matrix[index][index] for index in range(len(matrix)))
    frobenius_sq = sum(value * value for row in matrix for value in row)
    if frobenius_sq <= 0.0:
        participation_ratio = 0.0
    else:
        participation_ratio = (trace * trace) / frobenius_sq

    ambient_dim = len(matrix)
    collapse_fraction = 0.0 if ambient_dim == 0 else max(
        0.0,
        min(1.0, 1.0 - (participation_ratio / ambient_dim)),
    )
    return {
        "participation_ratio": participation_ratio,
        "ambient_dim": ambient_dim,
        "effective_rank": participation_ratio,
        "collapse_fraction": collapse_fraction,
        "is_low_rank": participation_ratio < ambient_dim,
    }


def meta_parameters_to_theta(meta_params: MetaParameters) -> list[float]:
    """Vectorize MetaParameters into a geometry-friendly coordinate list."""
    weights = normalize_fitness_weights(meta_params.fitness_weights)
    theta = [weights[key] for key in FITNESS_DIMENSIONS]
    theta.extend(
        [
            float(meta_params.mutation_rate),
            float(meta_params.exploration_coeff),
            float(meta_params.circuit_breaker_limit),
            float(meta_params.map_elites_n_bins),
        ]
    )
    return theta


def theta_to_meta_parameters(theta: Vector) -> MetaParameters:
    """Convert a manifold coordinate vector back into MetaParameters."""
    values = _as_vector(theta, expected_dim=len(_META_PARAMETER_ORDER))
    weight_values = {
        key: max(1e-9, values[index])
        for index, key in enumerate(FITNESS_DIMENSIONS)
    }
    base = len(FITNESS_DIMENSIONS)
    return MetaParameters(
        fitness_weights=normalize_fitness_weights(weight_values),
        mutation_rate=max(0.01, values[base]),
        exploration_coeff=max(0.1, values[base + 1]),
        circuit_breaker_limit=max(1, round(values[base + 2])),
        map_elites_n_bins=max(3, round(values[base + 3])),
    )


def natural_meta_step(
    meta_params: MetaParameters,
    loss_grad: Vector,
    *,
    step_size: float = 0.1,
) -> MetaParameters:
    """Apply one natural-gradient step to the vectorized meta-parameter surface."""
    theta = meta_parameters_to_theta(meta_params)
    manifold = StatisticalManifold(len(theta))
    optimizer = NaturalGradientOptimizer(manifold, step_size=step_size)
    updated = optimizer.step(theta, loss_grad)
    return theta_to_meta_parameters(updated)


__all__ = [
    "DharmicAttractor",
    "DharmicConstraint",
    "Matrix",
    "NaturalGradientOptimizer",
    "StatisticalManifold",
    "Vector",
    "meta_parameters_to_theta",
    "natural_meta_step",
    "rv_as_manifold_collapse",
    "theta_to_meta_parameters",
]
