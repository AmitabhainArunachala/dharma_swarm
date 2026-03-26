"""Canonical data contracts for the AutoGrade layer."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class GradeCard(BaseModel):
    task_id: str
    report_id: str
    groundedness: float
    citation_precision: float
    citation_coverage: float
    source_quality: float
    source_diversity: float
    topical_coverage: float
    contradiction_handling: float
    freshness: float
    structure: float
    actionability: float
    novelty: float
    traceability: float
    latency_ms: int = 0
    token_cost_usd: float = 0.0
    gate_failures: list[str] = Field(default_factory=list)
    final_score: float = 0.0
    promotion_state: str = "candidate"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "groundedness",
        "citation_precision",
        "citation_coverage",
        "source_quality",
        "source_diversity",
        "topical_coverage",
        "contradiction_handling",
        "freshness",
        "structure",
        "actionability",
        "novelty",
        "traceability",
        "final_score",
        mode="before",
    )
    @classmethod
    def _normalize_score(cls, value: float) -> float:
        return _clamp01(float(value))


class RewardSignal(BaseModel):
    task_id: str
    report_id: str
    grade_card: GradeCard
    scalar_reward: float
    gate_multiplier: float
    penalties: dict[str, float] = Field(default_factory=dict)
    attribution_ready: bool = True

    @field_validator("gate_multiplier", mode="before")
    @classmethod
    def _normalize_gate_multiplier(cls, value: float) -> float:
        return _clamp01(float(value))
