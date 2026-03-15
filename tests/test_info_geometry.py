"""Tests for dharma_swarm.info_geometry -- Information Geometry module.

Covers:
- StatisticalManifold: Fisher metric, geodesic distance, KL divergence
- NaturalGradientOptimizer: parameterization-invariance, descent
- DharmicAttractor: constraint checking, distance, pressure, contractivity
- R_V as manifold collapse: participation ratio, covariance-based R_V
- MetaEvolutionStep: combined fitness + dharmic dynamics
"""

import math

import numpy as np
import pytest

from dharma_swarm.info_geometry import (
    DharmicAttractor,
    MetaEvolutionStep,
    NaturalGradientOptimizer,
    StatisticalManifold,
    effective_dimension_trajectory,
    participation_ratio,
    rv_from_covariances,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _identity(n: int) -> np.ndarray:
    return np.eye(n)


def _random_psd(n: int, rng: np.random.Generator) -> np.ndarray:
    """Random positive-definite matrix."""
    a = rng.standard_normal((n, n))
    return a.T @ a + 0.1 * np.eye(n)


# ── TestStatisticalManifold ──────────────────────────────────────────────

class TestStatisticalManifold:
    def test_creation(self):
        m = StatisticalManifold(dim=3)
        assert m.dim == 3

    def test_creation_invalid_dim(self):
        with pytest.raises(ValueError):
            StatisticalManifold(dim=0)

    def test_fisher_metric_identity_samples(self):
        """Fisher metric from identity-like score samples should be ~I."""
        m = StatisticalManifold(dim=2)
        theta = np.array([1.0, 2.0])
        # Each sample is a standard basis vector
        samples = np.eye(2)
        g = m.fisher_metric(theta, samples)
        # G = (1/2) * I^T @ I = (1/2) * I
        np.testing.assert_allclose(g, 0.5 * np.eye(2))

    def test_fisher_metric_psd(self):
        """Fisher metric must be positive semi-definite."""
        m = StatisticalManifold(dim=3)
        theta = np.array([0.5, 0.5, 0.5])
        rng = np.random.default_rng(42)
        samples = rng.standard_normal((50, 3))
        g = m.fisher_metric(theta, samples)
        eigenvalues = np.linalg.eigvalsh(g)
        assert all(ev >= -1e-10 for ev in eigenvalues)

    def test_fisher_metric_shape(self):
        m = StatisticalManifold(dim=4)
        theta = np.zeros(4)
        samples = np.ones((10, 4))
        g = m.fisher_metric(theta, samples)
        assert g.shape == (4, 4)

    def test_fisher_metric_wrong_theta_shape(self):
        m = StatisticalManifold(dim=3)
        with pytest.raises(ValueError, match="theta"):
            m.fisher_metric(np.zeros(2), np.ones((5, 3)))

    def test_fisher_metric_wrong_samples_shape(self):
        m = StatisticalManifold(dim=3)
        with pytest.raises(ValueError, match="Samples"):
            m.fisher_metric(np.zeros(3), np.ones((5, 2)))

    def test_geodesic_distance_zero(self):
        """Distance from a point to itself is 0."""
        g = np.eye(3)
        theta = np.array([1.0, 2.0, 3.0])
        d = StatisticalManifold.geodesic_distance_approx(g, theta, theta)
        assert d == pytest.approx(0.0, abs=1e-10)

    def test_geodesic_distance_euclidean(self):
        """With identity Fisher metric, geodesic distance = Euclidean distance."""
        g = np.eye(2)
        t1 = np.array([0.0, 0.0])
        t2 = np.array([3.0, 4.0])
        d = StatisticalManifold.geodesic_distance_approx(g, t1, t2)
        assert d == pytest.approx(5.0, abs=1e-10)

    def test_geodesic_distance_scaled(self):
        """With scaled Fisher metric, distance scales accordingly."""
        g = 4.0 * np.eye(2)
        t1 = np.array([0.0, 0.0])
        t2 = np.array([1.0, 0.0])
        d = StatisticalManifold.geodesic_distance_approx(g, t1, t2)
        assert d == pytest.approx(2.0, abs=1e-10)

    def test_kl_divergence_same(self):
        """KL divergence of identical Gaussians is 0."""
        mu = np.array([1.0, 2.0])
        sigma = np.eye(2)
        kl = StatisticalManifold.kl_divergence_gaussian(mu, sigma, mu, sigma)
        assert kl == pytest.approx(0.0, abs=1e-10)

    def test_kl_divergence_nonneg(self):
        """KL divergence is always non-negative."""
        rng = np.random.default_rng(42)
        mu1 = rng.standard_normal(3)
        mu2 = rng.standard_normal(3)
        s1 = _random_psd(3, rng)
        s2 = _random_psd(3, rng)
        kl = StatisticalManifold.kl_divergence_gaussian(mu1, s1, mu2, s2)
        assert kl >= -1e-10

    def test_kl_divergence_asymmetric(self):
        """KL(p||q) != KL(q||p) in general."""
        rng = np.random.default_rng(123)
        mu1 = np.array([0.0, 0.0])
        mu2 = np.array([1.0, 1.0])
        s1 = _random_psd(2, rng)
        s2 = _random_psd(2, rng)
        kl_12 = StatisticalManifold.kl_divergence_gaussian(mu1, s1, mu2, s2)
        kl_21 = StatisticalManifold.kl_divergence_gaussian(mu2, s2, mu1, s1)
        assert abs(kl_12 - kl_21) > 1e-6


class TestFisherFromLogProbs:
    def test_fisher_from_constant_fn(self):
        """Constant log-prob => zero Fisher metric."""
        m = StatisticalManifold(dim=2)
        theta = np.array([1.0, 1.0])
        g = m.fisher_metric_from_log_probs(
            theta, lambda t: 0.0, n_samples=20, epsilon=1e-3
        )
        np.testing.assert_allclose(g, np.zeros((2, 2)), atol=1e-6)

    def test_fisher_from_quadratic(self):
        """For -0.5 * ||theta||^2, score = -theta, Fisher ~ theta @ theta^T."""
        m = StatisticalManifold(dim=2)
        theta = np.array([1.0, 2.0])
        g = m.fisher_metric_from_log_probs(
            theta,
            lambda t: -0.5 * float(t @ t),
            n_samples=50,
            epsilon=1e-4,
        )
        # Score at theta is -theta. Fisher = E[score @ score^T] = theta @ theta^T
        # (since log_prob_fn is deterministic, all samples give same score)
        expected = np.outer(-theta, -theta)
        np.testing.assert_allclose(g, expected, atol=1e-2)


# ── TestNaturalGradientOptimizer ─────────────────────────────────────────

class TestNaturalGradientOptimizer:
    def test_identity_fisher(self):
        """With identity Fisher, natural gradient = standard gradient."""
        m = StatisticalManifold(dim=3)
        opt = NaturalGradientOptimizer(manifold=m, damping=0.0)
        grad = np.array([1.0, 2.0, 3.0])
        fisher = np.eye(3)
        nat = opt.natural_gradient(grad, fisher)
        np.testing.assert_allclose(nat, grad, atol=1e-10)

    def test_scaled_fisher(self):
        """With 2*I Fisher, natural gradient = grad/2."""
        m = StatisticalManifold(dim=2)
        opt = NaturalGradientOptimizer(manifold=m, damping=0.0)
        grad = np.array([4.0, 6.0])
        fisher = 2.0 * np.eye(2)
        nat = opt.natural_gradient(grad, fisher)
        np.testing.assert_allclose(nat, np.array([2.0, 3.0]), atol=1e-10)

    def test_step_decreases_loss(self):
        """A natural gradient step should decrease a quadratic loss."""
        m = StatisticalManifold(dim=2)
        opt = NaturalGradientOptimizer(manifold=m, learning_rate=0.1)
        theta = np.array([5.0, 5.0])
        # L = 0.5 * ||theta||^2, grad = theta
        loss_before = 0.5 * float(theta @ theta)
        new_theta = opt.step(theta, theta, np.eye(2))
        loss_after = 0.5 * float(new_theta @ new_theta)
        assert loss_after < loss_before

    def test_parameterization_invariance(self):
        """Natural gradient direction should be invariant under reparameterization.

        If we change coordinates phi = A @ theta, the natural gradient
        in the new coordinates should give the same geometric direction.
        """
        m = StatisticalManifold(dim=2)
        opt = NaturalGradientOptimizer(manifold=m, damping=1e-8)

        theta = np.array([1.0, 2.0])
        grad = np.array([3.0, 1.0])
        fisher = np.array([[2.0, 0.5], [0.5, 1.0]])

        # Natural gradient in original coordinates
        nat1 = opt.natural_gradient(grad, fisher)

        # Reparameterize: phi = A @ theta
        A = np.array([[2.0, 1.0], [0.0, 1.0]])
        A_inv = np.linalg.inv(A)

        # In new coordinates: G' = A^{-T} G A^{-1}, grad' = A^{-T} grad
        fisher_new = A_inv.T @ fisher @ A_inv
        grad_new = A_inv.T @ grad

        nat2_new = opt.natural_gradient(grad_new, fisher_new)
        # Transform back: nat2 = A^{-1} @ nat2_new
        nat2 = A_inv @ nat2_new

        np.testing.assert_allclose(nat1, nat2, atol=1e-6)

    def test_damping_effect(self):
        """Damping prevents blowup with singular Fisher."""
        m = StatisticalManifold(dim=2)
        opt = NaturalGradientOptimizer(manifold=m, damping=1.0)
        grad = np.array([1.0, 1.0])
        # Nearly singular Fisher
        fisher = np.array([[1e-10, 0.0], [0.0, 1e-10]])
        nat = opt.natural_gradient(grad, fisher)
        # Should be finite and reasonable
        assert all(np.isfinite(nat))
        assert float(np.linalg.norm(nat)) < 100.0


# ── TestDharmicAttractor ─────────────────────────────────────────────────

class TestDharmicAttractor:
    def _make_attractor(self):
        m = StatisticalManifold(dim=2)
        # Constraint: both parameters must be positive
        constraints = [
            lambda t: bool(t[0] > 0),
            lambda t: bool(t[1] > 0),
        ]
        return DharmicAttractor(
            constraints=constraints,
            manifold=m,
            constraint_names=["positive_x", "positive_y"],
        )

    def test_is_dharmic_true(self):
        a = self._make_attractor()
        assert a.is_dharmic(np.array([1.0, 2.0]))

    def test_is_dharmic_false(self):
        a = self._make_attractor()
        assert not a.is_dharmic(np.array([-1.0, 2.0]))

    def test_constraint_violations(self):
        a = self._make_attractor()
        violations = a.constraint_violations(np.array([-1.0, -2.0]))
        assert "positive_x" in violations
        assert "positive_y" in violations

    def test_constraint_violations_empty(self):
        a = self._make_attractor()
        assert a.constraint_violations(np.array([1.0, 1.0])) == []

    def test_distance_to_dharma(self):
        a = self._make_attractor()
        theta = np.array([-1.0, -1.0])
        fisher = np.eye(2)
        dharmic_pts = np.array([[1.0, 1.0], [2.0, 2.0]])
        d = a.distance_to_dharma(theta, fisher, dharmic_pts)
        # Distance to [1,1] is sqrt(4+4) = 2*sqrt(2) ~ 2.828
        assert d == pytest.approx(2.0 * math.sqrt(2.0), abs=1e-6)

    def test_distance_no_dharmic_points(self):
        a = self._make_attractor()
        d = a.distance_to_dharma(np.array([1.0, 1.0]), np.eye(2), np.zeros((0, 2)))
        assert d == float("inf")

    def test_dharmic_pressure_toward_nearest(self):
        a = self._make_attractor()
        theta = np.array([0.0, 0.0])
        fisher = np.eye(2)
        dharmic_pts = np.array([[1.0, 0.0], [0.0, 3.0]])
        pressure = a.dharmic_pressure(theta, fisher, dharmic_pts)
        # Nearest point is [1, 0], pressure = 2 * ([1,0] - [0,0]) = [2, 0]
        np.testing.assert_allclose(pressure, np.array([2.0, 0.0]), atol=1e-10)

    def test_dharmic_pressure_zero_at_dharmic(self):
        """Pressure is zero when theta IS a dharmic point."""
        a = self._make_attractor()
        theta = np.array([1.0, 1.0])
        fisher = np.eye(2)
        dharmic_pts = np.array([[1.0, 1.0]])
        pressure = a.dharmic_pressure(theta, fisher, dharmic_pts)
        np.testing.assert_allclose(pressure, np.zeros(2), atol=1e-10)

    def test_dharmic_pressure_empty(self):
        a = self._make_attractor()
        pressure = a.dharmic_pressure(np.zeros(2), np.eye(2), np.zeros((0, 2)))
        np.testing.assert_allclose(pressure, np.zeros(2))

    def test_check_contractivity(self):
        a = self._make_attractor()
        fisher = np.eye(2)
        # Contractive Jacobian: spectral radius < 1
        jac = 0.5 * np.eye(2)
        is_contracting, sr = a.check_contractivity(fisher, jac)
        assert is_contracting
        assert sr == pytest.approx(0.5, abs=1e-6)

    def test_check_not_contractive(self):
        a = self._make_attractor()
        fisher = np.eye(2)
        jac = 2.0 * np.eye(2)
        is_contracting, sr = a.check_contractivity(fisher, jac)
        assert not is_contracting
        assert sr == pytest.approx(2.0, abs=1e-6)


# ── TestParticipationRatio ───────────────────────────────────────────────

class TestParticipationRatio:
    def test_identity(self):
        """PR(I_n) = n."""
        pr = participation_ratio(np.eye(4))
        assert pr == pytest.approx(4.0, abs=1e-10)

    def test_rank_one(self):
        """PR of rank-1 matrix is 1."""
        v = np.array([[1.0], [0.0], [0.0]])
        cov = v @ v.T
        pr = participation_ratio(cov)
        assert pr == pytest.approx(1.0, abs=1e-10)

    def test_zero_matrix(self):
        """PR of zero matrix is 1.0 (degenerate case)."""
        pr = participation_ratio(np.zeros((3, 3)))
        assert pr == pytest.approx(1.0, abs=1e-10)

    def test_diagonal(self):
        """PR of diag(1,1,0,0) should be 2."""
        cov = np.diag([1.0, 1.0, 0.0, 0.0])
        pr = participation_ratio(cov)
        assert pr == pytest.approx(2.0, abs=1e-10)

    def test_between_bounds(self):
        """1 <= PR <= n for any PSD matrix."""
        rng = np.random.default_rng(42)
        for _ in range(10):
            cov = _random_psd(5, rng)
            pr = participation_ratio(cov)
            assert 1.0 - 1e-10 <= pr <= 5.0 + 1e-10


class TestRVFromCovariances:
    def test_no_contraction(self):
        """Same covariance => R_V = 1."""
        cov = np.eye(3)
        rv = rv_from_covariances(cov, cov)
        assert rv == pytest.approx(1.0, abs=1e-10)

    def test_contraction(self):
        """Rank reduction => R_V < 1."""
        cov_early = np.eye(4)  # PR = 4
        cov_late = np.diag([1.0, 1.0, 0.0, 0.0])  # PR = 2
        rv = rv_from_covariances(cov_early, cov_late)
        assert rv == pytest.approx(0.5, abs=1e-10)

    def test_expansion(self):
        """PR increase => R_V > 1."""
        cov_early = np.diag([1.0, 1.0, 0.0, 0.0])  # PR = 2
        cov_late = np.eye(4)  # PR = 4
        rv = rv_from_covariances(cov_early, cov_late)
        assert rv == pytest.approx(2.0, abs=1e-10)

    def test_zero_early(self):
        """Zero early covariance: PR(0) = 1.0, PR(I_3) = 3.0 => R_V = 3.0."""
        rv = rv_from_covariances(np.zeros((3, 3)), np.eye(3))
        # PR(zeros) = 1.0 (degenerate), PR(I_3) = 3.0
        assert rv == pytest.approx(3.0, abs=1e-10)


class TestEffectiveDimensionTrajectory:
    def test_empty(self):
        assert effective_dimension_trajectory([]) == []

    def test_constant(self):
        covs = [np.eye(3)] * 5
        trajectory = effective_dimension_trajectory(covs)
        assert all(pr == pytest.approx(3.0, abs=1e-10) for pr in trajectory)

    def test_contracting(self):
        """Progressively lower-rank covariances should show decreasing PR."""
        covs = [
            np.eye(4),
            np.diag([1.0, 1.0, 1.0, 0.0]),
            np.diag([1.0, 1.0, 0.0, 0.0]),
            np.diag([1.0, 0.0, 0.0, 0.0]),
        ]
        trajectory = effective_dimension_trajectory(covs)
        assert trajectory[0] > trajectory[-1]
        # Check monotonically decreasing
        assert all(a >= b for a, b in zip(trajectory, trajectory[1:]))


# ── TestMetaEvolutionStep ────────────────────────────────────────────────

class TestMetaEvolutionStep:
    def _make_step(self):
        m = StatisticalManifold(dim=2)
        opt = NaturalGradientOptimizer(manifold=m, learning_rate=0.1)
        constraints = [lambda t: bool(t[0] > 0), lambda t: bool(t[1] > 0)]
        attractor = DharmicAttractor(
            constraints=constraints,
            manifold=m,
            constraint_names=["pos_x", "pos_y"],
        )
        return MetaEvolutionStep(optimizer=opt, attractor=attractor, dharmic_weight=0.5)

    def test_step_returns_new_theta(self):
        step = self._make_step()
        theta = np.array([5.0, 5.0])
        fisher = np.eye(2)
        dharmic_pts = np.array([[1.0, 1.0]])
        new_theta, diag = step.step(theta, theta, fisher, dharmic_pts)
        assert new_theta.shape == (2,)
        assert not np.array_equal(new_theta, theta)

    def test_step_diagnostics(self):
        step = self._make_step()
        theta = np.array([5.0, 5.0])
        fisher = np.eye(2)
        dharmic_pts = np.array([[1.0, 1.0]])
        _, diag = step.step(theta, theta, fisher, dharmic_pts)
        assert "fitness_grad_norm" in diag
        assert "dharmic_pressure_norm" in diag
        assert "distance_to_dharma" in diag
        assert "is_dharmic" in diag
        assert "violations" in diag

    def test_converges_toward_dharma(self):
        """Multiple steps should decrease distance to dharmic subspace."""
        step = self._make_step()
        theta = np.array([5.0, 5.0])
        fisher = np.eye(2)
        dharmic_pts = np.array([[1.0, 1.0]])

        distances = []
        for _ in range(10):
            theta, diag = step.step(theta, theta, fisher, dharmic_pts)
            distances.append(diag["distance_to_dharma"])

        # Distance should generally decrease
        assert distances[-1] < distances[0]
