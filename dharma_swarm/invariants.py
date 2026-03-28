"""The four computable invariants that define system health.

From the 8-expert council synthesis (2026-03-28):

1. Criticality: λ_max of catalytic adjacency matrix ∈ [0.9, 1.1]
   Subcritical = perturbations die out (dead). Supercritical = explosions (chaos).
   Critical = maximal computational capacity (self-organized criticality).

2. Closure: autocatalytic closure ratio → 1.0
   Every active component must be catalyzed by at least one other.
   Below 1.0 = not self-sustaining, requires external management.

3. Information retention: mutation rate < s/L (Eigen threshold)
   Above threshold = evolution is random drift. Below = directed adaptation.

4. Diversity equilibrium: Krogh-Vedelsby E_diversity term
   Maximized subject to E_mean < threshold.
   When diversity falls, transcendence dies.

Each invariant is a pure function. InvariantSnapshot bundles them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Target bands
# ---------------------------------------------------------------------------

CRITICALITY_LOW = 0.9
CRITICALITY_HIGH = 1.1
CLOSURE_TARGET = 0.8  # Relaxed from 1.0 — new systems won't be fully closed yet
INFO_RETENTION_MARGIN = 0.0  # Must be positive (mutation_rate < s/L)
DIVERSITY_FLOOR = 0.2  # Minimum KV diversity or archive coverage


# ---------------------------------------------------------------------------
# InvariantSnapshot
# ---------------------------------------------------------------------------


@dataclass
class InvariantSnapshot:
    """A point-in-time measurement of all four system invariants."""

    timestamp: str
    criticality: float
    criticality_status: str
    closure_ratio: float
    closure_status: str
    info_retention: float
    info_retention_status: str
    diversity_equilibrium: float
    diversity_status: str
    overall: str


# ---------------------------------------------------------------------------
# Individual invariant computations (pure functions)
# ---------------------------------------------------------------------------


def compute_criticality(adjacency_matrix: np.ndarray) -> tuple[float, str]:
    """Spectral radius of the weighted adjacency matrix.

    Returns (lambda_max, status).
    """
    if adjacency_matrix.size == 0:
        return 0.0, "subcritical"

    try:
        eigenvalues = np.linalg.eigvals(adjacency_matrix)
        lambda_max = float(np.max(np.abs(eigenvalues)))
    except np.linalg.LinAlgError:
        return 0.0, "subcritical"

    if lambda_max < CRITICALITY_LOW:
        status = "subcritical"
    elif lambda_max > CRITICALITY_HIGH:
        status = "supercritical"
    else:
        status = "healthy"

    return round(lambda_max, 4), status


def compute_closure(
    total_nodes: int,
    autocatalytic_node_count: int,
) -> tuple[float, str]:
    """Autocatalytic closure ratio.

    Args:
        total_nodes: Total nodes in the catalytic graph.
        autocatalytic_node_count: Nodes that belong to any autocatalytic set.

    Returns (ratio, status).
    """
    if total_nodes == 0:
        return 0.0, "subcritical"

    ratio = autocatalytic_node_count / total_nodes

    if ratio >= CLOSURE_TARGET:
        status = "healthy"
    elif ratio >= CLOSURE_TARGET * 0.5:
        status = "degraded"
    else:
        status = "critical"

    return round(ratio, 4), status


def compute_info_retention(
    mutation_rate: float,
    selective_advantage: float,
    genome_length: int,
) -> tuple[float, str]:
    """Check mutation rate against Eigen's error threshold.

    Eigen threshold: q < s/L where:
      q = per-parameter mutation rate
      s = selective advantage of best genotype
      L = effective genome length

    Returns (margin, status) where margin = s/L - q.
    Positive margin = healthy. Negative = information loss.
    """
    if genome_length <= 0 or selective_advantage <= 0:
        return 0.0, "unknown"

    threshold = selective_advantage / genome_length
    margin = threshold - mutation_rate

    if margin > INFO_RETENTION_MARGIN:
        status = "healthy"
    elif margin > -0.01:
        status = "degraded"
    else:
        status = "critical"

    return round(margin, 6), status


def compute_diversity_equilibrium(
    coverage: float,
    kv_diversity: float | None = None,
) -> tuple[float, str]:
    """Diversity health from archive coverage and/or KV diversity term.

    Args:
        coverage: MAP-Elites archive coverage in [0, 1].
        kv_diversity: Krogh-Vedelsby diversity term (if available).

    Returns (value, status).
    """
    # Use KV diversity if available, else fall back to coverage
    value = kv_diversity if kv_diversity is not None else coverage

    if value >= DIVERSITY_FLOOR * 2:
        status = "healthy"
    elif value >= DIVERSITY_FLOOR:
        status = "degraded"
    else:
        status = "critical"

    return round(value, 4), status


# ---------------------------------------------------------------------------
# Snapshot factory
# ---------------------------------------------------------------------------


_STATUS_RANK = {"critical": 0, "subcritical": 1, "degraded": 2, "unknown": 3, "healthy": 4, "supercritical": 1}


def snapshot(
    adjacency_matrix: np.ndarray | None = None,
    total_nodes: int = 0,
    autocatalytic_node_count: int = 0,
    mutation_rate: float = 0.0,
    selective_advantage: float = 0.1,
    genome_length: int = 10,
    archive_coverage: float = 0.0,
    kv_diversity: float | None = None,
    timestamp: str = "",
) -> InvariantSnapshot:
    """Take a complete invariant snapshot.

    All parameters have defaults so callers can provide what they have.
    """
    from dharma_swarm.models import _utc_now

    if not timestamp:
        timestamp = _utc_now().isoformat()

    mat = adjacency_matrix if adjacency_matrix is not None else np.zeros((0, 0))
    crit_val, crit_status = compute_criticality(mat)
    clos_val, clos_status = compute_closure(total_nodes, autocatalytic_node_count)
    info_val, info_status = compute_info_retention(mutation_rate, selective_advantage, genome_length)
    div_val, div_status = compute_diversity_equilibrium(archive_coverage, kv_diversity)

    # Overall = worst of all four
    statuses = [crit_status, clos_status, info_status, div_status]
    overall = min(statuses, key=lambda s: _STATUS_RANK.get(s, 3))

    return InvariantSnapshot(
        timestamp=timestamp,
        criticality=crit_val,
        criticality_status=crit_status,
        closure_ratio=clos_val,
        closure_status=clos_status,
        info_retention=info_val,
        info_retention_status=info_status,
        diversity_equilibrium=div_val,
        diversity_status=div_status,
        overall=overall,
    )
