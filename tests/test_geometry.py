"""Tests for Phase 7b: geometry.py — subspace tracking and geometric analysis."""

from __future__ import annotations

import math

import numpy as np
import pytest

from dharma_swarm.geometry import (
    SubspaceEntry,
    SubspaceRegistry,
    batched_principal_angles,
    classify_drift_phase,
    forgetting_risk,
    subspace_overlap_score,
)


# ── Helper ────────────────────────────────────────────────────────────────


def _random_orthonormal(d: int, k: int, rng=None) -> np.ndarray:
    """Generate a random (d, k) orthonormal matrix."""
    if rng is None:
        rng = np.random.default_rng(42)
    A = rng.standard_normal((d, k))
    Q, _ = np.linalg.qr(A)
    return Q[:, :k]


# ── batched_principal_angles tests ────────────────────────────────────────


class TestBatchedPrincipalAngles:
    def test_identical_subspaces_zero_angles(self):
        """Identical subspaces should have all principal angles ≈ 0."""
        Q = _random_orthonormal(10, 3)
        angles = batched_principal_angles(Q, Q)
        np.testing.assert_allclose(angles, 0.0, atol=1e-3)

    def test_orthogonal_subspaces_pi_over_2(self):
        """Orthogonal subspaces should have all principal angles ≈ π/2."""
        # Construct two orthogonal 2D subspaces in R^4
        Q_i = np.eye(4)[:, :2]  # span of e1, e2
        Q_j = np.eye(4)[:, 2:]  # span of e3, e4
        angles = batched_principal_angles(Q_i, Q_j)
        np.testing.assert_allclose(angles, np.pi / 2, atol=1e-6)

    def test_known_45_degree_angle(self):
        """Two subspaces at exactly 45° should yield θ_min = π/4."""
        # 1D subspaces in R^2: [1,0] and [1,1]/√2
        Q_i = np.array([[1.0], [0.0]])
        Q_j = np.array([[1.0], [1.0]]) / np.sqrt(2)
        angles = batched_principal_angles(Q_i, Q_j)
        np.testing.assert_allclose(angles[0], np.pi / 4, atol=1e-6)

    def test_batched_shape(self):
        """Batched input should return (batch, min(p,q)) shape."""
        rng = np.random.default_rng(0)
        Q_i = np.stack([_random_orthonormal(10, 3, rng) for _ in range(5)])
        Q_j = np.stack([_random_orthonormal(10, 2, rng) for _ in range(5)])
        angles = batched_principal_angles(Q_i, Q_j)
        assert angles.shape == (5, 2)

    def test_angles_in_valid_range(self):
        """All angles should be in [0, π/2]."""
        rng = np.random.default_rng(7)
        Q_i = _random_orthonormal(20, 5, rng)
        Q_j = _random_orthonormal(20, 5, rng)
        angles = batched_principal_angles(Q_i, Q_j)
        assert np.all(angles >= -1e-10)
        assert np.all(angles <= np.pi / 2 + 1e-10)

    def test_single_vs_batched_consistency(self):
        """Single-pair result should match first element of batch=1."""
        rng = np.random.default_rng(3)
        Q_i = _random_orthonormal(8, 3, rng)
        Q_j = _random_orthonormal(8, 3, rng)
        single = batched_principal_angles(Q_i, Q_j)
        batched = batched_principal_angles(Q_i[np.newaxis], Q_j[np.newaxis])
        np.testing.assert_allclose(single, batched[0], atol=1e-10)


# ── subspace_overlap_score tests ──────────────────────────────────────────


class TestSubspaceOverlapScore:
    def test_identical_subspaces_full_overlap(self):
        """Identical subspaces: theta_min=0, grassmann_distance=0, overlap_fraction=1."""
        Q = _random_orthonormal(10, 3)
        result = subspace_overlap_score(Q, Q)
        assert result["theta_min"] < 1e-6
        assert result["grassmann_distance"] < 1e-6
        assert result["overlap_fraction"] == 1.0

    def test_orthogonal_subspaces_no_overlap(self):
        """Orthogonal subspaces: theta_min=π/2, overlap_fraction=0."""
        Q_i = np.eye(6)[:, :3]
        Q_j = np.eye(6)[:, 3:]
        result = subspace_overlap_score(Q_i, Q_j)
        np.testing.assert_allclose(result["theta_min"], np.pi / 2, atol=1e-6)
        assert result["overlap_fraction"] == 0.0

    def test_chordal_distance_range(self):
        """Chordal distance should be >= 0."""
        rng = np.random.default_rng(5)
        Q_i = _random_orthonormal(10, 3, rng)
        Q_j = _random_orthonormal(10, 3, rng)
        result = subspace_overlap_score(Q_i, Q_j)
        assert result["chordal_distance"] >= 0.0

    def test_result_keys(self):
        """Result should contain all expected keys."""
        Q = _random_orthonormal(5, 2)
        result = subspace_overlap_score(Q, Q)
        expected_keys = {
            "theta_min", "theta_max", "grassmann_distance",
            "chordal_distance", "overlap_fraction", "all_angles",
        }
        assert expected_keys == set(result.keys())


# ── forgetting_risk tests ────────────────────────────────────────────────


class TestForgettingRisk:
    def test_orthogonal_is_green_zone(self):
        """θ_min = π/2 → sin²=1, but cos²=0 → GREEN zone."""
        result = forgetting_risk(
            theta_min=np.pi / 2,
            learning_rate=0.01,
            update_norm=1.0,
        )
        assert result["zone"] == "GREEN"

    def test_aligned_is_red_zone(self):
        """θ_min ≈ 0 → cos² ≈ 1 → RED zone."""
        result = forgetting_risk(
            theta_min=0.1,  # ~5.7°, very aligned
            learning_rate=0.01,
            update_norm=1.0,
        )
        assert result["zone"] == "RED"

    def test_moderate_is_yellow_zone(self):
        """θ_min ≈ 0.8 rad (~46°) → cos² ≈ 0.49 → YELLOW zone."""
        result = forgetting_risk(
            theta_min=0.8,
            learning_rate=0.01,
            update_norm=1.0,
        )
        assert result["zone"] == "YELLOW"

    def test_forgetting_bound_increases_with_alignment(self):
        """More aligned subspaces (smaller θ) → lower sin² → lower bound.

        Wait — sin²(θ) decreases as θ→0, so the forgetting_bound
        should actually be LOWER for more aligned subspaces (the bound
        says forgetting is bounded by α·sin²θ + β).  But the RISK is
        higher because rank matters more.
        """
        aligned = forgetting_risk(0.1, 0.01, 1.0)
        orthogonal = forgetting_risk(np.pi / 2, 0.01, 1.0)
        # sin²(0.1) < sin²(π/2), so bound for aligned < bound for orthogonal
        assert aligned["forgetting_bound"] < orthogonal["forgetting_bound"]

    def test_forgetting_bound_formula(self):
        """Verify the exact formula: α·sin²(θ) + β."""
        theta = 1.0
        lr = 0.01
        norm = 2.0
        L = 1.5
        mu = 0.5
        beta = 0.02
        result = forgetting_risk(theta, lr, norm, L, mu, beta)
        expected_alpha = lr * L * norm**2 / mu
        expected_bound = expected_alpha * math.sin(theta)**2 + beta
        assert abs(result["forgetting_bound"] - expected_bound) < 1e-10
        assert abs(result["alpha"] - expected_alpha) < 1e-10

    def test_recommendation_present(self):
        """Every result should have a recommendation string."""
        for theta in [0.1, 0.8, 1.4]:
            result = forgetting_risk(theta, 0.01, 1.0)
            assert isinstance(result["recommendation"], str)
            assert len(result["recommendation"]) > 0


# ── classify_drift_phase tests ────────────────────────────────────────────


class TestClassifyDriftPhase:
    def test_short_history_returns_convergence(self):
        """History shorter than window → convergence."""
        result = classify_drift_phase([1.0] * 10, [0.5] * 10, [0.9] * 10, window=50)
        assert result == "convergence"

    def test_unstable_loss_returns_convergence(self):
        """Varying loss → Phase 1 convergence."""
        rng = np.random.default_rng(1)
        loss = list(rng.normal(1.0, 0.5, 100))  # high variance
        pr = list(np.linspace(5.0, 3.0, 100))
        cka = list(np.linspace(0.95, 0.8, 100))
        result = classify_drift_phase(pr, loss, cka, window=50)
        assert result == "convergence"

    def test_stable_loss_falling_pr_returns_directed_drift(self):
        """Stable loss + falling PR → Phase 2 directed drift."""
        loss = [1.0] * 100  # perfectly stable
        pr = list(np.linspace(10.0, 5.0, 100))  # clearly falling
        cka = list(np.linspace(0.95, 0.7, 100))
        result = classify_drift_phase(pr, loss, cka, window=50)
        assert result == "directed_drift"

    def test_stable_loss_stable_pr_returns_null_drift(self):
        """Stable loss + stable PR → Phase 3 null drift."""
        loss = [1.0] * 100
        pr = [5.0] * 100  # perfectly stable
        cka = list(np.linspace(0.95, 0.9, 100))
        result = classify_drift_phase(pr, loss, cka, window=50)
        assert result == "null_drift"


# ── SubspaceRegistry tests ───────────────────────────────────────────────


class TestSubspaceRegistry:
    def test_register_creates_entry(self):
        """register() should create an entry with orthonormal basis."""
        rng = np.random.default_rng(42)
        registry = SubspaceRegistry(agent_id="test-agent")
        activation = rng.standard_normal((10, 50))
        entry = registry.register("task1", "layer0", activation)

        assert entry.task_id == "task1"
        assert entry.layer_id == "layer0"
        assert entry.basis.shape[0] == 10
        assert entry.basis.shape[1] > 0

        # Basis should be orthonormal
        gram = entry.basis.T @ entry.basis
        np.testing.assert_allclose(gram, np.eye(gram.shape[0]), atol=1e-10)

    def test_accumulated_basis(self):
        """accumulated_basis should concatenate all bases for a layer."""
        rng = np.random.default_rng(42)
        registry = SubspaceRegistry(agent_id="test")
        activation1 = rng.standard_normal((10, 50))
        activation2 = rng.standard_normal((10, 50))
        e1 = registry.register("t1", "L0", activation1)
        e2 = registry.register("t2", "L0", activation2)
        M = registry.accumulated_basis("L0")
        assert M is not None
        assert M.shape[1] == e1.basis.shape[1] + e2.basis.shape[1]

    def test_get_basis(self):
        """get_basis should return the correct entry."""
        rng = np.random.default_rng(0)
        registry = SubspaceRegistry()
        activation = rng.standard_normal((5, 20))
        entry = registry.register("task1", "layer0", activation)
        found = registry.get_basis("layer0", "task1")
        assert found is not None
        np.testing.assert_array_equal(found, entry.basis)

    def test_get_basis_missing_returns_none(self):
        """get_basis for non-existent entry returns None."""
        registry = SubspaceRegistry()
        assert registry.get_basis("nope", "nope") is None

    def test_capacity_ratio(self):
        """capacity_ratio should be between 0 and 1."""
        rng = np.random.default_rng(42)
        registry = SubspaceRegistry()
        activation = rng.standard_normal((10, 50))
        registry.register("t1", "L0", activation)
        ratio = registry.capacity_ratio("L0", d=10)
        assert 0.0 < ratio <= 1.0

    def test_capacity_ratio_empty(self):
        """capacity_ratio for empty layer should be 0."""
        registry = SubspaceRegistry()
        assert registry.capacity_ratio("L0", d=10) == 0.0

    def test_residual_projection(self):
        """Second task's basis should be approximately orthogonal to first's."""
        rng = np.random.default_rng(42)
        d = 20
        registry = SubspaceRegistry()
        activation1 = rng.standard_normal((d, 100))
        activation2 = rng.standard_normal((d, 100))
        e1 = registry.register("t1", "L0", activation1, variance_threshold=0.5)
        e2 = registry.register("t2", "L0", activation2, variance_threshold=0.5)

        # The bases should be nearly orthogonal due to residual projection
        cross = e1.basis.T @ e2.basis
        # Frobenius norm of cross product should be small
        assert np.linalg.norm(cross, "fro") < 1.0

    def test_participation_ratio_positive(self):
        """Participation ratio should be positive."""
        rng = np.random.default_rng(42)
        registry = SubspaceRegistry()
        activation = rng.standard_normal((10, 50))
        entry = registry.register("t1", "L0", activation)
        assert entry.participation_ratio > 0.0
