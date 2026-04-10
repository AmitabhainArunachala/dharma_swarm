"""Policy-backed provider routing for canonical DGC engine requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
import time
from typing import Any, Iterable

from dharma_swarm.decision_router import DecisionInput, DecisionRouter, RoutePath
from dharma_swarm.model_hierarchy import (
    CANONICAL_SEED_ORDER,
    DELIBERATIVE_EXECUTION_PRIORITY,
    DELIBERATIVE_REASONING_PRIORITY,
    DEFAULT_MODELS,
    ESCALATION_PRIORITY,
    PRIMARY_TOOLING_PRIORITY,
    TIER_CHEAP,
    TIER_FREE,
    TIER_PAID,
    heuristic_score,
)
from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.smart_router import SmartRouter, SmartRouterConfig
from dharma_swarm.telemetry_optimizer import (
    ProviderOptimizationRecommendation,
    TelemetryOptimizer,
)
from dharma_swarm.telemetry_plane import TelemetryPlaneStore

_race_logger = logging.getLogger(__name__ + ".race")


def _dedupe_keep_order(items: Iterable[ProviderType]) -> list[ProviderType]:
    seen: set[ProviderType] = set()
    out: list[ProviderType] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _prefer_codex_for_tooling(items: list[ProviderType]) -> list[ProviderType]:
    """Promote CODEX to the front for tooling-heavy execution lanes."""
    if ProviderType.CODEX not in items:
        return items
    return [ProviderType.CODEX] + [item for item in items if item != ProviderType.CODEX]


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
    # All candidate lists source from model_hierarchy.CANONICAL_SEED_ORDER.
    # This is the ONLY place these tuples are defined.  Editing
    # model_hierarchy.py propagates everywhere.
    reflex_candidates: tuple[ProviderType, ...] = CANONICAL_SEED_ORDER
    deliberative_candidates: tuple[ProviderType, ...] = DELIBERATIVE_EXECUTION_PRIORITY
    escalate_candidates: tuple[ProviderType, ...] = ESCALATION_PRIORITY
    tooling_candidates: tuple[ProviderType, ...] = PRIMARY_TOOLING_PRIORITY
    low_cost_priority: tuple[ProviderType, ...] = (
        TIER_FREE + TIER_CHEAP + TIER_PAID
    )
    japanese_quality_priority: tuple[ProviderType, ...] = (
        ProviderType.OPENROUTER,
        ProviderType.OLLAMA,
        ProviderType.NVIDIA_NIM,
        ProviderType.SILICONFLOW,
        ProviderType.TOGETHER,
        ProviderType.FIREWORKS,
        ProviderType.ANTHROPIC,
        ProviderType.CLAUDE_CODE,
        ProviderType.CODEX,
        ProviderType.OPENAI,
        ProviderType.GROQ,
        ProviderType.OPENROUTER_FREE,
        ProviderType.GOOGLE_AI,
        ProviderType.MISTRAL,
        ProviderType.CHUTES,
        ProviderType.CEREBRAS,
        ProviderType.SAMBANOVA,
    )
    reasoning_priority: tuple[ProviderType, ...] = DELIBERATIVE_REASONING_PRIORITY
    default_model_hints: dict[ProviderType, str] = field(
        default_factory=lambda: dict(DEFAULT_MODELS)
    )
    telemetry_optimization_enabled: bool | None = None
    telemetry_db_path: str | Path | None = None
    telemetry_cache_ttl_seconds: float = 30.0
    telemetry_min_route_count: int = 2
    telemetry_path_bonus: float = 0.03
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
        smart_router: SmartRouter | None = None,
    ) -> None:
        self.config = config or ProviderRoutingConfig()
        self.decision_router = decision_router or DecisionRouter()
        self._smart_router = smart_router or self._build_smart_router()
        self._telemetry_enabled = self._resolve_telemetry_enabled()
        self._telemetry_cache: dict[ProviderType, ProviderOptimizationRecommendation] = {}
        self._telemetry_cache_loaded_at = 0.0
        self._telemetry_optimizer: TelemetryOptimizer | None = None
        if self._telemetry_enabled:
            telemetry_db_path = self._resolve_telemetry_db_path()
            telemetry = (
                TelemetryPlaneStore(Path(telemetry_db_path))
                if telemetry_db_path is not None
                else TelemetryPlaneStore()
            )
            self._telemetry_optimizer = TelemetryOptimizer(telemetry)

    @staticmethod
    def _build_smart_router() -> SmartRouter:
        enabled = os.environ.get("DGC_SMART_ROUTER_ENABLED", "").strip().lower()
        if enabled in {"0", "false", "no", "off"}:
            return SmartRouter(SmartRouterConfig(log_decisions=False))
        return SmartRouter()

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

        # SmartRouter cost-aware re-ranking: promotes cheaper providers for
        # simple tasks without overriding escalation, frontier, or tooling requests.
        requires_tooling = bool(request.context.get("requires_tooling"))
        if (
            self._smart_router is not None
            and path != RoutePath.ESCALATE
            and not request.requires_frontier_precision
            and not requires_tooling
            and request.preferred_low_cost
        ):
            task_text = str(request.context.get("last_user_message", request.action_name))
            smart_decision = self._smart_router.route(task_text, available=filtered)
            if smart_decision.selected_providers:
                filtered = self._smart_router.rerank_candidates(
                    filtered, smart_decision.cost_tier,
                )
                reasons.append(f"smart_router_tier={smart_decision.cost_tier.value}")

        filtered, telemetry_reasons = self._apply_telemetry_overlay(
            candidates=filtered,
            path=path,
            request=request,
        )
        reasons.extend(telemetry_reasons)

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

    def _resolve_telemetry_enabled(self) -> bool:
        if self.config.telemetry_optimization_enabled is not None:
            return bool(self.config.telemetry_optimization_enabled)
        raw = os.environ.get("DGC_ROUTER_TELEMETRY_ENABLE", "").strip().lower()
        if raw in {"1", "true", "yes", "on"}:
            return True
        if raw in {"0", "false", "no", "off"}:
            return False
        return self.config.telemetry_db_path is not None

    def _resolve_telemetry_db_path(self) -> str | Path | None:
        configured = self.config.telemetry_db_path
        if configured not in (None, ""):
            return configured
        raw = os.environ.get("DGC_ROUTER_TELEMETRY_DB", "").strip()
        return raw or None

    def _telemetry_recommendation_map(
        self,
    ) -> dict[ProviderType, ProviderOptimizationRecommendation]:
        if not self._telemetry_enabled or self._telemetry_optimizer is None:
            return {}

        ttl_seconds = max(0.0, float(self.config.telemetry_cache_ttl_seconds))
        now = time.monotonic()
        if (
            ttl_seconds > 0
            and self._telemetry_cache
            and now - self._telemetry_cache_loaded_at < ttl_seconds
        ):
            return self._telemetry_cache

        try:
            recommendations = self._telemetry_optimizer.provider_recommendations_sync(
                limit=len(tuple(ProviderType))
            )
        except Exception:
            self._telemetry_cache = {}
            self._telemetry_cache_loaded_at = now
            return {}

        minimum_routes = max(1, int(self.config.telemetry_min_route_count))
        mapped: dict[ProviderType, ProviderOptimizationRecommendation] = {}
        for item in recommendations:
            try:
                provider = ProviderType(item.provider)
            except ValueError:
                continue
            if item.route_count < minimum_routes:
                continue
            mapped[provider] = item

        self._telemetry_cache = mapped
        self._telemetry_cache_loaded_at = now
        return mapped

    def _apply_telemetry_overlay(
        self,
        *,
        candidates: list[ProviderType],
        path: RoutePath,
        request: ProviderRouteRequest,
    ) -> tuple[list[ProviderType], list[str]]:
        if not candidates:
            return (candidates, [])
        if path == RoutePath.ESCALATE or request.requires_frontier_precision:
            return (candidates, [])

        recommendations = self._telemetry_recommendation_map()
        if not recommendations:
            return (candidates, [])

        requires_tooling = bool(request.context.get("requires_tooling"))
        complexity_tier = str(request.context.get("complexity_tier", "")).upper()
        ranked_entries: list[
            tuple[int, int, float, int, ProviderType, ProviderOptimizationRecommendation | None]
        ] = []
        for index, provider in enumerate(candidates):
            recommendation = recommendations.get(provider)
            score = float(recommendation.optimization_score) if recommendation else 0.0
            if recommendation and recommendation.dominant_path == path.value:
                score += max(0.0, float(self.config.telemetry_path_bonus))
            if recommendation and request.preferred_low_cost and "cost_efficient" in recommendation.reasons:
                score += 0.01
            if (
                recommendation
                and complexity_tier in {"COMPLEX", "REASONING"}
                and recommendation.dominant_path
                in {RoutePath.DELIBERATIVE.value, RoutePath.ESCALATE.value}
            ):
                score += 0.01
            tooling_group = 0
            if requires_tooling and provider not in self.config.tooling_candidates:
                tooling_group = 1
            ranked_entries.append(
                (
                    tooling_group,
                    0 if recommendation is not None else 1,
                    -score if recommendation is not None else 0.0,
                    index,
                    provider,
                    recommendation,
                )
            )

        ranked_entries.sort()
        ranked = [entry[4] for entry in ranked_entries]
        if ranked == candidates:
            return (ranked, [])

        selected = ranked[0]
        recommendation = recommendations.get(selected)
        if recommendation is None:
            return (candidates, [])
        return (
            ranked,
            [
                "telemetry_optimization_applied",
                f"telemetry_preferred:{selected.value}",
                f"telemetry_score:{selected.value}:{recommendation.optimization_score:.3f}",
            ],
        )

    @property
    def smart_router(self) -> SmartRouter:
        """Expose the SmartRouter instance for direct access / stats."""
        return self._smart_router

    def smart_router_stats(self) -> str:
        """Return human-readable SmartRouter statistics."""
        return self._smart_router.stats_summary()

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
            candidates = _prefer_codex_for_tooling(tooling) + non_tooling

        return _dedupe_keep_order(candidates)


# ─── Parallel Racing ─────────────────────────────────────────────────────

class RaceError(Exception):
    """All providers in a race failed."""


async def race_providers(
    request: LLMRequest,
    providers: dict[ProviderType, Any],
    candidates: list[ProviderType],
    *,
    width: int = 3,
    timeout: float = 90.0,
    routing_memory: Any | None = None,
    task_signature: str = "*",
) -> tuple[LLMResponse, ProviderType]:
    """Fire top N providers in parallel, return first good response.

    Uses asyncio.wait(FIRST_COMPLETED).  Cancels losers on success.
    Records outcome to routing_memory EWMA if provided.

    Args:
        request: The LLM request to dispatch.
        providers: Map of ProviderType → instantiated provider objects.
        candidates: Ordered list of providers to try (EWMA-ranked).
        width: How many to fire simultaneously (default 3).
        timeout: Max seconds to wait for any response.
        routing_memory: Optional RoutingMemoryStore for EWMA feedback.
        task_signature: Routing bucket for EWMA recording.

    Returns:
        (response, winning_provider_type) tuple.

    Raises:
        RaceError: If all providers fail.
    """
    # Select top N candidates that have an available provider instance
    racers: list[ProviderType] = []
    for pt in candidates:
        if pt in providers and len(racers) < width:
            racers.append(pt)
    if not racers:
        raise RaceError("No providers available for racing")

    _race_logger.info(
        "Racing %d providers: %s",
        len(racers),
        [p.value for p in racers],
    )

    # Launch concurrent tasks
    task_map: dict[asyncio.Task, ProviderType] = {}
    start_time = time.monotonic()
    for pt in racers:
        provider = providers[pt]
        task = asyncio.create_task(provider.complete(request))
        task_map[task] = pt

    errors: dict[ProviderType, str] = {}

    while task_map:
        remaining_timeout = max(0.1, timeout - (time.monotonic() - start_time))
        done, pending = await asyncio.wait(
            task_map.keys(),
            return_when=asyncio.FIRST_COMPLETED,
            timeout=remaining_timeout,
        )

        if not done:
            # Timeout — cancel all
            for t in pending:
                t.cancel()
            break

        for task in done:
            pt = task_map.pop(task)
            elapsed_ms = (time.monotonic() - start_time) * 1000

            if task.exception():
                error_msg = str(task.exception())
                errors[pt] = error_msg
                _race_logger.debug("Race loser %s: %s", pt.value, error_msg)
                continue

            response = task.result()
            quality = heuristic_score(
                response,
                latency_ms=elapsed_ms,
            )

            if quality < 0.1:
                errors[pt] = f"quality_too_low={quality:.3f}"
                _race_logger.debug(
                    "Race reject %s: quality=%.3f", pt.value, quality,
                )
                continue

            # Winner! Cancel remaining tasks.
            for t in task_map:
                t.cancel()

            _race_logger.info(
                "Race winner: %s in %.0fms (quality=%.3f)",
                pt.value, elapsed_ms, quality,
            )

            # Record to EWMA
            if routing_memory is not None:
                try:
                    model = getattr(response, "model", "") or DEFAULT_MODELS.get(pt, "")
                    routing_memory.record_outcome(
                        provider=pt,
                        model=model,
                        task_signature=task_signature,
                        action_name="race",
                        route_path="race",
                        success=True,
                        latency_ms=elapsed_ms,
                        total_tokens=(
                            response.usage.get("input_tokens", 0)
                            + response.usage.get("output_tokens", 0)
                        ) if response.usage else 0,
                        quality_score=quality,
                    )
                except Exception:
                    _race_logger.debug("EWMA record failed", exc_info=True)

            return response, pt

    # All failed
    error_summary = "; ".join(f"{p.value}: {e}" for p, e in errors.items())
    raise RaceError(f"All {len(racers)} providers failed: {error_summary}")
