#!/usr/bin/env python3
"""Ginko Signal Runner — fetch historical data, run HMM+GARCH regime detection,
generate buy/sell/hold signals, and save report to ~/.dharma/ginko/signals/.

Usage:
    python3 scripts/ginko_run_signals.py
    python3 scripts/ginko_run_signals.py --symbols SPY QQQ AAPL NVDA
    python3 scripts/ginko_run_signals.py --days 180
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Ensure dharma_swarm is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


DEFAULT_SYMBOLS = ["SPY", "QQQ", "IWM", "TLT", "GLD", "AAPL", "NVDA", "MSFT"]
DEFAULT_DAYS = 252  # 1 year of trading days


def fetch_historical_data(
    symbols: list[str], days: int
) -> dict[str, dict[str, list[float]]]:
    """Fetch historical OHLCV data via yfinance.

    Returns dict of symbol -> {close, high, low, volume} lists.
    """
    import yfinance as yf

    period = f"{max(days, 60)}d"
    result: dict[str, dict[str, list[float]]] = {}

    for sym in symbols:
        try:
            ticker = yf.Ticker(sym)
            hist = ticker.history(period=period)
            if hist.empty:
                print(f"  [WARN] No data for {sym}")
                continue
            result[sym] = {
                "close": hist["Close"].tolist(),
                "high": hist["High"].tolist(),
                "low": hist["Low"].tolist(),
                "volume": hist["Volume"].tolist(),
            }
            print(f"  {sym}: {len(hist)} bars")
        except Exception as e:
            print(f"  [ERR] {sym}: {e}")

    return result


def compute_returns(prices: list[float]) -> list[float]:
    """Compute daily log returns from close prices."""
    returns = []
    for i in range(1, len(prices)):
        if prices[i - 1] > 0:
            returns.append(np.log(prices[i] / prices[i - 1]))
    return returns


def run_signal_pipeline(
    symbols: list[str], days: int
) -> None:
    """Main pipeline: fetch data -> regime detection -> signal generation -> report."""
    from dharma_swarm.ginko_regime import ReturnSeries, analyze_regime
    from dharma_swarm.ginko_signals import (
        compute_indicators,
        format_signal_report,
        generate_signal_report,
    )

    print("=" * 60)
    print("SHAKTI GINKO — Signal Generation Pipeline")
    print(f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    print("=" * 60)

    # 1. Fetch historical data
    print(f"\n[1/4] Fetching {days}d historical data for {len(symbols)} symbols...")
    hist_data = fetch_historical_data(symbols, days)

    if not hist_data:
        print("ERROR: No data fetched. Check network/yfinance.")
        sys.exit(1)

    # 2. Regime detection using SPY (or first available symbol)
    regime_symbol = "SPY" if "SPY" in hist_data else next(iter(hist_data))
    spy_closes = hist_data[regime_symbol]["close"]
    spy_returns = compute_returns(spy_closes)

    print(f"\n[2/4] Running regime detection on {regime_symbol} ({len(spy_returns)} return observations)...")
    series = ReturnSeries(
        values=spy_returns,
        timestamps=[],
        symbol=regime_symbol,
    )
    regime_result = analyze_regime(series, use_hmm=True, use_garch=True)

    print(f"  Regime: {regime_result.regime.upper()}")
    print(f"  Method: {regime_result.method}")
    print(f"  Confidence: {regime_result.confidence:.1%}")
    if regime_result.volatility_forecast is not None:
        print(f"  Vol forecast (ann.): {regime_result.volatility_forecast:.1%}")
    if regime_result.volatility_current is not None:
        print(f"  Vol current (ann.): {regime_result.volatility_current:.1%}")

    # GARCH details if present
    garch_vol = regime_result.indicators.get("garch_vol_forecast")
    if garch_vol is not None:
        print(f"  GARCH vol forecast: {garch_vol:.1%}")
        persistence = regime_result.indicators.get("garch_persistence")
        if persistence is not None:
            print(f"  GARCH persistence: {persistence:.4f}")

    # 3. Generate signals
    print(f"\n[3/4] Generating signals for {len(hist_data)} symbols...")
    price_data = {sym: d["close"] for sym, d in hist_data.items()}

    report = generate_signal_report(
        regime=regime_result.regime,
        regime_confidence=regime_result.confidence,
        price_data=price_data,
        macro_data=None,  # FRED requires API key
    )

    # Enrich signals with full OHLCV indicators
    for signal in report.signals:
        sym = signal.symbol
        if sym in hist_data:
            d = hist_data[sym]
            from dharma_swarm.ginko_signals import compute_indicators as _ci
            signal.indicators = _ci(
                sym, d["close"],
                highs=d["high"],
                lows=d["low"],
                volumes=d["volume"],
            )

    # 4. Output report
    print(f"\n[4/4] Signal Report")
    print("-" * 60)
    report_text = format_signal_report(report)
    print(report_text)

    # Also print detailed per-signal indicators
    print("\n" + "-" * 60)
    print("DETAILED INDICATORS:")
    for s in report.signals:
        ind = s.indicators
        if ind is None:
            continue
        parts = [f"  {s.symbol}:"]
        if ind.rsi_14 is not None:
            parts.append(f"RSI={ind.rsi_14:.0f}({ind.rsi_interpretation})")
        if ind.trend_direction:
            parts.append(f"Trend={ind.trend_direction}")
        if ind.price_vs_sma20 is not None:
            parts.append(f"Price/SMA20={ind.price_vs_sma20:+.1f}%")
        if ind.bollinger_position is not None:
            parts.append(f"BB={ind.bollinger_position:.2f}")
        if ind.atr_14 is not None:
            parts.append(f"ATR={ind.atr_14:.2f}")
        if ind.volume_ratio is not None:
            parts.append(f"VolRatio={ind.volume_ratio:.2f}")
        print(" | ".join(parts))

    # Regime detection metadata
    print(f"\n{'=' * 60}")
    print("REGIME DETECTION DETAIL:")
    for k, v in regime_result.indicators.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.6f}")
        else:
            print(f"  {k}: {v}")

    # Confirm save location
    from dharma_swarm.ginko_signals import SIGNALS_DIR
    print(f"\nReport saved to: {SIGNALS_DIR}/")

    # Return for programmatic use
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ginko Signal Runner")
    parser.add_argument(
        "--symbols", nargs="+", default=DEFAULT_SYMBOLS,
        help="Ticker symbols to analyze",
    )
    parser.add_argument(
        "--days", type=int, default=DEFAULT_DAYS,
        help="Days of historical data to fetch",
    )
    args = parser.parse_args()

    run_signal_pipeline(args.symbols, args.days)
