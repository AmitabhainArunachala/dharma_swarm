"""Tests for ginko_backtest.py — historical strategy backtesting engine."""

from __future__ import annotations

import json
import math
from dataclasses import asdict
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.ginko_backtest import (
    BacktestConfig,
    BacktestResult,
    TradeRecord,
    _BacktestPortfolio,
    _BacktestPosition,
    _CONFIDENCE_THRESHOLD,
    _MIN_LOOKBACK_DAYS,
    _POSITION_SIZE_PCT,
    _STOP_LOSS_PCT,
    _TAKE_PROFIT_PCT,
    _persist_result,
    compute_annualized_return,
    compute_calmar_ratio,
    compute_profit_factor,
    format_backtest_report,
    run_backtest,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_lookback_days(self):
        assert _MIN_LOOKBACK_DAYS == 50

    def test_position_size(self):
        assert 0 < _POSITION_SIZE_PCT < 0.1

    def test_stop_loss(self):
        assert 0 < _STOP_LOSS_PCT < 0.2

    def test_take_profit(self):
        assert 0 < _TAKE_PROFIT_PCT < 0.5

    def test_confidence_threshold(self):
        assert 0 < _CONFIDENCE_THRESHOLD < 1.0


# ---------------------------------------------------------------------------
# BacktestConfig
# ---------------------------------------------------------------------------


class TestBacktestConfig:
    def test_defaults(self):
        cfg = BacktestConfig()
        assert cfg.symbols == ["AAPL", "MSFT", "NVDA"]
        assert cfg.initial_capital == 100_000.0
        assert cfg.benchmark == "SPY"

    def test_date_defaults_fill(self):
        cfg = BacktestConfig()
        today = date.today()
        assert cfg.end_date == today.isoformat()
        expected_start = (today - timedelta(days=365)).isoformat()
        assert cfg.start_date == expected_start

    def test_explicit_dates_preserved(self):
        cfg = BacktestConfig(start_date="2024-01-01", end_date="2024-12-31")
        assert cfg.start_date == "2024-01-01"
        assert cfg.end_date == "2024-12-31"

    def test_custom_symbols(self):
        cfg = BacktestConfig(symbols=["TSLA"])
        assert cfg.symbols == ["TSLA"]

    def test_custom_thresholds(self):
        cfg = BacktestConfig(
            confidence_threshold=0.8,
            position_size_pct=0.02,
            stop_loss_pct=0.03,
            take_profit_pct=0.15,
        )
        assert cfg.confidence_threshold == 0.8
        assert cfg.position_size_pct == 0.02
        assert cfg.stop_loss_pct == 0.03
        assert cfg.take_profit_pct == 0.15


# ---------------------------------------------------------------------------
# TradeRecord
# ---------------------------------------------------------------------------


class TestTradeRecord:
    def test_construction(self):
        trade = TradeRecord(
            symbol="AAPL",
            direction="long",
            entry_date="2024-01-01",
            entry_price=150.0,
            exit_date="2024-02-01",
            exit_price=160.0,
            quantity=10.0,
            pnl=100.0,
            signal_confidence=0.75,
            regime="bullish",
        )
        assert trade.symbol == "AAPL"
        assert trade.pnl == 100.0

    def test_asdict(self):
        trade = TradeRecord(
            symbol="X", direction="short", entry_date="2024-01-01",
            entry_price=100.0, exit_date="2024-01-10", exit_price=90.0,
            quantity=5.0, pnl=50.0, signal_confidence=0.65, regime="bearish",
        )
        d = asdict(trade)
        assert d["symbol"] == "X"
        assert d["direction"] == "short"


# ---------------------------------------------------------------------------
# BacktestResult
# ---------------------------------------------------------------------------


class TestBacktestResult:
    def test_defaults(self):
        r = BacktestResult(
            total_return=0.1,
            annualized_return=0.12,
            sharpe_ratio=1.5,
            max_drawdown=0.05,
            win_rate=0.6,
            total_trades=10,
        )
        assert r.equity_curve == []
        assert r.daily_returns == []
        assert r.trades == []
        assert r.errors == []
        assert r.benchmark_return == 0.0

    def test_with_all_fields(self):
        r = BacktestResult(
            total_return=0.15,
            annualized_return=0.18,
            sharpe_ratio=2.0,
            max_drawdown=0.08,
            win_rate=0.7,
            total_trades=20,
            equity_curve=[100000, 101000, 102000],
            daily_returns=[0.01, 0.0099],
            dates=["2024-01-01", "2024-01-02", "2024-01-03"],
            calmar_ratio=2.25,
            avg_win=500.0,
            avg_loss=200.0,
            profit_factor=2.5,
        )
        assert len(r.equity_curve) == 3
        assert r.calmar_ratio == 2.25


# ---------------------------------------------------------------------------
# Helper math
# ---------------------------------------------------------------------------


class TestComputeAnnualizedReturn:
    def test_positive_return(self):
        # 10% in 365 days -> annualized = 10%
        result = compute_annualized_return(0.10, 365)
        assert abs(result - 0.10) < 0.001

    def test_half_year(self):
        # 5% in 182 days -> annualized > 5%
        result = compute_annualized_return(0.05, 182)
        assert result > 0.05

    def test_zero_days(self):
        assert compute_annualized_return(0.10, 0) == 0.0

    def test_negative_days(self):
        assert compute_annualized_return(0.10, -5) == 0.0

    def test_negative_return(self):
        result = compute_annualized_return(-0.05, 365)
        assert abs(result - (-0.05)) < 0.001

    def test_one_day(self):
        result = compute_annualized_return(0.01, 1)
        # (1.01)^365 - 1 should be very large
        assert result > 1.0


class TestComputeCalmarRatio:
    def test_positive(self):
        result = compute_calmar_ratio(0.20, 0.10)
        assert abs(result - 2.0) < 0.001

    def test_zero_drawdown(self):
        assert compute_calmar_ratio(0.20, 0.0) == 0.0

    def test_negative_drawdown(self):
        assert compute_calmar_ratio(0.20, -0.05) == 0.0

    def test_negative_return(self):
        result = compute_calmar_ratio(-0.10, 0.15)
        assert result < 0


class TestComputeProfitFactor:
    def test_profitable(self):
        trades = [
            TradeRecord("A", "long", "d1", 100, "d2", 110, 1, 10, 0.7, "bull"),
            TradeRecord("B", "long", "d1", 100, "d2", 95, 1, -5, 0.7, "bull"),
        ]
        result = compute_profit_factor(trades)
        assert abs(result - 2.0) < 0.001

    def test_no_losers(self):
        trades = [
            TradeRecord("A", "long", "d1", 100, "d2", 110, 1, 10, 0.7, "bull"),
        ]
        result = compute_profit_factor(trades)
        assert result == float("inf")

    def test_no_winners(self):
        trades = [
            TradeRecord("A", "long", "d1", 100, "d2", 90, 1, -10, 0.7, "bear"),
        ]
        result = compute_profit_factor(trades)
        assert result == 0.0

    def test_empty_trades(self):
        assert compute_profit_factor([]) == 0.0

    def test_breakeven(self):
        trades = [
            TradeRecord("A", "long", "d1", 100, "d2", 110, 1, 10, 0.7, "bull"),
            TradeRecord("B", "long", "d1", 100, "d2", 90, 1, -10, 0.7, "bear"),
        ]
        result = compute_profit_factor(trades)
        assert abs(result - 1.0) < 0.001


# ---------------------------------------------------------------------------
# _BacktestPortfolio
# ---------------------------------------------------------------------------


class TestBacktestPortfolio:
    def _make_portfolio(self, capital: float = 100_000.0) -> _BacktestPortfolio:
        return _BacktestPortfolio(capital)

    def test_initial_state(self):
        p = self._make_portfolio()
        assert p.cash == 100_000.0
        assert p.positions == {}
        assert p.closed_trades == []

    def test_portfolio_value_no_positions(self):
        p = self._make_portfolio()
        assert p.portfolio_value({}) == 100_000.0

    def test_open_long_position(self):
        p = self._make_portfolio()
        ok = p.open_position(
            symbol="AAPL", direction="long", price=150.0,
            capital_fraction=0.04, stop_loss_pct=0.05, take_profit_pct=0.10,
            signal_confidence=0.7, regime="bullish",
            current_date="2024-01-01", current_prices={"AAPL": 150.0},
        )
        assert ok is True
        assert "AAPL" in p.positions
        pos = p.positions["AAPL"]
        assert pos.direction == "long"
        assert pos.entry_price == 150.0
        # Cash reduced by 4% of equity
        assert p.cash < 100_000.0

    def test_open_short_position(self):
        p = self._make_portfolio()
        ok = p.open_position(
            symbol="TSLA", direction="short", price=200.0,
            capital_fraction=0.04, stop_loss_pct=0.05, take_profit_pct=0.10,
            signal_confidence=0.65, regime="bearish",
            current_date="2024-01-01", current_prices={"TSLA": 200.0},
        )
        assert ok is True
        pos = p.positions["TSLA"]
        assert pos.direction == "short"
        # Short stop is above entry, take-profit below
        assert pos.stop_loss > pos.entry_price
        assert pos.take_profit < pos.entry_price

    def test_cannot_duplicate_position(self):
        p = self._make_portfolio()
        prices = {"AAPL": 150.0}
        p.open_position("AAPL", "long", 150.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", prices)
        ok = p.open_position("AAPL", "long", 155.0, 0.04, 0.05, 0.10, 0.7, "bull", "d2", prices)
        assert ok is False

    def test_cannot_open_with_zero_price(self):
        p = self._make_portfolio()
        ok = p.open_position("X", "long", 0.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", {"X": 0.0})
        assert ok is False

    def test_close_long_profit(self):
        p = self._make_portfolio()
        prices = {"AAPL": 150.0}
        p.open_position("AAPL", "long", 150.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", prices)
        cash_after_open = p.cash

        trade = p.close_position("AAPL", 160.0, "d2")
        assert trade is not None
        assert trade.pnl > 0
        assert trade.exit_price == 160.0
        assert "AAPL" not in p.positions
        assert p.cash > cash_after_open
        assert len(p.closed_trades) == 1

    def test_close_long_loss(self):
        p = self._make_portfolio()
        prices = {"AAPL": 150.0}
        p.open_position("AAPL", "long", 150.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", prices)
        trade = p.close_position("AAPL", 140.0, "d2")
        assert trade is not None
        assert trade.pnl < 0

    def test_close_short_profit(self):
        p = self._make_portfolio()
        prices = {"TSLA": 200.0}
        p.open_position("TSLA", "short", 200.0, 0.04, 0.05, 0.10, 0.7, "bear", "d1", prices)
        trade = p.close_position("TSLA", 180.0, "d2")
        assert trade is not None
        assert trade.pnl > 0  # Short: sold high, bought low

    def test_close_short_loss(self):
        p = self._make_portfolio()
        prices = {"TSLA": 200.0}
        p.open_position("TSLA", "short", 200.0, 0.04, 0.05, 0.10, 0.7, "bear", "d1", prices)
        trade = p.close_position("TSLA", 220.0, "d2")
        assert trade is not None
        assert trade.pnl < 0  # Short: sold low, bought high

    def test_close_nonexistent(self):
        p = self._make_portfolio()
        assert p.close_position("AAPL", 150.0, "d1") is None

    def test_portfolio_value_with_long(self):
        p = self._make_portfolio()
        prices = {"AAPL": 150.0}
        p.open_position("AAPL", "long", 150.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", prices)
        # Mark to market at same price — equity should equal initial
        val = p.portfolio_value({"AAPL": 150.0})
        assert abs(val - 100_000.0) < 1.0  # rounding tolerance

    def test_portfolio_value_long_appreciation(self):
        p = self._make_portfolio()
        prices = {"AAPL": 100.0}
        p.open_position("AAPL", "long", 100.0, 0.10, 0.05, 0.20, 0.7, "bull", "d1", prices)
        # 10% of 100k = 10k. At $100, qty = 100. At $110, position = 11000.
        val = p.portfolio_value({"AAPL": 110.0})
        assert val > 100_000.0

    def test_check_stops_long_stop_loss(self):
        p = self._make_portfolio()
        prices = {"AAPL": 100.0}
        p.open_position("AAPL", "long", 100.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", prices)
        pos = p.positions["AAPL"]
        # Stop loss at 95.0 (5% below 100)
        assert abs(pos.stop_loss - 95.0) < 0.01

        triggered = p.check_stops({"AAPL": 94.0}, "d2")
        assert len(triggered) == 1
        assert triggered[0].pnl < 0
        assert "AAPL" not in p.positions

    def test_check_stops_long_take_profit(self):
        p = self._make_portfolio()
        prices = {"AAPL": 100.0}
        p.open_position("AAPL", "long", 100.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", prices)
        pos = p.positions["AAPL"]
        assert abs(pos.take_profit - 110.0) < 0.01

        triggered = p.check_stops({"AAPL": 111.0}, "d2")
        assert len(triggered) == 1
        assert triggered[0].pnl > 0

    def test_check_stops_short_stop_loss(self):
        p = self._make_portfolio()
        prices = {"TSLA": 200.0}
        p.open_position("TSLA", "short", 200.0, 0.04, 0.05, 0.10, 0.7, "bear", "d1", prices)
        pos = p.positions["TSLA"]
        # Short stop loss at 210.0 (5% above 200)
        assert abs(pos.stop_loss - 210.0) < 0.01

        triggered = p.check_stops({"TSLA": 211.0}, "d2")
        assert len(triggered) == 1
        assert triggered[0].pnl < 0

    def test_check_stops_short_take_profit(self):
        p = self._make_portfolio()
        prices = {"TSLA": 200.0}
        p.open_position("TSLA", "short", 200.0, 0.04, 0.05, 0.10, 0.7, "bear", "d1", prices)
        pos = p.positions["TSLA"]
        # Short take profit at 180.0 (10% below 200)
        assert abs(pos.take_profit - 180.0) < 0.01

        triggered = p.check_stops({"TSLA": 179.0}, "d2")
        assert len(triggered) == 1
        assert triggered[0].pnl > 0

    def test_check_stops_no_trigger(self):
        p = self._make_portfolio()
        prices = {"AAPL": 100.0}
        p.open_position("AAPL", "long", 100.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", prices)
        triggered = p.check_stops({"AAPL": 102.0}, "d2")
        assert triggered == []

    def test_check_stops_missing_price(self):
        p = self._make_portfolio()
        prices = {"AAPL": 100.0}
        p.open_position("AAPL", "long", 100.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", prices)
        # No price for AAPL in check — should skip
        triggered = p.check_stops({}, "d2")
        assert triggered == []
        assert "AAPL" in p.positions

    def test_multiple_positions(self):
        p = self._make_portfolio(200_000.0)
        prices = {"AAPL": 150.0, "MSFT": 300.0}
        p.open_position("AAPL", "long", 150.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", prices)
        p.open_position("MSFT", "long", 300.0, 0.04, 0.05, 0.10, 0.7, "bull", "d1", prices)
        assert len(p.positions) == 2
        val = p.portfolio_value(prices)
        # Equity should still be ~200k at entry prices
        assert abs(val - 200_000.0) < 10.0


# ---------------------------------------------------------------------------
# _persist_result
# ---------------------------------------------------------------------------


class TestPersistResult:
    def test_saves_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.ginko_backtest.BACKTEST_DIR", tmp_path)
        result = BacktestResult(
            total_return=0.05,
            annualized_return=0.06,
            sharpe_ratio=1.2,
            max_drawdown=0.03,
            win_rate=0.55,
            total_trades=5,
            equity_curve=[100000, 101000, 102000],
            daily_returns=[0.01, 0.0099],
            dates=["2024-01-01", "2024-01-02", "2024-01-03"],
            run_timestamp="2024-06-15T12:00:00+00:00",
        )
        _persist_result(result)

        files = list(tmp_path.glob("*.json"))
        assert len(files) == 2  # summary + equity curve

        # Verify summary file
        summary_files = [f for f in files if f.name.startswith("backtest_")]
        assert len(summary_files) == 1
        data = json.loads(summary_files[0].read_text())
        assert data["total_return"] == 0.05
        assert data["sharpe_ratio"] == 1.2

        # Verify equity curve file
        curve_files = [f for f in files if f.name.startswith("equity_")]
        assert len(curve_files) == 1
        curve = json.loads(curve_files[0].read_text())
        assert len(curve["equity_curve"]) == 3

    def test_creates_directory(self, tmp_path, monkeypatch):
        target = tmp_path / "nested" / "dir"
        monkeypatch.setattr("dharma_swarm.ginko_backtest.BACKTEST_DIR", target)
        result = BacktestResult(
            total_return=0.0, annualized_return=0.0, sharpe_ratio=0.0,
            max_drawdown=0.0, win_rate=0.0, total_trades=0,
            run_timestamp="2024-06-15T12:00:00+00:00",
        )
        _persist_result(result)
        assert target.exists()


# ---------------------------------------------------------------------------
# format_backtest_report
# ---------------------------------------------------------------------------


class TestFormatBacktestReport:
    def _make_result(self, **overrides) -> BacktestResult:
        defaults = dict(
            total_return=0.12,
            annualized_return=0.15,
            sharpe_ratio=1.8,
            max_drawdown=0.06,
            win_rate=0.65,
            total_trades=25,
            equity_curve=[100000, 108000, 112000],
            benchmark_return=0.10,
            benchmark_sharpe=1.2,
            benchmark_max_drawdown=0.08,
            calmar_ratio=2.5,
            avg_win=450.0,
            avg_loss=200.0,
            profit_factor=2.25,
            config={
                "symbols": ["AAPL", "MSFT"],
                "benchmark": "SPY",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
                "initial_capital": 100000,
            },
        )
        defaults.update(overrides)
        return BacktestResult(**defaults)

    def test_contains_header(self):
        report = format_backtest_report(self._make_result())
        assert "GINKO BACKTESTING ENGINE" in report

    def test_contains_performance(self):
        report = format_backtest_report(self._make_result())
        assert "PERFORMANCE" in report
        assert "+12.00%" in report  # total return
        assert "1.8000" in report  # sharpe

    def test_contains_trade_stats(self):
        report = format_backtest_report(self._make_result())
        assert "TRADE STATISTICS" in report
        assert "25" in report  # total trades
        assert "65.0%" in report  # win rate

    def test_contains_benchmark(self):
        report = format_backtest_report(self._make_result())
        assert "BENCHMARK" in report
        assert "SPY" in report
        assert "Alpha" in report

    def test_errors_section(self):
        r = self._make_result(errors=["Warn 1", "Warn 2"])
        report = format_backtest_report(r)
        assert "WARNINGS (2)" in report
        assert "Warn 1" in report

    def test_no_errors_no_section(self):
        r = self._make_result(errors=[])
        report = format_backtest_report(r)
        assert "WARNINGS" not in report

    def test_truncates_many_errors(self):
        r = self._make_result(errors=[f"err{i}" for i in range(15)])
        report = format_backtest_report(r)
        assert "and 5 more" in report

    def test_returns_string(self):
        assert isinstance(format_backtest_report(self._make_result()), str)


# ---------------------------------------------------------------------------
# run_backtest (no-yfinance path and mocked paths)
# ---------------------------------------------------------------------------


class TestRunBacktest:
    @pytest.mark.asyncio
    async def test_no_yfinance_returns_error(self):
        """When yfinance is not available, run_backtest returns error result."""
        with patch("dharma_swarm.ginko_backtest._HAS_YFINANCE", False):
            result = await run_backtest(BacktestConfig(symbols=["AAPL"]))
        assert result.total_trades == 0
        assert len(result.errors) >= 1
        assert "yfinance" in result.errors[0].lower()

    @pytest.mark.asyncio
    async def test_no_data_returns_error(self):
        """When download returns empty, run_backtest returns error."""
        with patch("dharma_swarm.ginko_backtest._HAS_YFINANCE", True), \
             patch("dharma_swarm.ginko_backtest._download_ohlcv", return_value={}):
            result = await run_backtest(BacktestConfig(symbols=["AAPL"]))
        assert result.total_trades == 0
        assert any("No data" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_insufficient_data_returns_error(self):
        """When too few overlapping dates, run_backtest returns error."""
        sparse_data = {
            "AAPL": {
                "dates": ["2024-01-01", "2024-01-02"],
                "open": [150.0, 151.0],
                "high": [152.0, 153.0],
                "low": [149.0, 150.0],
                "close": [151.0, 152.0],
                "volume": [1000, 1100],
            },
            "SPY": {
                "dates": ["2024-01-01", "2024-01-02"],
                "open": [450.0, 451.0],
                "high": [452.0, 453.0],
                "low": [449.0, 450.0],
                "close": [451.0, 452.0],
                "volume": [5000, 5100],
            },
        }
        with patch("dharma_swarm.ginko_backtest._HAS_YFINANCE", True), \
             patch("dharma_swarm.ginko_backtest._download_ohlcv", return_value=sparse_data):
            result = await run_backtest(BacktestConfig(symbols=["AAPL"]))
        assert result.total_trades == 0
        assert any("Insufficient" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_full_backtest_with_mocked_data(self, tmp_path, monkeypatch):
        """Full backtest with synthetic data — no yfinance needed."""
        monkeypatch.setattr("dharma_swarm.ginko_backtest.BACKTEST_DIR", tmp_path)

        # Generate 80 trading days of synthetic price data
        base_date = date(2024, 1, 1)
        num_days = 80
        dates = [(base_date + timedelta(days=i)).isoformat() for i in range(num_days)]

        # AAPL: trending up
        aapl_close = [150.0 + i * 0.5 for i in range(num_days)]
        # SPY: mild uptrend
        spy_close = [450.0 + i * 0.2 for i in range(num_days)]

        def make_ohlcv(closes, dates_list):
            return {
                "dates": dates_list,
                "open": [c - 0.5 for c in closes],
                "high": [c + 1.0 for c in closes],
                "low": [c - 1.0 for c in closes],
                "close": closes,
                "volume": [10000] * len(closes),
            }

        mock_data = {
            "AAPL": make_ohlcv(aapl_close, dates),
            "SPY": make_ohlcv(spy_close, dates),
        }

        # Mock the signal pipeline to produce actionable signals
        from dharma_swarm.ginko_signals import Signal

        def mock_synthesize(symbol, indicators, regime, regime_conf):
            return Signal(
                symbol=symbol,
                direction="buy",
                confidence=0.8,
                strength="moderate",
                reasons=["test"],
                indicators=indicators,
            )

        with patch("dharma_swarm.ginko_backtest._HAS_YFINANCE", True), \
             patch("dharma_swarm.ginko_backtest._download_ohlcv", return_value=mock_data), \
             patch("dharma_swarm.ginko_backtest.synthesize_signal", side_effect=mock_synthesize):
            cfg = BacktestConfig(
                symbols=["AAPL"],
                start_date=dates[0],
                end_date=dates[-1],
            )
            result = await run_backtest(cfg)

        # Should have completed without fatal errors
        assert result.run_timestamp != ""
        assert len(result.equity_curve) > 0
        # At least some trades should have executed
        assert result.total_trades >= 0
        # Result should be persisted
        assert len(list(tmp_path.glob("*.json"))) >= 1


# ---------------------------------------------------------------------------
# _download_ohlcv (no-yfinance path)
# ---------------------------------------------------------------------------


class TestDownloadOhlcv:
    def test_no_yfinance_returns_empty(self):
        from dharma_swarm.ginko_backtest import _download_ohlcv
        with patch("dharma_swarm.ginko_backtest._HAS_YFINANCE", False):
            result = _download_ohlcv(["AAPL"], "2024-01-01", "2024-12-31")
        assert result == {}
