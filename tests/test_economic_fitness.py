"""Tests for dharma_swarm.economic_fitness."""

from __future__ import annotations

import pytest

from dharma_swarm.economic_fitness import (
    EconomicMetrics,
    evaluate_economic_fitness,
    format_economic_report,
)


# ---------------------------------------------------------------------------
# EconomicMetrics.annual_value
# ---------------------------------------------------------------------------

class TestEconomicMetricsAnnualValue:
    def test_all_zeros_maintenance_cost(self) -> None:
        m = EconomicMetrics(api_cost_saved_usd=0, time_saved_ms=0, throughput_gain_pct=0, maintenance_cost_usd=0)
        assert m.annual_value() == 0.0

    def test_positive_api_savings_give_positive_value(self) -> None:
        m = EconomicMetrics(api_cost_saved_usd=0.01, time_saved_ms=0, throughput_gain_pct=0, maintenance_cost_usd=0)
        assert m.annual_value(usage_freq_per_day=100) > 0

    def test_maintenance_cost_reduces_annual_value(self) -> None:
        without_cost = EconomicMetrics(api_cost_saved_usd=0.01, time_saved_ms=100, throughput_gain_pct=5, maintenance_cost_usd=0)
        with_cost = EconomicMetrics(api_cost_saved_usd=0.01, time_saved_ms=100, throughput_gain_pct=5, maintenance_cost_usd=1000)
        assert with_cost.annual_value() < without_cost.annual_value()

    def test_usage_frequency_scales_value(self) -> None:
        m = EconomicMetrics(api_cost_saved_usd=0.001, time_saved_ms=10, throughput_gain_pct=1, maintenance_cost_usd=0)
        low = m.annual_value(usage_freq_per_day=10)
        high = m.annual_value(usage_freq_per_day=1000)
        assert high > low

    def test_negative_time_savings_still_computes(self) -> None:
        # Regression (slower)
        m = EconomicMetrics(api_cost_saved_usd=0, time_saved_ms=-200, throughput_gain_pct=-10, maintenance_cost_usd=0)
        # Should return a negative value (cost) — or at least compute without error
        value = m.annual_value()
        assert isinstance(value, float)


# ---------------------------------------------------------------------------
# evaluate_economic_fitness
# ---------------------------------------------------------------------------

class TestEvaluateEconomicFitness:
    def test_speedup_and_fewer_calls_gives_high_fitness(self) -> None:
        baseline = {"wall_clock_ms": 1000, "api_calls": 5}
        test = {"wall_clock_ms": 500, "api_calls": 3}
        score, metrics = evaluate_economic_fitness(baseline, test)
        assert score > 0.5
        assert isinstance(metrics, EconomicMetrics)

    def test_no_change_gives_neutral_fitness(self) -> None:
        baseline = {"wall_clock_ms": 500, "api_calls": 2}
        test = {"wall_clock_ms": 500, "api_calls": 2}
        score, metrics = evaluate_economic_fitness(baseline, test)
        assert abs(score - 0.5) < 0.05  # near 0.5

    def test_regression_gives_lower_fitness(self) -> None:
        baseline = {"wall_clock_ms": 300, "api_calls": 2}
        test = {"wall_clock_ms": 600, "api_calls": 4}
        score_good, _ = evaluate_economic_fitness(
            {"wall_clock_ms": 600, "api_calls": 4},
            {"wall_clock_ms": 300, "api_calls": 2},
        )
        score_bad, _ = evaluate_economic_fitness(baseline, test)
        assert score_good > score_bad

    def test_score_clamped_to_0_1(self) -> None:
        # Extreme improvement
        baseline = {"wall_clock_ms": 100_000, "api_calls": 1000}
        test = {"wall_clock_ms": 1, "api_calls": 0}
        score, _ = evaluate_economic_fitness(baseline, test)
        assert 0.0 <= score <= 1.0

    def test_extreme_regression_clamps_to_zero(self) -> None:
        baseline = {"wall_clock_ms": 1, "api_calls": 0}
        test = {"wall_clock_ms": 100_000, "api_calls": 1000}
        score, _ = evaluate_economic_fitness(baseline, test)
        assert score >= 0.0

    def test_custom_api_costs(self) -> None:
        baseline = {"wall_clock_ms": 500, "api_calls": 5}
        test = {"wall_clock_ms": 400, "api_calls": 3}
        score_default, _ = evaluate_economic_fitness(baseline, test)
        score_custom, _ = evaluate_economic_fitness(baseline, test, api_costs={"custom_provider": 1.0})
        # With much higher API cost per call, savings should be larger
        assert score_custom >= score_default

    def test_diff_size_affects_maintenance_cost(self) -> None:
        big_diff = "line\n" * 1000
        small_diff = "line\n"
        baseline = {"wall_clock_ms": 500, "api_calls": 2}
        test_big = {"wall_clock_ms": 400, "api_calls": 2, "diff": big_diff}
        test_small = {"wall_clock_ms": 400, "api_calls": 2, "diff": small_diff}
        _, metrics_big = evaluate_economic_fitness(baseline, test_big)
        _, metrics_small = evaluate_economic_fitness(baseline, test_small)
        assert metrics_big.maintenance_cost_usd > metrics_small.maintenance_cost_usd

    def test_missing_keys_use_zero_defaults(self) -> None:
        # Should not raise even if dict keys are absent
        score, metrics = evaluate_economic_fitness({}, {})
        assert isinstance(score, float)
        assert isinstance(metrics, EconomicMetrics)

    def test_zero_test_time_avoids_division(self) -> None:
        baseline = {"wall_clock_ms": 0, "api_calls": 0}
        test = {"wall_clock_ms": 0, "api_calls": 0}
        score, metrics = evaluate_economic_fitness(baseline, test)
        assert metrics.throughput_gain_pct == 0.0


# ---------------------------------------------------------------------------
# format_economic_report
# ---------------------------------------------------------------------------

class TestFormatEconomicReport:
    def test_report_contains_section_headers(self) -> None:
        m = EconomicMetrics(api_cost_saved_usd=0.05, time_saved_ms=200, throughput_gain_pct=10, maintenance_cost_usd=100)
        report = format_economic_report(m, usage_freq=1000)
        assert "API Cost Savings" in report
        assert "Time Savings" in report
        assert "Throughput Gain" in report
        assert "Maintenance Cost" in report
        assert "Net Annual Value" in report

    def test_profitable_report_shows_status(self) -> None:
        m = EconomicMetrics(api_cost_saved_usd=1.0, time_saved_ms=1000, throughput_gain_pct=50, maintenance_cost_usd=0)
        report = format_economic_report(m, usage_freq=500)
        assert "PROFITABLE" in report

    def test_costly_report_shows_status(self) -> None:
        m = EconomicMetrics(api_cost_saved_usd=-0.05, time_saved_ms=-500, throughput_gain_pct=-20, maintenance_cost_usd=100_000)
        report = format_economic_report(m, usage_freq=100)
        assert "COSTLY" in report

    def test_report_is_string(self) -> None:
        m = EconomicMetrics(api_cost_saved_usd=0, time_saved_ms=0, throughput_gain_pct=0, maintenance_cost_usd=0)
        report = format_economic_report(m)
        assert isinstance(report, str)
        assert len(report) > 0
