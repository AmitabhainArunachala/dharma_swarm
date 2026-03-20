"""Tests for organism-level model routing."""

import pytest
from dharma_swarm.model_routing import (
    ComplexityTier,
    LanguageHint,
    OrganismRouter,
    RoutingDecision,
)


class TestComplexityClassification:

    def test_trivial_task(self):
        router = OrganismRouter()
        assert router.classify_complexity("translate this text") == ComplexityTier.TRIVIAL
        assert router.classify_complexity("format the data") == ComplexityTier.TRIVIAL

    def test_standard_task(self):
        router = OrganismRouter()
        assert router.classify_complexity("process the records") == ComplexityTier.STANDARD

    def test_frontier_task(self):
        router = OrganismRouter()
        assert router.classify_complexity("analyze the architecture") == ComplexityTier.FRONTIER
        assert router.classify_complexity("research novel approaches") == ComplexityTier.FRONTIER

    def test_privileged_task(self):
        router = OrganismRouter()
        assert router.classify_complexity("deploy to production") == ComplexityTier.PRIVILEGED
        assert router.classify_complexity("delete the credential") == ComplexityTier.PRIVILEGED

    def test_long_text_is_frontier(self):
        router = OrganismRouter()
        long_text = "process " * 500  # > 2000 chars
        assert router.classify_complexity(long_text) == ComplexityTier.FRONTIER


class TestLanguageDetection:

    def test_english(self):
        router = OrganismRouter()
        assert router.detect_language("Hello world") == LanguageHint.EN

    def test_japanese(self):
        router = OrganismRouter()
        assert router.detect_language("こんにちは世界") == LanguageHint.JP

    def test_mixed(self):
        router = OrganismRouter()
        # Mix of English and Japanese
        result = router.detect_language("Hello こんにちは world 世界 testing テスト")
        assert result in (LanguageHint.JP, LanguageHint.MIXED)

    def test_empty_string(self):
        router = OrganismRouter()
        assert router.detect_language("") == LanguageHint.EN


class TestRoutingDecisions:

    def test_trivial_routes_cheap(self):
        router = OrganismRouter()
        d = router.classify_and_route("translate this text")
        assert d.recommended_tier in ("T0", "T1")

    def test_frontier_routes_t3(self):
        router = OrganismRouter()
        d = router.classify_and_route("analyze the architecture deeply")
        assert d.recommended_tier in ("T2", "T3")

    def test_privileged_always_t3(self):
        router = OrganismRouter()
        d = router.classify_and_route("deploy to production")
        assert d.recommended_tier == "T3"

    def test_jp_detection_noted_in_reasoning(self):
        router = OrganismRouter()
        d = router.classify_and_route("このデータを分析してください")
        assert "JP" in d.reasoning

    def test_budget_pressure_downgrades(self):
        router = OrganismRouter()
        # Simulate heavy spending
        import time
        for _ in range(100):
            router._cost_window.append((time.time(), 0.01))
        d = router.classify_and_route("analyze the architecture")
        # Should be downgraded from T3 to T2 due to budget
        assert d.recommended_tier in ("T1", "T2")

    def test_decisions_tracked(self):
        router = OrganismRouter()
        router.classify_and_route("hello")
        router.classify_and_route("analyze data")
        assert len(router._decisions) == 2

    def test_fallback_tiers_present(self):
        router = OrganismRouter()
        d = router.classify_and_route("research novel paper")
        assert len(d.fallback_tiers) >= 1


class TestBudgetPressure:

    def test_no_costs_no_pressure(self):
        router = OrganismRouter()
        assert router._compute_budget_pressure() == 0.0

    def test_heavy_spending_creates_pressure(self):
        router = OrganismRouter()
        import time
        for _ in range(50):
            router._cost_window.append((time.time(), 0.02))
        pressure = router._compute_budget_pressure()
        assert pressure > 0.5

    def test_old_costs_excluded(self):
        router = OrganismRouter()
        import time
        # Add costs from 2 hours ago (should be excluded)
        old_time = time.time() - 7200
        for _ in range(100):
            router._cost_window.append((old_time, 1.0))
        router.record_cost(0.001)  # This triggers cleanup
        pressure = router._compute_budget_pressure()
        # Should be low because old costs are excluded
        assert pressure < 0.5


class TestRouterStats:

    def test_empty_stats(self):
        router = OrganismRouter()
        s = router.stats()
        assert s["total_decisions"] == 0

    def test_stats_after_decisions(self):
        router = OrganismRouter()
        router.classify_and_route("hello")
        router.classify_and_route("deploy production")
        s = router.stats()
        assert s["total_decisions"] == 2
        assert "recent_tier_distribution" in s
