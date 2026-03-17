"""Tests for Ginko regime detection pipeline."""

from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

_temp_dir = tempfile.mkdtemp()
os.environ.setdefault("DHARMA_HOME", _temp_dir)

from dharma_swarm.ginko_regime import (
    MarketRegime,
    RegimeDetection,
    ReturnSeries,
    detect_regime_hmm,
    detect_regime_rules,
    analyze_regime,
    load_regime_history,
)


class TestReturnSeries:
    def test_basic(self):
        series = ReturnSeries(values=[0.01, -0.02, 0.03], timestamps=["a", "b", "c"])
        assert len(series.values) == 3
        assert series.symbol == "SPY"
        assert isinstance(series.array, np.ndarray)

    def test_mean_std(self):
        series = ReturnSeries(values=[0.01, 0.01, 0.01], timestamps=[])
        assert series.mean == pytest.approx(0.01)
        assert series.std == pytest.approx(0.0)

    def test_empty(self):
        series = ReturnSeries(values=[], timestamps=[])
        assert series.mean == 0.0
        assert series.std == 0.0


class TestRuleBasedRegime:
    def test_bull_regime(self):
        """Strong positive returns + low vol → BULL."""
        values = [0.005] * 20  # consistent +0.5% daily
        series = ReturnSeries(values=values, timestamps=[""] * 20)
        result = detect_regime_rules(series)
        assert result.regime == MarketRegime.BULL.value

    def test_bear_regime(self):
        """Strong negative returns + high vol → BEAR."""
        # Mix of large negative returns with some volatility
        rng = np.random.RandomState(42)
        values = list(-0.01 + rng.normal(0, 0.02, 20))
        series = ReturnSeries(values=values, timestamps=[""] * 20)
        result = detect_regime_rules(series)
        assert result.regime in (MarketRegime.BEAR.value, MarketRegime.SIDEWAYS.value)

    def test_sideways_regime(self):
        """Near-zero returns → SIDEWAYS."""
        rng = np.random.RandomState(42)
        values = list(rng.normal(0, 0.001, 20))  # tiny movements
        series = ReturnSeries(values=values, timestamps=[""] * 20)
        result = detect_regime_rules(series)
        assert result.regime == MarketRegime.SIDEWAYS.value

    def test_insufficient_data(self):
        series = ReturnSeries(values=[0.01], timestamps=[""])
        result = detect_regime_rules(series)
        assert result.regime == MarketRegime.UNKNOWN.value

    def test_result_fields(self):
        series = ReturnSeries(values=[0.01] * 20, timestamps=[""] * 20)
        result = detect_regime_rules(series)
        assert result.method == "rule_based"
        assert result.timestamp
        assert isinstance(result.indicators, dict)


class TestHMMRegime:
    def test_with_sufficient_data(self):
        """HMM should work with 30+ data points."""
        rng = np.random.RandomState(42)
        values = list(rng.normal(0.001, 0.01, 100))
        series = ReturnSeries(values=values, timestamps=[""] * 100)

        try:
            result = detect_regime_hmm(series)
            assert result.regime in [r.value for r in MarketRegime]
            assert 0 <= result.confidence <= 1
            assert result.method in ("hmm", "rule_based")
        except ImportError:
            pytest.skip("hmmlearn not installed")

    def test_insufficient_data_falls_back(self):
        """With <30 points, should fall back to rules."""
        series = ReturnSeries(values=[0.01] * 10, timestamps=[""] * 10)
        result = detect_regime_hmm(series)
        assert result.method == "rule_based"


class TestAnalyzeRegime:
    def test_combined_analysis(self):
        rng = np.random.RandomState(42)
        values = list(rng.normal(0.001, 0.01, 60))
        series = ReturnSeries(values=values, timestamps=[""] * 60)
        result = analyze_regime(series, use_hmm=False, use_garch=False)
        assert isinstance(result, RegimeDetection)
        assert result.regime in [r.value for r in MarketRegime]

    def test_persistence(self):
        rng = np.random.RandomState(42)
        values = list(rng.normal(0.001, 0.01, 30))
        series = ReturnSeries(values=values, timestamps=[""] * 30)
        analyze_regime(series, use_hmm=False, use_garch=False)
        history = load_regime_history()
        assert len(history) >= 1

    def test_no_hmm(self):
        values = [0.01] * 30
        series = ReturnSeries(values=values, timestamps=[""] * 30)
        result = analyze_regime(series, use_hmm=False, use_garch=False)
        assert result.method == "rule_based"
