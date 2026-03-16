"""Ginko Backtesting Engine -- historical strategy validation.

Downloads OHLCV data via yfinance, replays the signal pipeline
(regime detection -> signal generation -> paper trade execution)
day-by-day, and computes performance metrics vs benchmark.

Usage:
    python3 -m dharma_swarm.ginko_backtest
    # or
    from dharma_swarm.ginko_backtest import BacktestConfig, run_backtest
    result = await run_backtest(BacktestConfig(symbols=["AAPL"]))

Output persisted to: ~/.dharma/ginko/backtest/
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any

# Graceful yfinance import -- the engine degrades cleanly without it
try:
    import yfinance as yf

    _HAS_YFINANCE = True
except ImportError:
    yf = None  # type: ignore[assignment]
    _HAS_YFINANCE = False

# Internal ginko imports -- regime detection, signal synthesis, analytics
from dharma_swarm.ginko_regime import ReturnSeries, analyze_regime
from dharma_swarm.ginko_signals import (
    Signal,
    SignalReport,
    compute_indicators,
    synthesize_signal,
)
from dharma_swarm.ginko_paper_trade import compute_sharpe, compute_max_drawdown

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
BACKTEST_DIR = GINKO_DIR / "backtest"

# Minimum trading-day lookback required before the signal pipeline can
# produce meaningful regime detection and technical indicators.
_MIN_LOOKBACK_DAYS = 50

# Position sizing: fraction of portfolio equity committed per trade.
# Kept well under the live AHIMSA 5% gate for conservative backtesting.
_POSITION_SIZE_PCT = 0.04

# Stop-loss and take-profit offsets (fraction of entry price).
_STOP_LOSS_PCT = 0.05
_TAKE_PROFIT_PCT = 0.10

# Minimum signal confidence required to enter a position.
_CONFIDENCE_THRESHOLD = 0.6


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class BacktestConfig:
    """Configuration for a backtest run."""

    symbols: list[str] = field(default_factory=lambda: ["AAPL", "MSFT", "NVDA"])
    start_date: str = ""  # YYYY-MM-DD; empty = 1 year ago
    end_date: str = ""  # YYYY-MM-DD; empty = today
    initial_capital: float = 100_000.0
    benchmark: str = "SPY"
    confidence_threshold: float = _CONFIDENCE_THRESHOLD
    position_size_pct: float = _POSITION_SIZE_PCT
    stop_loss_pct: float = _STOP_LOSS_PCT
    take_profit_pct: float = _TAKE_PROFIT_PCT

    def __post_init__(self) -> None:
        today = date.today()
        if not self.start_date:
            self.start_date = (today - timedelta(days=365)).isoformat()
        if not self.end_date:
            self.end_date = today.isoformat()


@dataclass
class TradeRecord:
    """A single completed backtest trade."""

    symbol: str
    direction: str  # "long" or "short"
    entry_date: str
    entry_price: float
    exit_date: str
    exit_price: float
    quantity: float
    pnl: float
    signal_confidence: float
    regime: str


@dataclass
class BacktestResult:
    """Complete results from a backtest run."""

    # Headline numbers
    total_return: float  # fractional, e.g. 0.12 = 12%
    annualized_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int

    # Curves
    equity_curve: list[float] = field(default_factory=list)
    daily_returns: list[float] = field(default_factory=list)
    dates: list[str] = field(default_factory=list)

    # Benchmark comparison
    benchmark_return: float = 0.0
    benchmark_sharpe: float = 0.0
    benchmark_max_drawdown: float = 0.0

    # Additional analytics
    calmar_ratio: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    trades: list[TradeRecord] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    run_timestamp: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helper math
# ---------------------------------------------------------------------------


def compute_annualized_return(total_return: float, days: int) -> float:
    """Annualize a total return over a given number of calendar days.

    Uses the standard formula: (1 + R)^(365/days) - 1

    Args:
        total_return: Fractional total return (e.g. 0.15 = 15%).
        days: Number of calendar days over which the return was earned.

    Returns:
        Annualized return as a fraction.
    """
    if days <= 0:
        return 0.0
    return (1 + total_return) ** (365.0 / days) - 1


def compute_calmar_ratio(annualized_return: float, max_drawdown: float) -> float:
    """Calmar ratio = annualized return / max drawdown.

    A risk-adjusted return metric favoring strategies with small drawdowns.

    Args:
        annualized_return: Annualized fractional return.
        max_drawdown: Maximum drawdown as a positive fraction.

    Returns:
        Calmar ratio, or 0.0 if max_drawdown is zero/negative.
    """
    if max_drawdown <= 0:
        return 0.0
    return annualized_return / max_drawdown


def compute_profit_factor(trades: list[TradeRecord]) -> float:
    """Gross profits / gross losses. > 1.0 means profitable.

    Args:
        trades: List of completed trade records.

    Returns:
        Profit factor, or 0.0 if no losing trades.
    """
    gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
    gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
    if gross_loss == 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


# ---------------------------------------------------------------------------
# Lightweight in-memory portfolio for backtesting
# ---------------------------------------------------------------------------


@dataclass
class _BacktestPosition:
    """Open position during a backtest simulation."""

    symbol: str
    direction: str
    entry_price: float
    entry_date: str
    quantity: float
    stop_loss: float
    take_profit: float
    signal_confidence: float
    regime: str


class _BacktestPortfolio:
    """In-memory portfolio for backtesting -- no disk persistence.

    Mirrors the PaperPortfolio API surface but avoids touching
    ~/.dharma/ginko/ state, so backtests never pollute live trading.
    """

    def __init__(self, initial_capital: float) -> None:
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.positions: dict[str, _BacktestPosition] = {}
        self.closed_trades: list[TradeRecord] = []

    def portfolio_value(self, prices: dict[str, float]) -> float:
        """Total equity = cash + mark-to-market positions."""
        positions_value = 0.0
        for sym, pos in self.positions.items():
            price = prices.get(sym, pos.entry_price)
            if pos.direction == "long":
                positions_value += price * pos.quantity
            else:
                # Short: capital committed + unrealized P&L
                positions_value += (
                    pos.entry_price * pos.quantity
                    + (pos.entry_price - price) * pos.quantity
                )
        return self.cash + positions_value

    def open_position(
        self,
        symbol: str,
        direction: str,
        price: float,
        capital_fraction: float,
        stop_loss_pct: float,
        take_profit_pct: float,
        signal_confidence: float,
        regime: str,
        current_date: str,
        current_prices: dict[str, float],
    ) -> bool:
        """Try to open a position. Returns True on success.

        Enforces:
          - No duplicate positions per symbol
          - Position size <= capital_fraction of current equity
          - Sufficient cash
        """
        if symbol in self.positions:
            return False

        equity = self.portfolio_value(current_prices)
        position_value = equity * capital_fraction
        if position_value > self.cash or position_value <= 0 or price <= 0:
            return False

        quantity = position_value / price

        if direction == "long":
            stop_loss = price * (1 - stop_loss_pct)
            take_profit = price * (1 + take_profit_pct)
        else:
            stop_loss = price * (1 + stop_loss_pct)
            take_profit = price * (1 - take_profit_pct)

        self.cash -= position_value
        self.positions[symbol] = _BacktestPosition(
            symbol=symbol,
            direction=direction,
            entry_price=price,
            entry_date=current_date,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            signal_confidence=signal_confidence,
            regime=regime,
        )
        return True

    def close_position(
        self,
        symbol: str,
        price: float,
        current_date: str,
    ) -> TradeRecord | None:
        """Close a position and return the trade record."""
        if symbol not in self.positions:
            return None

        pos = self.positions[symbol]

        if pos.direction == "long":
            pnl = (price - pos.entry_price) * pos.quantity
            returned_capital = price * pos.quantity
        else:
            pnl = (pos.entry_price - price) * pos.quantity
            returned_capital = pos.entry_price * pos.quantity + pnl

        self.cash += returned_capital

        trade = TradeRecord(
            symbol=symbol,
            direction=pos.direction,
            entry_date=pos.entry_date,
            entry_price=pos.entry_price,
            exit_date=current_date,
            exit_price=price,
            quantity=pos.quantity,
            pnl=pnl,
            signal_confidence=pos.signal_confidence,
            regime=pos.regime,
        )
        self.closed_trades.append(trade)
        del self.positions[symbol]
        return trade

    def check_stops(
        self,
        prices: dict[str, float],
        current_date: str,
    ) -> list[TradeRecord]:
        """Check stop-loss and take-profit levels, close triggered positions."""
        triggered: list[TradeRecord] = []
        symbols_to_close: list[tuple[str, float]] = []

        for sym, pos in self.positions.items():
            price = prices.get(sym)
            if price is None:
                continue

            if pos.direction == "long":
                if price <= pos.stop_loss or price >= pos.take_profit:
                    symbols_to_close.append((sym, price))
            else:
                if price >= pos.stop_loss or price <= pos.take_profit:
                    symbols_to_close.append((sym, price))

        for sym, price in symbols_to_close:
            trade = self.close_position(sym, price, current_date)
            if trade is not None:
                triggered.append(trade)

        return triggered


# ---------------------------------------------------------------------------
# Data download
# ---------------------------------------------------------------------------


def _download_ohlcv(
    symbols: list[str],
    start_date: str,
    end_date: str,
) -> dict[str, dict[str, list[Any]]]:
    """Download OHLCV data for multiple symbols via yfinance.

    Returns:
        Dict of symbol -> {dates, open, high, low, close, volume} where
        each value is a list aligned by index. Empty dict entries for
        symbols that fail.
    """
    if not _HAS_YFINANCE:
        return {}

    result: dict[str, dict[str, list[Any]]] = {}

    # Add buffer days before start for lookback window
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    buffered_start = (start_dt - timedelta(days=_MIN_LOOKBACK_DAYS + 30)).strftime(
        "%Y-%m-%d"
    )

    for symbol in symbols:
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(start=buffered_start, end=end_date, auto_adjust=True)
            if df is None or df.empty:
                logger.warning("No data returned for %s", symbol)
                continue

            result[symbol] = {
                "dates": [d.strftime("%Y-%m-%d") for d in df.index],
                "open": df["Open"].tolist(),
                "high": df["High"].tolist(),
                "low": df["Low"].tolist(),
                "close": df["Close"].tolist(),
                "volume": df["Volume"].tolist(),
            }
            logger.info(
                "Downloaded %d bars for %s (%s to %s)",
                len(df),
                symbol,
                result[symbol]["dates"][0],
                result[symbol]["dates"][-1],
            )
        except Exception as e:
            logger.error("Failed to download %s: %s", symbol, e)

    return result


# ---------------------------------------------------------------------------
# Core backtest loop
# ---------------------------------------------------------------------------


async def run_backtest(config: BacktestConfig) -> BacktestResult:
    """Execute a full historical backtest.

    Pipeline per trading day:
      1. Collect close prices up to current day for each symbol
      2. Compute daily log returns for SPY (or benchmark) -> regime detection
      3. Generate signals for each symbol using technical indicators + regime
      4. Execute trades when signal confidence > threshold
      5. Check stop-loss / take-profit on open positions
      6. Record daily equity

    Args:
        config: BacktestConfig with symbols, dates, capital, etc.

    Returns:
        BacktestResult with performance metrics and trade log.
    """
    if not _HAS_YFINANCE:
        return BacktestResult(
            total_return=0.0,
            annualized_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            total_trades=0,
            errors=[
                "yfinance is not installed. "
                "Install it with: pip install yfinance"
            ],
            config=asdict(config),
            run_timestamp=_utc_now().isoformat(),
        )

    # Download all data
    all_symbols = list(set(config.symbols + [config.benchmark]))
    data = _download_ohlcv(all_symbols, config.start_date, config.end_date)

    if not data:
        return BacktestResult(
            total_return=0.0,
            annualized_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            total_trades=0,
            errors=["No data available for any symbol"],
            config=asdict(config),
            run_timestamp=_utc_now().isoformat(),
        )

    # Find the common date range across all symbols
    date_sets = [set(d["dates"]) for d in data.values()]
    if not date_sets:
        return BacktestResult(
            total_return=0.0,
            annualized_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            total_trades=0,
            errors=["No overlapping dates found"],
            config=asdict(config),
            run_timestamp=_utc_now().isoformat(),
        )

    common_dates = sorted(date_sets[0].intersection(*date_sets[1:]))
    if len(common_dates) < _MIN_LOOKBACK_DAYS + 1:
        return BacktestResult(
            total_return=0.0,
            annualized_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            total_trades=0,
            errors=[
                f"Insufficient overlapping data: {len(common_dates)} days "
                f"(need at least {_MIN_LOOKBACK_DAYS + 1})"
            ],
            config=asdict(config),
            run_timestamp=_utc_now().isoformat(),
        )

    # Build date-indexed price lookup: symbol -> {date -> {o,h,l,c,v}}
    price_index: dict[str, dict[str, dict[str, float]]] = {}
    for sym, sym_data in data.items():
        price_index[sym] = {}
        for i, dt in enumerate(sym_data["dates"]):
            price_index[sym][dt] = {
                "open": sym_data["open"][i],
                "high": sym_data["high"][i],
                "low": sym_data["low"][i],
                "close": sym_data["close"][i],
                "volume": sym_data["volume"][i],
            }

    # Determine actual backtest start (skip lookback window)
    backtest_start_date = config.start_date
    trading_dates = [d for d in common_dates if d >= backtest_start_date]
    if len(trading_dates) < 2:
        return BacktestResult(
            total_return=0.0,
            annualized_return=0.0,
            sharpe_ratio=0.0,
            max_drawdown=0.0,
            win_rate=0.0,
            total_trades=0,
            errors=["Fewer than 2 trading days in backtest window"],
            config=asdict(config),
            run_timestamp=_utc_now().isoformat(),
        )

    # Initialize portfolio
    portfolio = _BacktestPortfolio(config.initial_capital)
    equity_curve: list[float] = []
    daily_returns: list[float] = []
    result_dates: list[str] = []
    errors: list[str] = []

    # Benchmark tracking (buy-and-hold from day 1)
    benchmark_start_price: float | None = None
    benchmark_equity_curve: list[float] = []

    for day_idx, current_date in enumerate(trading_dates):
        # Gather close prices for all symbols up to (and including) current_date
        lookback_dates = [d for d in common_dates if d <= current_date]

        current_prices: dict[str, float] = {}
        for sym in all_symbols:
            bar = price_index.get(sym, {}).get(current_date)
            if bar:
                current_prices[sym] = bar["close"]

        # Benchmark equity tracking
        bench_price = current_prices.get(config.benchmark)
        if bench_price is not None:
            if benchmark_start_price is None:
                benchmark_start_price = bench_price
            benchmark_equity_curve.append(
                config.initial_capital * (bench_price / benchmark_start_price)
            )

        # Check stop-loss / take-profit on existing positions
        portfolio.check_stops(current_prices, current_date)

        # Need enough lookback for indicators
        if len(lookback_dates) < _MIN_LOOKBACK_DAYS:
            # Record equity but skip signal generation
            equity = portfolio.portfolio_value(current_prices)
            equity_curve.append(equity)
            result_dates.append(current_date)
            if len(equity_curve) >= 2:
                prev = equity_curve[-2]
                daily_returns.append(
                    (equity / prev - 1) if prev > 0 else 0.0
                )
            continue

        # --- Regime Detection ---
        # Use benchmark returns for regime detection (market-wide signal)
        bench_closes: list[float] = []
        bench_timestamps: list[str] = []
        for d in lookback_dates:
            bar = price_index.get(config.benchmark, {}).get(d)
            if bar:
                bench_closes.append(bar["close"])
                bench_timestamps.append(d)

        regime = "unknown"
        regime_confidence = 0.0

        if len(bench_closes) >= 20:
            # Compute log returns for regime detection
            log_returns: list[float] = []
            for i in range(1, len(bench_closes)):
                if bench_closes[i - 1] > 0:
                    log_returns.append(
                        math.log(bench_closes[i] / bench_closes[i - 1])
                    )

            if len(log_returns) >= 10:
                return_series = ReturnSeries(
                    values=log_returns,
                    timestamps=bench_timestamps[1:],
                    symbol=config.benchmark,
                )
                try:
                    # Use rule-based only for backtest speed (HMM is expensive
                    # to fit on every single trading day)
                    detection = analyze_regime(
                        return_series, use_hmm=False, use_garch=False
                    )
                    regime = detection.regime
                    regime_confidence = detection.confidence
                except Exception as e:
                    errors.append(f"Regime detection failed on {current_date}: {e}")

        # --- Signal Generation ---
        signals: list[Signal] = []
        for sym in config.symbols:
            sym_closes: list[float] = []
            sym_highs: list[float] = []
            sym_lows: list[float] = []
            sym_volumes: list[float] = []

            for d in lookback_dates:
                bar = price_index.get(sym, {}).get(d)
                if bar:
                    sym_closes.append(bar["close"])
                    sym_highs.append(bar["high"])
                    sym_lows.append(bar["low"])
                    sym_volumes.append(bar["volume"])

            if len(sym_closes) < 20:
                continue

            try:
                indicators = compute_indicators(
                    sym, sym_closes, sym_highs, sym_lows, sym_volumes
                )
                signal = synthesize_signal(
                    sym, indicators, regime, regime_confidence
                )
                signals.append(signal)
            except Exception as e:
                errors.append(f"Signal generation failed for {sym} on {current_date}: {e}")

        # --- Trade Execution ---
        for signal in signals:
            sym = signal.symbol
            price = current_prices.get(sym)
            if price is None or price <= 0:
                continue

            # Close existing position on opposing signal
            if sym in portfolio.positions:
                pos = portfolio.positions[sym]
                should_close = False
                if pos.direction == "long" and signal.direction == "sell":
                    should_close = True
                elif pos.direction == "short" and signal.direction == "buy":
                    should_close = True
                # Also close on HOLD if we have a position
                if signal.direction == "hold" and signal.confidence > 0.5:
                    should_close = True

                if should_close:
                    portfolio.close_position(sym, price, current_date)

            # Open new position on buy/sell with sufficient confidence
            if signal.confidence >= config.confidence_threshold:
                if signal.direction == "buy" and sym not in portfolio.positions:
                    portfolio.open_position(
                        symbol=sym,
                        direction="long",
                        price=price,
                        capital_fraction=config.position_size_pct,
                        stop_loss_pct=config.stop_loss_pct,
                        take_profit_pct=config.take_profit_pct,
                        signal_confidence=signal.confidence,
                        regime=regime,
                        current_date=current_date,
                        current_prices=current_prices,
                    )
                elif signal.direction == "sell" and sym not in portfolio.positions:
                    portfolio.open_position(
                        symbol=sym,
                        direction="short",
                        price=price,
                        capital_fraction=config.position_size_pct,
                        stop_loss_pct=config.stop_loss_pct,
                        take_profit_pct=config.take_profit_pct,
                        signal_confidence=signal.confidence,
                        regime=regime,
                        current_date=current_date,
                        current_prices=current_prices,
                    )

        # --- Daily equity snapshot ---
        equity = portfolio.portfolio_value(current_prices)
        equity_curve.append(equity)
        result_dates.append(current_date)

        if len(equity_curve) >= 2:
            prev = equity_curve[-2]
            daily_returns.append(
                (equity / prev - 1) if prev > 0 else 0.0
            )

    # --- Close any remaining positions at final prices ---
    if trading_dates:
        final_date = trading_dates[-1]
        final_prices: dict[str, float] = {}
        for sym in all_symbols:
            bar = price_index.get(sym, {}).get(final_date)
            if bar:
                final_prices[sym] = bar["close"]

        for sym in list(portfolio.positions.keys()):
            price = final_prices.get(sym)
            if price:
                portfolio.close_position(sym, price, final_date)

    # --- Compute results ---
    trades = portfolio.closed_trades
    total_trades = len(trades)
    winning = [t for t in trades if t.pnl > 0]
    losing = [t for t in trades if t.pnl < 0]
    win_rate = len(winning) / total_trades if total_trades > 0 else 0.0
    avg_win = (
        sum(t.pnl for t in winning) / len(winning) if winning else 0.0
    )
    avg_loss = (
        abs(sum(t.pnl for t in losing) / len(losing)) if losing else 0.0
    )

    final_equity = equity_curve[-1] if equity_curve else config.initial_capital
    total_return = (final_equity / config.initial_capital) - 1

    # Calendar days for annualization
    if trading_dates:
        start_dt = datetime.strptime(trading_dates[0], "%Y-%m-%d")
        end_dt = datetime.strptime(trading_dates[-1], "%Y-%m-%d")
        calendar_days = max((end_dt - start_dt).days, 1)
    else:
        calendar_days = 1

    annualized = compute_annualized_return(total_return, calendar_days)
    sharpe = compute_sharpe(daily_returns)
    max_dd = compute_max_drawdown(equity_curve)
    calmar = compute_calmar_ratio(annualized, max_dd)
    pf = compute_profit_factor(trades)

    # Benchmark stats
    benchmark_total_return = 0.0
    benchmark_sharpe_val = 0.0
    benchmark_max_dd = 0.0

    if benchmark_equity_curve and len(benchmark_equity_curve) >= 2:
        benchmark_total_return = (
            benchmark_equity_curve[-1] / benchmark_equity_curve[0] - 1
        )
        bench_daily: list[float] = []
        for i in range(1, len(benchmark_equity_curve)):
            prev = benchmark_equity_curve[i - 1]
            if prev > 0:
                bench_daily.append(benchmark_equity_curve[i] / prev - 1)
        benchmark_sharpe_val = compute_sharpe(bench_daily)
        benchmark_max_dd = compute_max_drawdown(benchmark_equity_curve)

    result = BacktestResult(
        total_return=round(total_return, 6),
        annualized_return=round(annualized, 6),
        sharpe_ratio=round(sharpe, 4),
        max_drawdown=round(max_dd, 6),
        win_rate=round(win_rate, 4),
        total_trades=total_trades,
        equity_curve=equity_curve,
        daily_returns=daily_returns,
        dates=result_dates,
        benchmark_return=round(benchmark_total_return, 6),
        benchmark_sharpe=round(benchmark_sharpe_val, 4),
        benchmark_max_drawdown=round(benchmark_max_dd, 6),
        calmar_ratio=round(calmar, 4),
        avg_win=round(avg_win, 2),
        avg_loss=round(avg_loss, 2),
        profit_factor=round(pf, 4) if pf != float("inf") else 999.99,
        trades=trades,
        config=asdict(config),
        run_timestamp=_utc_now().isoformat(),
        errors=errors,
    )

    # Persist results
    _persist_result(result)

    return result


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _persist_result(result: BacktestResult) -> None:
    """Save backtest result to ~/.dharma/ginko/backtest/."""
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.fromisoformat(result.run_timestamp).strftime("%Y%m%d_%H%M%S")
    result_file = BACKTEST_DIR / f"backtest_{ts}.json"

    # Convert to serializable dict (exclude large equity_curve from JSON for readability,
    # store it in a companion file)
    summary = {
        "run_timestamp": result.run_timestamp,
        "config": result.config,
        "total_return": result.total_return,
        "annualized_return": result.annualized_return,
        "sharpe_ratio": result.sharpe_ratio,
        "max_drawdown": result.max_drawdown,
        "calmar_ratio": result.calmar_ratio,
        "win_rate": result.win_rate,
        "total_trades": result.total_trades,
        "avg_win": result.avg_win,
        "avg_loss": result.avg_loss,
        "profit_factor": result.profit_factor,
        "benchmark_return": result.benchmark_return,
        "benchmark_sharpe": result.benchmark_sharpe,
        "benchmark_max_drawdown": result.benchmark_max_drawdown,
        "trades": [asdict(t) for t in result.trades],
        "errors": result.errors,
    }

    try:
        result_file.write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Backtest result saved to %s", result_file)

        # Save equity curve separately (can be large)
        curve_file = BACKTEST_DIR / f"equity_{ts}.json"
        curve_data = {
            "dates": result.dates,
            "equity_curve": [round(v, 2) for v in result.equity_curve],
            "daily_returns": [round(v, 6) for v in result.daily_returns],
        }
        curve_file.write_text(
            json.dumps(curve_data, indent=2), encoding="utf-8"
        )
    except Exception as e:
        logger.error("Failed to persist backtest result: %s", e)


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_backtest_report(result: BacktestResult) -> str:
    """Format backtest results as a human-readable summary.

    Args:
        result: Completed BacktestResult.

    Returns:
        Multi-line string suitable for terminal or log output.
    """
    symbols = result.config.get("symbols", [])
    benchmark = result.config.get("benchmark", "SPY")
    start = result.config.get("start_date", "?")
    end = result.config.get("end_date", "?")
    initial = result.config.get("initial_capital", 100_000)

    final_equity = result.equity_curve[-1] if result.equity_curve else initial
    total_pnl = final_equity - initial

    lines = [
        "",
        "=" * 64,
        "  GINKO BACKTESTING ENGINE -- RESULTS",
        "=" * 64,
        "",
        f"  Period:          {start} to {end}",
        f"  Symbols:         {', '.join(symbols)}",
        f"  Benchmark:       {benchmark}",
        f"  Initial Capital: ${initial:,.2f}",
        f"  Final Equity:    ${final_equity:,.2f}",
        f"  Total P&L:       ${total_pnl:,.2f}",
        "",
        "-" * 64,
        "  PERFORMANCE",
        "-" * 64,
        f"  Total Return:      {result.total_return:+.2%}",
        f"  Annualized Return: {result.annualized_return:+.2%}",
        f"  Sharpe Ratio:      {result.sharpe_ratio:.4f}",
        f"  Calmar Ratio:      {result.calmar_ratio:.4f}",
        f"  Max Drawdown:      {result.max_drawdown:.2%}",
        "",
        "-" * 64,
        "  TRADE STATISTICS",
        "-" * 64,
        f"  Total Trades:    {result.total_trades}",
        f"  Win Rate:        {result.win_rate:.1%}",
        f"  Avg Win:         ${result.avg_win:,.2f}",
        f"  Avg Loss:        ${result.avg_loss:,.2f}",
        f"  Profit Factor:   {result.profit_factor:.2f}",
        "",
        "-" * 64,
        f"  BENCHMARK ({benchmark} Buy & Hold)",
        "-" * 64,
        f"  Benchmark Return:   {result.benchmark_return:+.2%}",
        f"  Benchmark Sharpe:   {result.benchmark_sharpe:.4f}",
        f"  Benchmark Max DD:   {result.benchmark_max_drawdown:.2%}",
        "",
        f"  Alpha (vs {benchmark}): {result.total_return - result.benchmark_return:+.2%}",
        "",
    ]

    if result.errors:
        lines.append("-" * 64)
        lines.append(f"  WARNINGS ({len(result.errors)})")
        lines.append("-" * 64)
        for err in result.errors[:10]:
            lines.append(f"    - {err}")
        if len(result.errors) > 10:
            lines.append(f"    ... and {len(result.errors) - 10} more")
        lines.append("")

    lines.append("=" * 64)
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for standalone backtest runs."""
    if not _HAS_YFINANCE:
        print(
            "ERROR: yfinance is not installed.\n"
            "Install it with: pip install yfinance\n"
            "Then re-run this module."
        )
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    config = BacktestConfig(
        symbols=["AAPL", "MSFT", "NVDA"],
        # start_date and end_date default to last 1 year
    )

    print(f"Starting backtest: {config.symbols}")
    print(f"Period: {config.start_date} to {config.end_date}")
    print(f"Initial capital: ${config.initial_capital:,.2f}")
    print(f"Benchmark: {config.benchmark}")
    print()

    result = asyncio.run(run_backtest(config))
    report = format_backtest_report(result)
    print(report)

    if result.errors:
        print(f"Completed with {len(result.errors)} warnings.")
    else:
        print("Completed successfully.")


if __name__ == "__main__":
    main()
