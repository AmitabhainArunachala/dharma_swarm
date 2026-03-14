"""Typed decision ontology and deterministic decision-quality scoring.

This module models decisions as first-class objects with evidence, objections,
reviews, and outcome metrics. The scoring is intentionally deterministic and
artifact-backed so DGC can judge decision quality using structure, grounding,
and traceability instead of prose style alone.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.decision_router import DecisionInput
from dharma_swarm.steelman_gate import SteelmanCheck, check_steelman


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return _clamp01(numerator / denominator)


class DecisionState(str, Enum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    EXECUTING = "executing"
    OBSERVED = "observed"
    CLOSED = "closed"


class EvidenceKind(str, Enum):
    PRIMARY_SOURCE = "primary_source"
    REPO_FACT = "repo_fact"
    TEST = "test"
    BENCHMARK = "benchmark"
    RUNTIME = "runtime"
    USER_CONSTRAINT = "user_constraint"
    MODEL_OUTPUT = "model_output"


class ChallengeSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewVerdict(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class DecisionQualityVerdict(str, Enum):
    FRAGILE = "fragile"
    DEFENSIBLE = "defensible"
    AUDIT_READY = "audit_ready"


class DecisionContext(BaseModel):
    mission: str
    owner: str
    time_horizon: str = ""
    domains: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risk_score: float = Field(default=0.5, ge=0.0, le=1.0)
    uncertainty: float = Field(default=0.5, ge=0.0, le=1.0)
    novelty: float = Field(default=0.3, ge=0.0, le=1.0)
    urgency: float = Field(default=0.5, ge=0.0, le=1.0)
    expected_impact: float = Field(default=0.5, ge=0.0, le=1.0)
    reversible: bool = True


class DecisionOption(BaseModel):
    option_id: str = Field(default_factory=_new_id)
    title: str
    description: str = ""
    selected: bool = False
    tradeoffs: list[str] = Field(default_factory=list)


class DecisionClaim(BaseModel):
    claim_id: str = Field(default_factory=_new_id)
    text: str
    supports_option_id: str = ""
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class DecisionEvidence(BaseModel):
    evidence_id: str = Field(default_factory=_new_id)
    kind: EvidenceKind
    summary: str
    source_uri: str = ""
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    verified: bool = False
    provenance_refs: list[str] = Field(default_factory=list)


class DecisionChallenge(BaseModel):
    challenge_id: str = Field(default_factory=_new_id)
    summary: str
    severity: ChallengeSeverity = ChallengeSeverity.MEDIUM
    source_agent: str = ""
    addressed: bool = False
    response: str = ""


class DecisionMetric(BaseModel):
    name: str
    baseline: str = ""
    target: str = ""
    measurement_plan: str = ""
    owner: str = ""


class DecisionReview(BaseModel):
    reviewer: str
    role: str = ""
    verdict: ReviewVerdict = ReviewVerdict.WARN
    notes: str = ""


class DecisionQualityAssessment(BaseModel):
    decision_id: str
    overall_score: float
    structural_score: float
    evidence_score: float
    challenge_score: float
    traceability_score: float
    observability_score: float
    verdict: DecisionQualityVerdict
    hard_failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    summary: str = ""


class DecisionRecord(BaseModel):
    decision_id: str = Field(default_factory=_new_id)
    title: str
    statement: str
    state: DecisionState = DecisionState.DRAFT
    context: DecisionContext
    options: list[DecisionOption] = Field(default_factory=list)
    claims: list[DecisionClaim] = Field(default_factory=list)
    evidence: list[DecisionEvidence] = Field(default_factory=list)
    challenges: list[DecisionChallenge] = Field(default_factory=list)
    metrics: list[DecisionMetric] = Field(default_factory=list)
    reviews: list[DecisionReview] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    kill_criteria: list[str] = Field(default_factory=list)
    provenance_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: _utc_now().isoformat())

    def selected_option(self) -> DecisionOption | None:
        for option in self.options:
            if option.selected:
                return option
        return None

    def evaluate_quality(self) -> DecisionQualityAssessment:
        return evaluate_decision_quality(self)

    def to_decision_input(
        self,
        *,
        assessment: DecisionQualityAssessment | None = None,
    ) -> DecisionInput:
        quality = assessment or self.evaluate_quality()
        complexity_signals = [
            _clamp01(len(self.options) / 3.0),
            _clamp01(len(self.claims) / 4.0),
            _clamp01(len(self.challenges) / 3.0),
            _clamp01(len(self.context.domains) / 3.0),
            self.context.expected_impact,
        ]
        complexity_score = sum(complexity_signals) / len(complexity_signals)
        requires_human = bool(quality.hard_failures) and self.context.expected_impact >= 0.7

        return DecisionInput(
            action_name=self.title,
            risk_score=self.context.risk_score,
            uncertainty=max(self.context.uncertainty, 1.0 - quality.evidence_score),
            novelty=self.context.novelty,
            urgency=self.context.urgency,
            expected_impact=self.context.expected_impact,
            explicit_confidence=quality.overall_score,
            requires_human_consent=requires_human,
            privileged_action=(not self.context.reversible and self.context.expected_impact >= 0.7),
            context={
                "complexity_score": round(complexity_score, 4),
                "reasoning_markers": min(3, len(self.claims) + len(self.challenges)),
                "broad_domain": len(self.context.domains) >= 2,
                "requires_verification": quality.verdict != DecisionQualityVerdict.AUDIT_READY,
                "has_multi_step": len(self.next_actions) >= 2,
                "domain_count": len(self.context.domains),
                "deliverable_count": len(self.metrics) + len(self.next_actions),
                "parallelizable_subtasks": len(self.next_actions) >= 2,
                "decision_quality_score": round(quality.overall_score, 4),
                "decision_quality_verdict": quality.verdict.value,
                "decision_hard_failure_count": len(quality.hard_failures),
            },
        )


def evaluate_decision_quality(record: DecisionRecord) -> DecisionQualityAssessment:
    hard_failures: list[str] = []
    warnings: list[str] = []

    selected_option = record.selected_option()
    if len(record.options) < 2:
        hard_failures.append("fewer_than_two_options")
    if selected_option is None:
        hard_failures.append("no_selected_option")
    if not record.evidence:
        hard_failures.append("no_evidence")
    if not record.metrics:
        hard_failures.append("no_metrics")

    structural_score = _score_structure(record)
    evidence_score = _score_evidence(record)
    challenge_score, challenge_hard_failures, challenge_warnings = _score_challenges(record)
    traceability_score, trace_hard_failures, trace_warnings = _score_traceability(
        record,
        selected_option_id=selected_option.option_id if selected_option else "",
    )
    observability_score, observability_warnings = _score_observability(record)

    hard_failures.extend(challenge_hard_failures)
    hard_failures.extend(trace_hard_failures)
    warnings.extend(challenge_warnings)
    warnings.extend(trace_warnings)
    warnings.extend(observability_warnings)

    if not any(
        evidence.kind in {
            EvidenceKind.PRIMARY_SOURCE,
            EvidenceKind.REPO_FACT,
            EvidenceKind.TEST,
            EvidenceKind.BENCHMARK,
            EvidenceKind.RUNTIME,
            EvidenceKind.USER_CONSTRAINT,
        }
        for evidence in record.evidence
    ):
        warnings.append("no_grounded_evidence_kind")

    if not record.reviews:
        warnings.append("no_reviews")

    overall_score = _clamp01(
        (0.22 * structural_score)
        + (0.26 * evidence_score)
        + (0.18 * challenge_score)
        + (0.18 * traceability_score)
        + (0.16 * observability_score)
    )

    if hard_failures or overall_score < 0.55:
        verdict = DecisionQualityVerdict.FRAGILE
    elif overall_score >= 0.85 and not warnings:
        verdict = DecisionQualityVerdict.AUDIT_READY
    else:
        verdict = DecisionQualityVerdict.DEFENSIBLE

    summary = (
        f"{verdict.value}: score={overall_score:.2f} "
        f"(structure={structural_score:.2f}, evidence={evidence_score:.2f}, "
        f"challenge={challenge_score:.2f}, traceability={traceability_score:.2f}, "
        f"observability={observability_score:.2f})"
    )
    return DecisionQualityAssessment(
        decision_id=record.decision_id,
        overall_score=round(overall_score, 4),
        structural_score=round(structural_score, 4),
        evidence_score=round(evidence_score, 4),
        challenge_score=round(challenge_score, 4),
        traceability_score=round(traceability_score, 4),
        observability_score=round(observability_score, 4),
        verdict=verdict,
        hard_failures=sorted(set(hard_failures)),
        warnings=sorted(set(warnings)),
        summary=summary,
    )


def _score_structure(record: DecisionRecord) -> float:
    checks = [
        bool(record.title.strip()),
        bool(record.statement.strip()),
        bool(record.context.mission.strip()),
        bool(record.context.owner.strip()),
        bool(record.context.time_horizon.strip()),
        len(record.options) >= 2,
        record.selected_option() is not None,
        bool(record.context.constraints or record.context.assumptions),
    ]
    return _ratio(sum(1 for item in checks if item), len(checks))


def _score_evidence(record: DecisionRecord) -> float:
    if not record.evidence:
        return 0.0
    count_score = _clamp01(len(record.evidence) / 4.0)
    diversity_score = _clamp01(len({item.kind for item in record.evidence}) / 4.0)
    mean_confidence = sum(item.confidence for item in record.evidence) / len(record.evidence)
    verified_ratio = _ratio(sum(1 for item in record.evidence if item.verified), len(record.evidence))
    grounded_ratio = _ratio(
        sum(
            1
            for item in record.evidence
            if item.kind
            in {
                EvidenceKind.PRIMARY_SOURCE,
                EvidenceKind.REPO_FACT,
                EvidenceKind.TEST,
                EvidenceKind.BENCHMARK,
                EvidenceKind.RUNTIME,
                EvidenceKind.USER_CONSTRAINT,
            }
        ),
        len(record.evidence),
    )
    score = (
        0.25 * count_score
        + 0.20 * diversity_score
        + 0.25 * mean_confidence
        + 0.15 * verified_ratio
        + 0.15 * grounded_ratio
    )
    return _clamp01(score)


def _score_challenges(record: DecisionRecord) -> tuple[float, list[str], list[str]]:
    if not record.challenges:
        return 0.0, ["no_counterarguments"], []

    steelman = check_steelman(
        SteelmanCheck(counterarguments=[item.summary for item in record.challenges])
    )
    substantive_score = _clamp01(steelman.substantive_counterarguments / 2.0)
    addressed_ratio = _ratio(sum(1 for item in record.challenges if item.addressed), len(record.challenges))
    unresolved_severe = sum(
        1
        for item in record.challenges
        if not item.addressed and item.severity in {ChallengeSeverity.HIGH, ChallengeSeverity.CRITICAL}
    )
    severity_penalty = 0.2 if unresolved_severe else 0.0
    gate_score = {
        "PASS": 1.0,
        "WARN": 0.45,
        "FAIL": 0.0,
    }[steelman.gate_result.value]
    score = _clamp01((0.40 * gate_score) + (0.30 * substantive_score) + (0.30 * addressed_ratio) - severity_penalty)

    hard_failures: list[str] = []
    warnings: list[str] = []
    if steelman.gate_result.value == "FAIL":
        hard_failures.append("no_counterarguments")
    if unresolved_severe:
        warnings.append("unresolved_high_severity_counterargument")
    return score, hard_failures, warnings


def _score_traceability(
    record: DecisionRecord,
    *,
    selected_option_id: str,
) -> tuple[float, list[str], list[str]]:
    hard_failures: list[str] = []
    warnings: list[str] = []

    if not record.claims:
        hard_failures.append("no_claims")
        return 0.0, hard_failures, warnings

    claims_with_evidence = _ratio(
        sum(1 for item in record.claims if item.evidence_refs),
        len(record.claims),
    )
    evidence_with_provenance = _ratio(
        sum(1 for item in record.evidence if item.provenance_refs or item.source_uri),
        len(record.evidence),
    )
    option_supported = 0.0
    if selected_option_id:
        option_supported = _ratio(
            sum(
                1
                for item in record.claims
                if item.supports_option_id == selected_option_id and item.evidence_refs
            ),
            1,
        )
        if option_supported == 0.0:
            hard_failures.append("selected_option_has_no_supported_claim")
    review_coverage = _clamp01(len(record.reviews) / 2.0)
    review_quality = 0.0
    if record.reviews:
        verdict_scores = {
            ReviewVerdict.PASS: 1.0,
            ReviewVerdict.WARN: 0.5,
            ReviewVerdict.FAIL: 0.0,
        }
        review_quality = sum(verdict_scores[item.verdict] for item in record.reviews) / len(record.reviews)
        if any(item.verdict == ReviewVerdict.FAIL for item in record.reviews):
            warnings.append("failed_review_present")
        if not any(item.verdict == ReviewVerdict.PASS for item in record.reviews):
            warnings.append("no_passing_review")
    review_score = _clamp01((0.5 * review_coverage) + (0.5 * review_quality))
    if not record.provenance_refs:
        warnings.append("decision_missing_provenance_refs")

    score = _clamp01(
        (0.35 * claims_with_evidence)
        + (0.25 * evidence_with_provenance)
        + (0.25 * option_supported)
        + (0.15 * review_score)
    )
    return score, hard_failures, warnings


def _score_observability(record: DecisionRecord) -> tuple[float, list[str]]:
    warnings: list[str] = []
    if not record.metrics:
        return 0.0, warnings

    metric_count_score = _clamp01(len(record.metrics) / 2.0)
    complete_metrics = _ratio(
        sum(
            1
            for metric in record.metrics
            if metric.target.strip() and metric.measurement_plan.strip() and metric.owner.strip()
        ),
        len(record.metrics),
    )
    next_action_score = 1.0 if record.next_actions else 0.0
    kill_criteria_score = 1.0 if record.kill_criteria else 0.0
    if not record.kill_criteria:
        warnings.append("no_kill_criteria")
    if not record.next_actions:
        warnings.append("no_next_actions")
    score = _clamp01(
        (0.30 * metric_count_score)
        + (0.30 * complete_metrics)
        + (0.20 * next_action_score)
        + (0.20 * kill_criteria_score)
    )
    return score, warnings
