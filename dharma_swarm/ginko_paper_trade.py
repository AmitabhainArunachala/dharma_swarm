"""Ginko Paper Trading -- simulated portfolio for strategy validation.

Paper trading with $100K initial capital. Tracks positions, P&L,
Sharpe ratio, max drawdown. Enforces telos gates:
  - AHIMSA: max 5% per position
  - REVERSIBILITY: every position requires stop_loss

Persistence:
  ~/.dharma/ginko/paper_portfolio.json  (portfolio state)
  ~/.dharma/ginko/trades.jsonl          (closed trade log)
  ~/.dharma/ginko/equity_curve.jsonl    (daily snapshots)
"""

from __future__ import annotations

import json
import logging
import math
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"

AHIMSA_MAX_POSITION_PCT = 0.05  # 5% of portfolio value per position


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class Position:
    """An open paper trading position."""

    symbol: str
    direction: str  # "long" or "short"
    entry_price: float
    entry_time: str
    quantity: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Trade:
    """A closed (realized) paper trade."""

    id: str  # uuid hex
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    entry_time: str
    exit_time: str
    quantity: float
    realized_pnl: float
    signal_source: str = ""
    brier_prediction_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Trade:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Standalone analytics
# ---------------------------------------------------------------------------


def compute_sharpe(daily_returns: list[float], risk_free_rate: float = 0.05) -> float:
    """Compute annualized Sharpe ratio.

    Sharpe = (mean_return - rf_daily) / std_return * sqrt(252)

    Args:
        daily_returns: List of daily fractional returns (e.g. 0.01 = 1%).
        risk_free_rate: Annualized risk-free rate (default 5%).

    Returns:
        Annualized Sharpe ratio, or 0.0 if insufficient data or zero std.
    """
    if len(daily_returns) < 2:
        return 0.0

    rf_daily = risk_free_rate / 252.0
    mean_ret = sum(daily_returns) / len(daily_returns)
    variance = sum((r - mean_ret) ** 2 for r in daily_returns) / (len(daily_returns) - 1)
    std_ret = math.sqrt(variance)

    if std_ret == 0.0:
        return 0.0

    return (mean_ret - rf_daily) / std_ret * math.sqrt(252)


def compute_max_drawdown(equity_curve: list[float]) -> float:
    """Compute maximum drawdown from peak.

    Args:
        equity_curve: List of portfolio equity values over time.

    Returns:
        Maximum drawdown as a fraction (e.g. 0.15 = 15% drawdown).
        Returns 0.0 if fewer than 2 data points or no drawdown.
    """
    if len(equity_curve) < 2:
        return 0.0

    peak = equity_curve[0]
    max_dd = 0.0

    for value in equity_curve:
        if value > peak:
            peak = value
        if peak > 0:
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd

    return max_dd


# ---------------------------------------------------------------------------
# PaperPortfolio
# ---------------------------------------------------------------------------


class PaperPortfolio:
    """Simulated paper trading portfolio with telos gate enforcement.

    Tracks open positions, closed trades, cash balance, and equity curve.
    Persists state to disk after every mutation.

    Telos gates:
        AHIMSA -- no single position may exceed 5% of total portfolio value.
        REVERSIBILITY -- every position must have a stop_loss > 0.
    """

    def __init__(
        self,
        initial_capital: float = 100_000.0,
        portfolio_path: Path | None = None,
    ) -> None:
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, Position] = {}  # symbol -> Position
        self.trades: list[Trade] = []  # closed trades

        self._portfolio_path = portfolio_path or GINKO_DIR / "paper_portfolio.json"
        if portfolio_path:
            parent = portfolio_path.parent
        else:
            parent = GINKO_DIR
        self._trades_path = parent / "trades.jsonl"
        self._equity_path = parent / "equity_curve.jsonl"

        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open_position(
        self,
        symbol: str,
        direction: str,
        quantity: float,
        price: float,
        stop_loss: float | None,
        take_profit: float = 0.0,
        signal_source: str = "",
        brier_prediction_id: str = "",
    ) -> Position:
        """Open a paper position.

        AHIMSA gate: position value must be <= 5% of total portfolio value.
        REVERSIBILITY gate: stop_loss must be > 0.

        Args:
            symbol: Ticker/asset symbol.
            direction: "long" or "short".
            quantity: Number of units.
            price: Entry price per unit.
            stop_loss: Stop-loss price (must be > 0).
            take_profit: Take-profit price (0 = none).
            signal_source: Which signal/strategy triggered this.
            brier_prediction_id: Linked Brier prediction ID.

        Returns:
            The new Position.

        Raises:
            ValueError: If telos gates fail, direction invalid, quantity/price
                non-positive, insufficient cash, or symbol already has a position.
        """
        # --- Input validation ---
        if direction not in ("long", "short"):
            raise ValueError(f"direction must be 'long' or 'short', got '{direction}'")
        if quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {quantity}")
        if price <= 0:
            raise ValueError(f"price must be > 0, got {price}")

        # --- REVERSIBILITY gate ---
        if stop_loss is None or stop_loss <= 0:
            logger.warning(
                "REVERSIBILITY GATE: stop_loss required for %s (got %s)",
                symbol,
                stop_loss,
            )
            raise ValueError(
                f"REVERSIBILITY GATE: stop_loss required for {symbol} (must be > 0)"
            )

        # --- Duplicate check ---
        if symbol in self.positions:
            raise ValueError(
                f"Position already open for {symbol}. Close it before opening a new one."
            )

        # --- AHIMSA gate ---
        position_value = price * quantity
        portfolio_value = self._compute_portfolio_value()
        # Use max of current portfolio or initial capital to avoid div-by-zero
        # on a completely drawn-down portfolio
        base_value = max(portfolio_value, self.initial_capital * 0.01)
        position_pct = position_value / base_value

        if position_pct > AHIMSA_MAX_POSITION_PCT:
            logger.warning(
                "AHIMSA GATE: %s position %.1f%% exceeds 5%% limit "
                "(value=$%.2f, portfolio=$%.2f)",
                symbol,
                position_pct * 100,
                position_value,
                base_value,
            )
            raise ValueError(
                f"AHIMSA GATE: position {position_pct:.1%} exceeds 5% limit"
            )

        # --- Cash check ---
        cost = position_value  # for both long and short, capital is committed
        if cost > self.cash:
            raise ValueError(
                f"Insufficient cash: need ${cost:,.2f}, have ${self.cash:,.2f}"
            )

        # --- Create position ---
        now = _utc_now().isoformat()
        pos = Position(
            symbol=symbol,
            direction=direction,
            entry_price=price,
            entry_time=now,
            quantity=quantity,
            current_price=price,
            unrealized_pnl=0.0,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        self.cash -= cost
        self.positions[symbol] = pos
        self._save()

        logger.info(
            "Opened %s %s: %.4f @ $%.2f (stop=%.2f, tp=%.2f)",
            direction,
            symbol,
            quantity,
            price,
            stop_loss,
            take_profit,
        )
        return pos

    def close_position(self, symbol: str, price: float, reason: str = "") -> Trade:
        """Close an existing position at given price.

        Computes realized P&L, creates Trade record, updates cash.
        Appends Trade to trades.jsonl.

        Args:
            symbol: Symbol of the position to close.
            price: Exit price per unit.
            reason: Why the position was closed.

        Returns:
            The closed Trade record.

        Raises:
            ValueError: If no position exists for the symbol or price <= 0.
        """
        if symbol not in self.positions:
            raise ValueError(f"No open position for {symbol}")
        if price <= 0:
            raise ValueError(f"price must be > 0, got {price}")

        pos = self.positions[symbol]

        # Compute realized P&L
        if pos.direction == "long":
            realized_pnl = (price - pos.entry_price) * pos.quantity
        else:  # short
            realized_pnl = (pos.entry_price - price) * pos.quantity

        # Return capital + P&L to cash
        # Original cost was entry_price * quantity
        original_cost = pos.entry_price * pos.quantity
        self.cash += original_cost + realized_pnl

        now = _utc_now().isoformat()
        trade = Trade(
            id=uuid.uuid4().hex,
            symbol=symbol,
            direction=pos.direction,
            entry_price=pos.entry_price,
            exit_price=price,
            entry_time=pos.entry_time,
            exit_time=now,
            quantity=pos.quantity,
            realized_pnl=realized_pnl,
        )

        del self.positions[symbol]
        self.trades.append(trade)

        self._save_trade(trade)
        self._save()

        logger.info(
            "Closed %s %s @ $%.2f -> P&L: $%.2f (%s)",
            trade.direction,
            symbol,
            price,
            realized_pnl,
            reason or "manual",
        )
        return trade

    def mark_to_market(self, prices: dict[str, float]) -> dict[str, Any]:
        """Update current prices and unrealized P&L for all positions.

        Args:
            prices: Dict of symbol -> current market price.

        Returns:
            Portfolio summary dict with total_value, cash, positions_value,
            unrealized_pnl, and per-position details.
        """
        position_details: list[dict[str, Any]] = []

        for symbol, pos in self.positions.items():
            if symbol in prices:
                pos.current_price = prices[symbol]

            # Compute unrealized P&L
            if pos.direction == "long":
                pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.quantity
            else:  # short
                pos.unrealized_pnl = (pos.entry_price - pos.current_price) * pos.quantity

            position_details.append({
                "symbol": symbol,
                "direction": pos.direction,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "quantity": pos.quantity,
                "unrealized_pnl": round(pos.unrealized_pnl, 2),
                "stop_loss": pos.stop_loss,
                "take_profit": pos.take_profit,
            })

        positions_value = self._compute_positions_value()
        total_value = self.cash + positions_value

        self._save()

        return {
            "total_value": round(total_value, 2),
            "cash": round(self.cash, 2),
            "positions_value": round(positions_value, 2),
            "unrealized_pnl": round(sum(p.unrealized_pnl for p in self.positions.values()), 2),
            "positions": position_details,
        }

    def get_portfolio_stats(self) -> dict[str, Any]:
        """Compute comprehensive portfolio statistics.

        Returns:
            Dict with total_value, cash, positions_value, total_pnl,
            total_pnl_pct, sharpe_ratio, max_drawdown, win_rate,
            avg_win, avg_loss, trade_count, open_positions.
        """
        positions_value = self._compute_positions_value()
        total_value = self.cash + positions_value
        total_pnl = total_value - self.initial_capital
        total_pnl_pct = (total_value / self.initial_capital - 1) * 100 if self.initial_capital > 0 else 0.0

        # Load equity curve for Sharpe and drawdown
        equity_entries = self._load_equity_curve()
        daily_returns: list[float] = []
        equity_values: list[float] = []
        for entry in equity_entries:
            dr = entry.get("daily_return")
            if dr is not None:
                daily_returns.append(dr)
            tv = entry.get("total_value")
            if tv is not None:
                equity_values.append(tv)

        sharpe = compute_sharpe(daily_returns)
        max_dd = compute_max_drawdown(equity_values) if equity_values else 0.0

        # Trade statistics
        winning = [t for t in self.trades if t.realized_pnl > 0]
        losing = [t for t in self.trades if t.realized_pnl < 0]
        trade_count = len(self.trades)

        win_rate = len(winning) / trade_count if trade_count > 0 else 0.0
        avg_win = sum(t.realized_pnl for t in winning) / len(winning) if winning else 0.0
        avg_loss = abs(sum(t.realized_pnl for t in losing) / len(losing)) if losing else 0.0

        return {
            "total_value": round(total_value, 2),
            "cash": round(self.cash, 2),
            "positions_value": round(positions_value, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct, 4),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown": round(max_dd, 4),
            "win_rate": round(win_rate, 4),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "trade_count": trade_count,
            "open_positions": len(self.positions),
        }

    def daily_equity_snapshot(self) -> None:
        """Append current equity to equity_curve.jsonl.

        Entry: {timestamp, total_value, cash, positions_value, daily_return}
        Daily return is computed relative to the previous snapshot.
        """
        positions_value = self._compute_positions_value()
        total_value = self.cash + positions_value

        # Compute daily return from previous snapshot
        prev_entries = self._load_equity_curve()
        if prev_entries:
            prev_value = prev_entries[-1].get("total_value", self.initial_capital)
            daily_return = (total_value / prev_value - 1) if prev_value > 0 else 0.0
        else:
            daily_return = (total_value / self.initial_capital - 1) if self.initial_capital > 0 else 0.0

        entry = {
            "timestamp": _utc_now().isoformat(),
            "total_value": round(total_value, 2),
            "cash": round(self.cash, 2),
            "positions_value": round(positions_value, 2),
            "daily_return": round(daily_return, 6),
        }

        self._equity_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._equity_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")

        logger.info(
            "Equity snapshot: $%.2f (return: %.4f%%)",
            total_value,
            daily_return * 100,
        )

    # ------------------------------------------------------------------
    # Internal: position value helpers
    # ------------------------------------------------------------------

    def _compute_position_value(self, pos: Position) -> float:
        """Compute current market value of a single position.

        Long: current_price * quantity
        Short: entry_price * quantity + unrealized_pnl (margin accounting)
        """
        if pos.direction == "long":
            return pos.current_price * pos.quantity
        else:  # short
            return pos.entry_price * pos.quantity + pos.unrealized_pnl

    def _compute_positions_value(self) -> float:
        """Sum of all open position values."""
        return sum(self._compute_position_value(p) for p in self.positions.values())

    def _compute_portfolio_value(self) -> float:
        """Total portfolio value: cash + positions."""
        return self.cash + self._compute_positions_value()

    # ------------------------------------------------------------------
    # Persistence: portfolio state
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load portfolio state from paper_portfolio.json if it exists."""
        if not self._portfolio_path.exists():
            return

        try:
            data = json.loads(self._portfolio_path.read_text(encoding="utf-8"))
            self.initial_capital = data.get("initial_capital", self.initial_capital)
            self.cash = data.get("cash", self.initial_capital)
            self.positions = {}
            for sym, pos_data in data.get("positions", {}).items():
                self.positions[sym] = Position.from_dict(pos_data)
            self.trades = []
            for trade_data in data.get("trades", []):
                self.trades.append(Trade.from_dict(trade_data))
            logger.debug(
                "Loaded portfolio: cash=$%.2f, %d positions, %d trades",
                self.cash,
                len(self.positions),
                len(self.trades),
            )
        except Exception as e:
            logger.error("Failed to load portfolio from %s: %s", self._portfolio_path, e)

    def _save(self) -> None:
        """Persist portfolio state to paper_portfolio.json."""
        self._portfolio_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "initial_capital": self.initial_capital,
            "cash": round(self.cash, 2),
            "positions": {sym: pos.to_dict() for sym, pos in self.positions.items()},
            "trades": [t.to_dict() for t in self.trades],
            "last_updated": _utc_now().isoformat(),
        }

        try:
            self._portfolio_path.write_text(
                json.dumps(data, indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error("Failed to save portfolio: %s", e)

    def _save_trade(self, trade: Trade) -> None:
        """Append a single trade to trades.jsonl."""
        self._trades_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._trades_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trade.to_dict(), default=str) + "\n")
        except Exception as e:
            logger.error("Failed to append trade: %s", e)

    def _load_equity_curve(self) -> list[dict[str, Any]]:
        """Load all equity curve entries from equity_curve.jsonl."""
        if not self._equity_path.exists():
            return []

        entries: list[dict[str, Any]] = []
        try:
            text = self._equity_path.read_text(encoding="utf-8").strip()
            if not text:
                return []
            for line in text.split("\n"):
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        except Exception as e:
            logger.error("Failed to load equity curve: %s", e)

        return entries
