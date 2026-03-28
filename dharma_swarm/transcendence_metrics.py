"""Transcendence metrics — measuring whether diversity produces outperformance.

Core equation (Krogh-Vedelsby 1995):
    E_ensemble = E_mean - E_diversity

Where E_diversity is ALWAYS non-negative for non-identical agents.
When positive, diversity directly subtracts from ensemble error.

All functions are pure: no state, no I/O, fully testable.
"""

from __future__ import annotations

import math
from itertools import combinations
from typing import Sequence


def behavioral_diversity(outputs: Sequence[str]) -> float:
    """Pairwise token-set Jaccard distance across agent outputs.

    Returns average pairwise distance in [0, 1].
    Higher = more diverse outputs. 0 = identical. 1 = no overlap.
    """
    if len(outputs) < 2:
        return 0.0

    distances: list[float] = []
    token_sets = [set(o.lower().split()) for o in outputs]

    for a, b in combinations(token_sets, 2):
        union = a | b
        if not union:
            distances.append(0.0)
            continue
        intersection = a & b
        distances.append(1.0 - len(intersection) / len(union))

    return sum(distances) / len(distances) if distances else 0.0


def error_decorrelation(agent_errors: Sequence[float]) -> float:
    """Measure independence of agent errors.

    Takes a flat list of per-agent errors (e.g., Brier scores, squared errors).
    Returns a decorrelation score in [0, 1].
    1.0 = perfectly independent errors (ideal for transcendence).
    0.0 = perfectly correlated errors (no diversity benefit).

    For N agents, this computes the coefficient of variation of errors.
    High CV means errors vary a lot across agents = decorrelated.
    Low CV means all agents err similarly = correlated.
    """
    if len(agent_errors) < 2:
        return 0.0

    mean_err = sum(agent_errors) / len(agent_errors)
    if mean_err == 0.0:
        return 1.0  # All errors are zero — perfectly decorrelated (no errors)

    variance = sum((e - mean_err) ** 2 for e in agent_errors) / len(agent_errors)
    std = math.sqrt(variance)
    cv = std / abs(mean_err)

    # Normalize CV to [0, 1] using tanh-like squash
    return min(cv, 1.0)


def krogh_vedelsby_diversity(
    individual_errors: Sequence[float],
    ensemble_error: float,
) -> float:
    """The diversity term from the Krogh-Vedelsby decomposition.

    E_ensemble = E_mean - E_diversity
    Therefore: E_diversity = E_mean - E_ensemble

    Returns the diversity term. When positive, diversity is helping.
    When zero, no diversity benefit. When negative (shouldn't happen
    with proper aggregation), aggregation is HURTING.
    """
    if not individual_errors:
        return 0.0
    e_mean = sum(individual_errors) / len(individual_errors)
    return e_mean - ensemble_error


def transcendence_margin(
    ensemble_score: float,
    best_individual_score: float,
) -> float:
    """Did the ensemble beat the best individual?

    For HIGHER-IS-BETTER metrics (accuracy, etc.):
        Positive = transcendence achieved.
        Zero = ensemble equals best individual.
        Negative = ensemble worse than best individual.

    For LOWER-IS-BETTER metrics (Brier score, error):
        Caller should pass negative values or use brier_transcendence_margin().
    """
    return ensemble_score - best_individual_score


def brier_transcendence_margin(
    ensemble_brier: float,
    best_individual_brier: float,
) -> float:
    """Transcendence margin for Brier scores (lower is better).

    Returns positive when ensemble outperforms best individual.
    """
    return best_individual_brier - ensemble_brier


def aggregation_lift(
    ensemble_score: float,
    mean_individual_score: float,
) -> float:
    """Did aggregation improve over the average individual?

    Easier bar than transcendence_margin. If this is negative,
    the aggregation mechanism is actively harmful.
    """
    return ensemble_score - mean_individual_score


def brier_aggregation_lift(
    ensemble_brier: float,
    mean_individual_brier: float,
) -> float:
    """Aggregation lift for Brier scores (lower is better).

    Returns positive when ensemble beats average individual.
    """
    return mean_individual_brier - ensemble_brier


def diversity_health(
    behavioral_div: float,
    error_decorr: float,
    kv_diversity: float,
) -> dict[str, float | str]:
    """Composite diversity health assessment.

    Returns a dict with scores and a status label.
    """
    # Weighted composite: behavioral diversity matters most
    composite = (
        0.4 * behavioral_div
        + 0.3 * error_decorr
        + 0.3 * min(max(kv_diversity, 0.0), 1.0)
    )

    if composite >= 0.5:
        status = "healthy"
    elif composite >= 0.25:
        status = "degraded"
    else:
        status = "critical"

    return {
        "behavioral_diversity": behavioral_div,
        "error_decorrelation": error_decorr,
        "kv_diversity_term": kv_diversity,
        "composite": round(composite, 4),
        "status": status,
    }
