"""Efficiency penalty helpers for AutoGrade."""

from __future__ import annotations


def bounded_efficiency_penalty(
    *,
    token_cost_usd: float,
    latency_ms: int,
    total_tokens: int,
    cost_budget_usd: float,
    latency_budget_ms: int,
    token_budget: int,
) -> tuple[float, dict[str, float]]:
    cost_norm = min(float(token_cost_usd) / max(float(cost_budget_usd), 1e-9), 1.0)
    latency_norm = min(float(latency_ms) / max(float(latency_budget_ms), 1.0), 1.0)
    token_norm = min(float(total_tokens) / max(float(token_budget), 1.0), 1.0)
    penalties = {
        "cost_norm": cost_norm,
        "latency_norm": latency_norm,
        "token_norm": token_norm,
    }
    total = (0.05 * cost_norm) + (0.04 * latency_norm) + (0.03 * token_norm)
    return total, penalties
