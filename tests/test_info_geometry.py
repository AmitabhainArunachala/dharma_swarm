from __future__ import annotations

import math

import pytest

from dharma_swarm.info_geometry import (
    DharmicAttractor,
    NaturalGradientOptimizer,
    StatisticalManifold,
    meta_parameters_to_theta,
    natural_meta_step,
    rv_as_manifold_collapse,
    theta_to_meta_parameters,
)
from dharma_swarm.meta_evolution import MetaParameters


def test_fisher_metric_is_positive_diagonal() -> None:
    manifold = StatisticalManifold(param_dim=3)

    metric = manifold.fisher_metric([0.2, 0.3, 0.5])

    assert len(metric) == 3
    assert metric[0][0] > 0.0
    assert metric[1][1] > 0.0
    assert metric[2][2] > 0.0
    assert metric[0][1] == 0.0


def test_geodesic_distance_is_symmetric_and_zero_on_identity() -> None:
    manifold = StatisticalManifold(param_dim=3)
    theta_a = [0.2, 0.3, 0.5]
    theta_b = [0.4, 0.2, 0.4]

    assert manifold.geodesic_distance(theta_a, theta_a) == pytest.approx(0.0)
    assert manifold.geodesic_distance(theta_a, theta_b) == pytest.approx(
        manifold.geodesic_distance(theta_b, theta_a)
    )


def test_kl_divergence_is_non_negative() -> None:
    manifold = StatisticalManifold(param_dim=3)

    divergence = manifold.kl_divergence([0.2, 0.3, 0.5], [0.4, 0.2, 0.4])

    assert divergence >= 0.0


def test_natural_gradient_step_moves_against_loss_gradient() -> None:
    manifold = StatisticalManifold(param_dim=3)
    optimizer = NaturalGradientOptimizer(manifold, step_size=0.5)
    theta = [0.3, 0.3, 0.4]
    grad = [1.0, -1.0, 0.0]

    updated = optimizer.step(theta, grad)

    assert updated[0] < theta[0]
    assert updated[1] > theta[1]
    assert updated[2] == pytest.approx(theta[2])


def test_dharmic_attractor_distance_and_pressure() -> None:
    attractor = DharmicAttractor(
        [
            lambda theta: theta[0] >= 0.4,
            lambda theta: theta[1] <= 0.4,
        ],
        target_point=[0.5, 0.3, 0.2],
    )

    violated = [0.1, 0.8, 0.1]
    satisfied = [0.5, 0.3, 0.2]

    assert attractor.distance_to_dharma(satisfied) == pytest.approx(0.0)
    assert attractor.distance_to_dharma(violated) > 0.0
    assert attractor.dharmic_pressure(satisfied) == [0.0, 0.0, 0.0]
    assert attractor.dharmic_pressure(violated)[0] > 0.0


def test_dharmic_attractor_convexity_check() -> None:
    attractor = DharmicAttractor(
        [lambda theta: theta[0] >= 0.4],
        target_point=[0.5, 0.3, 0.2],
    )

    assert attractor.is_geodesically_convex(
        samples=[
            [0.5, 0.3, 0.2],
            [0.6, 0.2, 0.2],
        ]
    ) is True


def test_rv_as_manifold_collapse_identity_and_rank_one() -> None:
    identity = rv_as_manifold_collapse(
        [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    rank_one = rv_as_manifold_collapse(
        [
            [1.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
            [0.0, 0.0, 0.0],
        ]
    )

    assert identity["participation_ratio"] == pytest.approx(3.0)
    assert rank_one["participation_ratio"] == pytest.approx(1.0)
    assert rank_one["collapse_fraction"] > identity["collapse_fraction"]


def test_meta_parameters_roundtrip_preserves_structure() -> None:
    params = MetaParameters(
        mutation_rate=0.25,
        exploration_coeff=0.7,
        circuit_breaker_limit=4,
        map_elites_n_bins=7,
    )

    restored = theta_to_meta_parameters(meta_parameters_to_theta(params))

    assert math.isclose(sum(restored.fitness_weights.values()), 1.0)
    assert restored.mutation_rate == pytest.approx(0.25)
    assert restored.exploration_coeff == pytest.approx(0.7)
    assert restored.circuit_breaker_limit == 4
    assert restored.map_elites_n_bins == 7


def test_natural_meta_step_keeps_weights_normalized() -> None:
    params = MetaParameters()
    theta = meta_parameters_to_theta(params)
    grad = [0.05] * len(theta)

    updated = natural_meta_step(params, grad, step_size=0.2)

    assert math.isclose(sum(updated.fitness_weights.values()), 1.0)
    assert updated.mutation_rate >= 0.01
    assert updated.exploration_coeff >= 0.1
    assert updated.map_elites_n_bins >= 3
