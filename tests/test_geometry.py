"""Test Phase 7b: geometry.py — subspace geometry primitives.

Tests all geometry functions with known analytic values:
1. batched_principal_angles — identity → all zeros, orthogonal → all π/2
2. subspace_overlap_score — overlap metrics
3. forgetting_risk — geometric forgetting bound
4. classify_drift_phase — three-phase drift model
5. SubspaceRegistry — registration, snapshot, tracking
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from dharma_swarm.geometry import (
    SubspaceRegistry,
    batched_principal_angles,
    classify_drift_phase,
    forgetting_risk,
    subspace_overlap_score,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _random_orthonormal(n: int, k: int, seed: int = 42) -> np.ndarray:
    """Generate a random orthonormal basis (n x k) via QR."""
    rng = np.random.default_rng(seed)
    A = rng.standard_normal((n, k))
    Q, _ = np.linalg.qr(A)
    return Q[:, :k]


# ---------------------------------------------------------------------------
# Test 1: batched_principal_angles
# ---------------------------------------------------------------------------


class TestBatchedPrincipalAngles:
    def test_identical_subspaces_gives_zero_angles(self):
        """Two identical subspaces → all principal angles ≈ 0."""
        Q = _random_orthonormal(10, 3, seed=1)
        angles = batched_principal_angles(Q, Q)
        np.testing.assert_allclose(angles, 0.0, atol=1e-3)

    def test_orthogonal_subspaces_gives_pi_over_2(self):
        """Two orthogonal subspaces → all principal angles ≈ π/2."""
        # First 3 basis vectors vs next 3
        I = np.eye(10)
        U = I[:, :3]
        V = I[:, 3:6]
        angles = batched_principal_angles(U, V)
        expected = np.full(3, math.pi / 2)
        np.testing.assert_allclose(angles, expected, atol=1e-10)

    def test_known_45_degree_angle(self):
        """Two 1D subspaces at 45° → θ = π/4."""
        u = np.array([[1.0], [0.0]])
        v = np.array([[1.0 / math.sqrt(2)], [1.0 / math.sqrt(2)]])
        angles = batched_principal_angles(u, v)
        np.testing.assert_allclose(angles, [math.pi / 4], atol=1e-10)

    def test_different_rank_subspaces(self):
        """When subspaces have different ranks, output rank = min(k1, k2)."""
        U = _random_orthonormal(10, 5, seed=2)
        V = _random_orthonormal(10, 3, seed=3)
        angles = batched_principal_angles(U, V)
        assert len(angles) == 3  # min(5, 3)

    def test_angles_are_sorted_ascending(self):
        """Principal angles should be in non-decreasing order."""
        U = _random_orthonormal(20, 5, seed=4)
        V = _random_orthonormal(20, 5, seed=5)
        angles = batched_principal_angles(U, V)
        assert len(angles) == 5
        for i in range(len(angles) - 1):
            assert angles[i] <= angles[i + 1] + 1e-10

    def test_angles_in_valid_range(self):
        """All angles should be in [0, π/2]."""
        U = _random_orthonormal(15, 4, seed=6)
        V = _random_orthonormal(15, 4, seed=7)
        angles = batched_principal_angles(U, V)
        assert np.all(angles >= -1e-10)
        assert np.all(angles <= math.pi / 2 + 1e-10)


# ---------------------------------------------------------------------------
# Test 2: subspace_overlap_score
# ---------------------------------------------------------------------------


class TestSubspaceOverlapScore:
    def test_identical_subspaces(self):
        Q = _random_orthonormal(10, 3, seed=10)
        result = subspace_overlap_score(Q, Q)
        assert "theta_min" in result
        assert "theta_max" in result
        assert "grassmann_distance" in result
        assert "chordal_distance" in result
        assert "overlap_fraction" in result

        # Identical → overlap_fraction ≈ 1, distances ≈ 0
        assert result["overlap_fraction"] == pytest.approx(1.0, abs=1e-3)
        assert result["grassmann_distance"] == pytest.approx(0.0, abs=1e-2)

    def test_orthogonal_subspaces(self):
        I = np.eye(10)
        U = I[:, :3]
        V = I[:, 3:6]
        result = subspace_overlap_score(U, V)
        assert result["overlap_fraction"] == pytest.approx(0.0, abs=1e-8)

    def test_partial_overlap(self):
        """Two subspaces sharing one basis vector."""
        I = np.eye(10)
        U = I[:, :3]  # e1, e2, e3
        V = I[:, 2:5]  # e3, e4, e5 — share e3
        result = subspace_overlap_score(U, V)
        # overlap should be between 0 and 1
        assert 0.0 < result["overlap_fraction"] < 1.0


# ---------------------------------------------------------------------------
# Test 3: forgetting_risk
# ---------------------------------------------------------------------------


class TestForgettingRisk:
    def test_zero_angle_low_risk(self):
        """theta_min = 0 → sin²(0)=0 → low forgetting bound."""
        risk = forgetting_risk(theta_min=0.0)
        assert "forgetting_bound" in risk
        assert "zone" in risk
        assert "recommendation" in risk
        # forgetting_bound = alpha * sin²(0) + beta = 0 + 0.01
        assert risk["forgetting_bound"] == pytest.approx(0.01, abs=1e-6)
        assert risk["zone"] == "RED"  # cos²(0) = 1 > 0.75

    def test_orthogonal_angle_high_risk(self):
        """theta_min = pi/2 → sin²(pi/2) = 1 → high forgetting bound."""
        risk = forgetting_risk(theta_min=math.pi / 2)
        # forgetting_bound = alpha * 1 + beta = 0.001 * 1.0 * 1.0 / 1.0 + 0.01 = 0.011
        assert risk["forgetting_bound"] > 0.01
        assert risk["zone"] == "GREEN"  # cos²(pi/2) ≈ 0 < 0.33

    def test_moderate_angle(self):
        """theta_min = pi/4 (45°) should be in YELLOW zone."""
        risk = forgetting_risk(theta_min=math.pi / 4)
        # cos²(pi/4) = 0.5, which is between 0.33 and 0.75
        assert risk["zone"] == "YELLOW"

    def test_return_keys(self):
        risk = forgetting_risk(theta_min=0.5)
        assert "forgetting_bound" in risk
        assert "alpha" in risk
        assert "sin2_theta_min" in risk
        assert "rank_sensitivity" in risk
        assert "zone" in risk
        assert "recommendation" in risk


# ---------------------------------------------------------------------------
# Test 4: classify_drift_phase
# ---------------------------------------------------------------------------


class TestClassifyDriftPhase:
    def test_convergence_phase_short_history(self):
        """Short history (< window) → convergence."""
        phase = classify_drift_phase(
            pr_history=[1.0] * 10,
            loss_history=[0.5] * 10,
            cka_history=[0.9] * 10,
            window=50,
        )
        assert phase == "convergence"

    def test_null_drift_phase(self):
        """Stable loss + stable PR → null_drift."""
        n = 60
        phase = classify_drift_phase(
            pr_history=[5.0] * n,
            loss_history=[0.01] * n,
            cka_history=[0.95] * n,
            window=50,
        )
        assert phase == "null_drift"

    def test_convergence_phase_changing_loss(self):
        """Changing loss → convergence."""
        n = 60
        # Loss with high variance
        rng = np.random.default_rng(42)
        loss = list(rng.uniform(0.1, 10.0, n))
        phase = classify_drift_phase(
            pr_history=[5.0] * n,
            loss_history=loss,
            cka_history=[0.95] * n,
            window=50,
        )
        assert phase == "convergence"

    def test_empty_history(self):
        """Empty history should return convergence."""
        phase = classify_drift_phase([], [], [])
        assert phase == "convergence"

    def test_returns_string(self):
        phase = classify_drift_phase([1.0] * 5, [0.5] * 5, [0.9] * 5)
        assert isinstance(phase, str)
        assert phase in ("convergence", "directed_drift", "null_drift")


# ---------------------------------------------------------------------------
# Test 5: SubspaceRegistry
# ---------------------------------------------------------------------------


class TestSubspaceRegistry:
    def test_add_task_and_retrieve(self):
        reg = SubspaceRegistry(hidden_dim=10, max_rank=256)
        # activations: (d, n_samples)
        rng = np.random.default_rng(30)
        activations = rng.standard_normal((10, 50))
        entry = reg.add_task("task_1", activations, agent_id="agent_1")

        assert entry.task_id == "task_1"
        assert entry.agent_id == "agent_1"
        assert entry.basis.shape[0] == 10
        assert entry.basis.shape[1] >= 1
        assert "task_1" in reg.entries

    def test_missing_task_returns_none(self):
        reg = SubspaceRegistry(hidden_dim=10)
        assert reg.entries.get("nonexistent") is None

    def test_multiple_tasks(self):
        reg = SubspaceRegistry(hidden_dim=10)
        rng = np.random.default_rng(31)
        reg.add_task("task_1", rng.standard_normal((10, 30)))
        reg.add_task("task_2", rng.standard_normal((10, 30)))

        assert len(reg.entries) == 2
        assert reg._merged_basis is not None

    def test_interference_between_tasks(self):
        reg = SubspaceRegistry(hidden_dim=10)
        rng = np.random.default_rng(32)
        reg.add_task("task_a", rng.standard_normal((10, 30)))
        reg.add_task("task_b", rng.standard_normal((10, 30)))

        result = reg.interference("task_a", "task_b")
        assert "overlap_fraction" in result
        assert 0.0 <= result["overlap_fraction"] <= 1.0

    def test_interference_missing_task(self):
        reg = SubspaceRegistry(hidden_dim=10)
        rng = np.random.default_rng(33)
        reg.add_task("task_a", rng.standard_normal((10, 30)))

        result = reg.interference("task_a", "missing")
        assert "error" in result

    def test_saturation_ratio(self):
        reg = SubspaceRegistry(hidden_dim=10)
        assert reg.saturation_ratio() == 0.0

        rng = np.random.default_rng(34)
        reg.add_task("task_1", rng.standard_normal((10, 30)))
        assert 0.0 < reg.saturation_ratio() <= 1.0

    def test_project_gradient(self):
        reg = SubspaceRegistry(hidden_dim=10)
        rng = np.random.default_rng(35)
        reg.add_task("task_1", rng.standard_normal((10, 30)))

        grad = rng.standard_normal(10)
        projected = reg.project_gradient(grad)
        assert projected.shape == grad.shape
        # Projected gradient should have removed stored directions
        if reg._merged_basis is not None:
            overlap = reg._merged_basis.T @ projected
            np.testing.assert_allclose(overlap, 0.0, atol=1e-10)

    def test_summary_returns_dict(self):
        reg = SubspaceRegistry(hidden_dim=10)
        rng = np.random.default_rng(36)
        reg.add_task("task_1", rng.standard_normal((10, 30)), agent_id="a1")

        summary = reg.summary()
        assert isinstance(summary, dict)
        assert summary["hidden_dim"] == 10
        assert summary["num_tasks"] == 1
        assert "task_1" in summary["tasks"]
