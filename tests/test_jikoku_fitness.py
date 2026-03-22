"""Tests for jikoku_fitness.py — JIKOKU performance fitness evaluators."""

from __future__ import annotations

from dharma_swarm.jikoku_fitness import (
    evaluate_performance_improvement,
    evaluate_utilization_improvement,
)


# ---------------------------------------------------------------------------
# evaluate_performance_improvement
# ---------------------------------------------------------------------------


class TestEvaluatePerformanceImprovement:
    def test_2x_speedup_is_max(self):
        """2x speedup → 1.0."""
        assert evaluate_performance_improvement(100.0, 50.0) == 1.0

    def test_greater_than_2x_clamps(self):
        """3x speedup → still 1.0."""
        assert evaluate_performance_improvement(300.0, 100.0) == 1.0

    def test_no_change(self):
        """Same time → speedup=1.0 → (1.0-0.9)/1.1 ≈ 0.09."""
        score = evaluate_performance_improvement(100.0, 100.0)
        assert 0.08 < score < 0.11

    def test_10pct_regression_is_zero(self):
        """10% slower → speedup=0.91 → barely above 0."""
        score = evaluate_performance_improvement(100.0, 110.0)
        assert score >= 0.0
        assert score < 0.02

    def test_large_regression_is_zero(self):
        """50% slower → 0.0."""
        assert evaluate_performance_improvement(100.0, 150.0) == 0.0

    def test_1_5x_speedup(self):
        """1.5x speedup → (1.5-0.9)/1.1 ≈ 0.545."""
        score = evaluate_performance_improvement(150.0, 100.0)
        assert 0.54 < score < 0.56

    def test_zero_test_time_returns_neutral(self):
        """Division by zero protection."""
        assert evaluate_performance_improvement(100.0, 0.0) == 0.5

    def test_negative_test_time_returns_neutral(self):
        assert evaluate_performance_improvement(100.0, -10.0) == 0.5

    def test_result_bounded(self):
        """All results should be in [0, 1]."""
        for baseline, test in [(1, 1000), (1000, 1), (100, 100), (50, 200)]:
            score = evaluate_performance_improvement(float(baseline), float(test))
            assert 0.0 <= score <= 1.0, f"Out of bounds for ({baseline}, {test}): {score}"


# ---------------------------------------------------------------------------
# evaluate_utilization_improvement
# ---------------------------------------------------------------------------


class TestEvaluateUtilizationImprovement:
    def test_no_change(self):
        """Same utilization → 0.5."""
        assert evaluate_utilization_improvement(100.0, 100.0) == 0.5

    def test_100pct_improvement(self):
        """+100% improvement → 1.0."""
        assert evaluate_utilization_improvement(100.0, 200.0) == 1.0

    def test_100pct_degradation(self):
        """-100% degradation → 0.0."""
        assert evaluate_utilization_improvement(200.0, 100.0) == 0.0

    def test_large_improvement_clamps(self):
        """+200% improvement → still 1.0."""
        assert evaluate_utilization_improvement(100.0, 300.0) == 1.0

    def test_large_degradation_clamps(self):
        """-200% degradation → still 0.0."""
        assert evaluate_utilization_improvement(300.0, 100.0) == 0.0

    def test_moderate_improvement(self):
        """+50% → 0.75."""
        score = evaluate_utilization_improvement(100.0, 150.0)
        assert 0.74 < score < 0.76

    def test_moderate_degradation(self):
        """-50% → 0.25."""
        score = evaluate_utilization_improvement(150.0, 100.0)
        assert 0.24 < score < 0.26

    def test_zero_to_zero(self):
        """0→0 is no change → 0.5."""
        assert evaluate_utilization_improvement(0.0, 0.0) == 0.5

    def test_result_bounded(self):
        for baseline, test in [(0, 500), (500, 0), (100, 100), (0, 0)]:
            score = evaluate_utilization_improvement(float(baseline), float(test))
            assert 0.0 <= score <= 1.0, f"Out of bounds for ({baseline}, {test}): {score}"
