"""Tests for Ginko Paper Trading engine.

Validates Position/Trade dataclasses, PaperPortfolio lifecycle (open, close,
mark-to-market, persistence), telos gate enforcement (AHIMSA, REVERSIBILITY),
standalone analytics (Sharpe ratio, max drawdown), and edge cases.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

_temp_dir = tempfile.mkdtemp()
os.environ.setdefault("DHARMA_HOME", _temp_dir)

from dharma_swarm.ginko_paper_trade import (
    AHIMSA_MAX_POSITION_PCT,
    PaperPortfolio,
    Position,
    Trade,
    compute_max_drawdown,
    compute_sharpe,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_portfolio(
    initial_capital: float = 100_000.0,
) -> tuple[PaperPortfolio, Path]:
    """Create a portfolio backed by a fresh temp directory."""
    d = Path(tempfile.mkdtemp())
    path = d / "paper_portfolio.json"
    return PaperPortfolio(initial_capital=initial_capital, portfolio_path=path), d


# ===========================================================================
# TestPosition
# ===========================================================================


class TestPosition:
    def test_position_creation(self) -> None:
        """All explicitly-set fields are stored correctly."""
        pos = Position(
            symbol="AAPL",
            direction="long",
            entry_price=150.0,
            entry_time="2026-03-17T08:00:00Z",
            quantity=10.0,
            current_price=155.0,
            unrealized_pnl=50.0,
            stop_loss=145.0,
            take_profit=170.0,
        )
        assert pos.symbol == "AAPL"
        assert pos.direction == "long"
        assert pos.entry_price == 150.0
        assert pos.entry_time == "2026-03-17T08:00:00Z"
        assert pos.quantity == 10.0
        assert pos.current_price == 155.0
        assert pos.unrealized_pnl == 50.0
        assert pos.stop_loss == 145.0
        assert pos.take_profit == 170.0

    def test_position_defaults(self) -> None:
        """Optional fields default to 0.0."""
        pos = Position(
            symbol="BTC",
            direction="short",
            entry_price=60000.0,
            entry_time="2026-03-17T08:00:00Z",
            quantity=0.5,
        )
        assert pos.current_price == 0.0
        assert pos.unrealized_pnl == 0.0
        assert pos.stop_loss == 0.0
        assert pos.take_profit == 0.0


# ===========================================================================
# TestTrade
# ===========================================================================


class TestTrade:
    def test_trade_creation(self) -> None:
        """All fields populated on construction."""
        trade = Trade(
            id="abc123",
            symbol="MSFT",
            direction="long",
            entry_price=400.0,
            exit_price=420.0,
            entry_time="2026-03-17T08:00:00Z",
            exit_time="2026-03-17T16:00:00Z",
            quantity=5.0,
            realized_pnl=100.0,
            signal_source="momentum",
            brier_prediction_id="pred42",
        )
        assert trade.id == "abc123"
        assert trade.symbol == "MSFT"
        assert trade.direction == "long"
        assert trade.entry_price == 400.0
        assert trade.exit_price == 420.0
        assert trade.quantity == 5.0
        assert trade.realized_pnl == 100.0
        assert trade.signal_source == "momentum"
        assert trade.brier_prediction_id == "pred42"

    def test_trade_pnl_calculation(self) -> None:
        """realized_pnl = (exit - entry) * quantity for a long trade."""
        entry = 100.0
        exit_ = 110.0
        qty = 10.0
        expected = (exit_ - entry) * qty  # 100.0
        trade = Trade(
            id="t1",
            symbol="TEST",
            direction="long",
            entry_price=entry,
            exit_price=exit_,
            entry_time="2026-03-17T08:00:00Z",
            exit_time="2026-03-17T16:00:00Z",
            quantity=qty,
            realized_pnl=expected,
        )
        assert trade.realized_pnl == pytest.approx(100.0)


# ===========================================================================
# TestPaperPortfolio
# ===========================================================================


class TestPaperPortfolio:
    def test_initial_state(self) -> None:
        """Fresh portfolio starts with full cash, no positions, no trades."""
        pf, _ = _fresh_portfolio()
        assert pf.cash == pytest.approx(100_000.0)
        assert pf.initial_capital == pytest.approx(100_000.0)
        assert len(pf.positions) == 0
        assert len(pf.trades) == 0

    def test_open_long_position(self) -> None:
        """Opening a long deducts cash and tracks the position."""
        pf, _ = _fresh_portfolio()
        pos = pf.open_position(
            symbol="AAPL",
            direction="long",
            quantity=10.0,
            price=150.0,
            stop_loss=140.0,
        )
        assert pos.symbol == "AAPL"
        assert pos.direction == "long"
        assert pos.entry_price == 150.0
        assert pos.quantity == 10.0
        assert pos.stop_loss == 140.0
        assert "AAPL" in pf.positions
        # Cash should be reduced by position_value = 150 * 10 = 1500
        assert pf.cash == pytest.approx(100_000.0 - 1500.0)

    def test_open_short_position(self) -> None:
        """Opening a short also commits capital (margin-style)."""
        pf, _ = _fresh_portfolio()
        pos = pf.open_position(
            symbol="TSLA",
            direction="short",
            quantity=5.0,
            price=200.0,
            stop_loss=220.0,
        )
        assert pos.direction == "short"
        assert pos.symbol == "TSLA"
        # Cash commitment: 200 * 5 = 1000
        assert pf.cash == pytest.approx(100_000.0 - 1000.0)

    def test_close_long_position_profit(self) -> None:
        """Buy at 100, sell at 110 -> P&L = (110 - 100) * quantity."""
        pf, _ = _fresh_portfolio()
        pf.open_position("SPY", "long", quantity=10.0, price=100.0, stop_loss=90.0)
        trade = pf.close_position("SPY", price=110.0)
        assert trade.realized_pnl == pytest.approx(100.0)  # (110-100)*10
        assert trade.direction == "long"
        assert trade.entry_price == 100.0
        assert trade.exit_price == 110.0
        assert "SPY" not in pf.positions
        # Cash: started 100000, spent 1000, got back 1000+100 = 1100
        assert pf.cash == pytest.approx(100_000.0 + 100.0)

    def test_close_long_position_loss(self) -> None:
        """Buy at 100, sell at 90 -> P&L = (90 - 100) * quantity = -100."""
        pf, _ = _fresh_portfolio()
        pf.open_position("QQQ", "long", quantity=10.0, price=100.0, stop_loss=85.0)
        trade = pf.close_position("QQQ", price=90.0)
        assert trade.realized_pnl == pytest.approx(-100.0)
        assert pf.cash == pytest.approx(100_000.0 - 100.0)

    def test_close_short_position_profit(self) -> None:
        """Short at 100, cover at 90 -> P&L = (100 - 90) * quantity = 100."""
        pf, _ = _fresh_portfolio()
        pf.open_position("IWM", "short", quantity=10.0, price=100.0, stop_loss=110.0)
        trade = pf.close_position("IWM", price=90.0)
        assert trade.realized_pnl == pytest.approx(100.0)
        # Cash: 100000 - 1000 + (1000 + 100) = 100100
        assert pf.cash == pytest.approx(100_000.0 + 100.0)

    def test_mark_to_market(self) -> None:
        """Updating prices recalculates unrealized P&L."""
        pf, _ = _fresh_portfolio()
        pf.open_position("AAPL", "long", quantity=10.0, price=150.0, stop_loss=140.0)
        summary = pf.mark_to_market({"AAPL": 160.0})

        # Unrealized P&L: (160 - 150) * 10 = 100
        assert summary["unrealized_pnl"] == pytest.approx(100.0)
        assert pf.positions["AAPL"].current_price == pytest.approx(160.0)
        assert pf.positions["AAPL"].unrealized_pnl == pytest.approx(100.0)

        # Portfolio value: cash + position_value
        expected_position_value = 160.0 * 10.0  # 1600 for long
        expected_total = pf.cash + expected_position_value
        assert summary["total_value"] == pytest.approx(expected_total)

    def test_portfolio_stats(self) -> None:
        """Stats include trade count, win_rate, and P&L figures."""
        pf, _ = _fresh_portfolio()
        # Open and close 2 winning trades, 1 losing
        pf.open_position("WIN1", "long", 10.0, 100.0, stop_loss=90.0)
        pf.close_position("WIN1", 110.0)

        pf.open_position("WIN2", "long", 10.0, 100.0, stop_loss=90.0)
        pf.close_position("WIN2", 105.0)

        pf.open_position("LOSE1", "long", 10.0, 100.0, stop_loss=80.0)
        pf.close_position("LOSE1", 95.0)

        stats = pf.get_portfolio_stats()
        assert stats["trade_count"] == 3
        assert stats["win_rate"] == pytest.approx(2 / 3, abs=0.01)
        # Net P&L: +100 +50 -50 = +100
        assert stats["total_pnl"] == pytest.approx(100.0)
        assert stats["open_positions"] == 0

    def test_portfolio_persistence(self) -> None:
        """A new PaperPortfolio instance at the same path loads prior state."""
        d = Path(tempfile.mkdtemp())
        path = d / "paper_portfolio.json"

        pf1 = PaperPortfolio(initial_capital=100_000.0, portfolio_path=path)
        pf1.open_position("GOOG", "long", quantity=10.0, price=100.0, stop_loss=90.0)
        pf1.close_position("GOOG", price=105.0)
        pf1.open_position("META", "long", quantity=5.0, price=200.0, stop_loss=180.0)

        # Create a second instance from the same path
        pf2 = PaperPortfolio(initial_capital=100_000.0, portfolio_path=path)
        assert "META" in pf2.positions
        assert pf2.positions["META"].entry_price == pytest.approx(200.0)
        assert len(pf2.trades) == 1
        assert pf2.trades[0].symbol == "GOOG"
        assert pf2.cash == pytest.approx(pf1.cash)

    def test_multiple_positions(self) -> None:
        """Multiple open positions contribute to total portfolio value."""
        pf, _ = _fresh_portfolio()
        pf.open_position("A", "long", 10.0, 100.0, stop_loss=90.0)
        pf.open_position("B", "long", 10.0, 200.0, stop_loss=180.0)
        pf.open_position("C", "short", 10.0, 150.0, stop_loss=170.0)

        # Total committed: 1000 + 2000 + 1500 = 4500
        assert pf.cash == pytest.approx(100_000.0 - 4500.0)
        assert len(pf.positions) == 3

        # Mark to market and check total value
        summary = pf.mark_to_market({"A": 100.0, "B": 200.0, "C": 150.0})
        # No price change, so unrealized P&L == 0
        assert summary["unrealized_pnl"] == pytest.approx(0.0)
        assert summary["total_value"] == pytest.approx(100_000.0)


# ===========================================================================
# TestTelosGates
# ===========================================================================


class TestTelosGates:
    def test_ahimsa_gate_blocks_large_position(self) -> None:
        """Position exceeding 5% of portfolio value is rejected."""
        pf, _ = _fresh_portfolio(initial_capital=100_000.0)
        # Try to open a position worth > 5% = $5000+
        # 60 shares * $100 = $6000 > $5000
        with pytest.raises(ValueError, match="AHIMSA"):
            pf.open_position("BIG", "long", quantity=60.0, price=100.0, stop_loss=90.0)

    def test_ahimsa_gate_passes_small_position(self) -> None:
        """Position under 5% threshold opens successfully."""
        pf, _ = _fresh_portfolio(initial_capital=100_000.0)
        # 40 shares * $100 = $4000 < $5000 (5% of 100K)
        pos = pf.open_position("SMALL", "long", quantity=40.0, price=100.0, stop_loss=90.0)
        assert pos.symbol == "SMALL"
        assert "SMALL" in pf.positions

    def test_ahimsa_gate_message_format(self) -> None:
        """AHIMSA error message contains 'AHIMSA GATE', percentage, and '5% limit'."""
        pf, _ = _fresh_portfolio(initial_capital=100_000.0)
        with pytest.raises(ValueError, match=r"AHIMSA GATE.*exceeds 5% limit"):
            pf.open_position("X", "long", quantity=60.0, price=100.0, stop_loss=90.0)

    def test_ahimsa_gate_at_boundary(self) -> None:
        """Position at exactly 5% passes (not strictly greater)."""
        pf, _ = _fresh_portfolio(initial_capital=100_000.0)
        # 50 * 100 = $5000 = exactly 5% of $100K
        pos = pf.open_position("EDGE", "long", quantity=50.0, price=100.0, stop_loss=90.0)
        assert pos.symbol == "EDGE"

    def test_ahimsa_gate_just_over_boundary(self) -> None:
        """Position at 5.001% is blocked."""
        pf, _ = _fresh_portfolio(initial_capital=100_000.0)
        # 50.01 * 100 = $5001 > 5% of $100K
        with pytest.raises(ValueError, match="AHIMSA GATE"):
            pf.open_position("OVER", "long", quantity=50.01, price=100.0, stop_loss=90.0)

    def test_ahimsa_max_position_pct_constant(self) -> None:
        """The AHIMSA_MAX_POSITION_PCT constant is exactly 0.05 (5%)."""
        assert AHIMSA_MAX_POSITION_PCT == 0.05

    def test_reversibility_gate_blocks_no_stop(self) -> None:
        """stop_loss=0 is rejected by REVERSIBILITY gate."""
        pf, _ = _fresh_portfolio()
        with pytest.raises(ValueError, match="REVERSIBILITY"):
            pf.open_position("NOSTOP", "long", quantity=10.0, price=100.0, stop_loss=0.0)

    def test_reversibility_gate_blocks_none_stop(self) -> None:
        """stop_loss=None is rejected by REVERSIBILITY gate."""
        pf, _ = _fresh_portfolio()
        with pytest.raises(ValueError, match="REVERSIBILITY GATE"):
            pf.open_position("NOSTOP", "long", quantity=10.0, price=100.0, stop_loss=None)

    def test_reversibility_gate_blocks_negative_stop(self) -> None:
        """stop_loss=-5 is rejected by REVERSIBILITY gate."""
        pf, _ = _fresh_portfolio()
        with pytest.raises(ValueError, match="REVERSIBILITY GATE"):
            pf.open_position("NEGSTOP", "long", quantity=10.0, price=100.0, stop_loss=-5.0)

    def test_reversibility_gate_message_includes_symbol(self) -> None:
        """REVERSIBILITY error message includes the symbol name."""
        pf, _ = _fresh_portfolio()
        with pytest.raises(ValueError, match="ETH"):
            pf.open_position("ETH", "long", quantity=10.0, price=100.0, stop_loss=None)

    def test_reversibility_gate_passes_with_stop(self) -> None:
        """A valid stop_loss passes the REVERSIBILITY gate."""
        pf, _ = _fresh_portfolio()
        pos = pf.open_position("SAFE", "long", quantity=10.0, price=100.0, stop_loss=95.0)
        assert pos.stop_loss == 95.0


# ===========================================================================
# TestSharpeRatio
# ===========================================================================


class TestSharpeRatio:
    def test_sharpe_positive(self) -> None:
        """Known positive returns produce a positive Sharpe ratio."""
        returns = [0.01, 0.02, -0.005, 0.015, 0.008]
        sharpe = compute_sharpe(returns)
        assert sharpe > 0.0

    def test_sharpe_zero_std(self) -> None:
        """All equal returns -> zero standard deviation -> Sharpe = 0.0."""
        returns = [0.01, 0.01, 0.01, 0.01, 0.01]
        sharpe = compute_sharpe(returns)
        assert sharpe == 0.0

    def test_sharpe_insufficient_data(self) -> None:
        """Empty or single-element list returns 0.0."""
        assert compute_sharpe([]) == 0.0
        assert compute_sharpe([0.01]) == 0.0


# ===========================================================================
# TestMaxDrawdown
# ===========================================================================


class TestMaxDrawdown:
    def test_max_drawdown_known(self) -> None:
        """Equity [100, 110, 105, 95, 100, 108] -> drawdown from 110 to 95."""
        equity = [100.0, 110.0, 105.0, 95.0, 100.0, 108.0]
        dd = compute_max_drawdown(equity)
        # Max drawdown: (110 - 95) / 110 = 15/110 ~ 0.13636
        assert dd == pytest.approx(15.0 / 110.0, abs=1e-4)

    def test_max_drawdown_no_drawdown(self) -> None:
        """Monotonically increasing equity has zero drawdown."""
        equity = [100.0, 105.0, 110.0, 115.0, 120.0]
        assert compute_max_drawdown(equity) == 0.0

    def test_max_drawdown_empty(self) -> None:
        """Empty or single-value curve returns 0.0."""
        assert compute_max_drawdown([]) == 0.0
        assert compute_max_drawdown([100.0]) == 0.0


# ===========================================================================
# TestEdgeCases
# ===========================================================================


class TestEdgeCases:
    def test_close_nonexistent_position(self) -> None:
        """Closing a symbol with no open position raises ValueError."""
        pf, _ = _fresh_portfolio()
        with pytest.raises(ValueError, match="No open position"):
            pf.close_position("GHOST", price=100.0)

    def test_open_duplicate_position(self) -> None:
        """Opening a second position on the same symbol is rejected."""
        pf, _ = _fresh_portfolio()
        pf.open_position("DUP", "long", quantity=10.0, price=100.0, stop_loss=90.0)
        with pytest.raises(ValueError, match="already open"):
            pf.open_position("DUP", "long", quantity=5.0, price=105.0, stop_loss=95.0)


# ===========================================================================
# TestEquitySnapshot
# ===========================================================================


class TestEquitySnapshot:
    def test_daily_equity_snapshot(self) -> None:
        """Snapshot appends a line to equity_curve.jsonl with correct fields."""
        pf, d = _fresh_portfolio()
        equity_path = d / "equity_curve.jsonl"

        # Take two snapshots to also verify daily_return calculation
        pf.daily_equity_snapshot()

        # Open a position and take a second snapshot (no price change yet)
        pf.open_position("SPY", "long", quantity=10.0, price=100.0, stop_loss=90.0)
        pf.daily_equity_snapshot()

        assert equity_path.exists()
        lines = equity_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        first = json.loads(lines[0])
        assert "timestamp" in first
        assert "total_value" in first
        assert "cash" in first
        assert "positions_value" in first
        assert "daily_return" in first
        assert first["total_value"] == pytest.approx(100_000.0)

        second = json.loads(lines[1])
        # Portfolio value unchanged (current_price defaults to entry_price)
        assert second["total_value"] == pytest.approx(100_000.0)


# ===========================================================================
# TestMarkToMarketShort
# ===========================================================================


class TestMarkToMarketShort:
    def test_mark_to_market_short_profit(self) -> None:
        """Short position profits when price drops."""
        pf, _ = _fresh_portfolio()
        pf.open_position("SHORT", "short", quantity=10.0, price=100.0, stop_loss=110.0)
        summary = pf.mark_to_market({"SHORT": 90.0})
        # Short unrealized P&L: (100 - 90) * 10 = 100
        assert summary["unrealized_pnl"] == pytest.approx(100.0)

    def test_mark_to_market_short_loss(self) -> None:
        """Short position loses when price rises."""
        pf, _ = _fresh_portfolio()
        pf.open_position("SHORT", "short", quantity=10.0, price=100.0, stop_loss=115.0)
        summary = pf.mark_to_market({"SHORT": 110.0})
        # Short unrealized P&L: (100 - 110) * 10 = -100
        assert summary["unrealized_pnl"] == pytest.approx(-100.0)


# ===========================================================================
# TestInputValidation
# ===========================================================================


class TestInputValidation:
    def test_invalid_direction(self) -> None:
        """Direction must be 'long' or 'short'."""
        pf, _ = _fresh_portfolio()
        with pytest.raises(ValueError, match="direction"):
            pf.open_position("BAD", "sideways", quantity=10.0, price=100.0, stop_loss=90.0)

    def test_zero_quantity(self) -> None:
        """Quantity must be > 0."""
        pf, _ = _fresh_portfolio()
        with pytest.raises(ValueError, match="quantity"):
            pf.open_position("BAD", "long", quantity=0.0, price=100.0, stop_loss=90.0)

    def test_negative_price(self) -> None:
        """Price must be > 0."""
        pf, _ = _fresh_portfolio()
        with pytest.raises(ValueError, match="price"):
            pf.open_position("BAD", "long", quantity=10.0, price=-5.0, stop_loss=1.0)

    def test_close_at_zero_price(self) -> None:
        """Closing at price=0 raises ValueError."""
        pf, _ = _fresh_portfolio()
        pf.open_position("X", "long", quantity=10.0, price=100.0, stop_loss=90.0)
        with pytest.raises(ValueError, match="price"):
            pf.close_position("X", price=0.0)

    def test_insufficient_cash(self) -> None:
        """Cannot open position that exceeds available cash."""
        pf, _ = _fresh_portfolio(initial_capital=1000.0)
        # Ahimsa limit: 5% of 1000 = 50, so position_value must be <= 50
        # But even a small position can exceed cash if we drain it first
        # Open max allowed position (50) then try another
        pf.open_position("A", "long", quantity=5.0, price=10.0, stop_loss=5.0)  # 50
        pf.open_position("B", "long", quantity=5.0, price=10.0, stop_loss=5.0)  # 50
        # After 19 positions of $50 each, we have $50 cash left
        for i in range(17):
            pf.open_position(
                f"S{i}", "long", quantity=5.0, price=10.0, stop_loss=5.0,
            )
        # 19 * 50 = 950, cash = 50
        # Try opening position worth more than remaining cash
        # We need the AHIMSA check to pass (<=5% of portfolio) but fail on cash.
        # Portfolio value is still ~1000, 5% = 50, so 50 is right at the boundary.
        # Position of $50 should still work (we have exactly $50).
        pos = pf.open_position("LAST", "long", quantity=5.0, price=10.0, stop_loss=5.0)
        assert pos.symbol == "LAST"
        # Now cash is 0, next one should fail
        with pytest.raises(ValueError, match="Insufficient cash"):
            pf.open_position("OVER", "long", quantity=1.0, price=10.0, stop_loss=5.0)


# ===========================================================================
# TestPersistenceFiles
# ===========================================================================


class TestPersistenceFiles:
    def test_trades_jsonl_written(self) -> None:
        """Each closed trade appends a line to trades.jsonl."""
        pf, d = _fresh_portfolio()
        trades_path = d / "trades.jsonl"

        pf.open_position("T1", "long", 10.0, 100.0, stop_loss=90.0)
        pf.close_position("T1", 105.0)

        pf.open_position("T2", "short", 10.0, 100.0, stop_loss=110.0)
        pf.close_position("T2", 95.0)

        assert trades_path.exists()
        lines = trades_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2

        t1 = json.loads(lines[0])
        assert t1["symbol"] == "T1"
        assert t1["direction"] == "long"
        assert t1["realized_pnl"] == pytest.approx(50.0)

        t2 = json.loads(lines[1])
        assert t2["symbol"] == "T2"
        assert t2["direction"] == "short"
        assert t2["realized_pnl"] == pytest.approx(50.0)

    def test_portfolio_json_structure(self) -> None:
        """The saved portfolio JSON has the expected top-level keys."""
        pf, d = _fresh_portfolio()
        path = d / "paper_portfolio.json"

        pf.open_position("X", "long", 10.0, 100.0, stop_loss=90.0)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert "initial_capital" in data
        assert "cash" in data
        assert "positions" in data
        assert "trades" in data
        assert "last_updated" in data
        assert "X" in data["positions"]
