"""Rubric constants and score composition for AutoGrade."""

from __future__ import annotations


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def core_score(metrics: dict[str, float]) -> float:
    return clamp01(
        0.20 * metrics["groundedness"]
        + 0.14 * metrics["citation_precision"]
        + 0.10 * metrics["citation_coverage"]
        + 0.10 * metrics["source_quality"]
        + 0.08 * metrics["source_diversity"]
        + 0.10 * metrics["topical_coverage"]
        + 0.08 * metrics["contradiction_handling"]
        + 0.06 * metrics["freshness"]
        + 0.05 * metrics["structure"]
        + 0.04 * metrics["actionability"]
        + 0.03 * metrics["novelty"]
        + 0.02 * metrics["traceability"]
    )


def promotion_state(final_score: float, gate_failures: list[str]) -> str:
    if gate_failures or final_score < 0.55:
        return "rollback_or_revise"
    if final_score >= 0.82:
        return "promotable"
    if final_score >= 0.72:
        return "candidate"
    return "archive_only"
