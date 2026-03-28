"""Tests for SmartRouter cost-aware model routing."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from dharma_swarm.models import LLMRequest, ProviderType
from dharma_swarm.router_v1 import RoutingSignals, build_routing_signals
from dharma_swarm.smart_router import (
    CostTier,
    SmartRouteDecision,
    SmartRouter,
    SmartRouterConfig,
    _keyword_tier,
    _tier_index,
    _clamp_tier,
    get_smart_router,
    reset_smart_router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_global_router():
    """Reset global router singleton between tests."""
    reset_smart_router()
    yield
    reset_smart_router()


@pytest.fixture()
def tmp_log(tmp_path: Path) -> Path:
    return tmp_path / "decisions.jsonl"


@pytest.fixture()
def router(tmp_log: Path) -> SmartRouter:
    """SmartRouter with logging to a temp file."""
    return SmartRouter(SmartRouterConfig(
        log_decisions=True,
        decision_log_path=tmp_log,
    ))


def _signals_for(text: str) -> RoutingSignals:
    request = LLMRequest(
        model="auto",
        messages=[{"role": "user", "content": text}],
    )
    return build_routing_signals(request)


# ---------------------------------------------------------------------------
# CostTier ordering
# ---------------------------------------------------------------------------

class TestCostTierOrdering:
    def test_tier_index_order(self) -> None:
        assert _tier_index(CostTier.FREE) < _tier_index(CostTier.CHEAP)
        assert _tier_index(CostTier.CHEAP) < _tier_index(CostTier.MID)
        assert _tier_index(CostTier.MID) < _tier_index(CostTier.PREMIUM)

    def test_clamp_tier_floor(self) -> None:
        assert _clamp_tier(CostTier.FREE, min_tier=CostTier.CHEAP) == CostTier.CHEAP

    def test_clamp_tier_ceiling(self) -> None:
        assert _clamp_tier(CostTier.PREMIUM, max_tier=CostTier.MID) == CostTier.MID

    def test_clamp_tier_both(self) -> None:
        assert _clamp_tier(CostTier.FREE, min_tier=CostTier.CHEAP, max_tier=CostTier.MID) == CostTier.CHEAP
        assert _clamp_tier(CostTier.PREMIUM, min_tier=CostTier.CHEAP, max_tier=CostTier.MID) == CostTier.MID

    def test_clamp_tier_passthrough(self) -> None:
        assert _clamp_tier(CostTier.CHEAP) == CostTier.CHEAP


# ---------------------------------------------------------------------------
# Keyword tier detection
# ---------------------------------------------------------------------------

class TestKeywordTier:
    def test_simple_keywords(self) -> None:
        assert _keyword_tier("summarize this document") == CostTier.FREE

    def test_complex_keywords(self) -> None:
        assert _keyword_tier("architect the system design from scratch") == CostTier.PREMIUM

    def test_medium_keywords(self) -> None:
        # "review" + "analyze" = 2 medium keywords -> MID
        assert _keyword_tier("review and analyze this code") == CostTier.MID

    def test_no_keywords(self) -> None:
        assert _keyword_tier("the quick brown fox") is None

    def test_mixed_simple_and_complex(self) -> None:
        # complex keywords dominate simple
        result = _keyword_tier("architect a step by step plan from scratch")
        assert result == CostTier.PREMIUM

    def test_single_complex_with_medium(self) -> None:
        # 1 complex + 1 medium -> MID
        result = _keyword_tier("investigate and review the issue")
        assert result == CostTier.MID


# ---------------------------------------------------------------------------
# Classification from text
# ---------------------------------------------------------------------------

class TestClassifyComplexity:
    def test_simple_greeting(self, router: SmartRouter) -> None:
        tier = router.classify_complexity("hello, how are you?")
        assert tier in {CostTier.FREE, CostTier.CHEAP}

    def test_simple_summary(self, router: SmartRouter) -> None:
        tier = router.classify_complexity("summarize this in 3 bullet points")
        assert tier in {CostTier.FREE, CostTier.CHEAP}

    def test_reasoning_task(self, router: SmartRouter) -> None:
        tier = router.classify_complexity(
            "Think through this step by step and analyze why the design fails. "
            "Reason about each component."
        )
        assert tier == CostTier.PREMIUM

    def test_code_task_at_least_cheap(self, router: SmartRouter) -> None:
        tier = router.classify_complexity("```python\ndef hello():\n    pass\n```")
        assert _tier_index(tier) >= _tier_index(CostTier.CHEAP)

    def test_long_context_escalation(self, router: SmartRouter) -> None:
        # 60K+ tokens -> PREMIUM
        long_text = "word " * 80_000  # ~80K tokens
        tier = router.classify_complexity(long_text)
        assert tier == CostTier.PREMIUM

    def test_medium_context_escalation(self, router: SmartRouter) -> None:
        # 8K-60K tokens -> at least MID
        medium_text = "word " * 12_000  # ~12K tokens
        tier = router.classify_complexity(medium_text)
        assert _tier_index(tier) >= _tier_index(CostTier.MID)


# ---------------------------------------------------------------------------
# Classification from signals
# ---------------------------------------------------------------------------

class TestClassifyFromSignals:
    def test_simple_signals(self, router: SmartRouter) -> None:
        signals = _signals_for("hi there")
        tier = router.classify_from_signals(signals, "hi there")
        assert tier in {CostTier.FREE, CostTier.CHEAP}

    def test_reasoning_signals(self, router: SmartRouter) -> None:
        signals = _signals_for(
            "Think through this step by step and analyze the root cause"
        )
        assert signals.complexity_tier == "REASONING"
        tier = router.classify_from_signals(signals, "")
        assert tier == CostTier.PREMIUM

    def test_force_tier_overrides(self) -> None:
        config = SmartRouterConfig(force_tier=CostTier.FREE, log_decisions=False)
        router = SmartRouter(config)
        tier = router.classify_complexity(
            "Think through this step by step and analyze and reason carefully"
        )
        assert tier == CostTier.FREE


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

class TestSelectProviders:
    def test_free_tier_providers(self, router: SmartRouter) -> None:
        providers = router.select_providers(CostTier.FREE)
        assert ProviderType.OLLAMA in providers
        assert ProviderType.NVIDIA_NIM in providers
        # No paid providers
        assert ProviderType.ANTHROPIC not in providers

    def test_premium_tier_providers(self, router: SmartRouter) -> None:
        providers = router.select_providers(CostTier.PREMIUM)
        assert ProviderType.ANTHROPIC in providers
        assert ProviderType.OPENAI in providers

    def test_filter_by_available(self, router: SmartRouter) -> None:
        providers = router.select_providers(
            CostTier.FREE,
            available=[ProviderType.OLLAMA, ProviderType.ANTHROPIC],
        )
        assert providers == [ProviderType.OLLAMA]

    def test_empty_if_no_match(self, router: SmartRouter) -> None:
        providers = router.select_providers(
            CostTier.FREE,
            available=[ProviderType.ANTHROPIC],
        )
        assert providers == []


# ---------------------------------------------------------------------------
# Model hints
# ---------------------------------------------------------------------------

class TestModelHints:
    def test_free_tier_ollama_hint(self, router: SmartRouter) -> None:
        hint = router.model_hint_for(CostTier.FREE, ProviderType.OLLAMA)
        assert hint is not None
        assert "glm-5" in hint

    def test_premium_tier_anthropic_hint(self, router: SmartRouter) -> None:
        hint = router.model_hint_for(CostTier.PREMIUM, ProviderType.ANTHROPIC)
        assert hint is not None
        assert "opus" in hint.lower() or "claude" in hint.lower()

    def test_missing_provider_returns_none(self, router: SmartRouter) -> None:
        hint = router.model_hint_for(CostTier.FREE, ProviderType.ANTHROPIC)
        assert hint is None


# ---------------------------------------------------------------------------
# Fallback tiers
# ---------------------------------------------------------------------------

class TestFallbackTiers:
    def test_free_fallback_escalates(self, router: SmartRouter) -> None:
        fb = router.fallback_tiers(CostTier.FREE)
        assert CostTier.CHEAP in fb
        assert CostTier.MID in fb
        assert CostTier.PREMIUM in fb

    def test_premium_no_fallback(self, router: SmartRouter) -> None:
        fb = router.fallback_tiers(CostTier.PREMIUM)
        assert fb == []

    def test_max_tier_limits_fallback(self) -> None:
        config = SmartRouterConfig(max_tier=CostTier.MID, log_decisions=False)
        r = SmartRouter(config)
        fb = r.fallback_tiers(CostTier.FREE)
        assert CostTier.CHEAP in fb
        assert CostTier.MID in fb
        assert CostTier.PREMIUM not in fb


# ---------------------------------------------------------------------------
# Full route()
# ---------------------------------------------------------------------------

class TestRoute:
    def test_simple_task_routes_free(self, router: SmartRouter) -> None:
        decision = router.route("hello, what is your name?")
        assert decision.cost_tier in {CostTier.FREE, CostTier.CHEAP}
        assert len(decision.selected_providers) > 0
        assert len(decision.reasons) > 0

    def test_complex_task_routes_premium(self, router: SmartRouter) -> None:
        decision = router.route(
            "Architect a distributed system step by step. "
            "Reason about fault tolerance and design trade-offs."
        )
        assert decision.cost_tier == CostTier.PREMIUM

    def test_route_records_timestamp(self, router: SmartRouter) -> None:
        decision = router.route("hi")
        assert decision.timestamp > 0

    def test_fallback_when_no_available_providers(self, router: SmartRouter) -> None:
        # Only ANTHROPIC available, but task is simple -> should escalate to PREMIUM
        decision = router.route(
            "hello",
            available=[ProviderType.ANTHROPIC],
        )
        # Should still produce a result (graceful escalation)
        assert len(decision.selected_providers) > 0
        assert ProviderType.ANTHROPIC in decision.selected_providers

    def test_override_flag_in_decision(self) -> None:
        config = SmartRouterConfig(force_tier=CostTier.CHEAP, log_decisions=False)
        r = SmartRouter(config)
        decision = r.route("architect a complex system step by step reasoning")
        assert decision.override_active is True
        assert decision.cost_tier == CostTier.CHEAP

    def test_task_preview_truncated(self, router: SmartRouter) -> None:
        long_task = "x" * 200
        decision = router.route(long_task)
        assert len(decision.task_text_preview) <= 120


# ---------------------------------------------------------------------------
# Decision logging
# ---------------------------------------------------------------------------

class TestDecisionLogging:
    def test_decisions_written_to_jsonl(self, router: SmartRouter, tmp_log: Path) -> None:
        router.route("summarize this")
        router.route("architect the system from scratch step by step")

        assert tmp_log.exists()
        lines = tmp_log.read_text().strip().split("\n")
        assert len(lines) == 2

        for line in lines:
            record = json.loads(line)
            assert "timestamp" in record
            assert "cost_tier" in record
            assert "providers" in record
            assert "reasons" in record

    def test_logging_disabled(self, tmp_log: Path) -> None:
        config = SmartRouterConfig(log_decisions=False, decision_log_path=tmp_log)
        r = SmartRouter(config)
        r.route("hello")
        assert not tmp_log.exists()


# ---------------------------------------------------------------------------
# Statistics tracking
# ---------------------------------------------------------------------------

class TestStats:
    def test_decision_count(self, router: SmartRouter) -> None:
        assert router.decision_count == 0
        router.route("hi")
        assert router.decision_count == 1
        router.route("hello")
        assert router.decision_count == 2

    def test_tier_distribution(self, router: SmartRouter) -> None:
        router.route("hello")
        dist = router.tier_distribution
        assert isinstance(dist, dict)
        total = sum(dist.values())
        assert total == 1

    def test_estimated_savings(self, router: SmartRouter) -> None:
        # Simple tasks routed to free tier should show savings
        router.route("hi")
        assert router.estimated_savings_usd >= 0.0

    def test_stats_summary_with_no_decisions(self, router: SmartRouter) -> None:
        summary = router.stats_summary()
        assert "no decisions" in summary

    def test_stats_summary_with_decisions(self, router: SmartRouter) -> None:
        router.route("hello")
        summary = router.stats_summary()
        assert "1 decisions" in summary
        assert "Tier distribution" in summary


# ---------------------------------------------------------------------------
# Integration helpers
# ---------------------------------------------------------------------------

class TestIntegrationHelpers:
    def test_filter_candidates_by_tier(self, router: SmartRouter) -> None:
        candidates = [
            ProviderType.ANTHROPIC,
            ProviderType.OLLAMA,
            ProviderType.NVIDIA_NIM,
            ProviderType.OPENAI,
        ]
        filtered = router.filter_candidates_by_tier(candidates, CostTier.FREE)
        assert filtered == [ProviderType.OLLAMA, ProviderType.NVIDIA_NIM]

    def test_filter_candidates_fallback(self, router: SmartRouter) -> None:
        # Only premium providers -> filtering for FREE falls back
        candidates = [ProviderType.ANTHROPIC, ProviderType.OPENAI]
        filtered = router.filter_candidates_by_tier(candidates, CostTier.FREE)
        # Should eventually find them in PREMIUM tier fallback
        assert len(filtered) > 0

    def test_filter_no_match_returns_original(self, router: SmartRouter) -> None:
        candidates = [ProviderType.LOCAL]  # LOCAL is in no tier
        filtered = router.filter_candidates_by_tier(candidates, CostTier.FREE)
        assert filtered == candidates  # graceful degradation

    def test_rerank_candidates(self, router: SmartRouter) -> None:
        candidates = [
            ProviderType.ANTHROPIC,
            ProviderType.OPENAI,
            ProviderType.OLLAMA,
            ProviderType.NVIDIA_NIM,
        ]
        reranked = router.rerank_candidates(candidates, CostTier.FREE)
        # Free tier providers should come first
        assert reranked[0] == ProviderType.OLLAMA
        assert reranked[1] == ProviderType.NVIDIA_NIM
        # Premium providers follow
        assert ProviderType.ANTHROPIC in reranked[2:]
        assert ProviderType.OPENAI in reranked[2:]


# ---------------------------------------------------------------------------
# Environment variable overrides
# ---------------------------------------------------------------------------

class TestEnvOverrides:
    def test_force_tier_from_env(self, tmp_log: Path) -> None:
        with mock.patch.dict(os.environ, {"DGC_SMART_ROUTER_FORCE_TIER": "cheap"}):
            config = SmartRouterConfig(decision_log_path=tmp_log)
            r = SmartRouter(config)
            assert r.config.force_tier == CostTier.CHEAP

    def test_min_tier_from_env(self, tmp_log: Path) -> None:
        with mock.patch.dict(os.environ, {"DGC_SMART_ROUTER_MIN_TIER": "mid"}):
            config = SmartRouterConfig(decision_log_path=tmp_log)
            r = SmartRouter(config)
            assert r.config.min_tier == CostTier.MID

    def test_max_tier_from_env(self, tmp_log: Path) -> None:
        with mock.patch.dict(os.environ, {"DGC_SMART_ROUTER_MAX_TIER": "mid"}):
            config = SmartRouterConfig(decision_log_path=tmp_log)
            r = SmartRouter(config)
            assert r.config.max_tier == CostTier.MID

    def test_log_disabled_from_env(self, tmp_log: Path) -> None:
        with mock.patch.dict(os.environ, {"DGC_SMART_ROUTER_LOG": "off"}):
            config = SmartRouterConfig(decision_log_path=tmp_log)
            r = SmartRouter(config)
            assert r.config.log_decisions is False

    def test_invalid_force_tier_ignored(self, tmp_log: Path) -> None:
        with mock.patch.dict(os.environ, {"DGC_SMART_ROUTER_FORCE_TIER": "bogus"}):
            config = SmartRouterConfig(decision_log_path=tmp_log)
            r = SmartRouter(config)
            assert r.config.force_tier is None


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------

class TestGlobalSingleton:
    def test_get_returns_same_instance(self) -> None:
        a = get_smart_router()
        b = get_smart_router()
        assert a is b

    def test_reset_clears_singleton(self) -> None:
        a = get_smart_router()
        reset_smart_router()
        b = get_smart_router()
        assert a is not b
