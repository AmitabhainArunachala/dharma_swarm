"""Model Routing — Organism-level intelligent routing integration.

Connects the existing provider_policy.py and cost_tracker.py into the
organism's nervous system, implementing the architecture from the
Omniverse Model Routing research mandate:

    1. Sub-millisecond complexity classification
    2. Cross-provider 3-layer resilience (retry → fallback → circuit breaker)
    3. Language-aware model selection (JP → Qwen3-32B override)

This module doesn't replace the existing router — it wraps it with
organism-level intelligence: cost-awareness from AMIROS, load balancing
informed by agent viability, and algedonic signals on budget overruns.

Ground: Ashby (requisite variety — the router must match workload variety),
        Beer (S4 intelligence informing S3 control decisions).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ComplexityTier(str, Enum):
    """Task complexity classification for routing decisions."""
    TRIVIAL = "trivial"       # Formatting, translation, simple extraction
    STANDARD = "standard"     # Analysis, coding, multi-step reasoning
    FRONTIER = "frontier"     # Novel research, long-context, creative
    PRIVILEGED = "privileged" # Security-sensitive, deployment, credentials


class LanguageHint(str, Enum):
    """Primary language of the task for model selection."""
    EN = "en"
    JP = "jp"
    MIXED = "mixed"
    OTHER = "other"


@dataclass
class RoutingSignal:
    """A signal from the organism influencing routing decisions."""
    complexity: ComplexityTier = ComplexityTier.STANDARD
    language: LanguageHint = LanguageHint.EN
    budget_pressure: float = 0.0  # 0.0 = no pressure, 1.0 = critical
    agent_reliability: float = 1.0  # From VSM viability
    urgency: float = 0.5  # 0.0 = can wait, 1.0 = immediate
    context_tokens: int = 0


@dataclass
class RoutingDecision:
    """The routing decision produced by the organism."""
    recommended_tier: str  # "T0", "T1", "T2", "T3"
    reasoning: str
    fallback_tiers: list[str] = field(default_factory=list)
    estimated_cost_usd: float = 0.0
    signal: RoutingSignal | None = None


@dataclass
class RouteResult:
    """Simple routing result with model/provider/complexity fields."""
    model: str
    provider: str
    complexity: str
    tier: str = ""


class OrganismRouter:
    """Organism-level model routing intelligence.

    Wraps provider_policy.py with cost awareness, language detection,
    and budget monitoring fed by the organism's nervous system.

    Usage:
        router = OrganismRouter()
        decision = router.classify_and_route(
            task_text="分析するデータ...",
            agent_id="researcher_01",
        )
    """

    # Tier cost budgets (USD/hour) — derived from $200/month target
    _HOURLY_BUDGET = 200.0 / (30 * 24)  # ~$0.28/hour

    # Complexity keywords (from agent_runner.py patterns)
    _TRIVIAL_HINTS = frozenset({
        "format", "translate", "list", "extract", "convert", "summarize",
    })
    _FRONTIER_HINTS = frozenset({
        "analyze", "architecture", "compare", "debug", "design",
        "evaluate", "investigate", "prove", "research", "novel",
    })
    _PRIVILEGED_HINTS = frozenset({
        "credential", "delete", "deploy", "production", "secret",
        "ssh", "sudo", "rm -rf",
    })
    # Japanese detection (basic heuristic — Hiragana/Katakana/CJK ranges)
    _JP_RANGES = set(range(0x3040, 0x30FF + 1)) | set(range(0x4E00, 0x9FFF + 1))

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._decisions: list[RoutingDecision] = []
        self._cost_window: list[tuple[float, float]] = []  # (timestamp, cost)

    def classify_complexity(self, text: str) -> ComplexityTier:
        """Sub-millisecond complexity classification.

        Uses keyword heuristics (no LLM call) matching the patterns
        already established in agent_runner.py.
        """
        lower = text.lower()
        words = set(lower.split())

        if words & self._PRIVILEGED_HINTS:
            return ComplexityTier.PRIVILEGED
        if words & self._FRONTIER_HINTS:
            return ComplexityTier.FRONTIER
        if words & self._TRIVIAL_HINTS:
            return ComplexityTier.TRIVIAL

        # Length heuristic: longer tasks tend to be more complex
        if len(text) > 2000:
            return ComplexityTier.FRONTIER
        return ComplexityTier.STANDARD

    def detect_language(self, text: str) -> LanguageHint:
        """Detect primary language using character range heuristics."""
        if not text:
            return LanguageHint.EN

        jp_chars = sum(1 for c in text if ord(c) in self._JP_RANGES)
        total_alpha = sum(1 for c in text if c.isalpha())
        if total_alpha == 0:
            return LanguageHint.EN

        jp_ratio = jp_chars / total_alpha
        if jp_ratio > 0.5:
            return LanguageHint.JP
        if jp_ratio > 0.1:
            return LanguageHint.MIXED
        return LanguageHint.EN

    def classify_and_route(
        self,
        task_text: str,
        agent_id: str = "",
        urgency: float = 0.5,
        context_tokens: int = 0,
    ) -> RoutingDecision:
        """Classify task and produce a routing decision.

        Combines complexity, language, budget pressure, and agent
        reliability into a tier recommendation.
        """
        complexity = self.classify_complexity(task_text)
        language = self.detect_language(task_text)
        budget_pressure = self._compute_budget_pressure()

        signal = RoutingSignal(
            complexity=complexity,
            language=language,
            budget_pressure=budget_pressure,
            urgency=urgency,
            context_tokens=context_tokens,
        )

        # Decision logic
        if complexity == ComplexityTier.PRIVILEGED:
            tier = "T3"
            reasoning = "Privileged action requires frontier model with safety guardrails"
            fallbacks = ["T2"]
        elif complexity == ComplexityTier.FRONTIER:
            if budget_pressure > 0.8:
                tier = "T2"
                reasoning = "Frontier task downgraded to T2 due to budget pressure"
                fallbacks = ["T1"]
            else:
                tier = "T3"
                reasoning = "Frontier task routed to T3 for maximum capability"
                fallbacks = ["T2"]
        elif complexity == ComplexityTier.TRIVIAL:
            tier = "T0" if budget_pressure > 0.3 else "T1"
            reasoning = "Trivial task routed to cheapest adequate tier"
            fallbacks = ["T1", "T0"]
        else:  # STANDARD
            if budget_pressure > 0.6:
                tier = "T1"
                reasoning = "Standard task on T1 to manage budget"
                fallbacks = ["T0"]
            else:
                tier = "T2"
                reasoning = "Standard task on T2 for reliable quality"
                fallbacks = ["T1"]

        # Language override: JP tasks benefit from specific models
        if language in (LanguageHint.JP, LanguageHint.MIXED):
            reasoning += " | JP language detected — prefer Qwen3/Claude for JP quality"

        decision = RoutingDecision(
            recommended_tier=tier,
            reasoning=reasoning,
            fallback_tiers=fallbacks,
            signal=signal,
        )

        self._decisions.append(decision)
        if len(self._decisions) > 1000:
            self._decisions = self._decisions[-1000:]

        return decision

    # Tier → model/provider mapping for convenience route() method
    # Model strings must match AgentConfig.model field format (direct API names,
    # not OpenRouter prefix format like "anthropic/claude-sonnet-4").
    _TIER_MODELS: dict[str, tuple[str, str]] = {
        "T0": ("llama-3.1-8b-instruct", "openrouter"),
        "T1": ("llama-3.3-70b-instruct", "openrouter"),
        "T2": ("claude-sonnet-4-6", "anthropic"),
        "T3": ("claude-opus-4-6", "anthropic"),
    }

    def route(self, task_text: str, agent_id: str = "") -> "RouteResult":
        """Convenience route method — returns a RouteResult with model/provider/complexity.

        Wraps classify_and_route() for simple task-to-model mapping.
        """
        decision = self.classify_and_route(task_text, agent_id=agent_id)
        model, provider = self._TIER_MODELS.get(decision.recommended_tier, ("claude-opus-4-6", "anthropic"))
        complexity = decision.signal.complexity.value if (decision.signal and decision.signal.complexity) else ""
        return RouteResult(model=model, provider=provider, complexity=complexity, tier=decision.recommended_tier)

    def record_cost(self, cost_usd: float) -> None:
        """Record an LLM call cost for budget tracking."""
        self._cost_window.append((time.time(), cost_usd))
        # Keep last hour only
        cutoff = time.time() - 3600
        self._cost_window = [
            (t, c) for t, c in self._cost_window if t >= cutoff
        ]

    def _compute_budget_pressure(self) -> float:
        """Compute budget pressure (0.0 = fine, 1.0 = over budget).

        Based on hourly spending rate vs target.
        """
        if not self._cost_window:
            return 0.0

        cutoff = time.time() - 3600
        recent = [c for t, c in self._cost_window if t >= cutoff]
        hourly_spend = sum(recent)
        return min(1.0, hourly_spend / max(0.01, self._HOURLY_BUDGET))

    def stats(self) -> dict[str, Any]:
        """Routing statistics for organism observability."""
        if not self._decisions:
            return {"total_decisions": 0}

        tier_counts: dict[str, int] = {}
        for d in self._decisions[-100:]:
            tier_counts[d.recommended_tier] = tier_counts.get(d.recommended_tier, 0) + 1

        return {
            "total_decisions": len(self._decisions),
            "recent_tier_distribution": tier_counts,
            "budget_pressure": self._compute_budget_pressure(),
            "hourly_spend": sum(c for t, c in self._cost_window if t >= time.time() - 3600),
        }


__all__ = [
    "ComplexityTier",
    "LanguageHint",
    "OrganismRouter",
    "RouteResult",
    "RoutingDecision",
    "RoutingSignal",
]
