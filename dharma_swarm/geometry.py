"""geometry.py — Subspace geometry primitives for the Dharma Swarm.

STANDALONE MODULE — no dharma_swarm imports. numpy only.

This is the geometry seed from the Dharma Swarm: Geometry-Aware Cognitive
Architecture Blueprint. It provides the measurement layer for tracking
representational subspaces across agents and tasks.

Core insight: forgetting = subspace interference governed by principal
angles. Intelligence = geometry of representations evolving over time.

These primitives will be wired into the organism's monitoring loop once
real agents are running tasks end-to-end (Phase 9+). For now they exist
as self-contained, tested utilities.

Key functions:
    batched_principal_angles  — Björck-Golub via SVD of cross-Gram matrix
    subspace_overlap_score    — Multi-metric overlap quantification
    forgetting_risk           — Geometric forgetting bound (Steele 2026)
    classify_drift_phase      — Three-phase model (Ratzon et al. 2024)

Key class:
    SubspaceRegistry          — Per-layer subspace tracking with GPM-style
                                incremental updates

Ground: Saha et al. (GPM), Steele 2026 (geometric forgetting bound,
r=0.994), Ratzon et al. 2024 (three-phase drift model), Björck & Golub
1973 (principal angles).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import numpy as np
from numpy.typing import NDArray


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Principal angle computation (Björck-Golub algorithm)
# ---------------------------------------------------------------------------


def batched_principal_angles(
    q_i: NDArray,
    q_j: NDArray,
    eps: float = 1e-7,
) -> NDArray:
    """Compute principal angles between two subspaces.

    Uses the Björck-Golub algorithm: SVD of cross-Gram matrix Q_i^T Q_j.

    Args:
        q_i: (d, p) orthonormal basis for subspace i
        q_j: (d, q) orthonormal basis for subspace j
        eps: numerical clamp epsilon

    Returns:
        (min(p, q),) array of principal angles in [0, π/2]
    """
    # Cross-Gram matrix: (p, q)
    m = q_i.T @ q_j
    _, cos_theta, _ = np.linalg.svd(m, full_matrices=False)
    cos_theta = np.clip(cos_theta, -1.0 + eps, 1.0 - eps)
    theta = np.arccos(cos_theta)
    return theta


def subspace_overlap_score(
    basis_a: NDArray,
    basis_b: NDArray,
) -> dict[str, Any]:
    """Quantify overlap between two subspaces via multiple metrics.

    Args:
        basis_a: (d, k_a) orthonormal basis
        basis_b: (d, k_b) orthonormal basis

    Returns:
        dict with theta_min, theta_max, grassmann_distance,
        chordal_distance, overlap_fraction, all_angles
    """
    theta = batched_principal_angles(basis_a, basis_b)

    theta_min = float(theta[0]) if len(theta) > 0 else math.pi / 2
    theta_max = float(theta[-1]) if len(theta) > 0 else math.pi / 2

    # Grassmann geodesic distance
    grassmann_dist = float(np.linalg.norm(theta))

    # Chordal distance: sqrt(sum(sin²(θ_i)))
    chordal_dist = float(np.sqrt(np.sum(np.sin(theta) ** 2)))

    # Overlap fraction: proportion of dimensions with θ < 45°
    overlap_frac = float(np.mean(theta < (math.pi / 4))) if len(theta) > 0 else 0.0

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
    learning_rate: float = 0.001,
    update_norm: float = 1.0,
    smoothness_l: float = 1.0,
    curvature_mu: float = 1.0,
    beta: float = 0.01,
) -> dict[str, Any]:
    """Estimate forgetting risk using the geometric forgetting bound.

    F_{i,t} ≤ α * sin²(θ_min) + β
    where α = η * L * ||Δ_t||² / μ.

    Based on Steele (2026), arXiv:2603.02224 — validated at r=0.994
    correlation between predicted and measured forgetting.

    Args:
        theta_min: minimum principal angle between task subspaces (radians)
        learning_rate: η
        update_norm: ||Δ_t||
        smoothness_l: Lipschitz smoothness constant L
        curvature_mu: strong convexity parameter μ
        beta: baseline forgetting term

    Returns:
        dict with forgetting_bound, alpha, sin2_theta_min,
        rank_sensitivity, zone, recommendation
    """
    alpha = learning_rate * smoothness_l * (update_norm ** 2) / curvature_mu
    sin2_theta = math.sin(theta_min) ** 2
    forgetting_bound = alpha * sin2_theta + beta

    # Effective rank interaction: r_eff = min(r, c / (1 - cos(θ)))
    cos_theta = math.cos(theta_min)
    if cos_theta < 0.999:
        rank_sensitivity = 1.0 / (1.0 - cos_theta)
    else:
        rank_sensitivity = float("inf")

    # Classify zone by cos²(θ_min)
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
# Drift phase classifier (Ratzon et al. 2024 three-phase model)
# ---------------------------------------------------------------------------


def classify_drift_phase(
    pr_history: list[float],
    loss_history: list[float],
    cka_history: list[float],
    window: int = 50,
) -> str:
    """Classify current learning phase per Ratzon et al. 2024.

    Phase 1 (Convergence): loss changing, PR changing, CKA changing
    Phase 2 (Directed drift): loss stable, PR falling (sparsifying), CKA changing
    Phase 3 (Null drift): loss stable, PR stable, CKA may change (geometry preserved)

    Args:
        pr_history: participation ratio over time
        loss_history: training loss over time
        cka_history: CKA to reference snapshot over time
        window: sliding window size for statistics

    Returns:
        "convergence", "directed_drift", or "null_drift"
    """
    if len(pr_history) < window or len(loss_history) < window:
        return "convergence"

    recent_loss = np.array(loss_history[-window:])
    recent_pr = np.array(pr_history[-window:])

    mean_loss = float(np.mean(recent_loss))
    loss_var = float(np.var(recent_loss)) / (mean_loss ** 2 + 1e-8)

    # Linear fit for PR slope
    x = np.arange(window, dtype=np.float64)
    pr_slope = float(np.polyfit(x, recent_pr, 1)[0])

    mean_pr = float(np.mean(recent_pr))
    pr_var = float(np.var(recent_pr)) / (mean_pr ** 2 + 1e-8)

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


# ---------------------------------------------------------------------------
# Participation ratio
# ---------------------------------------------------------------------------


def participation_ratio(covariance: NDArray) -> float:
    """Compute participation ratio: Tr(C)² / Tr(C²).

    Measures effective dimensionality. Returns 1.0 for a rank-1 matrix,
    d for a d×d identity matrix.

    Args:
        covariance: (d, d) symmetric positive semi-definite matrix

    Returns:
        Participation ratio (float >= 1.0)
    """
    trace_c = float(np.trace(covariance))
    trace_c2 = float(np.trace(covariance @ covariance))
    if trace_c2 < 1e-12:
        return 1.0
    return (trace_c ** 2) / trace_c2


# ---------------------------------------------------------------------------
# Subspace Registry
# ---------------------------------------------------------------------------


@dataclass
class SubspaceEntry:
    """A single task/agent subspace entry in the registry."""
    basis: NDArray                  # (d, k) orthonormal
    singular_values: NDArray        # (k,)
    participation_ratio: float
    timestamp: str = field(default_factory=_utc_now_iso)
    task_id: str = ""
    agent_id: str = ""


class SubspaceRegistry:
    """Per-layer subspace registry with GPM-style incremental updates.

    Tracks representational subspaces for each task, supports interference
    queries via principal angles, and monitors subspace saturation.

    This is the geometry-aware memory of an agent — analogous to GPM's
    gradient projection memory but extended for multi-agent coordination.
    """

    def __init__(self, hidden_dim: int, max_rank: int = 256) -> None:
        self.hidden_dim = hidden_dim
        self.max_rank = max_rank

        self.entries: dict[str, SubspaceEntry] = {}    # task_id -> entry
        self._merged_basis: NDArray | None = None       # accumulated basis

    def add_task(
        self,
        task_id: str,
        activations: NDArray,
        threshold: float = 0.95,
        agent_id: str = "",
    ) -> SubspaceEntry:
        """GPM-style incremental subspace update.

        1. Project out existing basis directions
        2. SVD of residual
        3. Keep top-k directions by variance threshold
        4. Append to merged basis

        Args:
            task_id: unique identifier for this task
            activations: (d, n_samples) activation matrix
            threshold: cumulative variance threshold for rank selection
            agent_id: which agent produced these activations

        Returns:
            SubspaceEntry for the new task
        """
        if self._merged_basis is not None:
            # Remove existing directions
            m = self._merged_basis
            residual = activations - m @ (m.T @ activations)
        else:
            residual = activations

        u, s, _ = np.linalg.svd(residual, full_matrices=False)

        # Select top-k by variance threshold
        total_var = float(np.sum(s ** 2))
        if total_var < 1e-12:
            k = 1
        else:
            cumvar = np.cumsum(s ** 2) / total_var
            k = int(np.searchsorted(cumvar, threshold)) + 1

        # Respect max rank budget
        current_rank = self._merged_basis.shape[1] if self._merged_basis is not None else 0
        k = min(k, self.max_rank - current_rank)
        k = max(k, 1)  # at least 1 direction

        new_basis = u[:, :k]
        new_sv = s[:k]

        # Compute participation ratio
        cov = new_basis @ np.diag(new_sv ** 2) @ new_basis.T
        pr = participation_ratio(cov) if k > 1 else 1.0

        entry = SubspaceEntry(
            basis=new_basis,
            singular_values=new_sv,
            participation_ratio=pr,
            task_id=task_id,
            agent_id=agent_id,
        )
        self.entries[task_id] = entry

        # Update merged basis
        if self._merged_basis is not None:
            self._merged_basis = np.hstack([self._merged_basis, new_basis])
        else:
            self._merged_basis = new_basis

        return entry

    def project_gradient(self, grad: NDArray) -> NDArray:
        """Project gradient onto residual gradient space.

        Removes components that would interfere with stored subspaces.
        g_hat = g - M @ M^T @ g

        Args:
            grad: gradient matrix (d, d) or (d,) vector

        Returns:
            Projected gradient, same shape as input
        """
        if self._merged_basis is None:
            return grad
        m = self._merged_basis
        if grad.ndim == 1:
            return grad - m @ (m.T @ grad)
        else:
            return grad - (grad @ m) @ m.T

    def interference(self, task_a: str, task_b: str) -> dict[str, Any]:
        """Compute interference between two tasks via principal angles.

        Returns subspace_overlap_score dict, or error dict if task not found.
        """
        ea = self.entries.get(task_a)
        eb = self.entries.get(task_b)
        if ea is None or eb is None:
            return {"error": f"task not found: {task_a if ea is None else task_b}"}
        return subspace_overlap_score(ea.basis, eb.basis)

    def saturation_ratio(self) -> float:
        """Fraction of total subspace capacity consumed."""
        if self._merged_basis is None:
            return 0.0
        return self._merged_basis.shape[1] / self.hidden_dim

    def summary(self) -> dict[str, Any]:
        """Return a summary of the registry state."""
        return {
            "hidden_dim": self.hidden_dim,
            "max_rank": self.max_rank,
            "num_tasks": len(self.entries),
            "total_rank": self._merged_basis.shape[1] if self._merged_basis is not None else 0,
            "saturation": self.saturation_ratio(),
            "tasks": {
                tid: {
                    "rank": int(e.basis.shape[1]),
                    "pr": e.participation_ratio,
                    "agent": e.agent_id,
                }
                for tid, e in self.entries.items()
            },
        }
