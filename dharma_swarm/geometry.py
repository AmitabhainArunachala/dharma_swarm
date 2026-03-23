"""Geometry-aware subspace tracking for the DHARMA SWARM 7-layer architecture.

This module implements the geometric substrate described in the Dharma Swarm
blueprint: each agent's knowledge lives in a low-dimensional gradient subspace,
and forgetting / drift / interference are governed by the principal angles
between these subspaces.

Key components:
    - SubspaceRegistry: per-agent data structure tracking representational
      subspaces for each task or capability.
    - batched_principal_angles(): Björck-Golub algorithm (numpy) for computing
      principal angles between pairs of subspaces.
    - subspace_overlap_score(): multi-metric overlap quantification.
    - forgetting_risk(): geometric forgetting bound from Steele (2026).
    - classify_drift_phase(): three-phase classifier per Ratzon et al. (2024).

This module is **standalone** — it depends only on numpy and the Python
standard library.  No dharma_swarm imports.

References:
    - Steele (2026), arXiv:2603.02224 — geometric forgetting bound
    - Saha et al. (2021), arXiv:2103.09762 — GPM subspace registry
    - Ratzon et al. (2024) — three-phase drift model
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray


# ---------------------------------------------------------------------------
# SubspaceRegistry
# ---------------------------------------------------------------------------


@dataclass
class SubspaceEntry:
    """A single subspace snapshot for one task at one layer."""

    task_id: str
    layer_id: str
    basis: NDArray  # (d, k) orthonormal columns
    singular_values: NDArray  # (k,)
    participation_ratio: float
    timestamp: int  # training step when snapshot was taken


@dataclass
class SubspaceRegistry:
    """Per-agent registry of representational subspaces.

    Tracks the orthonormal bases learned for each task at each layer,
    following the GPM incremental update protocol.  The registry is the
    agent's geometric memory — it records *where* knowledge lives in
    parameter space.

    The accumulated basis ``M`` for a layer is the column-wise
    concatenation of all stored bases for that layer.  New tasks append
    only the *residual* directions not already spanned by ``M``.
    """

    agent_id: str = ""
    entries: list[SubspaceEntry] = field(default_factory=list)

    # -- query helpers -------------------------------------------------------

    def get_basis(self, layer_id: str, task_id: str) -> NDArray | None:
        """Return the stored basis for a (layer, task) pair, or None."""
        for e in self.entries:
            if e.layer_id == layer_id and e.task_id == task_id:
                return e.basis
        return None

    def accumulated_basis(self, layer_id: str) -> NDArray | None:
        """Return the column-concatenated accumulated basis for *layer_id*.

        If no entries exist for the layer, returns None.
        """
        bases = [e.basis for e in self.entries if e.layer_id == layer_id]
        if not bases:
            return None
        return np.hstack(bases)

    def capacity_ratio(self, layer_id: str, d: int) -> float:
        """Fraction of total capacity used: rank(M) / d.

        Args:
            layer_id: The layer to check.
            d: The full parameter-space dimensionality for this layer.

        Returns:
            A float in [0, 1].  Values above 0.8 indicate approaching
            subspace saturation.
        """
        M = self.accumulated_basis(layer_id)
        if M is None:
            return 0.0
        return min(M.shape[1] / max(d, 1), 1.0)

    # -- update protocol -----------------------------------------------------

    def register(
        self,
        task_id: str,
        layer_id: str,
        activation_matrix: NDArray,
        variance_threshold: float = 0.99,
        timestamp: int = 0,
    ) -> SubspaceEntry:
        """GPM-style incremental basis update.

        1. Project out existing basis directions.
        2. SVD of residual.
        3. Keep top-k directions that capture *variance_threshold* of
           residual variance.
        4. Append to registry.

        Args:
            task_id: Identifier for the new task.
            layer_id: Layer this snapshot belongs to.
            activation_matrix: (d, n_samples) activation matrix.
            variance_threshold: Fraction of residual variance to retain.
            timestamp: Training step counter.

        Returns:
            The newly created SubspaceEntry.
        """
        R = activation_matrix.astype(np.float64)
        M = self.accumulated_basis(layer_id)
        if M is not None:
            # Remove existing basis directions
            R = R - M @ (M.T @ R)

        U, S, _ = np.linalg.svd(R, full_matrices=False)
        # Select top-k by cumulative energy
        total_var = np.sum(S ** 2)
        if total_var < 1e-12:
            k = 1
        else:
            cumvar = np.cumsum(S ** 2) / total_var
            k = int(np.searchsorted(cumvar, variance_threshold)) + 1
        k = max(1, min(k, len(S)))

        basis = U[:, :k]
        svs = S[:k]

        # Participation ratio of the full activation covariance
        cov_diag = S ** 2
        trace = np.sum(cov_diag)
        trace_sq = np.sum(cov_diag ** 2)
        pr = (trace ** 2) / (trace_sq + 1e-12)

        entry = SubspaceEntry(
            task_id=task_id,
            layer_id=layer_id,
            basis=basis,
            singular_values=svs,
            participation_ratio=float(pr),
            timestamp=timestamp,
        )
        self.entries.append(entry)
        return entry


# ---------------------------------------------------------------------------
# Principal angle computation
# ---------------------------------------------------------------------------


def batched_principal_angles(
    Q_i: NDArray,
    Q_j: NDArray,
    eps: float = 1e-7,
) -> NDArray:
    """Compute principal angles between batched pairs of subspaces.

    Uses the Björck-Golub algorithm: SVD of the cross-Gram matrix yields
    cos(θ) as singular values.

    Args:
        Q_i: Orthonormal bases, shape ``(batch, d, p)`` or ``(d, p)`` for
            a single pair.
        Q_j: Orthonormal bases, shape ``(batch, d, q)`` or ``(d, q)``.
        eps: Clamping epsilon for numerical stability.

    Returns:
        Principal angles in [0, π/2], shape ``(batch, min(p,q))`` or
        ``(min(p,q),)`` for unbatched input.
    """
    single = Q_i.ndim == 2
    if single:
        Q_i = Q_i[np.newaxis, ...]
        Q_j = Q_j[np.newaxis, ...]

    # Cross-Gram: (batch, p, q)
    M = np.einsum("bdp,bdq->bpq", Q_i, Q_j)

    batch_size = M.shape[0]
    k = min(M.shape[1], M.shape[2])
    angles = np.empty((batch_size, k), dtype=np.float64)

    for b in range(batch_size):
        _, s, _ = np.linalg.svd(M[b], full_matrices=False)
        cos_theta = np.clip(s[:k], -1.0 + eps, 1.0 - eps)
        angles[b] = np.arccos(cos_theta)

    if single:
        return angles[0]
    return angles


# ---------------------------------------------------------------------------
# Subspace overlap score
# ---------------------------------------------------------------------------


def subspace_overlap_score(
    basis_a: NDArray,
    basis_b: NDArray,
) -> dict[str, Any]:
    """Quantify overlap between two subspaces using multiple metrics.

    Args:
        basis_a: (d, k_a) orthonormal columns.
        basis_b: (d, k_b) orthonormal columns.

    Returns:
        Dict with theta_min, theta_max, grassmann_distance,
        chordal_distance, overlap_fraction, and all_angles.
    """
    M = basis_a.T @ basis_b
    _, s, _ = np.linalg.svd(M, full_matrices=False)
    cos_theta = np.clip(s, 0.0, 1.0)
    theta = np.arccos(cos_theta)

    theta_min = float(theta[0]) if len(theta) > 0 else 0.0
    theta_max = float(theta[-1]) if len(theta) > 0 else 0.0

    grassmann_dist = float(np.linalg.norm(theta))
    chordal_dist = float(np.sqrt(np.sum(np.sin(theta) ** 2)))
    overlap_frac = float(np.mean(theta < (np.pi / 4))) if len(theta) > 0 else 0.0

    return {
        "theta_min": theta_min,
        "theta_max": theta_max,
        "grassmann_distance": grassmann_dist,
        "chordal_distance": chordal_dist,
        "overlap_fraction": overlap_frac,
        "all_angles": theta,
    }


# ---------------------------------------------------------------------------
# Forgetting risk estimator
# ---------------------------------------------------------------------------


def forgetting_risk(
    theta_min: float,
    learning_rate: float,
    update_norm: float,
    smoothness_L: float = 1.0,
    curvature_mu: float = 1.0,
    beta: float = 0.01,
) -> dict[str, Any]:
    """Estimate forgetting risk using the geometric forgetting bound.

    The bound is::

        F_{i,t} ≤ α · sin²(θ_min) + β

    where α = η · L · ‖Δ_t‖² / μ.

    Based on Steele (2026), arXiv:2603.02224.

    Args:
        theta_min: Minimum principal angle (radians) between current
            gradient subspace and nearest stored subspace.
        learning_rate: η — optimizer learning rate.
        update_norm: ‖Δ_t‖ — L2 norm of the parameter update.
        smoothness_L: Lipschitz smoothness constant of the loss.
        curvature_mu: Strong convexity / curvature constant.
        beta: Baseline forgetting term.

    Returns:
        Dict with forgetting_bound, alpha, zone classification, and
        actionable recommendation.
    """
    alpha = learning_rate * smoothness_L * (update_norm ** 2) / max(curvature_mu, 1e-12)
    sin2_theta = math.sin(theta_min) ** 2
    forgetting_bound = alpha * sin2_theta + beta

    cos_theta = math.cos(theta_min)
    if cos_theta < 0.999:
        rank_sensitivity = 1.0 / (1.0 - cos_theta)
    else:
        rank_sensitivity = float("inf")

    cos2 = cos_theta ** 2
    if cos2 > 0.75:
        zone = "RED"
    elif cos2 > 0.33:
        zone = "YELLOW"
    else:
        zone = "GREEN"

    recommendations = {
        "RED": "Apply full gradient projection + reduce rank",
        "YELLOW": "Apply GPM projection; consider TRGP for transfer",
        "GREEN": "Proceed normally; rank has minimal effect",
    }

    return {
        "forgetting_bound": forgetting_bound,
        "alpha": alpha,
        "sin2_theta_min": sin2_theta,
        "rank_sensitivity": rank_sensitivity,
        "zone": zone,
        "recommendation": recommendations[zone],
    }


# ---------------------------------------------------------------------------
# Drift phase classifier
# ---------------------------------------------------------------------------


def classify_drift_phase(
    pr_history: list[float],
    loss_history: list[float],
    cka_history: list[float],
    window: int = 50,
) -> str:
    """Classify current learning phase per the three-phase drift model.

    Based on Ratzon et al. (2024):

    - **Phase 1 (Convergence)**: loss changing, PR changing, CKA changing.
    - **Phase 2 (Directed drift)**: loss stable, PR falling (sparsifying),
      CKA changing.
    - **Phase 3 (Null drift)**: loss stable, PR stable, CKA may change
      (geometry preserved within zero-loss manifold).

    Args:
        pr_history: Participation ratio over time.
        loss_history: Training loss over time.
        cka_history: CKA similarity to reference snapshot over time.
        window: Sliding window size for analysis.

    Returns:
        One of ``"convergence"``, ``"directed_drift"``, or ``"null_drift"``.
    """
    if len(pr_history) < window or len(loss_history) < window:
        return "convergence"

    recent_loss = np.array(loss_history[-window:], dtype=np.float64)
    recent_pr = np.array(pr_history[-window:], dtype=np.float64)

    mean_loss = np.mean(recent_loss)
    loss_var = float(np.var(recent_loss) / (mean_loss ** 2 + 1e-8))

    # Linear fit for PR trend
    x = np.arange(window, dtype=np.float64)
    pr_slope = float(np.polyfit(x, recent_pr, 1)[0])

    mean_pr = np.mean(recent_pr)
    pr_var = float(np.var(recent_pr) / (mean_pr ** 2 + 1e-8))

    LOSS_STABLE_THRESH = 0.001
    PR_SLOPE_THRESH = -0.01
    PR_STABLE_THRESH = 0.001

    loss_stable = loss_var < LOSS_STABLE_THRESH
    pr_falling = pr_slope < PR_SLOPE_THRESH
    pr_stable = pr_var < PR_STABLE_THRESH

    if not loss_stable:
        return "convergence"
    elif loss_stable and pr_falling and not pr_stable:
        return "directed_drift"
    elif loss_stable and pr_stable:
        return "null_drift"
    else:
        return "directed_drift"
