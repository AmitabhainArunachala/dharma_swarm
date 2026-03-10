"""Policy-backed provider routing for canonical DGC engine requests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from dharma_swarm.decision_router import DecisionInput, DecisionRouter, RoutePath
from dharma_swarm.models import ProviderType


def _dedupe_keep_order(items: Iterable[ProviderType]) -> list[ProviderType]:
    seen: set[ProviderType] = set()
    out: list[ProviderType] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


@dataclass(frozen=True)
class ProviderRouteRequest:
    action_name: str
    risk_score: float
    uncertainty: float
    novelty: float
    urgency: float
    expected_impact: float
    estimated_latency_ms: int = 800
    estimated_tokens: int = 1200
    preferred_low_cost: bool = True
    requires_frontier_precision: bool = False
    privileged_action: bool = False
    requires_human_consent: bool = False
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderRoutingConfig:
    reflex_candidates: tuple[ProviderType, ...] = (
        ProviderType.OPENROUTER_FREE,
        ProviderType.OPENROUTER,
        ProviderType.OPENAI,
        ProviderType.CODEX,
        ProviderType.ANTHROPIC,
        ProviderType.CLAUDE_CODE,
        ProviderType.NVIDIA_NIM,
        ProviderType.OLLAMA,
    )
    deliberative_candidates: tuple[ProviderType, ...] = (
        ProviderType.OPENAI,
        ProviderType.ANTHROPIC,
        ProviderType.OPENROUTER,
        ProviderType.CODEX,
        ProviderType.CLAUDE_CODE,
        ProviderType.NVIDIA_NIM,
        ProviderType.OPENROUTER_FREE,
        ProviderType.OLLAMA,
    )
    escalate_candidates: tuple[ProviderType, ...] = (
        ProviderType.ANTHROPIC,
        ProviderType.OPENAI,
        ProviderType.CLAUDE_CODE,
        ProviderType.CODEX,
        ProviderType.OPENROUTER,
        ProviderType.NVIDIA_NIM,
        ProviderType.OPENROUTER_FREE,
        ProviderType.OLLAMA,
    )
    tooling_candidates: tuple[ProviderType, ...] = (
        ProviderType.CODEX,
        ProviderType.CLAUDE_CODE,
    )
    low_cost_priority: tuple[ProviderType, ...] = (
        ProviderType.OPENROUTER_FREE,
        ProviderType.OPENROUTER,
        ProviderType.OPENAI,
        ProviderType.NVIDIA_NIM,
        ProviderType.OLLAMA,
        ProviderType.ANTHROPIC,
        ProviderType.CODEX,
        ProviderType.CLAUDE_CODE,
    )
    japanese_quality_priority: tuple[ProviderType, ...] = (
        ProviderType.OPENROUTER,
        ProviderType.ANTHROPIC,
        ProviderType.OPENAI,
        ProviderType.NVIDIA_NIM,
        ProviderType.CODEX,
        ProviderType.CLAUDE_CODE,
        ProviderType.OLLAMA,
        ProviderType.OPENROUTER_FREE,
    )
    reasoning_priority: tuple[ProviderType, ...] = (
        ProviderType.ANTHROPIC,
        ProviderType.OPENAI,
        ProviderType.CODEX,
        ProviderType.CLAUDE_CODE,
        ProviderType.OPENROUTER,
        ProviderType.NVIDIA_NIM,
        ProviderType.OLLAMA,
        ProviderType.OPENROUTER_FREE,
    )
    default_model_hints: dict[ProviderType, str] = field(
        default_factory=lambda: {
            ProviderType.ANTHROPIC: "claude-sonnet-4-6",
            ProviderType.OPENAI: "gpt-4o",
            ProviderType.OPENROUTER: "openai/gpt-5-codex",
            ProviderType.OPENROUTER_FREE: "meta-llama/llama-3.3-70b-instruct:free",
            ProviderType.NVIDIA_NIM: "meta/llama-3.3-70b-instruct",
            ProviderType.CLAUDE_CODE: "claude-code",
            ProviderType.CODEX: "codex",
            ProviderType.OLLAMA: "llama3.2",
        }
    )
    force_escalate_when_frontier_required: bool = True


@dataclass(frozen=True)
class ProviderRouteDecision:
    path: RoutePath
    selected_provider: ProviderType
    selected_model_hint: str | None
    fallback_providers: list[ProviderType]
    fallback_model_hints: list[str]
    confidence: float
    requires_human: bool
    reasons: list[str]


class ProviderPolicyRouter:
    """Route engine work to providers using canonical risk policy."""

    def __init__(
        self,
        *,
        config: ProviderRoutingConfig | None = None,
        decision_router: DecisionRouter | None = None,
    ) -> None:
        self.config = config or ProviderRoutingConfig()
        self.decision_router = decision_router or DecisionRouter()

    def route(
        self,
        request: ProviderRouteRequest,
        *,
        available_providers: list[ProviderType] | None = None,
    ) -> ProviderRouteDecision:
        decision = self.decision_router.route(
            DecisionInput(
                action_name=request.action_name,
                risk_score=request.risk_score,
                uncertainty=request.uncertainty,
                novelty=request.novelty,
                urgency=request.urgency,
                expected_impact=request.expected_impact,
                estimated_latency_ms=request.estimated_latency_ms,
                estimated_tokens=request.estimated_tokens,
                privileged_action=request.privileged_action,
                requires_human_consent=request.requires_human_consent,
                context=request.context,
            )
        )

        path = decision.path
        reasons = list(decision.reasons)
        if (
            request.requires_frontier_precision
            and self.config.force_escalate_when_frontier_required
            and path != RoutePath.ESCALATE
        ):
            path = RoutePath.ESCALATE
            reasons.append("frontier_precision_requested")

        candidates = self._candidate_providers(
            path=path,
            prefer_low_cost=request.preferred_low_cost,
            context=request.context,
        )
        available = _dedupe_keep_order(available_providers or [])
        if available:
            filtered = [item for item in candidates if item in available]
            if not filtered:
                filtered = available
        else:
            filtered = candidates

        selected = filtered[0] if filtered else ProviderType.CLAUDE_CODE
        fallbacks = [item for item in filtered[1:] if item != selected]
        return ProviderRouteDecision(
            path=path,
            selected_provider=selected,
            selected_model_hint=self.config.default_model_hints.get(selected),
            fallback_providers=fallbacks,
            fallback_model_hints=[
                self.config.default_model_hints[item]
                for item in fallbacks
                if item in self.config.default_model_hints
            ],
            confidence=decision.confidence,
            requires_human=decision.requires_human,
            reasons=reasons,
        )

    def plan_swarm(
        self,
        request: ProviderRouteRequest,
        *,
        available_providers: list[ProviderType] | None = None,
    ) -> "SwarmExecutionPlan":
        from dharma_swarm.swarm_router import SwarmRouter

        router = SwarmRouter(
            provider_policy=self,
            decision_router=self.decision_router,
        )
        return router.plan(
            request,
            available_providers=available_providers,
        )

    def _candidate_providers(
        self,
        *,
        path: RoutePath,
        prefer_low_cost: bool,
        context: dict[str, Any],
    ) -> list[ProviderType]:
        requires_tooling = bool(context.get("requires_tooling"))
        prefer_japanese_quality = bool(context.get("prefer_japanese_quality"))
        complexity_tier = str(context.get("complexity_tier", "")).upper()
        if path == RoutePath.REFLEX:
            candidates = list(self.config.reflex_candidates)
        elif path == RoutePath.ESCALATE:
            candidates = list(self.config.escalate_candidates)
        else:
            candidates = list(self.config.deliberative_candidates)

        if requires_tooling:
            candidates = list(self.config.tooling_candidates) + candidates

        if prefer_japanese_quality:
            priority = {
                provider: idx
                for idx, provider in enumerate(self.config.japanese_quality_priority)
            }
            candidates.sort(key=lambda provider: priority.get(provider, len(priority)))

        if complexity_tier in {"COMPLEX", "REASONING"}:
            priority = {
                provider: idx
                for idx, provider in enumerate(self.config.reasoning_priority)
            }
            candidates.sort(key=lambda provider: priority.get(provider, len(priority)))

        if prefer_low_cost and path != RoutePath.ESCALATE:
            priority = {
                provider: idx for idx, provider in enumerate(self.config.low_cost_priority)
            }
            candidates.sort(key=lambda provider: priority.get(provider, len(priority)))

        if requires_tooling:
            tooling = [
                provider for provider in self.config.tooling_candidates
                if provider in candidates
            ]
            non_tooling = [provider for provider in candidates if provider not in tooling]
            candidates = tooling + non_tooling

        return _dedupe_keep_order(candidates)
