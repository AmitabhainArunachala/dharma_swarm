"""Router retrospectives and promotion drift guards for Darwin."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from dharma_swarm.archive import ArchiveEntry
from dharma_swarm.models import _new_id, _utc_now


ROUTER_POLICY_REVIEW_COMPONENT = "router_policy_review"
ROUTER_POLICY_REVIEW_SPEC_REF = "router_retrospective"


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class RouteOutcomeRecord(BaseModel):
    action_name: str
    route_path: str
    selected_provider: str
    selected_model: str | None = None
    confidence: float
    quality_score: float | None = None
    result: str = "success"
    task_signature: str | None = None
    latency_ms: float = 0.0
    total_tokens: int = 0
    reasons: list[str] = Field(default_factory=list)
    signals: dict[str, Any] = Field(default_factory=dict)
    failures: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("confidence", mode="before")
    @classmethod
    def _validate_confidence(cls, value: float) -> float:
        return _clamp01(value)

    @field_validator("quality_score", mode="before")
    @classmethod
    def _validate_quality(cls, value: float | None) -> float | None:
        if value is None:
            return None
        return _clamp01(value)

    @property
    def effective_quality(self) -> float:
        if self.quality_score is not None:
            return self.quality_score
        return 1.0 if self.result == "success" else 0.0


class RoutePolicyArchiveEntry(BaseModel):
    artifact_id: str
    target_component: str = ROUTER_POLICY_REVIEW_COMPONENT
    change_summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    proposed_constraints: list[str] = Field(
        default_factory=lambda: [
            "shadow_test_before_promotion",
            "goal_drift_index<0.44",
            "constraint_preservation>=0.987",
            "preserve_provider_runtime_contracts",
        ]
    )
    shadow_mode_required: bool = True
    promotion_state: str = "candidate"


class RouteRetrospectiveArtifact(BaseModel):
    id: str = Field(default_factory=_new_id)
    created_at: datetime = Field(default_factory=_utc_now)
    severity: str
    review_required: bool = True
    hypothesis: str
    recommended_actions: list[str] = Field(default_factory=list)
    route_record: RouteOutcomeRecord
    policy_archive_entry: RoutePolicyArchiveEntry
    darwin_archive_entry_id: str | None = None


class DriftGuardThresholds(BaseModel):
    goal_drift_index_critical: float = 0.44
    constraint_preservation_floor: float = 0.987


class DriftGuardDecision(BaseModel):
    allow_promotion: bool
    goal_drift_index: float
    constraint_preservation: float
    thresholds: DriftGuardThresholds = Field(default_factory=DriftGuardThresholds)
    reasons: list[str] = Field(default_factory=list)


def build_route_retrospective(
    record: RouteOutcomeRecord,
    *,
    high_confidence_floor: float = 0.80,
    low_quality_floor: float = 0.70,
) -> RouteRetrospectiveArtifact | None:
    quality = record.effective_quality
    if record.confidence < high_confidence_floor:
        return None
    if quality >= low_quality_floor:
        return None

    actions: list[str] = []
    complexity_tier = str(record.signals.get("complexity_tier", "")).upper()
    language_code = str(record.signals.get("language_code", "")).lower()
    if record.route_path == "reflex" and complexity_tier in {"COMPLEX", "REASONING"}:
        actions.append(
            "Raise the reflex-to-deliberative threshold for similar high-complexity requests."
        )
    if record.failures:
        actions.append(
            "Replay the task in shadow mode with a stronger fallback lane before promotion."
        )
    if language_code in {"ja", "en_ja_mixed", "cjk"}:
        actions.append(
            "Bias similar multilingual requests toward language-specialized providers."
        )
    if not actions:
        actions.append(
            "Shadow-test a routing rule adjustment before any production promotion."
        )

    hypothesis = (
        f"Route {record.route_path} underperformed at confidence={record.confidence:.2f} "
        f"with quality={quality:.2f}; similar requests need a stronger lane or tighter gate."
    )
    severity = "critical" if quality < 0.40 or record.result != "success" else "review"
    artifact_id = _new_id()
    policy_entry = RoutePolicyArchiveEntry(
        artifact_id=artifact_id,
        change_summary=(
            f"Review routing policy for {record.action_name} "
            f"({record.selected_provider}/{record.selected_model or 'default'})"
        ),
        evidence={
            "route_path": record.route_path,
            "selected_provider": record.selected_provider,
            "selected_model": record.selected_model,
            "confidence": record.confidence,
            "quality_score": quality,
            "signals": dict(record.signals),
            "reasons": list(record.reasons),
            "failures": list(record.failures),
        },
    )
    return RouteRetrospectiveArtifact(
        id=artifact_id,
        severity=severity,
        hypothesis=hypothesis,
        recommended_actions=actions,
        route_record=record,
        policy_archive_entry=policy_entry,
    )


def build_route_policy_archive_entry(
    artifact: RouteRetrospectiveArtifact,
) -> ArchiveEntry:
    """Project a retrospective artifact into Darwin's append-only archive."""
    evidence = {
        "review_required": artifact.review_required,
        "severity": artifact.severity,
        "hypothesis": artifact.hypothesis,
        "recommended_actions": list(artifact.recommended_actions),
        "route_record": artifact.route_record.model_dump(mode="json"),
        "policy_archive_entry": artifact.policy_archive_entry.model_dump(mode="json"),
    }
    return ArchiveEntry(
        id=artifact.policy_archive_entry.artifact_id,
        component=artifact.policy_archive_entry.target_component,
        change_type="route_retrospective",
        description=artifact.policy_archive_entry.change_summary,
        spec_ref=ROUTER_POLICY_REVIEW_SPEC_REF,
        requirement_refs=list(artifact.policy_archive_entry.proposed_constraints),
        status=artifact.policy_archive_entry.promotion_state,
        test_results=evidence,
        gates_passed=["RETROSPECTIVE_AUDIT"],
    )


def evaluate_router_drift(
    *,
    goal_drift_index: float,
    constraint_preservation: float,
    thresholds: DriftGuardThresholds | None = None,
) -> DriftGuardDecision:
    active_thresholds = thresholds or DriftGuardThresholds()
    gdi = _clamp01(goal_drift_index)
    preserved = _clamp01(constraint_preservation)
    reasons: list[str] = []

    if gdi >= active_thresholds.goal_drift_index_critical:
        reasons.append(
            f"goal_drift_index>={active_thresholds.goal_drift_index_critical}"
        )
    if preserved < active_thresholds.constraint_preservation_floor:
        reasons.append(
            "constraint_preservation"
            f"<{active_thresholds.constraint_preservation_floor}"
        )

    return DriftGuardDecision(
        allow_promotion=not reasons,
        goal_drift_index=gdi,
        constraint_preservation=preserved,
        thresholds=active_thresholds,
        reasons=reasons or ["promotion_safe"],
    )
