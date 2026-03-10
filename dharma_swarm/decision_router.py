"""Decision router for reflex vs deliberative vs escalation paths."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


class RoutePath(str, Enum):
    REFLEX = "reflex"
    DELIBERATIVE = "deliberative"
    ESCALATE = "escalate"


class CollaborationMode(str, Enum):
    SINGLE_AGENT = "single_agent"
    MULTI_AGENT = "multi_agent"


@dataclass(frozen=True)
class DecisionInput:
    action_name: str
    risk_score: float
    uncertainty: float
    novelty: float
    urgency: float
    expected_impact: float
    estimated_latency_ms: int = 250
    estimated_tokens: int = 300
    explicit_confidence: float | None = None
    requires_human_consent: bool = False
    privileged_action: bool = False
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RouterConfig:
    reflex_max_risk: float = 0.25
    reflex_max_uncertainty: float = 0.30
    reflex_min_confidence: float = 0.74
    reflex_max_latency_ms: int = 800
    reflex_max_tokens: int = 800

    escalate_min_risk: float = 0.85
    escalate_min_uncertainty: float = 0.80
    escalate_min_impact: float = 0.90
    force_escalate_privileged_without_consent: bool = True

    weight_risk: float = 0.45
    weight_uncertainty: float = 0.35
    weight_novelty: float = 0.20
    urgency_bonus_weight: float = 0.08
    multi_agent_min_score: float = 0.58
    multi_agent_min_complexity: float = 0.42
    multi_agent_min_parallel_signals: int = 1


@dataclass(frozen=True)
class CollaborationDecision:
    mode: CollaborationMode
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class RouteDecision:
    path: RoutePath
    confidence: float
    reasons: list[str]
    requires_human: bool
    safety_flags: list[str]


class DecisionRouter:
    def __init__(self, config: RouterConfig | None = None):
        self.config = config or RouterConfig()

    def calibrate_confidence(self, item: DecisionInput) -> float:
        if item.explicit_confidence is not None:
            return _clamp01(item.explicit_confidence)

        c = self.config
        penalty = (
            c.weight_risk * _clamp01(item.risk_score)
            + c.weight_uncertainty * _clamp01(item.uncertainty)
            + c.weight_novelty * _clamp01(item.novelty)
        )
        urgency_bonus = c.urgency_bonus_weight * _clamp01(item.urgency)
        base = 1.0 - penalty + urgency_bonus
        return _clamp01(base)

    def route(self, item: DecisionInput) -> RouteDecision:
        c = self.config
        reasons: list[str] = []
        safety_flags: list[str] = []

        risk = _clamp01(item.risk_score)
        uncertainty = _clamp01(item.uncertainty)
        impact = _clamp01(item.expected_impact)
        confidence = self.calibrate_confidence(item)

        if item.requires_human_consent:
            reasons.append("requires_human_consent=true")
        if item.privileged_action:
            safety_flags.append("privileged_action")

        if (
            c.force_escalate_privileged_without_consent
            and item.privileged_action
            and not item.requires_human_consent
        ):
            reasons.append("privileged_without_consent")
            return RouteDecision(
                path=RoutePath.ESCALATE,
                confidence=confidence,
                reasons=reasons,
                requires_human=True,
                safety_flags=safety_flags,
            )

        if risk >= c.escalate_min_risk:
            reasons.append(f"risk>={c.escalate_min_risk}")
            return RouteDecision(
                path=RoutePath.ESCALATE,
                confidence=confidence,
                reasons=reasons,
                requires_human=True,
                safety_flags=safety_flags,
            )
        if uncertainty >= c.escalate_min_uncertainty:
            reasons.append(f"uncertainty>={c.escalate_min_uncertainty}")
            return RouteDecision(
                path=RoutePath.ESCALATE,
                confidence=confidence,
                reasons=reasons,
                requires_human=True,
                safety_flags=safety_flags,
            )
        if impact >= c.escalate_min_impact and confidence < c.reflex_min_confidence:
            reasons.append("high_impact_low_confidence")
            return RouteDecision(
                path=RoutePath.ESCALATE,
                confidence=confidence,
                reasons=reasons,
                requires_human=True,
                safety_flags=safety_flags,
            )

        if (
            risk <= c.reflex_max_risk
            and uncertainty <= c.reflex_max_uncertainty
            and confidence >= c.reflex_min_confidence
            and item.estimated_latency_ms <= c.reflex_max_latency_ms
            and item.estimated_tokens <= c.reflex_max_tokens
            and not item.requires_human_consent
        ):
            reasons.append("low_risk_low_uncertainty")
            reasons.append("within_reflex_budget")
            return RouteDecision(
                path=RoutePath.REFLEX,
                confidence=confidence,
                reasons=reasons,
                requires_human=False,
                safety_flags=safety_flags,
            )

        reasons.append("default_to_deliberative")
        return RouteDecision(
            path=RoutePath.DELIBERATIVE,
            confidence=confidence,
            reasons=reasons,
            requires_human=False,
            safety_flags=safety_flags,
        )

    def collaboration_score(self, item: DecisionInput) -> tuple[float, list[str]]:
        ctx = item.context or {}
        reasons: list[str] = []

        complexity = _clamp01(float(ctx.get("complexity_score", 0.0) or 0.0))
        uncertainty = _clamp01(item.uncertainty)
        novelty = _clamp01(item.novelty)
        impact = _clamp01(item.expected_impact)
        reasoning_markers = int(ctx.get("reasoning_markers", 0) or 0)
        broad_domain = bool(ctx.get("broad_domain"))
        requires_verification = bool(ctx.get("requires_verification"))
        has_multi_step = bool(ctx.get("has_multi_step"))
        context_tier = str(ctx.get("context_tier", "")).upper()
        domain_count = max(0, int(ctx.get("domain_count", 0) or 0))
        deliverable_count = max(0, int(ctx.get("deliverable_count", 0) or 0))
        parallelizable_subtasks = bool(ctx.get("parallelizable_subtasks"))

        score = (
            0.40 * complexity
            + 0.22 * uncertainty
            + 0.16 * novelty
            + 0.10 * impact
        )

        if reasoning_markers >= 2:
            score += 0.10
            reasons.append("reasoning_markers>=2")
        if broad_domain:
            score += 0.18
            reasons.append("broad_domain")
        if requires_verification or item.privileged_action or item.requires_human_consent:
            score += 0.16
            reasons.append("verification_needed")
        if has_multi_step:
            score += 0.08
            reasons.append("multi_step_plan")
        if context_tier in {"LONG", "VERY_LONG"}:
            score += 0.10
            reasons.append(f"context_tier={context_tier.lower()}")
        if parallelizable_subtasks:
            score += 0.10
            reasons.append("parallelizable_subtasks")
        if domain_count >= 2:
            score += 0.06
            reasons.append("domain_count>=2")
        if deliverable_count >= 2:
            score += 0.04
            reasons.append("deliverable_count>=2")

        return (_clamp01(score), reasons)

    def route_collaboration(self, item: DecisionInput) -> CollaborationDecision:
        ctx = item.context or {}
        if bool(ctx.get("force_single_agent")):
            return CollaborationDecision(
                mode=CollaborationMode.SINGLE_AGENT,
                score=0.0,
                reasons=["force_single_agent"],
            )
        if bool(ctx.get("force_multi_agent")) or bool(ctx.get("requires_multi_agent")):
            return CollaborationDecision(
                mode=CollaborationMode.MULTI_AGENT,
                score=1.0,
                reasons=["force_multi_agent"],
            )

        score, reasons = self.collaboration_score(item)
        complexity = _clamp01(float(ctx.get("complexity_score", 0.0) or 0.0))
        broad_domain = bool(ctx.get("broad_domain"))
        requires_verification = (
            bool(ctx.get("requires_verification"))
            or item.privileged_action
            or item.requires_human_consent
        )
        has_multi_step = bool(ctx.get("has_multi_step"))
        domain_count = max(0, int(ctx.get("domain_count", 0) or 0))
        deliverable_count = max(0, int(ctx.get("deliverable_count", 0) or 0))
        parallelizable_subtasks = (
            bool(ctx.get("parallelizable_subtasks"))
            or domain_count >= 2
            or deliverable_count >= 2
        )
        sequential_reasoning_only = bool(ctx.get("sequential_reasoning_only"))
        risk = _clamp01(item.risk_score)
        uncertainty = _clamp01(item.uncertainty)
        collaboration_positive_signals = int(broad_domain) + int(requires_verification)
        collaboration_positive_signals += int(has_multi_step) + int(
            parallelizable_subtasks
        )

        if (
            risk <= self.config.reflex_max_risk
            and uncertainty <= self.config.reflex_max_uncertainty
            and complexity < self.config.multi_agent_min_complexity
            and not broad_domain
            and not requires_verification
            and not has_multi_step
        ):
            return CollaborationDecision(
                mode=CollaborationMode.SINGLE_AGENT,
                score=score,
                reasons=["simple_request_single_agent", *reasons],
            )

        if sequential_reasoning_only and collaboration_positive_signals == 0:
            return CollaborationDecision(
                mode=CollaborationMode.SINGLE_AGENT,
                score=score,
                reasons=[
                    *reasons,
                    "sequential_reasoning_prefers_single_agent",
                ],
            )

        if (
            score >= self.config.multi_agent_min_score
            and collaboration_positive_signals
            >= self.config.multi_agent_min_parallel_signals
        ):
            return CollaborationDecision(
                mode=CollaborationMode.MULTI_AGENT,
                score=score,
                reasons=[
                    *reasons,
                    f"collaboration_score>={self.config.multi_agent_min_score}",
                ],
            )

        if (
            score >= self.config.multi_agent_min_score
            and collaboration_positive_signals
            < self.config.multi_agent_min_parallel_signals
        ):
            reasons = [
                *reasons,
                "insufficient_collaboration_gain_signals",
            ]

        return CollaborationDecision(
            mode=CollaborationMode.SINGLE_AGENT,
            score=score,
            reasons=reasons or ["single_agent_default"],
        )
