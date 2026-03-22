"""Tests for ginko_risk.py — portfolio-level risk metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from dharma_swarm.ginko_risk import (
    DEFAULT_SECTOR_MAP,
    RiskReport,
    _classify_risk_score,
    _covariance,
    _mean,
    _pearson_correlation,
    _percentile,
    _std,
    _variance,
    assess_portfolio_risk,
    check_sector_exposure,
    compute_concentration_risk,
    compute_correlation_matrix,
    compute_cvar,
    compute_portfolio_beta,
    compute_sector_exposures,
    compute_var,
    format_risk_report,
)


# ---------------------------------------------------------------------------
# Fake position for tests
# ---------------------------------------------------------------------------


@dataclass
class _FakePos:
    current_price: float
    quantity: float
    entry_price: float = 0.0


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestDefaultSectorMap:
    def test_has_entries(self):
        assert len(DEFAULT_SECTOR_MAP) >= 50

    def test_known_tickers(self):
        assert DEFAULT_SECTOR_MAP["AAPL"] == "Technology"
        assert DEFAULT_SECTOR_MAP["JPM"] == "Financials"
        assert DEFAULT_SECTOR_MAP["XOM"] == "Energy"


# ---------------------------------------------------------------------------
# RiskReport
# ---------------------------------------------------------------------------


class TestRiskReport:
    def test_defaults(self):
        r = RiskReport()
        assert r.var_95 == 0.0
        assert r.risk_score == "LOW"

    def test_to_dict(self):
        r = RiskReport(var_95=1234.56, risk_score="HIGH", num_positions=5)
        d = r.to_dict()
        assert d["var_95"] == 1234.56
        assert d["risk_score"] == "HIGH"
        assert d["num_positions"] == 5

    def test_to_dict_rounds(self):
        r = RiskReport(var_95=1000.123456, portfolio_beta=1.23456789)
        d = r.to_dict()
        assert d["var_95"] == 1000.12
        assert d["portfolio_beta"] == 1.2346


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------


class TestMean:
    def test_basic(self):
        assert _mean([1.0, 2.0, 3.0]) == 2.0

    def test_empty(self):
        assert _mean([]) == 0.0

    def test_single(self):
        assert _mean([5.0]) == 5.0


class TestVariance:
    def test_basic(self):
        # [1, 2, 3] -> mean=2, var = ((1+0+1)/2) = 1.0
        assert abs(_variance([1.0, 2.0, 3.0]) - 1.0) < 0.001

    def test_single(self):
        assert _variance([5.0]) == 0.0

    def test_empty(self):
        assert _variance([]) == 0.0

    def test_ddof_zero(self):
        # Population variance
        result = _variance([1.0, 2.0, 3.0], ddof=0)
        assert abs(result - 2.0 / 3.0) < 0.001


class TestStd:
    def test_basic(self):
        assert abs(_std([1.0, 2.0, 3.0]) - 1.0) < 0.001

    def test_constant(self):
        assert _std([5.0, 5.0, 5.0]) == 0.0

    def test_empty(self):
        assert _std([]) == 0.0


class TestCovariance:
    def test_positive(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert _covariance(x, y) > 0

    def test_negative(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]
        assert _covariance(x, y) < 0

    def test_short_series(self):
        assert _covariance([1.0], [2.0]) == 0.0


class TestPearsonCorrelation:
    def test_perfect_positive(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert abs(_pearson_correlation(x, y) - 1.0) < 0.001

    def test_perfect_negative(self):
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [10.0, 8.0, 6.0, 4.0, 2.0]
        assert abs(_pearson_correlation(x, y) - (-1.0)) < 0.001

    def test_zero_std(self):
        x = [5.0, 5.0, 5.0]
        y = [1.0, 2.0, 3.0]
        assert _pearson_correlation(x, y) == 0.0

    def test_short_series(self):
        assert _pearson_correlation([1.0], [2.0]) == 0.0


class TestPercentile:
    def test_median(self):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert abs(_percentile(vals, 50) - 3.0) < 0.001

    def test_5th(self):
        vals = list(range(100))
        result = _percentile([float(v) for v in vals], 5)
        assert abs(result - 4.95) < 0.1

    def test_empty(self):
        assert _percentile([], 50) == 0.0

    def test_single(self):
        assert _percentile([42.0], 50) == 42.0


# ---------------------------------------------------------------------------
# VaR and CVaR
# ---------------------------------------------------------------------------


class TestComputeVar:
    def test_basic(self):
        # Uniform daily returns from -5% to +5%
        returns = [i * 0.01 for i in range(-5, 6)]  # 11 returns
        var = compute_var(returns, confidence=0.95, portfolio_value=100_000)
        assert var > 0

    def test_insufficient_data(self):
        assert compute_var([0.01, -0.01], confidence=0.95) == 0.0

    def test_all_positive(self):
        returns = [0.01] * 10
        var = compute_var(returns, confidence=0.95, portfolio_value=100_000)
        # VaR is abs of percentile * portfolio_value — should be small
        assert var >= 0

    def test_scales_with_portfolio(self):
        returns = [i * 0.01 for i in range(-5, 6)]
        var_small = compute_var(returns, portfolio_value=50_000)
        var_big = compute_var(returns, portfolio_value=100_000)
        assert abs(var_big - 2 * var_small) < 1.0


class TestComputeCvar:
    def test_basic(self):
        returns = [i * 0.01 for i in range(-5, 6)]
        cvar = compute_cvar(returns, confidence=0.95, portfolio_value=100_000)
        assert cvar > 0

    def test_cvar_exceeds_var(self):
        # CVaR (expected shortfall) >= VaR by definition
        returns = [i * 0.01 for i in range(-10, 11)]
        var = compute_var(returns, confidence=0.95, portfolio_value=100_000)
        cvar = compute_cvar(returns, confidence=0.95, portfolio_value=100_000)
        assert cvar >= var - 1.0  # small tolerance

    def test_insufficient_data(self):
        assert compute_cvar([0.01, -0.01], confidence=0.95) == 0.0


# ---------------------------------------------------------------------------
# Correlation matrix
# ---------------------------------------------------------------------------


class TestComputeCorrelationMatrix:
    def test_self_correlation(self):
        prices = {"A": [100, 101, 102, 103, 104, 105]}
        matrix = compute_correlation_matrix(prices)
        assert abs(matrix["A"]["A"] - 1.0) < 0.01

    def test_two_symbols(self):
        prices = {
            "A": [100, 102, 104, 106, 108, 110],
            "B": [50, 51, 52, 53, 54, 55],
        }
        matrix = compute_correlation_matrix(prices)
        assert "A" in matrix
        assert "B" in matrix["A"]
        # Both trending up — should be highly correlated
        assert matrix["A"]["B"] > 0.9

    def test_insufficient_data(self):
        prices = {"A": [100, 101]}  # < 5 observations
        matrix = compute_correlation_matrix(prices)
        assert matrix == {}

    def test_empty(self):
        assert compute_correlation_matrix({}) == {}


# ---------------------------------------------------------------------------
# Beta
# ---------------------------------------------------------------------------


class TestComputePortfolioBeta:
    def test_identical_series(self):
        returns = [0.01, -0.02, 0.015, -0.01, 0.005]
        beta = compute_portfolio_beta(returns, returns)
        assert abs(beta - 1.0) < 0.01

    def test_double_volatility(self):
        bench = [0.01, -0.02, 0.015, -0.01, 0.005]
        port = [r * 2 for r in bench]
        beta = compute_portfolio_beta(port, bench)
        assert abs(beta - 2.0) < 0.1

    def test_insufficient_data(self):
        assert compute_portfolio_beta([0.01], [0.01]) == 0.0

    def test_zero_benchmark_variance(self):
        port = [0.01, -0.01, 0.02, -0.02, 0.01]
        bench = [0.0, 0.0, 0.0, 0.0, 0.0]
        assert compute_portfolio_beta(port, bench) == 0.0


# ---------------------------------------------------------------------------
# Sector exposure
# ---------------------------------------------------------------------------


class TestCheckSectorExposure:
    def test_no_positions(self):
        assert check_sector_exposure({}) == []

    def test_within_limits(self):
        positions = {
            "AAPL": _FakePos(current_price=150, quantity=10),
            "JPM": _FakePos(current_price=200, quantity=10),
            "XOM": _FakePos(current_price=100, quantity=10),
        }
        warnings = check_sector_exposure(positions, max_pct=0.50)
        assert warnings == []

    def test_exceeds_limit(self):
        # All in tech
        positions = {
            "AAPL": _FakePos(current_price=150, quantity=100),
            "MSFT": _FakePos(current_price=300, quantity=50),
            "JPM": _FakePos(current_price=200, quantity=1),  # tiny
        }
        warnings = check_sector_exposure(positions, max_pct=0.30)
        assert len(warnings) >= 1
        assert "Technology" in warnings[0]


class TestComputeSectorExposures:
    def test_basic(self):
        positions = {
            "AAPL": _FakePos(current_price=100, quantity=10),  # 1000 tech
            "JPM": _FakePos(current_price=100, quantity=10),   # 1000 fin
        }
        exposures = compute_sector_exposures(positions)
        assert abs(exposures["Technology"] - 0.5) < 0.01
        assert abs(exposures["Financials"] - 0.5) < 0.01

    def test_empty(self):
        assert compute_sector_exposures({}) == {}


# ---------------------------------------------------------------------------
# Concentration risk (HHI)
# ---------------------------------------------------------------------------


class TestComputeConcentrationRisk:
    def test_single_position(self):
        positions = {"AAPL": _FakePos(current_price=150, quantity=10)}
        assert abs(compute_concentration_risk(positions) - 1.0) < 0.001

    def test_equal_positions(self):
        positions = {
            "AAPL": _FakePos(current_price=100, quantity=10),
            "MSFT": _FakePos(current_price=100, quantity=10),
            "JPM": _FakePos(current_price=100, quantity=10),
            "XOM": _FakePos(current_price=100, quantity=10),
        }
        # 4 equal positions: HHI = 4 * (0.25)^2 = 0.25
        hhi = compute_concentration_risk(positions)
        assert abs(hhi - 0.25) < 0.001

    def test_empty(self):
        assert compute_concentration_risk({}) == 0.0


# ---------------------------------------------------------------------------
# Risk classification
# ---------------------------------------------------------------------------


class TestClassifyRiskScore:
    def test_critical_var(self):
        assert _classify_risk_score(0.06, 0.2, 0.2) == "CRITICAL"

    def test_critical_concentration(self):
        assert _classify_risk_score(0.01, 0.6, 0.2) == "CRITICAL"

    def test_high_var(self):
        assert _classify_risk_score(0.04, 0.2, 0.2) == "HIGH"

    def test_high_sector(self):
        assert _classify_risk_score(0.01, 0.2, 0.45) == "HIGH"

    def test_medium_var(self):
        assert _classify_risk_score(0.02, 0.2, 0.2) == "MEDIUM"

    def test_medium_concentration(self):
        assert _classify_risk_score(0.01, 0.35, 0.2) == "MEDIUM"

    def test_low(self):
        assert _classify_risk_score(0.01, 0.2, 0.2) == "LOW"


# ---------------------------------------------------------------------------
# Master assessment
# ---------------------------------------------------------------------------


class TestAssessPortfolioRisk:
    def test_basic(self):
        positions = {
            "AAPL": _FakePos(current_price=150, quantity=20),
            "JPM": _FakePos(current_price=200, quantity=15),
        }
        returns = [0.01 * ((-1) ** i) for i in range(30)]
        report = assess_portfolio_risk(
            positions=positions,
            daily_returns=returns,
            portfolio_value=100_000,
        )
        assert isinstance(report, RiskReport)
        assert report.num_positions == 2
        assert report.portfolio_value == 100_000
        assert report.risk_score in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_with_benchmark(self):
        positions = {"AAPL": _FakePos(current_price=150, quantity=10)}
        returns = [0.005 * ((-1) ** i) for i in range(30)]
        bench = [0.003 * ((-1) ** i) for i in range(30)]
        report = assess_portfolio_risk(
            positions=positions,
            daily_returns=returns,
            portfolio_value=50_000,
            benchmark_returns=bench,
        )
        assert report.portfolio_beta != 0.0

    def test_with_price_histories(self):
        positions = {
            "AAPL": _FakePos(current_price=150, quantity=10),
            "MSFT": _FakePos(current_price=300, quantity=5),
        }
        returns = [0.01 * ((-1) ** i) for i in range(20)]
        prices = {
            "AAPL": [150 + i for i in range(20)],
            "MSFT": [300 + i * 2 for i in range(20)],
        }
        report = assess_portfolio_risk(
            positions=positions,
            daily_returns=returns,
            portfolio_value=100_000,
            price_histories=prices,
        )
        assert len(report.correlation_matrix) == 2

    def test_empty_positions(self):
        returns = [0.01] * 10
        report = assess_portfolio_risk(
            positions={},
            daily_returns=returns,
            portfolio_value=100_000,
        )
        assert report.num_positions == 0
        assert report.concentration_risk == 0.0


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


class TestFormatRiskReport:
    def test_contains_header(self):
        r = RiskReport(portfolio_value=100_000, risk_score="MEDIUM", num_positions=3)
        report = format_risk_report(r)
        assert "PORTFOLIO RISK REPORT" in report
        assert "MEDIUM" in report

    def test_contains_var(self):
        r = RiskReport(var_95=2500.0, var_99=4000.0, cvar_95=3500.0, portfolio_value=100_000)
        report = format_risk_report(r)
        assert "Value at Risk" in report
        assert "$2,500.00" in report

    def test_sector_warnings(self):
        r = RiskReport(
            portfolio_value=100_000,
            sector_warnings=["Sector 'Technology' at 55% exceeds 30% limit"],
        )
        report = format_risk_report(r)
        assert "SECTOR WARNINGS" in report
        assert "Technology" in report

    def test_correlation_matrix_display(self):
        r = RiskReport(
            portfolio_value=100_000,
            correlation_matrix={"A": {"A": 1.0, "B": 0.8}, "B": {"A": 0.8, "B": 1.0}},
        )
        report = format_risk_report(r)
        assert "Correlation Matrix" in report

    def test_returns_string(self):
        assert isinstance(format_risk_report(RiskReport()), str)

    def test_risk_classification_section(self):
        r = RiskReport(portfolio_value=100_000, risk_score="HIGH")
        report = format_risk_report(r)
        assert "Risk Classification" in report
        assert "CRITICAL" in report  # threshold explanation
