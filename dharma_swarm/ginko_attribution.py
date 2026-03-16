"""Ginko Performance Attribution -- P&L decomposition by agent, signal type, regime, and symbol.

Answers the question every fund must answer: WHERE did the alpha come from?

Decomposes realized P&L along four axes:
  1. Agent -- which fleet agent originated the trade signal?
  2. Signal type -- technical, SEC, sentiment, multi-factor, or unknown?
  3. Regime -- was the market bull, bear, or sideways at entry?
  4. Symbol -- per-ticker P&L for concentration analysis.

Data source: ~/.dharma/ginko/trades.jsonl (appended by PaperPortfolio.close_position)

Usage:
    from dharma_swarm.ginko_attribution import load_trades, compute_attribution, format_attribution_report
    trades = load_trades()
    report = compute_attribution(trades)
    print(format_attribution_report(report))
"""

from __future__ import annotations

import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
DEFAULT_TRADES_PATH = GINKO_DIR / "trades.jsonl"

# Known agent names from GinkoFleet (ginko_agents.py FLEET_SPEC).
# Used to extract agent identity from signal_source strings.
_KNOWN_AGENTS = frozenset({
    "kimi", "deepseek", "nemotron", "glm", "sentinel", "scout",
})

# Signal type classification keywords.
# Order matters -- first match wins.
_SIGNAL_TYPE_PATTERNS: list[tuple[str, list[str]]] = [
    ("sec", ["sec", "filing", "10-k", "10-q", "edgar"]),
    ("sentiment", ["sentiment", "news", "social"]),
    ("technical", ["technical", "rsi", "sma", "momentum", "bollinger", "macd", "regime"]),
    ("multi", ["multi", "consensus", "fleet", "combined", "composite"]),
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Attribution Report
# ---------------------------------------------------------------------------


@dataclass
class AttributionReport:
    """Complete P&L attribution breakdown.

    All monetary values are in the portfolio's base currency (USD for
    Dharmic Quant paper trading).
    """

    pnl_by_agent: dict[str, float] = field(default_factory=dict)
    pnl_by_signal_type: dict[str, float] = field(default_factory=dict)
    pnl_by_regime: dict[str, float] = field(default_factory=dict)
    pnl_by_symbol: dict[str, float] = field(default_factory=dict)
    best_agent: str = ""
    worst_agent: str = ""
    best_signal_type: str = ""
    total_pnl: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    computed_at: str = ""


# ---------------------------------------------------------------------------
# Trade Loading
# ---------------------------------------------------------------------------


def load_trades(trades_path: Path | None = None) -> list[dict[str, Any]]:
    """Load closed trades from the JSONL trade log.

    Args:
        trades_path: Override path. Defaults to ~/.dharma/ginko/trades.jsonl.

    Returns:
        List of trade dicts. Empty list if file does not exist or is empty.
        Malformed lines are skipped with a warning.
    """
    path = trades_path or DEFAULT_TRADES_PATH

    if not path.exists():
        logger.info("No trades file at %s -- returning empty list.", path)
        return []

    trades: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    trades.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    logger.warning(
                        "Skipping malformed JSON at %s:%d: %s", path, lineno, exc
                    )
    except Exception as exc:
        logger.error("Failed to read trades from %s: %s", path, exc)

    return trades


# ---------------------------------------------------------------------------
# Attribution Helpers
# ---------------------------------------------------------------------------


def _extract_agent(trade: dict[str, Any]) -> str:
    """Extract the originating agent name from a trade dict.

    Checks signal_source first, then metadata fields. Falls back to
    "unknown" if no agent can be identified.
    """
    signal_source = str(trade.get("signal_source", "")).lower()

    # Direct match: signal_source IS the agent name.
    if signal_source in _KNOWN_AGENTS:
        return signal_source

    # Substring match: signal_source contains an agent name.
    for agent in _KNOWN_AGENTS:
        if agent in signal_source:
            return agent

    # Check metadata / other fields.
    for key in ("agent", "agent_name", "source_agent"):
        val = str(trade.get(key, "")).lower()
        if val in _KNOWN_AGENTS:
            return val
        for agent in _KNOWN_AGENTS:
            if agent in val:
                return agent

    return "unknown"


def _classify_signal_type(trade: dict[str, Any]) -> str:
    """Classify the signal type of a trade.

    Uses signal_source string and any metadata to bucket into:
    technical, sec, sentiment, multi, or unknown.
    """
    signal_source = str(trade.get("signal_source", "")).lower()

    # Check explicit signal_type field first.
    explicit = str(trade.get("signal_type", "")).lower().strip()
    if explicit in ("technical", "sec", "sentiment", "multi"):
        return explicit

    # Pattern matching against signal_source.
    for signal_type, keywords in _SIGNAL_TYPE_PATTERNS:
        for kw in keywords:
            if kw in signal_source:
                return signal_type

    # If signal_source is just an agent name, infer from agent role.
    agent = _extract_agent(trade)
    _agent_to_signal: dict[str, str] = {
        "kimi": "technical",      # macro oracle -> macro/technical
        "deepseek": "technical",  # quant architect -> quantitative/technical
        "glm": "technical",       # pipeline smith -> data-driven
        "nemotron": "multi",      # intelligence synthesizer -> multi-source
        "sentinel": "technical",  # risk warden -> risk metrics
        "scout": "sentiment",     # alpha hunter -> opportunity/sentiment
    }
    if agent in _agent_to_signal:
        return _agent_to_signal[agent]

    return "unknown"


def _extract_regime(trade: dict[str, Any]) -> str:
    """Extract market regime at trade entry.

    Checks regime field, signal metadata, and signal_source string.
    Falls back to "unknown".
    """
    # Direct regime field.
    regime = str(trade.get("regime", "")).lower().strip()
    if regime in ("bull", "bear", "sideways"):
        return regime

    # Check inside metadata dict.
    metadata = trade.get("metadata", {})
    if isinstance(metadata, dict):
        regime = str(metadata.get("regime", "")).lower().strip()
        if regime in ("bull", "bear", "sideways"):
            return regime

    # Infer from signal_source.
    signal_source = str(trade.get("signal_source", "")).lower()
    for r in ("bull", "bear", "sideways"):
        if r in signal_source:
            return r

    return "unknown"


# ---------------------------------------------------------------------------
# Core Attribution Engine
# ---------------------------------------------------------------------------


def compute_attribution(trades: list[dict[str, Any]]) -> AttributionReport:
    """Compute full P&L attribution from a list of trade dicts.

    Groups realized_pnl by agent, signal type, regime, and symbol.
    Identifies best/worst performers.

    Args:
        trades: List of trade dicts (as loaded from trades.jsonl).

    Returns:
        Fully populated AttributionReport.
    """
    report = AttributionReport(
        computed_at=_utc_now().isoformat(),
    )

    if not trades:
        return report

    pnl_agent: dict[str, float] = defaultdict(float)
    pnl_signal: dict[str, float] = defaultdict(float)
    pnl_regime: dict[str, float] = defaultdict(float)
    pnl_symbol: dict[str, float] = defaultdict(float)

    total_pnl = 0.0
    wins: list[float] = []
    losses: list[float] = []

    for trade in trades:
        pnl = float(trade.get("realized_pnl", 0.0))
        symbol = str(trade.get("symbol", "UNKNOWN"))
        agent = _extract_agent(trade)
        signal_type = _classify_signal_type(trade)
        regime = _extract_regime(trade)

        pnl_agent[agent] += pnl
        pnl_signal[signal_type] += pnl
        pnl_regime[regime] += pnl
        pnl_symbol[symbol] += pnl
        total_pnl += pnl

        if pnl > 0:
            wins.append(pnl)
        elif pnl < 0:
            losses.append(pnl)

    # Populate report.
    report.pnl_by_agent = dict(pnl_agent)
    report.pnl_by_signal_type = dict(pnl_signal)
    report.pnl_by_regime = dict(pnl_regime)
    report.pnl_by_symbol = dict(pnl_symbol)
    report.total_pnl = round(total_pnl, 2)
    report.trade_count = len(trades)
    report.win_count = len(wins)
    report.loss_count = len(losses)
    report.win_rate = len(wins) / len(trades) if trades else 0.0
    report.avg_win = sum(wins) / len(wins) if wins else 0.0
    report.avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0

    # Best / worst agent.
    if pnl_agent:
        report.best_agent = max(pnl_agent, key=pnl_agent.get)  # type: ignore[arg-type]
        report.worst_agent = min(pnl_agent, key=pnl_agent.get)  # type: ignore[arg-type]

    # Best signal type.
    if pnl_signal:
        report.best_signal_type = max(pnl_signal, key=pnl_signal.get)  # type: ignore[arg-type]

    return report


# ---------------------------------------------------------------------------
# Report Formatting
# ---------------------------------------------------------------------------


def _format_pnl(value: float) -> str:
    """Format a P&L value with sign and dollar formatting."""
    if value == 0.0 or value == -0.0:
        return "$0.00"
    if value > 0:
        return f"+${value:,.2f}"
    return f"-${abs(value):,.2f}"


def _pnl_bar(value: float, max_abs: float, width: int = 20) -> str:
    """Render a simple text bar chart segment for a P&L value."""
    if max_abs == 0:
        return ""
    ratio = abs(value) / max_abs
    filled = int(ratio * width)
    char = "+" if value >= 0 else "-"
    return char * max(1, filled) if value != 0.0 else ""


def format_attribution_report(report: AttributionReport) -> str:
    """Render an AttributionReport as a human-readable text report.

    Includes sections for P&L by Agent, Signal Type, Regime, and Symbol
    with sorted tables and summary statistics.
    """
    lines: list[str] = []
    sep = "=" * 60

    lines.append(sep)
    lines.append("  DHARMIC QUANT -- PERFORMANCE ATTRIBUTION REPORT")
    lines.append(sep)
    lines.append("")

    # Summary
    lines.append("SUMMARY")
    lines.append("-" * 40)
    lines.append(f"  Total P&L:      {_format_pnl(report.total_pnl)}")
    lines.append(f"  Trade Count:    {report.trade_count}")
    lines.append(f"  Win / Loss:     {report.win_count} / {report.loss_count}")
    lines.append(f"  Win Rate:       {report.win_rate:.1%}")
    lines.append(f"  Avg Win:        {_format_pnl(report.avg_win)}")
    lines.append(f"  Avg Loss:       {_format_pnl(-report.avg_loss)}")
    lines.append(f"  Best Agent:     {report.best_agent or 'N/A'}")
    lines.append(f"  Worst Agent:    {report.worst_agent or 'N/A'}")
    lines.append(f"  Best Signal:    {report.best_signal_type or 'N/A'}")
    if report.computed_at:
        lines.append(f"  Computed At:    {report.computed_at}")
    lines.append("")

    # P&L by Agent
    lines.append("P&L BY AGENT")
    lines.append("-" * 40)
    if report.pnl_by_agent:
        sorted_agents = sorted(
            report.pnl_by_agent.items(), key=lambda x: x[1], reverse=True
        )
        max_abs = max(abs(v) for v in report.pnl_by_agent.values()) if report.pnl_by_agent else 1.0
        for agent, pnl in sorted_agents:
            bar = _pnl_bar(pnl, max_abs)
            lines.append(f"  {agent:<14} {_format_pnl(pnl):>14}  {bar}")
    else:
        lines.append("  (no agent data)")
    lines.append("")

    # P&L by Signal Type
    lines.append("P&L BY SIGNAL TYPE")
    lines.append("-" * 40)
    if report.pnl_by_signal_type:
        sorted_signals = sorted(
            report.pnl_by_signal_type.items(), key=lambda x: x[1], reverse=True
        )
        max_abs = max(abs(v) for v in report.pnl_by_signal_type.values()) if report.pnl_by_signal_type else 1.0
        for sig_type, pnl in sorted_signals:
            bar = _pnl_bar(pnl, max_abs)
            lines.append(f"  {sig_type:<14} {_format_pnl(pnl):>14}  {bar}")
    else:
        lines.append("  (no signal type data)")
    lines.append("")

    # P&L by Regime
    lines.append("P&L BY REGIME")
    lines.append("-" * 40)
    if report.pnl_by_regime:
        sorted_regimes = sorted(
            report.pnl_by_regime.items(), key=lambda x: x[1], reverse=True
        )
        max_abs = max(abs(v) for v in report.pnl_by_regime.values()) if report.pnl_by_regime else 1.0
        for regime, pnl in sorted_regimes:
            bar = _pnl_bar(pnl, max_abs)
            lines.append(f"  {regime:<14} {_format_pnl(pnl):>14}  {bar}")
    else:
        lines.append("  (no regime data)")
    lines.append("")

    # P&L by Symbol (top 5 winners + top 5 losers)
    lines.append("P&L BY SYMBOL")
    lines.append("-" * 40)
    if report.pnl_by_symbol:
        sorted_symbols = sorted(
            report.pnl_by_symbol.items(), key=lambda x: x[1], reverse=True
        )
        max_abs = max(abs(v) for v in report.pnl_by_symbol.values()) if report.pnl_by_symbol else 1.0

        # Top 5 winners
        winners = [(s, p) for s, p in sorted_symbols if p > 0][:5]
        losers = [(s, p) for s, p in sorted_symbols if p < 0][-5:]

        if winners:
            lines.append("  TOP WINNERS:")
            for sym, pnl in winners:
                bar = _pnl_bar(pnl, max_abs)
                lines.append(f"    {sym:<10} {_format_pnl(pnl):>14}  {bar}")

        if losers:
            lines.append("  TOP LOSERS:")
            for sym, pnl in losers:
                bar = _pnl_bar(pnl, max_abs)
                lines.append(f"    {sym:<10} {_format_pnl(pnl):>14}  {bar}")

        # Flat (zero P&L) symbols
        flat = [(s, p) for s, p in sorted_symbols if p == 0]
        if flat:
            lines.append(f"  FLAT: {', '.join(s for s, _ in flat)}")
    else:
        lines.append("  (no symbol data)")
    lines.append("")

    lines.append(sep)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# API Data Export
# ---------------------------------------------------------------------------


def get_attribution_api_data(report: AttributionReport) -> dict[str, Any]:
    """Convert an AttributionReport to a JSON-serializable dict.

    Suitable for returning from API endpoints, dashboard consumption,
    or serialization to disk.

    Returns:
        Dict with all report fields plus sorted breakdowns.
    """
    # Sort breakdowns for consistent API output.
    sorted_agents = sorted(
        report.pnl_by_agent.items(), key=lambda x: x[1], reverse=True
    )
    sorted_signals = sorted(
        report.pnl_by_signal_type.items(), key=lambda x: x[1], reverse=True
    )
    sorted_regimes = sorted(
        report.pnl_by_regime.items(), key=lambda x: x[1], reverse=True
    )
    sorted_symbols = sorted(
        report.pnl_by_symbol.items(), key=lambda x: x[1], reverse=True
    )

    return {
        "summary": {
            "total_pnl": round(report.total_pnl, 2),
            "trade_count": report.trade_count,
            "win_count": report.win_count,
            "loss_count": report.loss_count,
            "win_rate": round(report.win_rate, 4),
            "avg_win": round(report.avg_win, 2),
            "avg_loss": round(report.avg_loss, 2),
            "best_agent": report.best_agent,
            "worst_agent": report.worst_agent,
            "best_signal_type": report.best_signal_type,
            "computed_at": report.computed_at,
        },
        "pnl_by_agent": [
            {"agent": agent, "pnl": round(pnl, 2)}
            for agent, pnl in sorted_agents
        ],
        "pnl_by_signal_type": [
            {"signal_type": sig, "pnl": round(pnl, 2)}
            for sig, pnl in sorted_signals
        ],
        "pnl_by_regime": [
            {"regime": regime, "pnl": round(pnl, 2)}
            for regime, pnl in sorted_regimes
        ],
        "pnl_by_symbol": [
            {"symbol": sym, "pnl": round(pnl, 2)}
            for sym, pnl in sorted_symbols
        ],
    }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Accept optional path argument.
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else None

    trades = load_trades(path)

    if not trades:
        print(f"No trades found at {path or DEFAULT_TRADES_PATH}.")
        print("Run paper trades first, then re-run attribution.")
        # Still produce an empty report to demonstrate the module works.
        report = compute_attribution([])
        print(format_attribution_report(report))
    else:
        report = compute_attribution(trades)
        print(format_attribution_report(report))

        # Also dump API data.
        api_data = get_attribution_api_data(report)
        print("\n--- API DATA (JSON) ---")
        print(json.dumps(api_data, indent=2))
