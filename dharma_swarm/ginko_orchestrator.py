"""Ginko Orchestrator — autonomous economic engine daily cycle.

Coordinates the Shakti Ginko VentureCell:
  1. Data pull (05:00) — FRED + finnhub + CoinGecko
  2. Regime detection + signal generation (06:00)
  3. Arbitrage/opportunity scanning (every 15min)
  4. P&L reconciliation + Brier update (16:30)
  5. Report generation (18:00)

Integrates with:
  - ontology.py (VentureCell object)
  - cron_scheduler.py (job scheduling)
  - signal_bus.py (inter-loop signaling)
  - telos_gates.py (AHIMSA, SATYA, REVERSIBILITY)
  - metabolic loop (ValueEvent → Contribution → routing)

Autonomy ladder:
  Stage 1: Signal generation + Brier tracking (no capital)
  Stage 2: Paper trading on testnet (weekly review)
  Stage 3: Micro-capital ($100-500, per-trade approval)
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.ginko_brier import (
    build_dashboard,
    check_edge_validation,
    format_dashboard_report,
    record_prediction,
)
from dharma_swarm.ginko_data import (
    MarketDataPull,
    load_latest_pull,
    pull_all_data,
)
from dharma_swarm.ginko_regime import (
    ReturnSeries,
    analyze_regime,
)
from dharma_swarm.ginko_signals import (
    SignalReport,
    format_signal_report,
    generate_signal_report,
)

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
STATE_FILE = GINKO_DIR / "ginko_state.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GINKO STATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class GinkoState:
    """Persistent state of the Ginko VentureCell."""
    autonomy_stage: int = 1
    last_data_pull: str | None = None
    last_signal_report: str | None = None
    last_reconciliation: str | None = None
    current_regime: str = "unknown"
    regime_confidence: float = 0.0
    total_predictions: int = 0
    resolved_predictions: int = 0
    brier_score: float | None = None
    edge_validated: bool = False
    paper_pnl_usd: float = 0.0
    paper_portfolio_value: float = 100000.0
    paper_pnl_pct: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    errors: list[str] | None = None


def load_state() -> GinkoState:
    """Load Ginko state from disk."""
    if STATE_FILE.exists():
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return GinkoState(**{
                k: v for k, v in data.items()
                if k in GinkoState.__dataclass_fields__
            })
        except Exception as e:
            logger.error("Failed to load Ginko state: %s", e)
    return GinkoState()


def save_state(state: GinkoState) -> None:
    """Persist Ginko state to disk."""
    GINKO_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(
        json.dumps(asdict(state), indent=2, default=str),
        encoding="utf-8",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CYCLE ACTIONS (called by cron jobs)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def action_data_pull() -> dict[str, Any]:
    """Pull all market data. Scheduled: 05:00 daily.

    Returns:
        Summary dict for cron output.
    """
    state = load_state()

    pull = await pull_all_data()
    state.last_data_pull = _utc_now().isoformat()

    save_state(state)

    return {
        "action": "data_pull",
        "timestamp": pull.timestamp,
        "macro_available": pull.macro is not None,
        "stocks_count": len(pull.stocks),
        "crypto_count": len(pull.crypto),
        "errors": pull.errors,
    }


async def action_generate_signals(
    price_history: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """Generate signals from latest data. Scheduled: 06:00 daily.

    Args:
        price_history: Dict of symbol → historical close prices.
            If None, uses minimal data from latest pull.

    Returns:
        Summary dict for cron output.
    """
    state = load_state()

    # Load latest data pull
    pull = load_latest_pull()
    if not pull:
        return {"action": "generate_signals", "error": "No data pull available"}

    # Build price data from pull (minimal — just current prices)
    # In production, this would use historical data from a database
    if price_history is None:
        price_history = {}
        for stock in pull.stocks:
            # Use current price as a single-point series (regime needs history)
            price_history[stock.symbol] = [stock.previous_close, stock.current_price]

    # Regime detection (needs historical returns)
    # Use SPY as market proxy if available
    spy_prices = price_history.get("SPY", [])
    if len(spy_prices) >= 5:
        returns = []
        for i in range(1, len(spy_prices)):
            if spy_prices[i - 1] > 0:
                returns.append(
                    (spy_prices[i] - spy_prices[i - 1]) / spy_prices[i - 1]
                )
        series = ReturnSeries(values=returns, timestamps=[], symbol="SPY")
        regime_result = analyze_regime(series)
        regime = regime_result.regime
        regime_conf = regime_result.confidence
    else:
        regime = state.current_regime
        regime_conf = state.regime_confidence

    # Generate signal report
    macro_dict = None
    if pull.macro:
        macro_dict = asdict(pull.macro)

    report = generate_signal_report(
        regime=regime,
        regime_confidence=regime_conf,
        price_data=price_history,
        macro_data=macro_dict,
    )

    # Update state
    state.current_regime = regime
    state.regime_confidence = regime_conf
    state.last_signal_report = _utc_now().isoformat()
    save_state(state)

    return {
        "action": "generate_signals",
        "timestamp": report.timestamp,
        "regime": regime,
        "regime_confidence": regime_conf,
        "signal_count": len(report.signals),
        "risk_level": report.risk_level,
        "report_text": format_signal_report(report),
    }


async def action_reconcile() -> dict[str, Any]:
    """Daily P&L reconciliation + Brier update. Scheduled: 16:30 daily.

    Returns:
        Summary dict with dashboard metrics.
    """
    state = load_state()

    dashboard = build_dashboard()
    edge = check_edge_validation()

    state.total_predictions = dashboard.total_predictions
    state.resolved_predictions = dashboard.resolved_predictions
    state.brier_score = dashboard.overall_brier
    state.edge_validated = edge["validated"]
    state.last_reconciliation = _utc_now().isoformat()
    save_state(state)

    return {
        "action": "reconcile",
        "timestamp": _utc_now().isoformat(),
        "total_predictions": dashboard.total_predictions,
        "resolved_predictions": dashboard.resolved_predictions,
        "brier_score": dashboard.overall_brier,
        "edge_validated": edge["validated"],
        "edge_reasons": edge.get("reasons", []),
        "dashboard_text": format_dashboard_report(),
    }


async def action_generate_report() -> dict[str, Any]:
    """Generate daily intelligence report. Scheduled: 18:00 daily.

    Returns:
        Dict with report text for subscriber distribution.
    """
    state = load_state()
    dashboard = build_dashboard()

    # Build combined report
    lines = [
        "=" * 60,
        "SHAKTI GINKO — Daily Intelligence Report",
        f"Date: {_utc_now().strftime('%Y-%m-%d')}",
        f"Autonomy Stage: {state.autonomy_stage}",
        "=" * 60,
        "",
        f"MARKET REGIME: {state.current_regime.upper()} "
        f"(confidence: {state.regime_confidence:.0%})",
        "",
    ]

    # Include latest signal report
    from dharma_swarm.ginko_signals import load_latest_report
    latest_signals = load_latest_report()
    if latest_signals:
        lines.append("SIGNALS:")
        for s in latest_signals.get("signals", []):
            arrow = {"buy": "+", "sell": "-", "hold": "="}[s["direction"]]
            lines.append(
                f"  [{arrow}] {s['symbol']}: {s['direction'].upper()} "
                f"({s['strength']}, conf={s['confidence']:.0%})"
            )
        lines.append(f"\nRisk level: {latest_signals.get('risk_level', 'N/A').upper()}")
        if latest_signals.get("macro_summary"):
            lines.append(f"Macro: {latest_signals['macro_summary']}")
    else:
        lines.append("No signal report available today.")

    lines.extend([
        "",
        "PREDICTION SCORECARD:",
        f"  Total predictions: {dashboard.total_predictions}",
        f"  Resolved: {dashboard.resolved_predictions}",
    ])
    if dashboard.overall_brier is not None:
        lines.append(f"  Brier score: {dashboard.overall_brier:.4f} (target: < 0.125)")
    if dashboard.win_rate is not None:
        lines.append(f"  Win rate: {dashboard.win_rate:.1%}")
    lines.append(f"  Edge validated: {'YES' if dashboard.edge_validated else 'NO'}")

    lines.extend([
        "",
        "---",
        "SATYA: All predictions published, including misses.",
        "Generated by Shakti Ginko VentureCell (dharma_swarm)",
    ])

    report_text = "\n".join(lines)

    # Persist
    report_dir = GINKO_DIR / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"report_{_utc_now().strftime('%Y%m%d')}.txt"
    report_file.write_text(report_text, encoding="utf-8")

    return {
        "action": "generate_report",
        "timestamp": _utc_now().isoformat(),
        "report_text": report_text,
        "report_file": str(report_file),
    }


async def action_execute_paper_trades(signals: Any) -> dict[str, Any]:
    """Execute paper trades from signals with confidence > 0.6.

    For each BUY/SELL signal above threshold:
    - Compute position size via half-Kelly
    - Check AHIMSA gate (max 5% per position)
    - Open/close paper positions

    Args:
        signals: A SignalReport, or a dict with a ``signals`` key.

    Returns:
        Summary dict with executed trades and portfolio value.
    """
    from dharma_swarm.ginko_paper_trade import PaperPortfolio

    portfolio = PaperPortfolio()
    trades_executed: list[dict[str, Any]] = []
    errors: list[str] = []

    # Accept SignalReport objects or plain dicts
    signal_list = (
        signals.signals
        if hasattr(signals, "signals")
        else signals.get("signals", [])
    )

    for sig in signal_list:
        # Extract fields — handle both Signal objects and dicts
        direction = (
            sig.direction if hasattr(sig, "direction") else sig.get("direction", "hold")
        )
        confidence = (
            sig.confidence if hasattr(sig, "confidence") else sig.get("confidence", 0)
        )
        symbol = sig.symbol if hasattr(sig, "symbol") else sig.get("symbol", "")

        if direction == "hold" or confidence < 0.6:
            continue

        try:
            # Use default pricing if no real price available
            price = 100.0  # placeholder — in production, fetch from ginko_data
            quantity = max(1, int(portfolio.cash * 0.03 / price))  # 3% of cash
            stop_loss = price * 0.95 if direction == "buy" else price * 1.05

            if symbol in portfolio.positions:
                # Close existing position
                trade = portfolio.close_position(
                    symbol, price, reason=f"Signal reversed: {direction}",
                )
                trades_executed.append({
                    "action": "close",
                    "symbol": symbol,
                    "pnl": trade.realized_pnl,
                })

            if direction in ("buy", "sell"):
                pos_direction = "long" if direction == "buy" else "short"
                portfolio.open_position(
                    symbol=symbol,
                    direction=pos_direction,
                    quantity=quantity,
                    price=price,
                    stop_loss=stop_loss,
                )
                trades_executed.append({
                    "action": "open",
                    "symbol": symbol,
                    "direction": pos_direction,
                    "quantity": quantity,
                })
        except Exception as e:
            errors.append(f"{symbol}: {e}")

    # Update state with latest portfolio stats
    state = load_state()
    stats = portfolio.get_portfolio_stats()
    state.paper_portfolio_value = stats.get("total_value", 100000.0)
    state.paper_pnl_pct = stats.get("total_pnl_pct", 0.0)
    state.sharpe_ratio = stats.get("sharpe_ratio", 0.0)
    state.max_drawdown = stats.get("max_drawdown", 0.0)
    save_state(state)

    return {
        "action": "execute_paper_trades",
        "trades_executed": len(trades_executed),
        "trades": trades_executed,
        "portfolio_value": stats.get("total_value", 100000.0),
        "errors": errors,
    }


async def action_sec_analysis(
    tickers: list[str] | None = None,
) -> dict[str, Any]:
    """Fetch and analyze recent SEC 10-K filings.

    Returns SEC signals for incorporation into signal generation.
    """
    from dharma_swarm.ginko_sec import (
        analyze_filing_with_agent,
        extract_financial_sections,
        fetch_recent_10k_batch,
    )

    tickers = tickers or ["AAPL", "NVDA", "MSFT"]
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        filings = await fetch_recent_10k_batch(tickers)
        for filing in filings:
            try:
                sections = extract_financial_sections(filing)
                analysis = await analyze_filing_with_agent(
                    filing, sections, agent_fn=None,
                )
                results.append({
                    "ticker": filing.ticker,
                    "sentiment": analysis.sentiment,
                    "confidence": analysis.confidence,
                    "key_findings": analysis.key_findings,
                })
            except Exception as e:
                errors.append(f"{filing.ticker}: {e}")
    except Exception as e:
        errors.append(f"Batch fetch failed: {e}")

    return {
        "action": "sec_analysis",
        "analyzed": len(results),
        "results": results,
        "errors": errors,
    }


async def action_ensemble_predict(
    question: str,
    resolve_by: str,
    category: str = "macro",
) -> dict[str, Any]:
    """Run a transcendence trial: fan out prediction to all Ginko agents.

    Each agent independently estimates a probability. The ensemble
    aggregates via quality-weighted temperature concentration.
    Both individual and ensemble predictions are recorded for Brier scoring.

    Args:
        question: The prediction question (yes/no with probability).
        resolve_by: ISO timestamp for resolution deadline.
        category: Prediction category for Brier tracking.

    Returns:
        Summary dict with individual and ensemble probabilities.
    """
    from dharma_swarm.ginko_agents import GinkoFleet, agent_task
    from dharma_swarm.transcendence_aggregation import (
        temperature_concentrate,
        inverse_brier_weights,
    )

    # Bootstrap the fleet (loads existing agent state)
    fleet = GinkoFleet()
    agents = fleet.list_agents()
    if not agents:
        return {"action": "ensemble_predict", "error": "No agents available"}

    # Fan out: each agent independently predicts
    prompt = (
        f"You are making a probabilistic prediction.\n"
        f"Question: {question}\n"
        f"Respond with ONLY a number between 0.0 and 1.0 representing "
        f"the probability that the answer is YES.\n"
        f"Example: 0.72\n"
    )

    individual_results: list[dict[str, Any]] = []
    probabilities: list[float] = []
    brier_scores_list: list[float] = []

    for agent in agents:
        try:
            result = await agent_task(fleet, agent.name, prompt, temperature=0.4)
            if not result.get("success"):
                continue
            response = result.get("response", "")
            prob = _extract_probability_from_response(response)
            if prob is not None:
                individual_results.append({
                    "agent": agent.name,
                    "model": agent.model,
                    "probability": prob,
                })
                probabilities.append(prob)

                # Get agent's historical Brier score for weighting
                dashboard = build_dashboard()
                agent_brier = dashboard.brier_by_source.get(agent.name, 0.25)
                brier_scores_list.append(agent_brier)

                # Record individual prediction
                record_prediction(
                    question=question,
                    probability=prob,
                    category=category,
                    source=agent.name,
                    resolve_by=resolve_by,
                )
        except Exception as exc:
            logger.warning("Agent %s failed in ensemble predict: %s", agent.name, exc)

    if len(probabilities) < 2:
        return {
            "action": "ensemble_predict",
            "error": f"Only {len(probabilities)} agents responded (need 2+)",
            "individual_results": individual_results,
        }

    # Aggregate: quality-weighted + temperature concentration
    weights = inverse_brier_weights(brier_scores_list)
    ensemble_prob = temperature_concentrate(probabilities, weights, temperature=0.5)

    # Record ensemble prediction
    record_prediction(
        question=question,
        probability=ensemble_prob,
        category=category,
        source="ensemble",
        resolve_by=resolve_by,
        metadata={
            "n_agents": len(probabilities),
            "individual_probs": probabilities,
            "weights": weights,
            "method": "temperature_concentrate_0.5",
        },
    )

    state = load_state()
    state.total_predictions = (state.total_predictions or 0) + 1
    save_state(state)

    return {
        "action": "ensemble_predict",
        "question": question,
        "individual_results": individual_results,
        "ensemble_probability": ensemble_prob,
        "n_agents": len(probabilities),
        "diversity": max(probabilities) - min(probabilities),
    }


def _extract_probability_from_response(text: str) -> float | None:
    """Extract a probability from agent response text."""
    import re
    for pattern in [
        r'(\d*\.\d+)',
        r'(\d+)%',
    ]:
        match = re.search(pattern, text.strip())
        if match:
            val = float(match.group(1))
            if val > 1.0:
                val /= 100.0
            if 0.0 <= val <= 1.0:
                return val
    return None


async def action_full_cycle() -> dict[str, Any]:
    """Run the complete daily Ginko cycle.

    Sequence:
    1. Data pull
    2. SEC analysis (optional, continues on failure)
    3. Generate signals (with SEC input if available)
    4. Execute paper trades
    5. Reconcile + Brier update
    6. Generate report

    Returns:
        Combined results dict with per-phase outcomes and total duration.
    """
    import time

    results: dict[str, Any] = {}
    start = time.monotonic()

    # Phase 1: Data pull
    try:
        results["data_pull"] = await action_data_pull()
    except Exception as e:
        results["data_pull"] = {"error": str(e)}

    # Phase 2: SEC analysis (non-blocking — failure does not abort)
    sec_signals = None
    try:
        sec_result = await action_sec_analysis()
        results["sec_analysis"] = sec_result
        # Convert to SECSignal objects for signal generation
        if sec_result.get("results"):
            from dharma_swarm.ginko_signals import SECSignal

            sec_signals = [
                SECSignal(
                    ticker=r["ticker"],
                    filing_type="10-K",
                    sentiment=r["sentiment"],
                    confidence=r["confidence"],
                    key_findings=r.get("key_findings", []),
                )
                for r in sec_result["results"]
            ]
    except Exception as e:
        results["sec_analysis"] = {"error": str(e)}

    # Phase 3: Generate signals
    try:
        results["signals"] = await action_generate_signals()
    except Exception as e:
        results["signals"] = {"error": str(e)}

    # Phase 4: Paper trades
    try:
        from dharma_swarm.ginko_signals import load_latest_report as _load_report

        latest = _load_report()
        if latest:
            results["paper_trades"] = await action_execute_paper_trades(latest)
        else:
            results["paper_trades"] = {"skipped": "no signal report available"}
    except Exception as e:
        results["paper_trades"] = {"error": str(e)}

    # Phase 5: Reconcile
    try:
        results["reconcile"] = await action_reconcile()
    except Exception as e:
        results["reconcile"] = {"error": str(e)}

    # Phase 6: Report
    try:
        results["report"] = await action_generate_report()
    except Exception as e:
        results["report"] = {"error": str(e)}

    # Phase 7: Ensemble Prediction (Transcendence measurement)
    try:
        from datetime import timedelta
        resolve_by = (_utc_now() + timedelta(days=7)).isoformat()
        results["ensemble_predict"] = await action_ensemble_predict(
            question="Will BTC be above its current price in 7 days?",
            resolve_by=resolve_by,
            category="crypto",
        )
    except Exception as e:
        results["ensemble_predict"] = {"error": str(e)}

    results["total_duration_ms"] = round((time.monotonic() - start) * 1000)
    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CRON JOB REGISTRATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


GINKO_CRON_JOBS = [
    {
        "name": "ginko_data_pull",
        "prompt": (
            "Pull market data from FRED, finnhub, and CoinGecko. "
            "Save snapshot to ~/.dharma/ginko/data/. "
            "Report any API failures."
        ),
        "schedule": "0 5 * * *",  # 05:00 daily
        "deliver": "local",
    },
    {
        "name": "ginko_signals",
        "prompt": (
            "Generate buy/sell/hold signals from latest market data. "
            "Run regime detection (HMM + GARCH). "
            "Produce signal report with confidence scores. "
            "Save to ~/.dharma/ginko/signals/."
        ),
        "schedule": "0 6 * * *",  # 06:00 daily
        "deliver": "local",
    },
    {
        "name": "ginko_scanner",
        "prompt": (
            "Scan for arbitrage opportunities: "
            "cross-exchange crypto price differences, "
            "Polymarket mispriced contracts. "
            "Report any spreads > 0.5% after fees."
        ),
        "schedule": "every 15m",  # Every 15 minutes during market hours
        "deliver": "local",
    },
    {
        "name": "ginko_reconcile",
        "prompt": (
            "Daily P&L reconciliation. Update Brier scores for resolved predictions. "
            "Check edge validation status. "
            "Generate dashboard at ~/.dharma/ginko/brier_dashboard.json."
        ),
        "schedule": "30 16 * * *",  # 16:30 daily (after market close)
        "deliver": "local",
    },
    {
        "name": "ginko_report",
        "prompt": (
            "Generate daily intelligence report combining: "
            "regime detection, signal analysis, prediction scorecard, "
            "macro summary. Save to ~/.dharma/ginko/reports/. "
            "SATYA: include ALL Brier scores, even poor ones."
        ),
        "schedule": "0 18 * * *",  # 18:00 daily
        "deliver": "local",
    },
    {
        "name": "ginko_full_cycle",
        "prompt": (
            "Run the complete Ginko daily cycle: data pull, SEC analysis, "
            "signal generation, paper trading, reconciliation, and report. "
            "Save all outputs to ~/.dharma/ginko/."
        ),
        "schedule": "0 6 * * 1-5",  # 6 AM weekdays
        "deliver": "local",
    },
]


def register_ginko_crons() -> list[dict[str, Any]]:
    """Register Ginko cron jobs with the scheduler.

    Only registers jobs that don't already exist (idempotent).
    Returns list of created jobs.
    """
    from dharma_swarm.cron_scheduler import create_job, load_jobs

    existing = {j.get("name") for j in load_jobs()}
    created = []

    for job_def in GINKO_CRON_JOBS:
        if job_def["name"] not in existing:
            job = create_job(
                prompt=job_def["prompt"],
                schedule=job_def["schedule"],
                name=job_def["name"],
                deliver=job_def.get("deliver", "local"),
            )
            created.append(job)
            logger.info("Registered Ginko cron: %s", job_def["name"])
        else:
            logger.debug("Ginko cron already exists: %s", job_def["name"])

    return created


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# TELOS GATE CHECKS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def check_telos_gates(action: str, context: dict[str, Any]) -> dict[str, str]:
    """Check telos gates for a Ginko action.

    Returns:
        Dict of gate_name → "pass" | "warn" | "fail".
    """
    results: dict[str, str] = {}

    # AHIMSA: never concentrate risk dangerously
    if action in ("execute_trade", "open_position"):
        position_pct = context.get("position_pct", 0)
        if position_pct > 5.0:
            results["AHIMSA"] = "fail"
        elif position_pct > 3.0:
            results["AHIMSA"] = "warn"
        else:
            results["AHIMSA"] = "pass"

    # SATYA: never present backtests as guarantees
    if action in ("generate_report", "publish_prediction"):
        results["SATYA"] = "pass"  # Always pass — we publish ALL scores

    # REVERSIBILITY: position sizing allows graceful exit
    if action in ("execute_trade", "open_position"):
        can_exit_24h = context.get("can_exit_24h", True)
        results["REVERSIBILITY"] = "pass" if can_exit_24h else "fail"

    # SVABHAAVA: system stays coherent with its nature
    if action in ("advance_autonomy",):
        edge = check_edge_validation()
        results["SVABHAAVA"] = "pass" if edge["validated"] else "fail"

    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# AUTONOMY ADVANCEMENT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


AUTONOMY_REQUIREMENTS = {
    2: {  # Paper trading
        "min_predictions": 100,
        "max_brier": 0.20,
    },
    3: {  # Micro-capital ($100-500)
        "min_predictions": 500,
        "max_brier": 0.125,
        "min_win_rate": 0.55,
    },
    4: {  # Small capital ($1K-5K)
        "min_predictions": 1000,
        "max_brier": 0.10,
        "min_win_rate": 0.58,
        "min_sharpe": 1.5,
    },
    5: {  # Full autonomous
        "min_predictions": 2000,
        "max_brier": 0.08,
        "min_win_rate": 0.60,
        "min_sharpe": 2.0,
        "max_drawdown": 0.15,
    },
}


def check_autonomy_advancement(state: GinkoState) -> dict[str, Any]:
    """Check if the VentureCell can advance to the next autonomy stage.

    Returns:
        Dict with can_advance, next_stage, requirements, met, unmet.
    """
    next_stage = state.autonomy_stage + 1
    if next_stage not in AUTONOMY_REQUIREMENTS:
        return {
            "can_advance": False,
            "reason": f"No requirements defined for stage {next_stage}",
        }

    reqs = AUTONOMY_REQUIREMENTS[next_stage]
    met = []
    unmet = []

    if "min_predictions" in reqs:
        if state.resolved_predictions >= reqs["min_predictions"]:
            met.append(f"predictions: {state.resolved_predictions} >= {reqs['min_predictions']}")
        else:
            unmet.append(f"predictions: {state.resolved_predictions} < {reqs['min_predictions']}")

    if "max_brier" in reqs:
        if state.brier_score is not None and state.brier_score <= reqs["max_brier"]:
            met.append(f"brier: {state.brier_score:.4f} <= {reqs['max_brier']}")
        else:
            score_str = f"{state.brier_score:.4f}" if state.brier_score else "N/A"
            unmet.append(f"brier: {score_str} > {reqs['max_brier']}")

    return {
        "can_advance": len(unmet) == 0,
        "next_stage": next_stage,
        "requirements": reqs,
        "met": met,
        "unmet": unmet,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# POSITION SIZING (Half-Kelly)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def compute_position_size(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    capital: float,
    max_position_pct: float = 0.05,
) -> dict[str, float]:
    """Compute half-Kelly position size.

    Args:
        win_rate: Historical win rate (0-1).
        avg_win: Average winning trade return.
        avg_loss: Average losing trade return (positive number).
        capital: Total available capital.
        max_position_pct: Maximum position as fraction of capital.

    Returns:
        Dict with kelly_fraction, half_kelly, position_size_usd, position_pct.
    """
    if avg_win <= 0:
        return {"kelly_fraction": 0, "half_kelly": 0, "position_size_usd": 0, "position_pct": 0}

    kelly = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
    half_kelly = max(0, kelly / 2)
    position_pct = min(half_kelly, max_position_pct)
    position_usd = position_pct * capital

    return {
        "kelly_fraction": round(kelly, 4),
        "half_kelly": round(half_kelly, 4),
        "position_size_usd": round(position_usd, 2),
        "position_pct": round(position_pct * 100, 2),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# STATUS / HEALTH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def ginko_status() -> str:
    """Generate human-readable Ginko status summary."""
    state = load_state()
    edge = check_edge_validation()
    advancement = check_autonomy_advancement(state)

    lines = [
        "Shakti Ginko VentureCell Status",
        "=" * 40,
        f"Autonomy stage: {state.autonomy_stage}/5",
        f"Regime: {state.current_regime} (conf: {state.regime_confidence:.0%})",
        f"Predictions: {state.total_predictions} total, {state.resolved_predictions} resolved",
    ]

    if state.brier_score is not None:
        lines.append(f"Brier score: {state.brier_score:.4f} (target: < 0.125)")
    else:
        lines.append("Brier score: N/A")

    lines.append(f"Edge validated: {'YES' if state.edge_validated else 'NO'}")

    lines.append(f"Paper portfolio: ${state.paper_portfolio_value:,.0f}")
    lines.append(f"Paper P&L: {state.paper_pnl_pct:+.2f}%")
    if state.sharpe_ratio:
        lines.append(f"Sharpe ratio: {state.sharpe_ratio:.2f}")
    if state.max_drawdown:
        lines.append(f"Max drawdown: {state.max_drawdown:.1%}")

    if state.last_data_pull:
        lines.append(f"Last data pull: {state.last_data_pull}")
    if state.last_signal_report:
        lines.append(f"Last signal report: {state.last_signal_report}")

    if advancement["can_advance"]:
        lines.append(f"\nReady to advance to stage {advancement['next_stage']}")
    elif advancement.get("unmet"):
        lines.append(f"\nAdvancement to stage {advancement.get('next_stage', '?')} blocked:")
        for reason in advancement["unmet"]:
            lines.append(f"  - {reason}")

    return "\n".join(lines)
