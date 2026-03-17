"""Ginko Signal Generation — combines data + regime into actionable signals.

Signal pipeline:
  1. Data pull (ginko_data) → raw prices + macro
  2. Regime detection (ginko_regime) → market state
  3. Technical indicators (ta library or built-in) → momentum/trend/volatility
  4. Signal synthesis → buy/sell/hold with confidence

Output: SignalReport objects consumed by orchestrator and Brier tracker.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
SIGNALS_DIR = GINKO_DIR / "signals"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SignalDirection(str, Enum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class SignalStrength(str, Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


@dataclass
class TechnicalIndicators:
    """Computed technical indicators for an asset."""
    symbol: str
    # Momentum
    rsi_14: float | None = None
    rsi_interpretation: str = ""  # "oversold", "neutral", "overbought"
    # Trend
    sma_20: float | None = None
    sma_50: float | None = None
    price_vs_sma20: float | None = None   # % above/below
    trend_direction: str = ""  # "up", "down", "flat"
    # Volatility
    atr_14: float | None = None
    bollinger_position: float | None = None  # 0=lower band, 1=upper band
    # Volume
    volume_ratio: float | None = None  # current vs 20-day avg


@dataclass
class Signal:
    """A single actionable signal for an asset."""
    symbol: str
    direction: str  # buy/sell/hold
    strength: str   # strong/moderate/weak
    confidence: float  # 0.0 to 1.0
    reason: str
    regime: str
    indicators: TechnicalIndicators | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SECSignal:
    """Signal derived from SEC filing analysis."""
    ticker: str
    filing_type: str  # "10-K", "10-Q", "8-K"
    sentiment: str    # "bullish", "bearish", "neutral"
    confidence: float  # 0.0 to 1.0
    key_findings: list[str] = field(default_factory=list)


@dataclass
class SignalReport:
    """Complete signal report for a cycle."""
    timestamp: str
    regime: str
    regime_confidence: float
    signals: list[Signal] = field(default_factory=list)
    macro_summary: str = ""
    risk_level: str = "moderate"  # "low", "moderate", "high", "extreme"
    errors: list[str] = field(default_factory=list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TECHNICAL INDICATORS (built-in, no external deps)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def compute_rsi(prices: list[float], period: int = 14) -> float | None:
    """Compute Relative Strength Index.

    RSI = 100 - (100 / (1 + RS))
    RS = avg_gain / avg_loss over period
    """
    if len(prices) < period + 1:
        return None

    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    recent = deltas[-(period):]

    gains = [d for d in recent if d > 0]
    losses = [-d for d in recent if d < 0]

    avg_gain = sum(gains) / period if gains else 0
    avg_loss = sum(losses) / period if losses else 0.0001

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_sma(prices: list[float], period: int) -> float | None:
    """Simple Moving Average."""
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def compute_atr(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    period: int = 14,
) -> float | None:
    """Average True Range."""
    if len(highs) < period + 1:
        return None

    trs = []
    for i in range(1, len(highs)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)

    recent = trs[-period:]
    return sum(recent) / len(recent) if recent else None


def compute_bollinger_position(
    prices: list[float],
    period: int = 20,
    num_std: float = 2.0,
) -> float | None:
    """Position within Bollinger Bands (0=lower, 0.5=middle, 1=upper)."""
    if len(prices) < period:
        return None

    window = prices[-period:]
    sma = sum(window) / period
    std = math.sqrt(sum((p - sma) ** 2 for p in window) / period)

    if std == 0:
        return 0.5

    upper = sma + num_std * std
    lower = sma - num_std * std
    current = prices[-1]

    if upper == lower:
        return 0.5

    return max(0.0, min(1.0, (current - lower) / (upper - lower)))


def compute_indicators(
    symbol: str,
    prices: list[float],
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
) -> TechnicalIndicators:
    """Compute all technical indicators for an asset.

    Args:
        symbol: Ticker symbol.
        prices: Close prices (oldest to newest).
        highs: High prices (optional, for ATR).
        lows: Low prices (optional, for ATR).
        volumes: Volume data (optional, for volume ratio).
    """
    indicators = TechnicalIndicators(symbol=symbol)

    # RSI
    rsi = compute_rsi(prices)
    if rsi is not None:
        indicators.rsi_14 = round(rsi, 2)
        if rsi < 30:
            indicators.rsi_interpretation = "oversold"
        elif rsi > 70:
            indicators.rsi_interpretation = "overbought"
        else:
            indicators.rsi_interpretation = "neutral"

    # SMAs
    indicators.sma_20 = compute_sma(prices, 20)
    indicators.sma_50 = compute_sma(prices, 50)

    if indicators.sma_20 and prices:
        indicators.price_vs_sma20 = round(
            ((prices[-1] / indicators.sma_20) - 1) * 100, 2
        )

    # Trend direction
    if indicators.sma_20 and indicators.sma_50:
        if indicators.sma_20 > indicators.sma_50 * 1.01:
            indicators.trend_direction = "up"
        elif indicators.sma_20 < indicators.sma_50 * 0.99:
            indicators.trend_direction = "down"
        else:
            indicators.trend_direction = "flat"

    # ATR
    if highs and lows:
        indicators.atr_14 = compute_atr(highs, lows, prices)

    # Bollinger position
    indicators.bollinger_position = compute_bollinger_position(prices)

    # Volume ratio
    if volumes and len(volumes) >= 20:
        avg_vol = sum(volumes[-20:]) / 20
        if avg_vol > 0:
            indicators.volume_ratio = round(volumes[-1] / avg_vol, 2)

    return indicators


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SIGNAL SYNTHESIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def synthesize_signal(
    symbol: str,
    indicators: TechnicalIndicators,
    regime: str,
    regime_confidence: float,
) -> Signal:
    """Combine technical indicators and regime into a signal.

    Signal logic:
      - Regime provides the primary bias (bull → buy bias, bear → sell bias)
      - RSI extremes trigger counter-trend caution
      - Trend alignment with regime increases confidence
      - Bollinger extremes add confirmation
    """
    scores: list[float] = []  # positive = buy, negative = sell
    reasons: list[str] = []

    # 1. Regime bias (weight: 0.35)
    regime_score = 0.0
    if regime == "bull":
        regime_score = 0.6
        reasons.append(f"bull regime (conf={regime_confidence:.0%})")
    elif regime == "bear":
        regime_score = -0.6
        reasons.append(f"bear regime (conf={regime_confidence:.0%})")
    else:
        reasons.append(f"sideways regime (conf={regime_confidence:.0%})")
    scores.append(regime_score * 0.35)

    # 2. RSI (weight: 0.25)
    if indicators.rsi_14 is not None:
        if indicators.rsi_14 < 30:
            scores.append(0.25)
            reasons.append(f"RSI oversold ({indicators.rsi_14:.0f})")
        elif indicators.rsi_14 > 70:
            scores.append(-0.25)
            reasons.append(f"RSI overbought ({indicators.rsi_14:.0f})")
        else:
            # Slight bias based on RSI position relative to 50
            rsi_bias = (indicators.rsi_14 - 50) / 100
            scores.append(rsi_bias * 0.15)

    # 3. Trend alignment (weight: 0.25)
    if indicators.trend_direction == "up":
        scores.append(0.25)
        reasons.append("uptrend (SMA20 > SMA50)")
    elif indicators.trend_direction == "down":
        scores.append(-0.25)
        reasons.append("downtrend (SMA20 < SMA50)")

    # 4. Bollinger position (weight: 0.15)
    if indicators.bollinger_position is not None:
        if indicators.bollinger_position < 0.15:
            scores.append(0.15)
            reasons.append("near lower Bollinger band")
        elif indicators.bollinger_position > 0.85:
            scores.append(-0.15)
            reasons.append("near upper Bollinger band")

    # Aggregate
    total = sum(scores)
    abs_total = abs(total)

    if total > 0.15:
        direction = SignalDirection.BUY
    elif total < -0.15:
        direction = SignalDirection.SELL
    else:
        direction = SignalDirection.HOLD

    if abs_total > 0.4:
        strength = SignalStrength.STRONG
    elif abs_total > 0.2:
        strength = SignalStrength.MODERATE
    else:
        strength = SignalStrength.WEAK

    # Confidence = how decisive the signal is
    confidence = min(1.0, abs_total * 2)

    return Signal(
        symbol=symbol,
        direction=direction.value,
        strength=strength.value,
        confidence=round(confidence, 3),
        reason="; ".join(reasons),
        regime=regime,
        indicators=indicators,
    )


def generate_macro_summary(
    macro_data: dict[str, Any] | None,
    regime: str,
) -> str:
    """Generate human-readable macro summary."""
    if not macro_data:
        return "No macro data available."

    parts = [f"Regime: {regime.upper()}"]

    if macro_data.get("fed_funds_rate") is not None:
        parts.append(f"Fed Funds: {macro_data['fed_funds_rate']:.2f}%")
    if macro_data.get("yield_spread") is not None:
        spread = macro_data["yield_spread"]
        parts.append(f"Yield spread (10Y-2Y): {spread:.2f}%")
        if spread < 0:
            parts.append("WARNING: yield curve inverted")
    if macro_data.get("vix") is not None:
        vix = macro_data["vix"]
        parts.append(f"VIX: {vix:.1f}")
        if vix > 30:
            parts.append("WARNING: elevated fear")

    return " | ".join(parts)


def assess_risk_level(
    regime: str,
    vix: float | None = None,
    yield_spread: float | None = None,
) -> str:
    """Assess overall market risk level.

    Returns: "low", "moderate", "high", "extreme"
    """
    risk_score = 0.0

    if regime == "bear":
        risk_score += 2.0
    elif regime == "sideways":
        risk_score += 1.0

    if vix is not None:
        if vix > 35:
            risk_score += 2.0
        elif vix > 25:
            risk_score += 1.0

    if yield_spread is not None and yield_spread < 0:
        risk_score += 1.5

    if risk_score >= 4.0:
        return "extreme"
    elif risk_score >= 2.5:
        return "high"
    elif risk_score >= 1.0:
        return "moderate"
    return "low"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# REPORT GENERATION + PERSISTENCE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def generate_signal_report(
    regime: str,
    regime_confidence: float,
    price_data: dict[str, list[float]],
    macro_data: dict[str, Any] | None = None,
    sec_signals: list[SECSignal] | None = None,
) -> SignalReport:
    """Generate a complete signal report.

    Args:
        regime: Current market regime ("bull", "bear", "sideways").
        regime_confidence: Regime detection confidence.
        price_data: Dict of symbol → list of close prices.
        macro_data: Macro snapshot dict (from ginko_data).

    Returns:
        SignalReport with signals for each symbol.
    """
    report = SignalReport(
        timestamp=_utc_now().isoformat(),
        regime=regime,
        regime_confidence=regime_confidence,
    )

    for symbol, prices in price_data.items():
        try:
            indicators = compute_indicators(symbol, prices)
            signal = synthesize_signal(symbol, indicators, regime, regime_confidence)
            report.signals.append(signal)
        except Exception as e:
            report.errors.append(f"{symbol}: {e}")

    if macro_data:
        report.macro_summary = generate_macro_summary(macro_data, regime)
        report.risk_level = assess_risk_level(
            regime,
            vix=macro_data.get("vix"),
            yield_spread=macro_data.get("yield_spread"),
        )

    # Incorporate SEC signals if provided
    if sec_signals:
        incorporate_sec_signals(report, sec_signals)

    # Persist
    _persist_report(report)

    return report


def _persist_report(report: SignalReport) -> None:
    """Save signal report to disk."""
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.fromisoformat(report.timestamp).strftime("%Y%m%d_%H%M%S")
    report_file = SIGNALS_DIR / f"signals_{ts}.json"
    try:
        report_file.write_text(
            json.dumps(_report_to_dict(report), indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error("Failed to persist signal report: %s", e)


def _report_to_dict(report: SignalReport) -> dict[str, Any]:
    """Convert SignalReport to serializable dict."""
    return {
        "timestamp": report.timestamp,
        "regime": report.regime,
        "regime_confidence": report.regime_confidence,
        "signals": [
            {
                "symbol": s.symbol,
                "direction": s.direction,
                "strength": s.strength,
                "confidence": s.confidence,
                "reason": s.reason,
                "regime": s.regime,
                "indicators": asdict(s.indicators) if s.indicators else None,
            }
            for s in report.signals
        ],
        "macro_summary": report.macro_summary,
        "risk_level": report.risk_level,
        "errors": report.errors,
    }


def load_latest_report() -> dict[str, Any] | None:
    """Load the most recent signal report."""
    if not SIGNALS_DIR.exists():
        return None

    files = sorted(SIGNALS_DIR.glob("signals_*.json"), reverse=True)
    if not files:
        return None

    try:
        return json.loads(files[0].read_text(encoding="utf-8"))
    except Exception as e:
        logger.error("Failed to load signal report: %s", e)
        return None


def format_signal_report(report: SignalReport) -> str:
    """Format signal report as human-readable text."""
    lines = [
        "Shakti Ginko — Signal Report",
        "=" * 40,
        f"Timestamp: {report.timestamp}",
        f"Regime: {report.regime.upper()} (confidence: {report.regime_confidence:.0%})",
        f"Risk level: {report.risk_level.upper()}",
    ]

    if report.macro_summary:
        lines.append(f"\nMacro: {report.macro_summary}")

    lines.append(f"\nSignals ({len(report.signals)}):")
    for s in report.signals:
        arrow = {"buy": "+", "sell": "-", "hold": "="}[s.direction]
        lines.append(
            f"  [{arrow}] {s.symbol}: {s.direction.upper()} "
            f"({s.strength}, conf={s.confidence:.0%}) — {s.reason}"
        )

    if report.errors:
        lines.append(f"\nErrors: {', '.join(report.errors)}")

    return "\n".join(lines)


def incorporate_sec_signals(
    report: SignalReport,
    sec_signals: list[SECSignal],
) -> SignalReport:
    """Adjust signal confidence based on SEC filing analysis.

    When SEC signal aligns with technical signal: boost confidence by 15%.
    When SEC signal conflicts: reduce confidence by 20%, add warning.

    Args:
        report: Existing signal report with technical signals.
        sec_signals: SEC filing analysis signals.

    Returns:
        Updated SignalReport (modifies in place and returns).
    """
    sec_by_ticker = {s.ticker: s for s in sec_signals}

    for signal in report.signals:
        sec = sec_by_ticker.get(signal.symbol)
        if not sec:
            continue

        # Determine alignment
        signal_bullish = signal.direction == "buy"
        signal_bearish = signal.direction == "sell"
        sec_bullish = sec.sentiment == "bullish"
        sec_bearish = sec.sentiment == "bearish"

        if (signal_bullish and sec_bullish) or (signal_bearish and sec_bearish):
            # Aligned — boost confidence by 15%
            old_conf = signal.confidence
            signal.confidence = min(1.0, signal.confidence + 0.15)
            signal.reason += f"; SEC {sec.sentiment} aligns (+15% conf)"
            signal.metadata["sec_alignment"] = "aligned"
            signal.metadata["sec_confidence_boost"] = round(signal.confidence - old_conf, 3)
        elif (signal_bullish and sec_bearish) or (signal_bearish and sec_bullish):
            # Conflicting — reduce confidence by 20%
            old_conf = signal.confidence
            signal.confidence = max(0.0, signal.confidence - 0.20)
            signal.reason += f"; WARNING: SEC {sec.sentiment} conflicts (-20% conf)"
            signal.metadata["sec_alignment"] = "conflicting"
            signal.metadata["sec_confidence_reduction"] = round(old_conf - signal.confidence, 3)
        else:
            # Neutral SEC or hold signal — minor note
            signal.metadata["sec_alignment"] = "neutral"

        signal.metadata["sec_findings"] = sec.key_findings[:3]

    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MULTI-TIMEFRAME ANALYSIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class TimeFrame(str, Enum):
    """Trading timeframes for multi-timeframe analysis."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


def resample_to_weekly(daily_prices: list[float]) -> list[float]:
    """Approximate weekly closes by taking every 5th daily price.

    Takes prices at index 4, 9, 14, ... (0-based), simulating end-of-week
    closes from daily data. If the last chunk has fewer than 5 bars, the
    final daily price is included as the most recent weekly close.

    Args:
        daily_prices: Daily close prices, oldest to newest.

    Returns:
        Resampled weekly prices.
    """
    if not daily_prices:
        return []
    weekly = [daily_prices[i] for i in range(4, len(daily_prices), 5)]
    # Always include the latest price if the tail is incomplete
    if len(daily_prices) % 5 != 0:
        weekly.append(daily_prices[-1])
    return weekly


def resample_to_monthly(daily_prices: list[float]) -> list[float]:
    """Approximate monthly closes by taking every 21st daily price.

    Takes prices at index 20, 41, 62, ... (0-based), simulating end-of-month
    closes from daily data. If the last chunk has fewer than 21 bars, the
    final daily price is included as the most recent monthly close.

    Args:
        daily_prices: Daily close prices, oldest to newest.

    Returns:
        Resampled monthly prices.
    """
    if not daily_prices:
        return []
    monthly = [daily_prices[i] for i in range(20, len(daily_prices), 21)]
    # Always include the latest price if the tail is incomplete
    if len(daily_prices) % 21 != 0:
        monthly.append(daily_prices[-1])
    return monthly


def get_timeframe_alignment(
    daily_signal: Signal,
    weekly_signal: Signal,
    monthly_signal: Signal,
) -> tuple[bool, str]:
    """Check whether three timeframes agree on direction.

    Args:
        daily_signal: Signal from daily timeframe.
        weekly_signal: Signal from weekly timeframe.
        monthly_signal: Signal from monthly timeframe.

    Returns:
        Tuple of (aligned, detail) where aligned is True if all three
        timeframes share the same direction, and detail is a human-readable
        description of the alignment state.
    """
    directions = {
        TimeFrame.DAILY.value: daily_signal.direction,
        TimeFrame.WEEKLY.value: weekly_signal.direction,
        TimeFrame.MONTHLY.value: monthly_signal.direction,
    }
    unique = set(directions.values())

    if len(unique) == 1:
        direction = unique.pop()
        return True, f"all timeframes aligned: {direction}"

    parts = [f"{tf}={d}" for tf, d in directions.items()]
    return False, f"timeframe divergence: {', '.join(parts)}"


def generate_multi_timeframe_report(
    regime: str,
    regime_confidence: float,
    daily_price_data: dict[str, list[float]],
    macro_data: dict[str, Any] | None = None,
) -> SignalReport:
    """Generate a signal report with multi-timeframe confluence analysis.

    Runs the standard signal pipeline on daily, weekly, and monthly
    resampled prices and adjusts confidence based on cross-timeframe
    agreement.

    Rules:
      - All 3 timeframes agree on direction: confidence += 0.25 (cap 1.0)
      - Timeframes conflict: confidence -= 0.20 (floor 0.0), reason
        gets a "timeframe divergence" annotation

    Args:
        regime: Current market regime ("bull", "bear", "sideways").
        regime_confidence: Regime detection confidence (0-1).
        daily_price_data: Dict of symbol -> list of daily close prices.
        macro_data: Optional macro snapshot dict.

    Returns:
        SignalReport with confidence values adjusted for timeframe alignment.
    """
    # 1. Generate daily report (this is the base report we return)
    daily_report = generate_signal_report(
        regime, regime_confidence, daily_price_data, macro_data,
    )

    # 2. Resample prices to weekly and monthly
    weekly_prices: dict[str, list[float]] = {}
    monthly_prices: dict[str, list[float]] = {}
    for symbol, prices in daily_price_data.items():
        weekly_prices[symbol] = resample_to_weekly(prices)
        monthly_prices[symbol] = resample_to_monthly(prices)

    # 3. Generate weekly and monthly reports
    weekly_report = generate_signal_report(
        regime, regime_confidence, weekly_prices, macro_data,
    )
    monthly_report = generate_signal_report(
        regime, regime_confidence, monthly_prices, macro_data,
    )

    # Build lookup maps for weekly and monthly signals by symbol
    weekly_by_symbol = {s.symbol: s for s in weekly_report.signals}
    monthly_by_symbol = {s.symbol: s for s in monthly_report.signals}

    # 4. Adjust daily signals based on timeframe alignment
    for signal in daily_report.signals:
        weekly_signal = weekly_by_symbol.get(signal.symbol)
        monthly_signal = monthly_by_symbol.get(signal.symbol)

        if weekly_signal is None or monthly_signal is None:
            # Insufficient data at longer timeframes -- skip adjustment
            signal.metadata["mtf_status"] = "insufficient_data"
            continue

        aligned, detail = get_timeframe_alignment(
            signal, weekly_signal, monthly_signal,
        )

        if aligned:
            # All 3 timeframes agree -- boost confidence
            old_conf = signal.confidence
            signal.confidence = min(1.0, signal.confidence + 0.25)
            signal.reason += f"; MTF aligned ({detail})"
            signal.metadata["mtf_aligned"] = True
            signal.metadata["mtf_boost"] = round(signal.confidence - old_conf, 3)
        else:
            # Timeframes conflict -- reduce confidence
            old_conf = signal.confidence
            signal.confidence = max(0.0, signal.confidence - 0.20)
            signal.reason += f"; timeframe divergence ({detail})"
            signal.metadata["mtf_aligned"] = False
            signal.metadata["mtf_reduction"] = round(old_conf - signal.confidence, 3)

        signal.metadata["mtf_detail"] = detail
        signal.metadata["mtf_weekly_direction"] = weekly_signal.direction
        signal.metadata["mtf_monthly_direction"] = monthly_signal.direction

    return daily_report
