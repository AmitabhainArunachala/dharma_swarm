"""Transcendence aggregation — combining diverse agent outputs into ensembles.

Three aggregation protocols, selected by task type:

1. majority_vote — for discrete choices (classification, yes/no)
2. quality_weighted_average — for probabilities (predictions)
3. temperature_concentrate — Zhang's mechanism (softmax concentration)

All functions are pure: no state, no I/O, no LLM calls, fully testable.
The cascade_refine method (LLM-based synthesis) lives in Phase 2.
"""

from __future__ import annotations

import math
from typing import Sequence


def majority_vote(
    choices: Sequence[str],
    weights: Sequence[float] | None = None,
) -> tuple[str, float]:
    """Weighted majority vote over discrete choices.

    Args:
        choices: Each agent's discrete answer.
        weights: Quality weights per agent. Higher = more trusted.
                 If None, uniform weights (one-person-one-vote).

    Returns:
        (winning_choice, vote_share) where vote_share is in [0, 1].
    """
    if not choices:
        return ("", 0.0)

    if weights is None:
        weights = [1.0] * len(choices)

    # Accumulate weighted votes
    tallies: dict[str, float] = {}
    total_weight = 0.0
    for choice, weight in zip(choices, weights):
        w = max(weight, 0.0)
        tallies[choice] = tallies.get(choice, 0.0) + w
        total_weight += w

    if total_weight == 0.0:
        return (choices[0], 1.0 / len(choices))

    winner = max(tallies, key=tallies.__getitem__)
    share = tallies[winner] / total_weight
    return (winner, share)


def quality_weighted_average(
    probabilities: Sequence[float],
    quality_scores: Sequence[float] | None = None,
) -> float:
    """Quality-weighted average of probability estimates.

    For Ginko predictions: each agent provides a probability [0, 1].
    Agents with better historical Brier scores get more weight.

    Args:
        probabilities: Each agent's probability estimate.
        quality_scores: Higher = better quality. If using Brier scores
                       (lower is better), pass 1.0 - brier as quality.
                       If None, uniform weights.

    Returns:
        Weighted average probability in [0, 1].
    """
    if not probabilities:
        return 0.5

    if quality_scores is None:
        quality_scores = [1.0] * len(probabilities)

    total_weight = 0.0
    weighted_sum = 0.0
    for prob, quality in zip(probabilities, quality_scores):
        w = max(quality, 0.0)
        weighted_sum += prob * w
        total_weight += w

    if total_weight == 0.0:
        return sum(probabilities) / len(probabilities)

    result = weighted_sum / total_weight
    return max(0.0, min(1.0, result))


def temperature_concentrate(
    probabilities: Sequence[float],
    weights: Sequence[float] | None = None,
    temperature: float = 0.5,
) -> float:
    """Zhang's temperature concentration mechanism.

    First computes quality-weighted average, then concentrates
    toward extremes (0 or 1) based on temperature.

    Lower temperature = more concentration toward the majority direction.
    This is the direct analog of low-temperature sampling in Zhang et al.

    Args:
        probabilities: Each agent's probability estimate [0, 1].
        weights: Quality weights per agent.
        temperature: Concentration parameter. < 1.0 concentrates, > 1.0 disperses.
                    0.5 is a good default for moderate concentration.

    Returns:
        Concentrated probability in [0, 1].
    """
    if not probabilities:
        return 0.5

    # Step 1: quality-weighted average
    avg = quality_weighted_average(probabilities, weights)

    if temperature <= 0.0:
        # Zero temperature = argmax (hard decision)
        return 1.0 if avg >= 0.5 else 0.0

    if temperature >= 10.0:
        # Very high temperature = no concentration
        return avg

    # Step 2: concentrate via power transform
    # Map [0,1] probability through a sharpening function.
    # Using the Beta CDF-like sharpening: p^(1/t) / (p^(1/t) + (1-p)^(1/t))
    # This preserves 0.5 as a fixed point, pushes other values toward 0 or 1.
    eps = 1e-10
    p = max(eps, min(1.0 - eps, avg))
    inv_t = 1.0 / temperature

    p_sharp = p ** inv_t
    q_sharp = (1.0 - p) ** inv_t
    denom = p_sharp + q_sharp

    if denom == 0.0:
        return avg

    concentrated = p_sharp / denom
    return max(0.0, min(1.0, concentrated))


def softmax_select(
    scores: Sequence[float],
    temperature: float = 1.0,
) -> list[float]:
    """Softmax over quality scores to produce selection weights.

    Lower temperature = more weight on the highest-scoring agent.
    Used as input to other aggregation methods.

    Args:
        scores: Quality scores per agent (higher = better).
        temperature: Controls sharpness. 0.1 = nearly argmax.

    Returns:
        List of weights summing to 1.0.
    """
    if not scores:
        return []

    if temperature <= 0.0:
        # Argmax: all weight on the best
        best_idx = max(range(len(scores)), key=lambda i: scores[i])
        weights = [0.0] * len(scores)
        weights[best_idx] = 1.0
        return weights

    # Numerical stability: subtract max
    max_s = max(scores)
    exp_scores = [math.exp((s - max_s) / temperature) for s in scores]
    total = sum(exp_scores)

    if total == 0.0:
        return [1.0 / len(scores)] * len(scores)

    return [e / total for e in exp_scores]


def inverse_brier_weights(brier_scores: Sequence[float]) -> list[float]:
    """Convert Brier scores (lower = better) to quality weights (higher = better).

    Agents with lower Brier scores get higher weight in aggregation.

    Args:
        brier_scores: Per-agent Brier scores in [0, 1].

    Returns:
        Quality weights (not normalized — use with quality_weighted_average).
    """
    if not brier_scores:
        return []

    # Invert: quality = 1 - brier. A perfect predictor (brier=0) gets weight 1.
    # A random predictor (brier=0.25) gets weight 0.75.
    return [max(1.0 - b, 0.01) for b in brier_scores]
