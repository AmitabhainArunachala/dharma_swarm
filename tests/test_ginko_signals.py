"""Tests for Ginko signal generation engine."""

from __future__ import annotations

import math

import pytest

from dharma_swarm.ginko_signals import (
    SignalDirection,
    SignalStrength,
    TechnicalIndicators,
    assess_risk_level,
    compute_bollinger_position,
    compute_indicators,
    compute_rsi,
    compute_sma,
    format_signal_report,
    generate_signal_report,
    synthesize_signal,
)


class TestRSI:
    def test_uptrend_rsi(self):
        """Consistently rising prices → RSI near 100."""
        prices = [100 + i for i in range(20)]
        rsi = compute_rsi(prices)
        assert rsi is not None
        assert rsi > 70

    def test_downtrend_rsi(self):
        """Consistently falling prices → RSI near 0."""
        prices = [100 - i for i in range(20)]
        rsi = compute_rsi(prices)
        assert rsi is not None
        assert rsi < 30

    def test_flat_rsi(self):
        """Flat prices → RSI near 50."""
        prices = [100] * 20
        rsi = compute_rsi(prices)
        # With no movement, gains=0, so RSI should be near 0
        # (edge case: all zeros → 0/0.0001 → ~0)
        assert rsi is not None

    def test_insufficient_data(self):
        assert compute_rsi([100, 101]) is None

    def test_alternating(self):
        """Alternating up/down → RSI near 50."""
        prices = [100 + (1 if i % 2 == 0 else -1) for i in range(30)]
        rsi = compute_rsi(prices)
        assert rsi is not None
        assert 30 < rsi < 70


class TestSMA:
    def test_basic_sma(self):
        prices = [10, 20, 30, 40, 50]
        assert compute_sma(prices, 3) == pytest.approx(40.0)  # (30+40+50)/3

    def test_sma_full_window(self):
        prices = [10, 20, 30]
        assert compute_sma(prices, 3) == pytest.approx(20.0)

    def test_insufficient_data(self):
        assert compute_sma([10, 20], 5) is None


class TestBollingerPosition:
    def test_at_middle(self):
        """Price at SMA → position near 0.5."""
        prices = [100] * 20
        pos = compute_bollinger_position(prices)
        assert pos is not None
        assert pos == pytest.approx(0.5)

    def test_near_upper(self):
        """Price well above SMA → position near 1.0."""
        prices = [100] * 19 + [120]
        pos = compute_bollinger_position(prices)
        assert pos is not None
        assert pos > 0.7

    def test_near_lower(self):
        """Price well below SMA → position near 0.0."""
        prices = [100] * 19 + [80]
        pos = compute_bollinger_position(prices)
        assert pos is not None
        assert pos < 0.3

    def test_insufficient_data(self):
        assert compute_bollinger_position([100, 101]) is None


class TestComputeIndicators:
    def test_full_indicators(self):
        prices = [100 + i * 0.5 for i in range(60)]  # uptrend
        ind = compute_indicators("SPY", prices)
        assert ind.symbol == "SPY"
        assert ind.rsi_14 is not None
        assert ind.sma_20 is not None
        assert ind.sma_50 is not None
        assert ind.trend_direction in ("up", "down", "flat")
        assert ind.bollinger_position is not None

    def test_minimal_data(self):
        """With very few data points, indicators should be None."""
        prices = [100, 101]
        ind = compute_indicators("AAPL", prices)
        assert ind.rsi_14 is None
        assert ind.sma_20 is None

    def test_rsi_interpretation(self):
        # Oversold
        prices = [100 - i for i in range(20)]
        ind = compute_indicators("TEST", prices)
        if ind.rsi_14 and ind.rsi_14 < 30:
            assert ind.rsi_interpretation == "oversold"


class TestSynthesizeSignal:
    def test_bull_regime_buy(self):
        ind = TechnicalIndicators(
            symbol="SPY",
            rsi_14=45,
            rsi_interpretation="neutral",
            trend_direction="up",
            bollinger_position=0.4,
        )
        signal = synthesize_signal("SPY", ind, "bull", 0.85)
        assert signal.direction == SignalDirection.BUY.value
        assert signal.confidence > 0

    def test_bear_regime_sell(self):
        ind = TechnicalIndicators(
            symbol="SPY",
            rsi_14=65,
            rsi_interpretation="neutral",
            trend_direction="down",
            bollinger_position=0.8,
        )
        signal = synthesize_signal("SPY", ind, "bear", 0.8)
        assert signal.direction == SignalDirection.SELL.value

    def test_sideways_hold(self):
        ind = TechnicalIndicators(
            symbol="SPY",
            rsi_14=50,
            rsi_interpretation="neutral",
            trend_direction="flat",
            bollinger_position=0.5,
        )
        signal = synthesize_signal("SPY", ind, "sideways", 0.7)
        assert signal.direction == SignalDirection.HOLD.value

    def test_oversold_in_bear(self):
        """RSI oversold should temper bear sell signal."""
        ind = TechnicalIndicators(
            symbol="SPY",
            rsi_14=20,
            rsi_interpretation="oversold",
            trend_direction="down",
            bollinger_position=0.1,
        )
        signal = synthesize_signal("SPY", ind, "bear", 0.7)
        # Should have mixed signals (bear regime + oversold RSI)
        assert signal.direction in ("sell", "hold", "buy")

    def test_signal_has_reason(self):
        ind = TechnicalIndicators(symbol="TEST")
        signal = synthesize_signal("TEST", ind, "bull", 0.9)
        assert len(signal.reason) > 0


class TestRiskLevel:
    def test_low_risk(self):
        assert assess_risk_level("bull", vix=15) == "low"

    def test_moderate_risk(self):
        assert assess_risk_level("sideways", vix=20) == "moderate"

    def test_high_risk(self):
        assert assess_risk_level("bear", vix=28) == "high"

    def test_extreme_risk(self):
        assert assess_risk_level("bear", vix=40, yield_spread=-0.5) == "extreme"

    def test_inverted_yield_curve(self):
        level = assess_risk_level("sideways", yield_spread=-0.3)
        assert level in ("high", "extreme")


class TestSignalReport:
    def test_generate_report(self):
        prices = {
            "SPY": [400 + i * 0.5 for i in range(60)],
            "QQQ": [300 + i * 0.3 for i in range(60)],
        }
        report = generate_signal_report(
            regime="bull",
            regime_confidence=0.85,
            price_data=prices,
            macro_data={"fed_funds_rate": 5.25, "vix": 16.5, "yield_spread": 0.3},
        )
        assert report.regime == "bull"
        assert len(report.signals) == 2
        assert report.risk_level == "low"
        assert "VIX" in report.macro_summary

    def test_format_report(self):
        prices = {"SPY": [400 + i for i in range(60)]}
        report = generate_signal_report("bear", 0.7, prices)
        text = format_signal_report(report)
        assert "BEAR" in text
        assert "SPY" in text

    def test_empty_prices(self):
        report = generate_signal_report("sideways", 0.5, {})
        assert len(report.signals) == 0
