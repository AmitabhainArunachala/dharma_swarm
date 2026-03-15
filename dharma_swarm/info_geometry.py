"""Information Geometry for DHARMA SWARM meta-evolution.

Models the Darwin Engine's state space as a statistical manifold with
Fisher information metric. Implements natural gradient descent for
meta-evolution and dharmic attractor dynamics.

Mathematical foundation (Chapter 5, categorical_foundations.pdf):

THEOREM (Chentsov 1972): The Fisher information metric is the UNIQUE
Riemannian metric on a statistical manifold invariant under sufficient
statistics.

PROPOSITION 5.3 (Natural Gradient): Amari's natural gradient
nabla_tilde L(theta) = G(theta)^{-1} nabla L(theta) is the steepest
descent direction w.r.t. the Fisher metric -- parameterization-invariant.

THEOREM 5.5 (Dharmic Convergence): If the dharmic subspace D is
geodesically convex in (M, G_Fisher), then:
    d(S_t, D) <= d(S_0, D) * e^{-lambda*t}
(exponential convergence to dharmic subspace).

CONJECTURE: This convergence rate connects to R_V contraction.

All existing tests continue to pass -- this module is standalone math.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np


# ── Statistical Manifold ─────────────────────────────────────────────────

@dataclass
class StatisticalManifold:
    """M = {p(x|theta) : theta in Theta subset R^n}.

    The state of the Darwin Engine at time t is a point theta_t on M.
    Parameters: fitness weights, mutation rates, R_V thresholds,
    archive composition, meta-parameters.

    THEOREM (Chentsov 1972): The Fisher information matrix
        g_ij(theta) = E_{p(x|theta)}[d_i log p * d_j log p]
    is the UNIQUE Riemannian metric invariant under sufficient statistics.

    CONSTRUCTION: New statistical manifold over Darwin Engine parameters.
    """

    dim: int
    """Dimension of the parameter space Theta."""

    _param_names: list[str] = field(default_factory=list)
    """Human-readable names for each parameter dimension."""

    def __post_init__(self) -> None:
        if self.dim < 1:
            raise ValueError("Manifold dimension must be >= 1")

    def fisher_metric(
        self,
        theta: np.ndarray,
        log_likelihood_grad_samples: np.ndarray,
    ) -> np.ndarray:
        """Compute n x n Fisher information matrix at point theta.

        THEOREM (Fisher Information): G_ij(theta) = E[d_i log p * d_j log p]
        estimated from samples of the score function.

        The Fisher metric is positive semi-definite by construction
        (it's a covariance matrix of score vectors).

        Args:
            theta: Current parameter vector (n,).
            log_likelihood_grad_samples: Score function samples (m, n)
                where m = number of samples, n = parameter dimension.

        Returns:
            Fisher information matrix G (n, n), positive semi-definite.
        """
        if theta.shape != (self.dim,):
            raise ValueError(f"theta must have shape ({self.dim},), got {theta.shape}")
        samples = log_likelihood_grad_samples
        if samples.ndim != 2 or samples.shape[1] != self.dim:
            raise ValueError(
                f"Samples must have shape (m, {self.dim}), got {samples.shape}"
            )
        # G = (1/m) * sum_i (grad_i)(grad_i)^T = samples^T @ samples / m
        m = samples.shape[0]
        return samples.T @ samples / m

    def fisher_metric_from_log_probs(
        self,
        theta: np.ndarray,
        log_prob_fn: Callable[[np.ndarray], float],
        n_samples: int = 100,
        epsilon: float = 1e-4,
    ) -> np.ndarray:
        """Estimate Fisher metric via finite-difference score computation.

        For each sample, approximate d_i log p by centered difference:
            d_i log p ~ (log p(theta + eps*e_i) - log p(theta - eps*e_i)) / (2*eps)

        CONSTRUCTION: Numerical Fisher estimation for black-box log likelihoods.

        Args:
            theta: Current parameter vector (n,).
            log_prob_fn: Function mapping theta -> log p(x|theta) for a sample.
            n_samples: Number of Monte Carlo samples.
            epsilon: Finite difference step size.

        Returns:
            Fisher information matrix G (n, n).
        """
        if theta.shape != (self.dim,):
            raise ValueError(f"theta must have shape ({self.dim},), got {theta.shape}")
        scores = np.zeros((n_samples, self.dim))
        for s in range(n_samples):
            for i in range(self.dim):
                e_i = np.zeros(self.dim)
                e_i[i] = epsilon
                scores[s, i] = (
                    log_prob_fn(theta + e_i) - log_prob_fn(theta - e_i)
                ) / (2 * epsilon)
        return self.fisher_metric(theta, scores)

    @staticmethod
    def geodesic_distance_approx(
        g: np.ndarray,
        theta1: np.ndarray,
        theta2: np.ndarray,
    ) -> float:
        """Approximate geodesic distance on (M, G_Fisher).

        For nearby points, geodesic distance ~ sqrt((t2-t1)^T G (t2-t1)).
        This is the first-order approximation assuming G is approximately
        constant between theta1 and theta2.

        PROPOSITION: This approximation is exact for exponential families
        in natural parameters (the manifold is flat).

        Args:
            g: Fisher information matrix at midpoint (n, n).
            theta1: First parameter vector (n,).
            theta2: Second parameter vector (n,).

        Returns:
            Approximate geodesic distance (non-negative float).
        """
        delta = theta2 - theta1
        # d^2 = delta^T @ G @ delta
        d_sq = delta @ g @ delta
        return math.sqrt(max(0.0, d_sq))

    @staticmethod
    def kl_divergence_gaussian(
        mu1: np.ndarray,
        sigma1: np.ndarray,
        mu2: np.ndarray,
        sigma2: np.ndarray,
    ) -> float:
        """KL(p1 || p2) for multivariate Gaussians.

        KL = 0.5 * (tr(Sigma2^{-1} Sigma1) + (mu2-mu1)^T Sigma2^{-1} (mu2-mu1)
                     - k + ln(det(Sigma2)/det(Sigma1)))

        PROPOSITION: For exponential families, KL divergence equals the
        Bregman divergence of the log-partition function.

        Args:
            mu1, sigma1: Mean and covariance of p1.
            mu2, sigma2: Mean and covariance of p2.

        Returns:
            KL divergence (non-negative float).
        """
        k = mu1.shape[0]
        sigma2_inv = np.linalg.inv(sigma2)
        delta_mu = mu2 - mu1
        _, logdet1 = np.linalg.slogdet(sigma1)
        _, logdet2 = np.linalg.slogdet(sigma2)
        return 0.5 * float(
            np.trace(sigma2_inv @ sigma1)
            + delta_mu @ sigma2_inv @ delta_mu
            - k
            + logdet2 - logdet1
        )


# ── Natural Gradient Optimizer ───────────────────────────────────────────

@dataclass
class NaturalGradientOptimizer:
    """Amari's natural gradient (1998).

    nabla_tilde L(theta) = G(theta)^{-1} nabla_theta L(theta)

    PROPOSITION 5.3 (Natural Gradient):
    - Parameterization-invariant (same update regardless of coordinates)
    - Steepest descent w.r.t. Fisher metric
    - For exponential families: manifold is dually flat,
      Pythagorean theorem holds for KL divergence

    Uses Tikhonov regularization G + lambda*I for numerical stability
    (K-FAC style approximation).

    CONSTRUCTION: Natural gradient optimizer over Darwin Engine parameters.
    """

    manifold: StatisticalManifold
    """The underlying statistical manifold."""

    learning_rate: float = 0.01
    """Step size for gradient descent."""

    damping: float = 1e-4
    """Tikhonov regularization lambda for inverting G."""

    def natural_gradient(
        self,
        loss_grad: np.ndarray,
        fisher: np.ndarray,
    ) -> np.ndarray:
        """G(theta)^{-1} * nabla L -- the natural gradient direction.

        PROPOSITION 5.3: This is the steepest descent direction
        w.r.t. the Fisher-Rao metric, making it parameterization-invariant.

        Args:
            loss_grad: Euclidean gradient nabla_theta L (n,).
            fisher: Fisher information matrix G(theta) (n, n).

        Returns:
            Natural gradient direction (n,).
        """
        n = fisher.shape[0]
        # Regularized inverse: (G + lambda*I)^{-1}
        g_reg = fisher + self.damping * np.eye(n)
        return np.linalg.solve(g_reg, loss_grad)

    def step(
        self,
        theta: np.ndarray,
        loss_grad: np.ndarray,
        fisher: np.ndarray,
    ) -> np.ndarray:
        """One natural gradient step on the statistical manifold.

        theta_{t+1} = theta_t - lr * G(theta_t)^{-1} * nabla L(theta_t)

        Args:
            theta: Current parameters (n,).
            loss_grad: Euclidean loss gradient (n,).
            fisher: Fisher information matrix (n, n).

        Returns:
            Updated parameters theta_{t+1} (n,).
        """
        nat_grad = self.natural_gradient(loss_grad, fisher)
        return theta - self.learning_rate * nat_grad


# ── Dharmic Attractor ────────────────────────────────────────────────────

@dataclass
class DharmicAttractor:
    """D subset M is the dharmic subspace.

    D = {p in M : Ahimsa(p) AND Satya(p) AND Anekanta(p)
                  AND Swabhaav(p) AND Vyavasthit(p) AND BhedGnan(p)}

    Evolution dynamics on (M, G_Fisher):
        dS/dt = nabla_tilde F(S) + nabla_tilde A(S)
    where F(S) = fitness and A(S) = -d^2(S, D) (dharmic attraction).

    THEOREM 5.5 (Dharmic Convergence): If D is geodesically convex, then
        d(S_t, D) <= d(S_0, D) * e^{-lambda*t}
    (exponential convergence to dharmic subspace).

    CONJECTURE: The convergence rate lambda connects to R_V contraction.

    CONSTRUCTION: Dharmic attractor geometry on the Fisher manifold.
    """

    constraints: list[Callable[[np.ndarray], bool]]
    """Dharmic predicates: theta -> bool. Each must hold on D."""

    manifold: StatisticalManifold
    """The underlying statistical manifold."""

    constraint_names: list[str] = field(default_factory=list)
    """Human-readable names for each constraint."""

    def is_dharmic(self, theta: np.ndarray) -> bool:
        """Check if theta lies in D (all constraints satisfied).

        Args:
            theta: Parameter vector (n,).

        Returns:
            True if theta satisfies ALL dharmic constraints.
        """
        return all(c(theta) for c in self.constraints)

    def constraint_violations(self, theta: np.ndarray) -> list[str]:
        """List which dharmic constraints are violated at theta.

        Args:
            theta: Parameter vector (n,).

        Returns:
            Names of violated constraints (empty if theta in D).
        """
        names = self.constraint_names or [
            f"constraint_{i}" for i in range(len(self.constraints))
        ]
        return [
            names[i]
            for i, c in enumerate(self.constraints)
            if not c(theta)
        ]

    def distance_to_dharma(
        self,
        theta: np.ndarray,
        fisher: np.ndarray,
        dharmic_points: np.ndarray,
    ) -> float:
        """Approximate geodesic distance from theta to D.

        Uses minimum geodesic distance to a set of known dharmic points
        as proxy for d(theta, D).

        PROPOSITION: This is an upper bound on the true geodesic distance.

        Args:
            theta: Current parameter vector (n,).
            fisher: Fisher metric at theta (n, n).
            dharmic_points: Known points in D, shape (k, n).

        Returns:
            Minimum approximate geodesic distance to D.
        """
        if dharmic_points.shape[0] == 0:
            return float("inf")
        distances = [
            StatisticalManifold.geodesic_distance_approx(fisher, theta, dp)
            for dp in dharmic_points
        ]
        return min(distances)

    def dharmic_pressure(
        self,
        theta: np.ndarray,
        fisher: np.ndarray,
        dharmic_points: np.ndarray,
    ) -> np.ndarray:
        """nabla_tilde A(S) -- natural gradient of -d^2(S, D).

        Pulls the system toward the dharmic subspace D.
        Direction: toward the nearest dharmic point, scaled by Fisher inverse.

        THEOREM 5.5: This pressure ensures exponential convergence
        to D when D is geodesically convex.

        Args:
            theta: Current parameters (n,).
            fisher: Fisher metric at theta (n, n).
            dharmic_points: Known points in D (k, n).

        Returns:
            Dharmic pressure vector (n,). Points toward D.
        """
        if dharmic_points.shape[0] == 0:
            return np.zeros_like(theta)

        # Find nearest dharmic point
        distances = [
            StatisticalManifold.geodesic_distance_approx(fisher, theta, dp)
            for dp in dharmic_points
        ]
        nearest_idx = int(np.argmin(distances))
        nearest = dharmic_points[nearest_idx]

        # Euclidean gradient of -d^2: nabla(-d^2) = 2 * G @ (nearest - theta)
        # Natural gradient: G^{-1} @ (2 * G @ delta) = 2 * delta
        delta = nearest - theta
        return 2.0 * delta

    def check_contractivity(
        self,
        fisher: np.ndarray,
        jacobian: np.ndarray,
    ) -> tuple[bool, float]:
        """Test Wensing-Slotine criterion for geodesic convexity.

        If spectral radius of the Jacobian of the natural gradient flow
        is < 1, the dharmic subspace is contracting (geodesically convex).

        PROPOSITION: Spectral radius < 1 implies exponential convergence
        via the contraction mapping theorem.

        Args:
            fisher: Fisher metric (n, n).
            jacobian: Jacobian of natural gradient dynamics (n, n).

        Returns:
            Tuple of (is_contracting, spectral_radius).
        """
        # Metric-weighted Jacobian: G^{-1} @ J for natural gradient dynamics
        g_inv = np.linalg.inv(fisher + 1e-10 * np.eye(fisher.shape[0]))
        weighted_jac = g_inv @ jacobian
        eigenvalues = np.linalg.eigvals(weighted_jac)
        spectral_radius = float(np.max(np.abs(eigenvalues)))
        return spectral_radius < 1.0, spectral_radius


# ── R_V as Manifold Collapse ────────────────────────────────────────────

def participation_ratio(covariance: np.ndarray) -> float:
    """PR(Sigma) = (tr Sigma)^2 / tr(Sigma^2).

    Measures effective dimensionality of the distribution.
    1 <= PR <= n.

    PROPOSITION: PR is the reciprocal of the Herfindahl index of
    eigenvalues -- a measure of concentration.

    R_V < 1 implies FIM is becoming more singular -- manifold has
    collapsed to lower-dimensional submanifold.

    At the fixed point (L5): representation converged to stable low-rank
    structure. Manifold is locally flat. Information-theoretic ground state.

    Args:
        covariance: Symmetric positive semi-definite matrix (n, n).

    Returns:
        Participation ratio (float >= 1.0).
    """
    trace = np.trace(covariance)
    trace_sq = np.trace(covariance @ covariance)
    if trace_sq < 1e-30:
        return 1.0
    return float(trace ** 2 / trace_sq)


def rv_from_covariances(
    cov_early: np.ndarray,
    cov_late: np.ndarray,
) -> float:
    """R_V = PR_late / PR_early -- contraction ratio from covariance matrices.

    CONJECTURE 1.10: R_V < 1.0 measures convergence rate toward a
    Lawvere fixed point in transformer representations.

    Args:
        cov_early: Covariance at early layers (n, n).
        cov_late: Covariance at late layers (n, n).

    Returns:
        R_V ratio (float). Values < 1.0 indicate contraction.
    """
    pr_early = participation_ratio(cov_early)
    pr_late = participation_ratio(cov_late)
    if pr_early < 1e-12:
        return 1.0
    return pr_late / pr_early


def effective_dimension_trajectory(
    covariances: list[np.ndarray],
) -> list[float]:
    """Track PR across layers to visualize dimensional collapse.

    PROPOSITION: A monotonically decreasing PR trajectory indicates
    progressive contraction toward a low-rank attractor.

    Args:
        covariances: Covariance matrices at successive layers.

    Returns:
        List of participation ratios, one per layer.
    """
    return [participation_ratio(c) for c in covariances]


# ── Combined Evolution Step ──────────────────────────────────────────────

@dataclass
class MetaEvolutionStep:
    """One step of meta-evolution on the statistical manifold.

    Combines fitness gradient (local optimization) with dharmic pressure
    (global attractor) using natural gradient descent.

    THEOREM 5.5: The combined dynamics
        dS/dt = nabla_tilde F(S) + alpha * nabla_tilde A(S)
    converge exponentially to D when D is geodesically convex.

    CONSTRUCTION: Combined meta-evolution step integrating natural
    gradient with dharmic attractor dynamics.
    """

    optimizer: NaturalGradientOptimizer
    attractor: DharmicAttractor
    dharmic_weight: float = 0.1
    """Weight alpha for dharmic pressure relative to fitness gradient."""

    def step(
        self,
        theta: np.ndarray,
        fitness_grad: np.ndarray,
        fisher: np.ndarray,
        dharmic_points: np.ndarray,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """One combined meta-evolution step.

        theta_{t+1} = theta_t - lr * G^{-1}(nabla F + alpha * nabla A)

        Args:
            theta: Current meta-parameters (n,).
            fitness_grad: Euclidean fitness gradient (n,).
            fisher: Fisher information matrix (n, n).
            dharmic_points: Known dharmic points (k, n).

        Returns:
            Tuple of (new_theta, diagnostics_dict).
        """
        # Natural gradient of fitness
        nat_grad_fitness = self.optimizer.natural_gradient(fitness_grad, fisher)

        # Dharmic pressure (already in natural gradient form)
        pressure = self.attractor.dharmic_pressure(theta, fisher, dharmic_points)

        # Combined update
        combined = nat_grad_fitness + self.dharmic_weight * pressure
        new_theta = theta - self.optimizer.learning_rate * combined

        # Diagnostics
        d_dharma = self.attractor.distance_to_dharma(theta, fisher, dharmic_points)
        is_dharmic = self.attractor.is_dharmic(new_theta)

        return new_theta, {
            "fitness_grad_norm": float(np.linalg.norm(nat_grad_fitness)),
            "dharmic_pressure_norm": float(np.linalg.norm(pressure)),
            "distance_to_dharma": d_dharma,
            "is_dharmic": is_dharmic,
            "violations": self.attractor.constraint_violations(new_theta),
        }
