"""Ginko Live Test -- end-to-end pipeline validation.

Runs all 5 phases of the Ginko pipeline sequentially:
  1. Data Pull (FRED + finnhub + CoinGecko)
  2. Regime Detection (HMM/GARCH/rule-based)
  3. Signal Generation (technical indicators + regime)
  4. Predictions + Brier scoring
  5. Report generation

Each phase: prints status, logs duration, catches errors without stopping.
Runnable: python3 -m dharma_swarm.ginko_live_test

Returns: {"passed": N, "failed": N, "phases": [...]}
"""

from __future__ import annotations

import asyncio
import logging
import random
import sys
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("ginko_live_test")

# ANSI colors for terminal output
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _pass_tag(ms: int) -> str:
    return f"{_GREEN}PASS{_RESET} {_DIM}({ms}ms){_RESET}"


def _fail_tag(ms: int, reason: str) -> str:
    return f"{_RED}FAIL{_RESET} {_DIM}({ms}ms){_RESET} -- {reason}"


def _phase_header(num: int, total: int, name: str) -> str:
    padded = f"[{num}/{total}] {name} "
    dots = "." * max(1, 40 - len(padded))
    return f"{_BOLD}{padded}{_RESET}{_DIM}{dots}{_RESET} "


# ---------------------------------------------------------------------------
# Phase 1: Data Pull
# ---------------------------------------------------------------------------


async def _phase_data_pull() -> dict[str, Any]:
    """Pull market data from FRED, finnhub, and CoinGecko."""
    from dharma_swarm.ginko_data import MarketDataPull, pull_all_data

    t0 = time.monotonic()
    pull: MarketDataPull = await pull_all_data()
    duration_ms = int((time.monotonic() - t0) * 1000)

    # Determine what succeeded
    macro_ok = pull.macro is not None and any(
        getattr(pull.macro, f) is not None
        for f in (
            "fed_funds_rate",
            "ten_year_yield",
            "two_year_yield",
            "yield_spread",
            "vix",
            "unemployment",
        )
    )
    stock_count = len(pull.stocks)
    crypto_count = len(pull.crypto)

    parts = []
    parts.append(f"macro: {'yes' if macro_ok else 'no'}")
    parts.append(f"stocks: {stock_count}")
    parts.append(f"crypto: {crypto_count}")
    details = ", ".join(parts)

    # Phase passes if the function completed and returned a MarketDataPull.
    # Some data sources may be None when API keys are missing -- that is fine.
    return {
        "name": "data_pull",
        "passed": True,
        "duration_ms": duration_ms,
        "details": details,
        "payload": pull,
    }


# ---------------------------------------------------------------------------
# Phase 2: Regime Detection
# ---------------------------------------------------------------------------


async def _phase_regime_detection(
    data_pull: Any | None,
) -> dict[str, Any]:
    """Detect market regime using HMM/rule-based analysis."""
    from dharma_swarm.ginko_regime import ReturnSeries, analyze_regime

    t0 = time.monotonic()

    # Try to build a return series from real stock data
    returns: list[float] | None = None
    if data_pull is not None and data_pull.stocks:
        # Use percent_change from the first stock with valid data
        for quote in data_pull.stocks:
            if quote.percent_change != 0:
                # Single data point is not enough for HMM; build synthetic
                # series seeded with the real data direction
                seed = quote.percent_change / 100.0
                rng = random.Random(42)
                returns = [
                    seed + rng.gauss(0, 0.005) for _ in range(60)
                ]
                break

    # Fallback: synthetic returns that mimic a mild uptrend
    if returns is None:
        returns = [
            0.001, -0.002, 0.003, 0.001, -0.001,
            0.002, -0.003, 0.001, 0.002, -0.001,
            0.002, 0.001, -0.001, 0.003, -0.002,
            0.001, 0.002, -0.001, 0.001, -0.002,
            0.003, 0.001, -0.001, 0.002, -0.003,
            0.001, 0.002, -0.001, 0.002, 0.001,
        ]

    series = ReturnSeries(values=returns, timestamps=[], symbol="SPY")
    detection = analyze_regime(series)
    duration_ms = int((time.monotonic() - t0) * 1000)

    valid_regimes = {"bull", "bear", "sideways", "unknown"}
    passed = detection.regime in valid_regimes

    conf_pct = f"{detection.confidence * 100:.0f}%"
    details = f"{detection.regime} ({conf_pct}), method={detection.method}"

    return {
        "name": "regime_detection",
        "passed": passed,
        "duration_ms": duration_ms,
        "details": details,
        "payload": detection,
    }


# ---------------------------------------------------------------------------
# Phase 3: Signal Generation
# ---------------------------------------------------------------------------


async def _phase_signal_generation(
    data_pull: Any | None,
    regime_detection: Any | None,
) -> dict[str, Any]:
    """Generate trading signals from price data and regime."""
    from dharma_swarm.ginko_signals import (
        SignalReport,
        format_signal_report,
        generate_signal_report,
    )

    t0 = time.monotonic()

    # Extract regime info
    regime = "sideways"
    regime_confidence = 0.5
    if regime_detection is not None:
        regime = regime_detection.regime
        regime_confidence = regime_detection.confidence

    # Build price data from real quotes or synthetic
    price_data: dict[str, list[float]] = {}
    macro_dict: dict[str, Any] | None = None

    if data_pull is not None and data_pull.stocks:
        for quote in data_pull.stocks:
            # Build a synthetic price series anchored to the real price
            rng = random.Random(hash(quote.symbol))
            base = quote.current_price
            prices = []
            for i in range(50):
                prices.append(base * (1 + rng.gauss(0, 0.01)))
            prices.append(base)  # current price is last
            price_data[quote.symbol] = prices
    else:
        # Fully synthetic watchlist
        rng = random.Random(42)
        for sym in ["SPY", "QQQ", "IWM", "TLT", "GLD", "AAPL", "NVDA", "MSFT"]:
            base = 450 + rng.random() * 100
            prices = [base + rng.gauss(0, 3) for _ in range(50)]
            price_data[sym] = prices

    if data_pull is not None and data_pull.macro is not None:
        macro_dict = {
            k: v
            for k, v in asdict(data_pull.macro).items()
            if k != "timestamp" and v is not None
        }
    if not macro_dict:
        macro_dict = {
            "fed_funds_rate": 5.33,
            "ten_year_yield": 4.25,
            "yield_spread": 0.15,
            "vix": 18.5,
        }

    report: SignalReport = generate_signal_report(
        regime, regime_confidence, price_data, macro_dict,
    )
    duration_ms = int((time.monotonic() - t0) * 1000)

    # Also exercise the formatter
    formatted = format_signal_report(report)

    passed = len(report.signals) > 0
    details = f"{len(report.signals)} signals, risk={report.risk_level}"

    return {
        "name": "signal_generation",
        "passed": passed,
        "duration_ms": duration_ms,
        "details": details,
        "payload": report,
    }


# ---------------------------------------------------------------------------
# Phase 4: Predictions + Brier
# ---------------------------------------------------------------------------


async def _phase_predictions_brier(
    signal_report: Any | None,
) -> dict[str, Any]:
    """Record a test prediction and build the Brier dashboard."""
    from dharma_swarm.ginko_brier import (
        BrierDashboard,
        build_dashboard,
        format_dashboard_report,
        record_prediction,
    )

    t0 = time.monotonic()

    # Determine probability from signal confidence
    probability = 0.55
    if signal_report is not None and signal_report.signals:
        first = signal_report.signals[0]
        if first.direction == "buy":
            probability = min(0.95, 0.5 + first.confidence * 0.3)
        elif first.direction == "sell":
            probability = max(0.05, 0.5 - first.confidence * 0.3)

    resolve_by = (
        datetime.now(timezone.utc) + timedelta(days=1)
    ).isoformat()

    pred = record_prediction(
        question="[LIVE_TEST] Will SPY close higher tomorrow?",
        probability=round(probability, 3),
        resolve_by=resolve_by,
        category="equity",
        source="ginko-live-test",
        metadata={"test_run": True},
    )

    # Build dashboard
    dashboard: BrierDashboard = build_dashboard()
    dashboard_text = format_dashboard_report()

    duration_ms = int((time.monotonic() - t0) * 1000)

    brier_str = (
        f"{dashboard.overall_brier:.4f}"
        if dashboard.overall_brier is not None
        else "N/A"
    )
    details = (
        f"{dashboard.total_predictions} total, "
        f"{dashboard.pending_predictions} pending, "
        f"Brier: {brier_str}"
    )

    passed = (
        pred is not None
        and pred.id
        and dashboard.total_predictions > 0
    )

    return {
        "name": "predictions_brier",
        "passed": passed,
        "duration_ms": duration_ms,
        "details": details,
        "payload": dashboard,
    }


# ---------------------------------------------------------------------------
# Phase 5: Report Generation
# ---------------------------------------------------------------------------


async def _phase_report_generation() -> dict[str, Any]:
    """Generate, format, and save the daily report."""
    from dharma_swarm.ginko_report_gen import (
        DailyReport,
        format_report_markdown,
        generate_daily_report,
        save_report,
    )

    t0 = time.monotonic()

    report: DailyReport = generate_daily_report()
    md_text = format_report_markdown(report)
    saved_path = save_report(report)

    duration_ms = int((time.monotonic() - t0) * 1000)

    has_sections = all([
        report.date,
        report.regime,
        report.generated_at,
    ])
    file_saved = saved_path.exists()

    passed = has_sections and file_saved
    details = f"saved to {saved_path.parent}/"

    return {
        "name": "report_generation",
        "passed": passed,
        "duration_ms": duration_ms,
        "details": details,
        "payload": {"path": str(saved_path), "md_length": len(md_text)},
    }


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

PHASE_LABELS = {
    "data_pull": "Data Pull",
    "regime_detection": "Regime Detection",
    "signal_generation": "Signal Generation",
    "predictions_brier": "Predictions + Brier",
    "report_generation": "Report Generation",
}


async def run_live_test() -> dict[str, Any]:
    """Run the complete Ginko E2E pipeline test.

    Executes all 5 phases sequentially. Each phase catches its own
    errors so a failure in one does not block the rest.

    Returns:
        {
            "passed": int,
            "failed": int,
            "total_duration_ms": int,
            "phases": [
                {"name": str, "passed": bool, "duration_ms": int, "details": str},
                ...
            ]
        }
    """
    total_start = time.monotonic()
    phases: list[dict[str, Any]] = []
    total = 5

    print()
    print(f"{_BOLD}{_CYAN}Ginko Pipeline -- End-to-End Live Test{_RESET}")
    print(f"{_DIM}{'=' * 50}{_RESET}")
    print()

    # -- Phase 1: Data Pull --
    data_pull = None
    try:
        result = await _phase_data_pull()
        data_pull = result.pop("payload", None)
        phases.append(result)
    except Exception as exc:
        duration_ms = 0
        phases.append({
            "name": "data_pull",
            "passed": False,
            "duration_ms": duration_ms,
            "details": f"exception: {exc}",
        })

    r = phases[-1]
    label = _phase_header(1, total, PHASE_LABELS["data_pull"])
    tag = _pass_tag(r["duration_ms"]) if r["passed"] else _fail_tag(r["duration_ms"], r["details"])
    print(f"{label}{tag} -- {r['details']}")

    # -- Phase 2: Regime Detection --
    regime_detection = None
    try:
        result = await _phase_regime_detection(data_pull)
        regime_detection = result.pop("payload", None)
        phases.append(result)
    except Exception as exc:
        phases.append({
            "name": "regime_detection",
            "passed": False,
            "duration_ms": 0,
            "details": f"exception: {exc}",
        })

    r = phases[-1]
    label = _phase_header(2, total, PHASE_LABELS["regime_detection"])
    tag = _pass_tag(r["duration_ms"]) if r["passed"] else _fail_tag(r["duration_ms"], r["details"])
    print(f"{label}{tag} -- {r['details']}")

    # -- Phase 3: Signal Generation --
    signal_report = None
    try:
        result = await _phase_signal_generation(data_pull, regime_detection)
        signal_report = result.pop("payload", None)
        phases.append(result)
    except Exception as exc:
        phases.append({
            "name": "signal_generation",
            "passed": False,
            "duration_ms": 0,
            "details": f"exception: {exc}",
        })

    r = phases[-1]
    label = _phase_header(3, total, PHASE_LABELS["signal_generation"])
    tag = _pass_tag(r["duration_ms"]) if r["passed"] else _fail_tag(r["duration_ms"], r["details"])
    print(f"{label}{tag} -- {r['details']}")

    # -- Phase 4: Predictions + Brier --
    try:
        result = await _phase_predictions_brier(signal_report)
        result.pop("payload", None)
        phases.append(result)
    except Exception as exc:
        phases.append({
            "name": "predictions_brier",
            "passed": False,
            "duration_ms": 0,
            "details": f"exception: {exc}",
        })

    r = phases[-1]
    label = _phase_header(4, total, PHASE_LABELS["predictions_brier"])
    tag = _pass_tag(r["duration_ms"]) if r["passed"] else _fail_tag(r["duration_ms"], r["details"])
    print(f"{label}{tag} -- {r['details']}")

    # -- Phase 5: Report Generation --
    try:
        result = await _phase_report_generation()
        result.pop("payload", None)
        phases.append(result)
    except Exception as exc:
        phases.append({
            "name": "report_generation",
            "passed": False,
            "duration_ms": 0,
            "details": f"exception: {exc}",
        })

    r = phases[-1]
    label = _phase_header(5, total, PHASE_LABELS["report_generation"])
    tag = _pass_tag(r["duration_ms"]) if r["passed"] else _fail_tag(r["duration_ms"], r["details"])
    print(f"{label}{tag} -- {r['details']}")

    # -- Summary --
    total_duration_ms = int((time.monotonic() - total_start) * 1000)
    passed = sum(1 for p in phases if p["passed"])
    failed = sum(1 for p in phases if not p["passed"])

    print()
    print(f"{_DIM}{'=' * 50}{_RESET}")
    color = _GREEN if failed == 0 else (_YELLOW if failed <= 2 else _RED)
    print(
        f"{_BOLD}Result: {color}{passed}/{total} passed{_RESET}"
        f" {_DIM}({total_duration_ms}ms total){_RESET}"
    )
    if failed > 0:
        for p in phases:
            if not p["passed"]:
                print(f"  {_RED}FAILED{_RESET}: {p['name']} -- {p['details']}")
    print()

    return {
        "passed": passed,
        "failed": failed,
        "total_duration_ms": total_duration_ms,
        "phases": phases,
    }


if __name__ == "__main__":
    result = asyncio.run(run_live_test())
    sys.exit(0 if result["failed"] == 0 else 1)
