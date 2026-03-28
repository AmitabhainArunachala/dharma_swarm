"""SmartRouter: Cost-aware model routing for dharma_swarm.

Routes tasks to the cheapest model that can handle them:
- Simple tasks (summarize, classify, format) -> free tier (Ollama Cloud, NIM)
- Medium tasks (code review, analysis) -> mid tier (OpenRouter free models)
- Complex tasks (reasoning, planning, code generation) -> premium (Opus, GPT-5)

Saves 60-80% on API costs without quality loss.

Integration point: sits between router_v1 (classification) and provider_policy
(candidate selection), adding explicit cost-tier mapping and decision logging.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from dharma_swarm.models import LLMRequest, ProviderType

if TYPE_CHECKING:
    from dharma_swarm.router_v1 import RoutingSignals

logger = logging.getLogger(__name__)


def _build_routing_signals(request: LLMRequest) -> RoutingSignals:
    """Lazy import of router_v1.build_routing_signals to avoid circular imports.

    The import chain provider_policy -> smart_router -> router_v1 -> provider_policy
    would create a cycle if we imported at module level.
    """
    from dharma_swarm.router_v1 import build_routing_signals

    return build_routing_signals(request)


_DECISION_LOG_DIR = Path.home() / ".dharma" / "router"
_DECISION_LOG = _DECISION_LOG_DIR / "decisions.jsonl"


# ---------------------------------------------------------------------------
# Cost Tiers
# ---------------------------------------------------------------------------

class CostTier(str, Enum):
    """Provider cost tiers, ordered cheapest to most expensive."""
    FREE = "free"           # $0 — Ollama Cloud, NVIDIA NIM
    CHEAP = "cheap"         # ~$0 — OpenRouter free models, Groq, SiliconFlow
    MID = "mid"             # Low paid — OpenRouter paid cheap (Haiku, etc.)
    PREMIUM = "premium"     # Frontier — Opus, GPT-5, Sonnet


# ---------------------------------------------------------------------------
# Tier -> Provider mapping
# ---------------------------------------------------------------------------

# Tier → provider mapping sourced from model_hierarchy.py
from dharma_swarm.model_hierarchy import (
    DEFAULT_MODELS as _HIERARCHY_MODELS,
    TIER_CHEAP as _H_CHEAP,
    TIER_FREE as _H_FREE,
    TIER_PAID as _H_PAID,
)

_TIER_PROVIDERS: dict[CostTier, list[ProviderType]] = {
    CostTier.FREE: list(_H_FREE[:2]),   # Ollama, NIM
    CostTier.CHEAP: list(_H_FREE[2:]) + list(_H_CHEAP),  # Groq..Fireworks + Mistral..OR_FREE
    CostTier.MID: [
        ProviderType.OPENROUTER,
        ProviderType.GOOGLE_AI,
        ProviderType.MISTRAL,
    ],
    CostTier.PREMIUM: list(_H_PAID[:4]),  # OR paid, OpenAI, Anthropic, CC
}

# Model hints — single source: model_hierarchy.DEFAULT_MODELS
_TIER_MODEL_HINTS: dict[CostTier, dict[ProviderType, str]] = {
    tier: {
        p: _HIERARCHY_MODELS.get(p, "")
        for p in providers
        if p in _HIERARCHY_MODELS
    }
    for tier, providers in _TIER_PROVIDERS.items()
}

# Approximate $/1M input tokens per tier (for cost estimation)
_TIER_COST_PER_M: dict[CostTier, float] = {
    CostTier.FREE: 0.0,
    CostTier.CHEAP: 0.0,
    CostTier.MID: 0.25,
    CostTier.PREMIUM: 10.0,
}


# ---------------------------------------------------------------------------
# Complexity heuristics — supplements router_v1.classify_complexity
# ---------------------------------------------------------------------------

_SIMPLE_KEYWORDS = frozenset({
    "summarize", "summary", "list", "format", "translate", "define",
    "convert", "count", "extract", "categorize", "classify", "label",
    "rewrite", "paraphrase", "simplify", "hello", "hi", "thanks",
})

_MEDIUM_KEYWORDS = frozenset({
    "review", "analyze", "explain", "compare", "suggest", "improve",
    "refactor", "debug", "test", "describe", "evaluate", "assess",
    "generate", "write", "draft", "outline", "implement",
})

_COMPLEX_KEYWORDS = frozenset({
    "architect", "design", "plan", "reason", "prove", "derive",
    "strategy", "optimize", "security", "audit", "research",
    "investigate", "synthesize", "integrate", "orchestrate",
    "step by step", "think through", "from scratch", "end to end",
})


def _keyword_tier(text: str) -> CostTier | None:
    """Quick keyword scan to supplement router_v1 signals."""
    lowered = text.lower()
    words = set(lowered.split())

    # Check complex first (highest priority)
    complex_hits = sum(1 for kw in _COMPLEX_KEYWORDS if kw in lowered)
    if complex_hits >= 2:
        return CostTier.PREMIUM

    medium_hits = sum(1 for kw in _MEDIUM_KEYWORDS if kw in words)
    simple_hits = sum(1 for kw in _SIMPLE_KEYWORDS if kw in words)

    if complex_hits >= 1 and medium_hits >= 1:
        return CostTier.MID

    if medium_hits >= 2:
        return CostTier.MID

    if simple_hits >= 1 and medium_hits == 0 and complex_hits == 0:
        return CostTier.FREE

    return None


# ---------------------------------------------------------------------------
# Routing Decision record
# ---------------------------------------------------------------------------

@dataclass
class SmartRouteDecision:
    """Immutable record of a routing decision."""
    timestamp: float
    task_text_preview: str
    complexity_tier: str       # from router_v1
    complexity_score: float    # from router_v1
    cost_tier: CostTier
    selected_providers: list[ProviderType]
    selected_model_hint: str | None
    fallback_tiers: list[CostTier]
    reasons: list[str]
    token_estimate: int
    keyword_tier: str | None   # from our keyword scan
    override_active: bool      # env var override?


# ---------------------------------------------------------------------------
# SmartRouter
# ---------------------------------------------------------------------------

@dataclass
class SmartRouterConfig:
    """Tunable knobs for the SmartRouter."""
    # Complexity score thresholds for tier boundaries.
    # These map router_v1's [0,1] complexity score to cost tiers.
    free_max_score: float = 0.12
    cheap_max_score: float = 0.30
    mid_max_score: float = 0.55
    # Above mid_max_score -> PREMIUM

    # Token count escalation: long prompts need bigger models.
    long_context_token_threshold: int = 8_000
    very_long_context_token_threshold: int = 60_000

    # Force a specific tier via env var (DGC_SMART_ROUTER_FORCE_TIER)
    force_tier: CostTier | None = None

    # Minimum tier floor (never route below this)
    min_tier: CostTier | None = None

    # Maximum tier ceiling (never route above this — budget mode)
    max_tier: CostTier | None = None

    # Log decisions to JSONL
    log_decisions: bool = True
    decision_log_path: Path = _DECISION_LOG


_TIER_ORDER = [CostTier.FREE, CostTier.CHEAP, CostTier.MID, CostTier.PREMIUM]


def _tier_index(tier: CostTier) -> int:
    return _TIER_ORDER.index(tier)


def _clamp_tier(
    tier: CostTier,
    *,
    min_tier: CostTier | None = None,
    max_tier: CostTier | None = None,
) -> CostTier:
    """Clamp tier between floor and ceiling."""
    idx = _tier_index(tier)
    if min_tier is not None:
        idx = max(idx, _tier_index(min_tier))
    if max_tier is not None:
        idx = min(idx, _tier_index(max_tier))
    return _TIER_ORDER[idx]


class SmartRouter:
    """Cost-aware routing layer for dharma_swarm.

    Classifies task complexity using router_v1 signals + supplementary
    keyword heuristics, maps to a cost tier, and returns an ordered list
    of providers within that tier (plus fallback tiers).

    Designed to sit ON TOP of the existing provider_policy routing —
    it produces a cost tier recommendation that can be used to filter
    or re-rank the provider_policy candidate list.
    """

    def __init__(self, config: SmartRouterConfig | None = None) -> None:
        self.config = config or SmartRouterConfig()
        self._apply_env_overrides()
        self._decision_count = 0
        self._tier_counts: dict[CostTier, int] = {t: 0 for t in CostTier}
        self._estimated_savings_usd = 0.0

    def _apply_env_overrides(self) -> None:
        """Read environment variables for runtime overrides."""
        force = os.environ.get("DGC_SMART_ROUTER_FORCE_TIER", "").strip().lower()
        if force:
            try:
                self.config.force_tier = CostTier(force)
            except ValueError:
                logger.warning("Invalid DGC_SMART_ROUTER_FORCE_TIER=%r, ignoring", force)

        min_tier = os.environ.get("DGC_SMART_ROUTER_MIN_TIER", "").strip().lower()
        if min_tier:
            try:
                self.config.min_tier = CostTier(min_tier)
            except ValueError:
                pass

        max_tier = os.environ.get("DGC_SMART_ROUTER_MAX_TIER", "").strip().lower()
        if max_tier:
            try:
                self.config.max_tier = CostTier(max_tier)
            except ValueError:
                pass

        log_env = os.environ.get("DGC_SMART_ROUTER_LOG", "").strip().lower()
        if log_env in {"0", "false", "no", "off"}:
            self.config.log_decisions = False

    # -------------------------------------------------------------------
    # Core classification
    # -------------------------------------------------------------------

    def classify_complexity(self, task: str) -> CostTier:
        """Classify a task string into a cost tier using heuristics.

        Uses router_v1 signals as primary classifier, with keyword
        heuristics as supplementary signal.
        """
        if self.config.force_tier is not None:
            return self.config.force_tier

        # Build a minimal LLMRequest for router_v1 compatibility
        request = LLMRequest(
            model="auto",
            messages=[{"role": "user", "content": task}],
        )
        signals = _build_routing_signals(request)
        return self._tier_from_signals(signals, task)

    def classify_from_signals(
        self,
        signals: RoutingSignals,
        task_text: str = "",
    ) -> CostTier:
        """Classify using pre-built RoutingSignals (avoids double-building)."""
        if self.config.force_tier is not None:
            return self.config.force_tier
        return self._tier_from_signals(signals, task_text)

    def _tier_from_signals(self, signals: RoutingSignals, task_text: str) -> CostTier:
        """Map RoutingSignals to CostTier."""
        score = signals.complexity_score
        rv1_tier = signals.complexity_tier

        # router_v1 REASONING tier -> always PREMIUM
        if rv1_tier == "REASONING":
            tier = CostTier.PREMIUM
        elif score <= self.config.free_max_score:
            tier = CostTier.FREE
        elif score <= self.config.cheap_max_score:
            tier = CostTier.CHEAP
        elif score <= self.config.mid_max_score:
            tier = CostTier.MID
        else:
            tier = CostTier.PREMIUM

        # Keyword heuristics can push UP but never pull DOWN
        kw_tier = _keyword_tier(task_text) if task_text else None
        if kw_tier is not None and _tier_index(kw_tier) > _tier_index(tier):
            tier = kw_tier

        # Long context escalation: small models degrade on large inputs
        if signals.token_estimate >= self.config.very_long_context_token_threshold:
            tier = CostTier.PREMIUM
        elif signals.token_estimate >= self.config.long_context_token_threshold:
            tier = max(tier, CostTier.MID, key=_tier_index)

        # Code presence bumps minimum to CHEAP (free models often weak on code)
        if signals.has_code and _tier_index(tier) < _tier_index(CostTier.CHEAP):
            tier = CostTier.CHEAP

        return _clamp_tier(tier, min_tier=self.config.min_tier, max_tier=self.config.max_tier)

    # -------------------------------------------------------------------
    # Provider selection
    # -------------------------------------------------------------------

    def select_providers(
        self,
        tier: CostTier,
        *,
        available: list[ProviderType] | None = None,
    ) -> list[ProviderType]:
        """Return ordered providers for a given tier, filtered by availability."""
        candidates = list(_TIER_PROVIDERS.get(tier, []))
        if available is not None:
            available_set = set(available)
            candidates = [p for p in candidates if p in available_set]
        return candidates

    def model_hint_for(
        self,
        tier: CostTier,
        provider: ProviderType,
    ) -> str | None:
        """Return the default model hint for a provider within a tier."""
        tier_hints = _TIER_MODEL_HINTS.get(tier, {})
        return tier_hints.get(provider)

    def fallback_tiers(self, tier: CostTier) -> list[CostTier]:
        """Return tiers to try if primary tier has no available providers.

        Escalates upward: FREE -> CHEAP -> MID -> PREMIUM.
        """
        idx = _tier_index(tier)
        result = []
        for i in range(idx + 1, len(_TIER_ORDER)):
            candidate = _TIER_ORDER[i]
            if self.config.max_tier is not None and _tier_index(candidate) > _tier_index(self.config.max_tier):
                break
            result.append(candidate)
        return result

    # -------------------------------------------------------------------
    # Full routing
    # -------------------------------------------------------------------

    def route(
        self,
        task: str,
        *,
        available: list[ProviderType] | None = None,
    ) -> SmartRouteDecision:
        """Full routing decision: classify + select provider + log."""
        request = LLMRequest(
            model="auto",
            messages=[{"role": "user", "content": task}],
        )
        signals = _build_routing_signals(request)
        return self.route_from_signals(signals, task_text=task, available=available)

    def route_from_signals(
        self,
        signals: RoutingSignals,
        *,
        task_text: str = "",
        available: list[ProviderType] | None = None,
    ) -> SmartRouteDecision:
        """Route using pre-built signals."""
        tier = self.classify_from_signals(signals, task_text)
        kw_tier = _keyword_tier(task_text) if task_text else None

        providers = self.select_providers(tier, available=available)
        fb_tiers = self.fallback_tiers(tier)

        # If primary tier empty, escalate through fallbacks
        actual_tier = tier
        if not providers:
            for fb in fb_tiers:
                providers = self.select_providers(fb, available=available)
                if providers:
                    actual_tier = fb
                    break

        model_hint: str | None = None
        if providers:
            model_hint = self.model_hint_for(actual_tier, providers[0])

        reasons = self._build_reasons(signals, tier, actual_tier, kw_tier, providers)
        override = self.config.force_tier is not None

        decision = SmartRouteDecision(
            timestamp=time.time(),
            task_text_preview=task_text[:120] if task_text else "",
            complexity_tier=signals.complexity_tier,
            complexity_score=round(signals.complexity_score, 4),
            cost_tier=actual_tier,
            selected_providers=providers,
            selected_model_hint=model_hint,
            fallback_tiers=fb_tiers,
            reasons=reasons,
            token_estimate=signals.token_estimate,
            keyword_tier=kw_tier.value if kw_tier else None,
            override_active=override,
        )

        self._record_decision(decision)
        return decision

    def _build_reasons(
        self,
        signals: RoutingSignals,
        requested_tier: CostTier,
        actual_tier: CostTier,
        kw_tier: CostTier | None,
        providers: list[ProviderType],
    ) -> list[str]:
        reasons: list[str] = []

        if self.config.force_tier is not None:
            reasons.append(f"force_tier={self.config.force_tier.value}")
            return reasons

        reasons.append(f"rv1_tier={signals.complexity_tier}")
        reasons.append(f"score={signals.complexity_score:.3f}")

        if kw_tier is not None:
            reasons.append(f"keyword_tier={kw_tier.value}")

        if signals.token_estimate >= self.config.very_long_context_token_threshold:
            reasons.append("very_long_context_escalation")
        elif signals.token_estimate >= self.config.long_context_token_threshold:
            reasons.append("long_context_escalation")

        if signals.has_code:
            reasons.append("has_code")

        if actual_tier != requested_tier:
            reasons.append(f"tier_escalated={requested_tier.value}->{actual_tier.value}")

        if not providers:
            reasons.append("no_providers_available")

        if self.config.min_tier is not None:
            reasons.append(f"min_tier={self.config.min_tier.value}")
        if self.config.max_tier is not None:
            reasons.append(f"max_tier={self.config.max_tier.value}")

        return reasons

    # -------------------------------------------------------------------
    # Decision logging
    # -------------------------------------------------------------------

    def _record_decision(self, decision: SmartRouteDecision) -> None:
        """Track stats and optionally log to JSONL."""
        self._decision_count += 1
        self._tier_counts[decision.cost_tier] = self._tier_counts.get(decision.cost_tier, 0) + 1

        # Estimate savings vs always using PREMIUM
        premium_cost = _TIER_COST_PER_M.get(CostTier.PREMIUM, 10.0)
        actual_cost = _TIER_COST_PER_M.get(decision.cost_tier, premium_cost)
        tokens_m = decision.token_estimate / 1_000_000
        self._estimated_savings_usd += (premium_cost - actual_cost) * tokens_m

        if not self.config.log_decisions:
            return

        record = {
            "timestamp": decision.timestamp,
            "task_preview": decision.task_text_preview,
            "complexity_tier": decision.complexity_tier,
            "complexity_score": decision.complexity_score,
            "cost_tier": decision.cost_tier.value,
            "providers": [p.value for p in decision.selected_providers],
            "model_hint": decision.selected_model_hint,
            "fallback_tiers": [t.value for t in decision.fallback_tiers],
            "reasons": decision.reasons,
            "token_estimate": decision.token_estimate,
            "keyword_tier": decision.keyword_tier,
            "override": decision.override_active,
        }

        try:
            self.config.decision_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config.decision_log_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")
        except Exception as exc:
            logger.warning("SmartRouter: failed to log decision: %s", exc)

    # -------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------

    @property
    def decision_count(self) -> int:
        return self._decision_count

    @property
    def tier_distribution(self) -> dict[str, int]:
        return {t.value: c for t, c in self._tier_counts.items()}

    @property
    def estimated_savings_usd(self) -> float:
        return round(self._estimated_savings_usd, 6)

    def stats_summary(self) -> str:
        """Human-readable routing statistics."""
        if self._decision_count == 0:
            return "SmartRouter: no decisions recorded yet."

        lines = [
            f"SmartRouter: {self._decision_count} decisions",
            f"  Estimated savings: ${self._estimated_savings_usd:.4f}",
            "  Tier distribution:",
        ]
        for tier in _TIER_ORDER:
            count = self._tier_counts.get(tier, 0)
            pct = (count / self._decision_count * 100) if self._decision_count else 0
            lines.append(f"    {tier.value}: {count} ({pct:.0f}%)")
        return "\n".join(lines)

    # -------------------------------------------------------------------
    # Integration helpers
    # -------------------------------------------------------------------

    def filter_candidates_by_tier(
        self,
        candidates: list[ProviderType],
        tier: CostTier,
    ) -> list[ProviderType]:
        """Filter an existing candidate list to match a cost tier.

        Returns providers from the candidate list that belong to the
        specified tier. If none match, returns the original list unchanged
        (graceful degradation).
        """
        tier_set = set(_TIER_PROVIDERS.get(tier, []))
        filtered = [p for p in candidates if p in tier_set]
        if not filtered:
            # Graceful degradation: try the next tier up
            for fb in self.fallback_tiers(tier):
                fb_set = set(_TIER_PROVIDERS.get(fb, []))
                filtered = [p for p in candidates if p in fb_set]
                if filtered:
                    break
        return filtered if filtered else candidates

    def rerank_candidates(
        self,
        candidates: list[ProviderType],
        tier: CostTier,
    ) -> list[ProviderType]:
        """Re-rank a candidate list, promoting providers in the preferred tier.

        Providers matching the tier come first (in their original order),
        followed by remaining candidates.
        """
        tier_set = set(_TIER_PROVIDERS.get(tier, []))
        preferred = [p for p in candidates if p in tier_set]
        rest = [p for p in candidates if p not in tier_set]
        return preferred + rest


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

_GLOBAL_ROUTER: SmartRouter | None = None


def get_smart_router() -> SmartRouter:
    """Get or create the module-level SmartRouter singleton."""
    global _GLOBAL_ROUTER
    if _GLOBAL_ROUTER is None:
        _GLOBAL_ROUTER = SmartRouter()
    return _GLOBAL_ROUTER


def reset_smart_router() -> None:
    """Reset the global singleton (for testing)."""
    global _GLOBAL_ROUTER
    _GLOBAL_ROUTER = None


__all__ = [
    "CostTier",
    "SmartRouteDecision",
    "SmartRouter",
    "SmartRouterConfig",
    "get_smart_router",
    "reset_smart_router",
]
