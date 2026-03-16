"""Ginko Report Generator -- daily intelligence reports for Substack.

Combines all Ginko subsystems into publishable reports:
  - Market regime + macro summary
  - Signal table with confidence scores
  - Prediction scorecard with Brier scores
  - Paper portfolio performance (when active)
  - Risk assessment
  - SATYA disclosure (publish ALL scores including misses)

Persistence: ~/.dharma/ginko/reports/
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import escape as html_escape
from pathlib import Path
from typing import Any

from dharma_swarm.ginko_brier import BrierDashboard, build_dashboard
from dharma_swarm.ginko_data import load_latest_pull
from dharma_swarm.ginko_regime import load_regime_history
from dharma_swarm.ginko_signals import load_latest_report

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
REPORTS_DIR = GINKO_DIR / "reports"

SATYA_DISCLOSURE = (
    "**SATYA Disclosure**: Dharmic Quant publishes every prediction score, "
    "including misses. We believe radical transparency builds trust and "
    "improves calibration over time."
)

SATYA_DISCLOSURE_HTML = (
    "<strong>SATYA Disclosure</strong>: Dharmic Quant publishes every "
    "prediction score, including misses. We believe radical transparency "
    "builds trust and improves calibration over time."
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dirs() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------


@dataclass
class DailyReport:
    """Complete daily intelligence report for Dharmic Quant."""

    date: str
    regime: str
    regime_confidence: float
    macro_summary: str
    risk_level: str
    signals: list[dict[str, Any]] = field(default_factory=list)
    new_predictions: list[dict[str, Any]] = field(default_factory=list)
    resolved_predictions: list[dict[str, Any]] = field(default_factory=list)
    brier_scorecard: dict[str, Any] = field(default_factory=dict)
    paper_portfolio_summary: dict[str, Any] | None = None
    sec_highlights: list[dict[str, Any]] = field(default_factory=list)
    generated_at: str = ""


# ---------------------------------------------------------------------------
# Report Generation
# ---------------------------------------------------------------------------


def generate_daily_report() -> DailyReport:
    """Generate the daily intelligence report by combining all Ginko subsystems.

    Loads the latest data from ginko_data, ginko_regime, ginko_signals,
    and ginko_brier. Optionally loads paper portfolio stats if the module
    is available. Handles missing data gracefully throughout.

    Returns:
        A fully populated DailyReport.
    """
    now = _utc_now()
    report = DailyReport(
        date=now.strftime("%Y-%m-%d"),
        regime="unknown",
        regime_confidence=0.0,
        macro_summary="No data available.",
        risk_level="unknown",
        generated_at=now.isoformat(),
    )

    # -- Regime (most recent from history) --
    try:
        regime_history = load_regime_history(limit=1)
        if regime_history:
            latest_regime = regime_history[-1]
            report.regime = latest_regime.regime
            report.regime_confidence = latest_regime.confidence
    except Exception as exc:
        logger.error("Failed to load regime history: %s", exc)

    # -- Market data (macro summary) --
    try:
        data_pull = load_latest_pull()
        if data_pull and data_pull.macro:
            macro = data_pull.macro
            parts: list[str] = []
            if macro.fed_funds_rate is not None:
                parts.append(f"Fed Funds: {macro.fed_funds_rate:.2f}%")
            if macro.ten_year_yield is not None:
                parts.append(f"10Y: {macro.ten_year_yield:.2f}%")
            if macro.two_year_yield is not None:
                parts.append(f"2Y: {macro.two_year_yield:.2f}%")
            if macro.yield_spread is not None:
                parts.append(f"Spread: {macro.yield_spread:.2f}%")
                if macro.yield_spread < 0:
                    parts.append("INVERTED")
            if macro.vix is not None:
                parts.append(f"VIX: {macro.vix:.1f}")
            if macro.unemployment is not None:
                parts.append(f"Unemployment: {macro.unemployment:.1f}%")
            if macro.cpi_yoy is not None:
                parts.append(f"CPI YoY: {macro.cpi_yoy:.1f}%")
            if parts:
                report.macro_summary = " | ".join(parts)
    except Exception as exc:
        logger.error("Failed to load market data: %s", exc)

    # -- Signals --
    try:
        signals_report = load_latest_report()
        if signals_report:
            report.risk_level = signals_report.get("risk_level", "unknown")
            raw_signals = signals_report.get("signals", [])
            for sig in raw_signals:
                report.signals.append({
                    "symbol": sig.get("symbol", ""),
                    "direction": sig.get("direction", ""),
                    "strength": sig.get("strength", ""),
                    "confidence": sig.get("confidence", 0.0),
                    "reason": sig.get("reason", ""),
                    "indicators": sig.get("indicators"),
                })
            # Use signal report's macro_summary if ours is still default
            if report.macro_summary == "No data available.":
                ms = signals_report.get("macro_summary", "")
                if ms:
                    report.macro_summary = ms
    except Exception as exc:
        logger.error("Failed to load signal report: %s", exc)

    # -- Brier dashboard --
    try:
        dashboard: BrierDashboard = build_dashboard()
        report.brier_scorecard = {
            "total_predictions": dashboard.total_predictions,
            "resolved_predictions": dashboard.resolved_predictions,
            "pending_predictions": dashboard.pending_predictions,
            "overall_brier": dashboard.overall_brier,
            "brier_by_category": dashboard.brier_by_category,
            "brier_by_source": dashboard.brier_by_source,
            "calibration_bins": dashboard.calibration_bins,
            "win_rate": dashboard.win_rate,
            "edge_validated": dashboard.edge_validated,
        }
    except Exception as exc:
        logger.error("Failed to build Brier dashboard: %s", exc)

    # -- Paper portfolio (optional module) --
    try:
        from dharma_swarm.ginko_paper_trade import PaperPortfolio

        portfolio = PaperPortfolio()
        report.paper_portfolio_summary = portfolio.get_portfolio_stats()
    except ImportError:
        logger.debug("ginko_paper_trade not available -- skipping portfolio")
    except Exception as exc:
        logger.error("Failed to load paper portfolio: %s", exc)

    return report


# ---------------------------------------------------------------------------
# Markdown Formatting
# ---------------------------------------------------------------------------


def _regime_badge(regime: str, confidence: float) -> str:
    """Return a regime badge string for markdown."""
    icons = {
        "bull": "BULL",
        "bear": "BEAR",
        "sideways": "SIDEWAYS",
        "unknown": "UNKNOWN",
    }
    label = icons.get(regime, regime.upper())
    return f"**{label}** (confidence: {confidence:.0%})"


def _risk_indicator(level: str) -> str:
    """Return a risk level indicator for markdown."""
    indicators = {
        "low": "LOW",
        "moderate": "MODERATE",
        "high": "HIGH",
        "extreme": "EXTREME",
    }
    return indicators.get(level, level.upper())


def format_report_markdown(report: DailyReport) -> str:
    """Format a DailyReport as publishable Markdown for Substack.

    Sections:
      - Header with date and regime
      - Macro summary
      - Signal table
      - Prediction scorecard
      - Paper portfolio (if active)
      - Risk assessment
      - SATYA disclosure
      - Methodology footer

    Args:
        report: The DailyReport to format.

    Returns:
        A complete Markdown string.
    """
    lines: list[str] = []

    # Header
    lines.append("# Dharmic Quant -- Daily Intelligence Report")
    lines.append("")
    lines.append(f"**Date**: {report.date}")
    lines.append(f"**Regime**: {_regime_badge(report.regime, report.regime_confidence)}")
    lines.append(f"**Risk Level**: {_risk_indicator(report.risk_level)}")
    lines.append("")

    # Macro summary
    lines.append("## Macro Summary")
    lines.append("")
    lines.append(report.macro_summary)
    lines.append("")

    # Signal table
    lines.append("## Signals")
    lines.append("")
    if report.signals:
        lines.append("| Symbol | Direction | Strength | Confidence | Reason |")
        lines.append("|--------|-----------|----------|------------|--------|")
        for sig in report.signals:
            symbol = sig.get("symbol", "")
            direction = sig.get("direction", "").upper()
            strength = sig.get("strength", "")
            confidence = sig.get("confidence", 0.0)
            reason = sig.get("reason", "")
            # Truncate long reasons for table readability
            if len(reason) > 80:
                reason = reason[:77] + "..."
            lines.append(
                f"| {symbol} | {direction} | {strength} | "
                f"{confidence:.0%} | {reason} |"
            )
    else:
        lines.append("*No signals generated for this period.*")
    lines.append("")

    # Prediction scorecard
    lines.append("## Prediction Scorecard")
    lines.append("")
    sc = report.brier_scorecard
    if sc:
        total = sc.get("total_predictions", 0)
        resolved = sc.get("resolved_predictions", 0)
        pending = sc.get("pending_predictions", 0)
        brier = sc.get("overall_brier")
        win_rate = sc.get("win_rate")
        edge = sc.get("edge_validated", False)

        lines.append(f"- **Total predictions**: {total}")
        lines.append(f"- **Resolved**: {resolved}")
        lines.append(f"- **Pending**: {pending}")
        if brier is not None:
            lines.append(f"- **Brier score**: {brier:.4f} (target: < 0.125)")
        else:
            lines.append("- **Brier score**: N/A (no resolved predictions)")
        if win_rate is not None:
            lines.append(f"- **Win rate**: {win_rate:.1%}")
        else:
            lines.append("- **Win rate**: N/A")
        lines.append(f"- **Edge validated**: {'YES' if edge else 'NO'}")

        # Category breakdown
        by_cat = sc.get("brier_by_category", {})
        if by_cat:
            lines.append("")
            lines.append("**By category:**")
            for cat, score in sorted(by_cat.items()):
                lines.append(f"- {cat}: {score:.4f}")

        # Source breakdown
        by_src = sc.get("brier_by_source", {})
        if by_src:
            lines.append("")
            lines.append("**By source:**")
            for src, score in sorted(by_src.items()):
                lines.append(f"- {src}: {score:.4f}")
    else:
        lines.append("*No prediction data available.*")
    lines.append("")

    # Paper portfolio
    if report.paper_portfolio_summary:
        ps = report.paper_portfolio_summary
        lines.append("## Paper Portfolio")
        lines.append("")
        total_value = ps.get("total_value", 0.0)
        total_pnl = ps.get("total_pnl", 0.0)
        total_pnl_pct = ps.get("total_pnl_pct", 0.0)
        sharpe = ps.get("sharpe_ratio", 0.0)
        max_dd = ps.get("max_drawdown", 0.0)
        trade_count = ps.get("trade_count", 0)
        open_positions = ps.get("open_positions", 0)

        pnl_sign = "+" if total_pnl >= 0 else ""
        lines.append(f"- **Total value**: ${total_value:,.2f}")
        lines.append(f"- **P&L**: {pnl_sign}${total_pnl:,.2f} ({pnl_sign}{total_pnl_pct:.2f}%)")
        lines.append(f"- **Sharpe ratio**: {sharpe:.2f}")
        lines.append(f"- **Max drawdown**: {max_dd:.2%}")
        lines.append(f"- **Closed trades**: {trade_count}")
        lines.append(f"- **Open positions**: {open_positions}")
        lines.append("")

    # SEC highlights
    if report.sec_highlights:
        lines.append("## SEC Filing Highlights")
        lines.append("")
        for highlight in report.sec_highlights:
            filing = highlight.get("filing", "")
            summary = highlight.get("summary", "")
            lines.append(f"- **{filing}**: {summary}")
        lines.append("")

    # Risk assessment
    lines.append("## Risk Assessment")
    lines.append("")
    lines.append(f"Current risk level: **{_risk_indicator(report.risk_level)}**")
    lines.append("")
    if report.risk_level == "extreme":
        lines.append(
            "Markets are exhibiting extreme risk conditions. "
            "Position sizing should be minimal and defensive."
        )
    elif report.risk_level == "high":
        lines.append(
            "Elevated risk environment. Tighter stops and reduced "
            "position sizing recommended."
        )
    elif report.risk_level == "moderate":
        lines.append(
            "Moderate risk environment. Standard position sizing "
            "and risk management apply."
        )
    elif report.risk_level == "low":
        lines.append(
            "Low risk environment. Conditions favor measured "
            "position building with normal risk parameters."
        )
    else:
        lines.append("Risk level could not be assessed from available data.")
    lines.append("")

    # SATYA disclosure
    lines.append("---")
    lines.append("")
    lines.append(SATYA_DISCLOSURE)
    lines.append("")
    lines.append("---")
    lines.append("")

    # Methodology footer
    lines.append("## Methodology")
    lines.append("")
    lines.append(
        "Dharmic Quant uses a systematic, multi-factor approach combining "
        "HMM-based regime detection, GARCH volatility forecasting, technical "
        "indicator synthesis, and Brier-scored prediction tracking. Signals "
        "are generated algorithmically with no discretionary overrides. All "
        "predictions are immutably recorded at the time of generation and "
        "scored against outcomes. Paper portfolio enforces AHIMSA (max 5% "
        "per position) and REVERSIBILITY (mandatory stop-losses) gates."
    )
    lines.append("")
    lines.append(f"*Generated: {report.generated_at}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML Formatting
# ---------------------------------------------------------------------------


_CSS = """\
body {
    background: #0a0a0f;
    color: #e0e0e0;
    font-family: 'Inter', 'SF Pro', -apple-system, sans-serif;
    max-width: 800px;
    margin: 0 auto;
    padding: 2rem;
    line-height: 1.6;
}
h1, h2, h3 {
    color: #00ff88;
    font-weight: 600;
}
h1 { font-size: 1.8rem; border-bottom: 2px solid #00ff88; padding-bottom: 0.5rem; }
h2 { font-size: 1.3rem; margin-top: 2rem; }
.meta { color: #888; font-size: 0.9rem; margin-bottom: 1.5rem; }
.badge {
    display: inline-block;
    padding: 0.2rem 0.6rem;
    border-radius: 4px;
    font-weight: 600;
    font-size: 0.85rem;
    margin-right: 0.5rem;
}
.badge-bull { background: #0a3d1a; color: #00ff88; border: 1px solid #00ff88; }
.badge-bear { background: #3d0a0a; color: #ff4444; border: 1px solid #ff4444; }
.badge-sideways { background: #3d3d0a; color: #ffaa00; border: 1px solid #ffaa00; }
.badge-unknown { background: #1a1a2e; color: #888; border: 1px solid #444; }
.risk-low { color: #00ff88; }
.risk-moderate { color: #ffaa00; }
.risk-high { color: #ff6600; }
.risk-extreme { color: #ff0000; font-weight: bold; }
table {
    width: 100%;
    border-collapse: collapse;
    margin: 1rem 0;
    font-size: 0.9rem;
}
th {
    background: #111;
    color: #00ff88;
    padding: 0.6rem 0.8rem;
    text-align: left;
    border-bottom: 2px solid #00ff88;
}
td {
    padding: 0.5rem 0.8rem;
    border-bottom: 1px solid #222;
}
tr:hover { background: #111; }
.dir-buy { color: #00ff88; font-weight: 600; }
.dir-sell { color: #ff4444; font-weight: 600; }
.dir-hold { color: #ffaa00; }
.brier-good { color: #00ff88; }
.brier-ok { color: #ffaa00; }
.brier-bad { color: #ff4444; }
.stat { margin: 0.3rem 0; }
.stat-label { color: #888; }
.stat-value { color: #e0e0e0; font-weight: 600; }
.satya {
    background: #111;
    border-left: 3px solid #00ff88;
    padding: 1rem;
    margin: 2rem 0;
    font-size: 0.9rem;
}
.footer {
    color: #666;
    font-size: 0.8rem;
    margin-top: 2rem;
    border-top: 1px solid #222;
    padding-top: 1rem;
}
"""


def _brier_class(score: float | None) -> str:
    """Return a CSS class based on Brier score quality."""
    if score is None:
        return ""
    if score < 0.1:
        return "brier-good"
    if score < 0.2:
        return "brier-ok"
    return "brier-bad"


def _direction_class(direction: str) -> str:
    """Return a CSS class for signal direction."""
    d = direction.lower()
    if d == "buy":
        return "dir-buy"
    if d == "sell":
        return "dir-sell"
    return "dir-hold"


def _direction_arrow(direction: str) -> str:
    """Return an arrow character for signal direction."""
    d = direction.lower()
    if d == "buy":
        return "&#9650;"  # upward triangle
    if d == "sell":
        return "&#9660;"  # downward triangle
    return "&#9654;"  # right triangle (hold)


def format_report_html(report: DailyReport) -> str:
    """Format a DailyReport as styled HTML matching the SwarmLens theme.

    Uses #0a0a0f background with #00ff88 accent. Signal directions are
    color-coded. Brier scores use green/yellow/red color coding.

    Args:
        report: The DailyReport to format.

    Returns:
        A complete HTML document string.
    """
    regime_class = f"badge-{report.regime}" if report.regime in (
        "bull", "bear", "sideways"
    ) else "badge-unknown"
    risk_class = f"risk-{report.risk_level}" if report.risk_level in (
        "low", "moderate", "high", "extreme"
    ) else ""

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append("<html lang=\"en\">")
    parts.append("<head>")
    parts.append("<meta charset=\"UTF-8\">")
    parts.append("<meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">")
    parts.append(f"<title>Dharmic Quant -- {report.date}</title>")
    parts.append(f"<style>{_CSS}</style>")
    parts.append("</head>")
    parts.append("<body>")

    # Header
    parts.append("<h1>Dharmic Quant -- Daily Intelligence Report</h1>")
    parts.append("<div class=\"meta\">")
    parts.append(f"  <strong>Date:</strong> {html_escape(report.date)}")
    parts.append(
        f"  &nbsp;|&nbsp; <strong>Regime:</strong> "
        f"<span class=\"badge {regime_class}\">"
        f"{html_escape(report.regime.upper())}</span> "
        f"({report.regime_confidence:.0%})"
    )
    parts.append(
        f"  &nbsp;|&nbsp; <strong>Risk:</strong> "
        f"<span class=\"{risk_class}\">"
        f"{html_escape(report.risk_level.upper())}</span>"
    )
    parts.append("</div>")

    # Macro summary
    parts.append("<h2>Macro Summary</h2>")
    parts.append(f"<p>{html_escape(report.macro_summary)}</p>")

    # Signal table
    parts.append("<h2>Signals</h2>")
    if report.signals:
        parts.append("<table>")
        parts.append("<thead><tr>")
        parts.append("<th>Symbol</th><th>Direction</th><th>Strength</th>")
        parts.append("<th>Confidence</th><th>Reason</th>")
        parts.append("</tr></thead>")
        parts.append("<tbody>")
        for sig in report.signals:
            symbol = html_escape(str(sig.get("symbol", "")))
            direction = str(sig.get("direction", ""))
            strength = html_escape(str(sig.get("strength", "")))
            confidence = sig.get("confidence", 0.0)
            reason = html_escape(str(sig.get("reason", "")))
            dir_cls = _direction_class(direction)
            arrow = _direction_arrow(direction)
            parts.append("<tr>")
            parts.append(f"  <td><strong>{symbol}</strong></td>")
            parts.append(
                f"  <td class=\"{dir_cls}\">{arrow} {html_escape(direction.upper())}</td>"
            )
            parts.append(f"  <td>{strength}</td>")
            parts.append(f"  <td>{confidence:.0%}</td>")
            parts.append(f"  <td>{reason}</td>")
            parts.append("</tr>")
        parts.append("</tbody></table>")
    else:
        parts.append("<p><em>No signals generated for this period.</em></p>")

    # Prediction scorecard
    parts.append("<h2>Prediction Scorecard</h2>")
    sc = report.brier_scorecard
    if sc:
        total = sc.get("total_predictions", 0)
        resolved = sc.get("resolved_predictions", 0)
        pending = sc.get("pending_predictions", 0)
        brier = sc.get("overall_brier")
        win_rate = sc.get("win_rate")
        edge = sc.get("edge_validated", False)
        brier_cls = _brier_class(brier)

        parts.append("<div>")
        parts.append(
            f'<p class="stat"><span class="stat-label">Total predictions:</span> '
            f'<span class="stat-value">{total}</span></p>'
        )
        parts.append(
            f'<p class="stat"><span class="stat-label">Resolved:</span> '
            f'<span class="stat-value">{resolved}</span></p>'
        )
        parts.append(
            f'<p class="stat"><span class="stat-label">Pending:</span> '
            f'<span class="stat-value">{pending}</span></p>'
        )
        if brier is not None:
            parts.append(
                f'<p class="stat"><span class="stat-label">Brier score:</span> '
                f'<span class="stat-value {brier_cls}">{brier:.4f}</span> '
                f'(target: &lt; 0.125)</p>'
            )
        else:
            parts.append(
                '<p class="stat"><span class="stat-label">Brier score:</span> '
                '<span class="stat-value">N/A</span></p>'
            )
        if win_rate is not None:
            parts.append(
                f'<p class="stat"><span class="stat-label">Win rate:</span> '
                f'<span class="stat-value">{win_rate:.1%}</span></p>'
            )
        edge_text = "YES" if edge else "NO"
        edge_color = "brier-good" if edge else "brier-bad"
        parts.append(
            f'<p class="stat"><span class="stat-label">Edge validated:</span> '
            f'<span class="stat-value {edge_color}">{edge_text}</span></p>'
        )
        parts.append("</div>")
    else:
        parts.append("<p><em>No prediction data available.</em></p>")

    # Paper portfolio
    if report.paper_portfolio_summary:
        ps = report.paper_portfolio_summary
        total_value = ps.get("total_value", 0.0)
        total_pnl = ps.get("total_pnl", 0.0)
        total_pnl_pct = ps.get("total_pnl_pct", 0.0)
        sharpe = ps.get("sharpe_ratio", 0.0)
        max_dd = ps.get("max_drawdown", 0.0)
        trade_count = ps.get("trade_count", 0)
        open_positions = ps.get("open_positions", 0)

        pnl_sign = "+" if total_pnl >= 0 else ""
        pnl_color = "dir-buy" if total_pnl >= 0 else "dir-sell"

        parts.append("<h2>Paper Portfolio</h2>")
        parts.append("<div>")
        parts.append(
            f'<p class="stat"><span class="stat-label">Total value:</span> '
            f'<span class="stat-value">${total_value:,.2f}</span></p>'
        )
        parts.append(
            f'<p class="stat"><span class="stat-label">P&amp;L:</span> '
            f'<span class="stat-value {pnl_color}">'
            f'{pnl_sign}${total_pnl:,.2f} ({pnl_sign}{total_pnl_pct:.2f}%)'
            f'</span></p>'
        )
        parts.append(
            f'<p class="stat"><span class="stat-label">Sharpe ratio:</span> '
            f'<span class="stat-value">{sharpe:.2f}</span></p>'
        )
        parts.append(
            f'<p class="stat"><span class="stat-label">Max drawdown:</span> '
            f'<span class="stat-value">{max_dd:.2%}</span></p>'
        )
        parts.append(
            f'<p class="stat"><span class="stat-label">Closed trades:</span> '
            f'<span class="stat-value">{trade_count}</span></p>'
        )
        parts.append(
            f'<p class="stat"><span class="stat-label">Open positions:</span> '
            f'<span class="stat-value">{open_positions}</span></p>'
        )
        parts.append("</div>")

    # SEC highlights
    if report.sec_highlights:
        parts.append("<h2>SEC Filing Highlights</h2>")
        parts.append("<ul>")
        for highlight in report.sec_highlights:
            filing = html_escape(str(highlight.get("filing", "")))
            summary = html_escape(str(highlight.get("summary", "")))
            parts.append(f"<li><strong>{filing}</strong>: {summary}</li>")
        parts.append("</ul>")

    # Risk assessment
    parts.append("<h2>Risk Assessment</h2>")
    parts.append(
        f'<p>Current risk level: <strong class="{risk_class}">'
        f'{html_escape(report.risk_level.upper())}</strong></p>'
    )

    # SATYA disclosure
    parts.append(f'<div class="satya">{SATYA_DISCLOSURE_HTML}</div>')

    # Footer
    parts.append('<div class="footer">')
    parts.append(
        "<p><strong>Methodology:</strong> "
        "Dharmic Quant uses a systematic, multi-factor approach combining "
        "HMM-based regime detection, GARCH volatility forecasting, technical "
        "indicator synthesis, and Brier-scored prediction tracking. Signals "
        "are generated algorithmically with no discretionary overrides. All "
        "predictions are immutably recorded at the time of generation and "
        "scored against outcomes. Paper portfolio enforces AHIMSA (max 5% "
        "per position) and REVERSIBILITY (mandatory stop-losses) gates.</p>"
    )
    parts.append(f"<p><em>Generated: {html_escape(report.generated_at)}</em></p>")
    parts.append("</div>")

    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def _report_to_dict(report: DailyReport) -> dict[str, Any]:
    """Convert a DailyReport to a JSON-serializable dict."""
    return asdict(report)


def _report_from_dict(data: dict[str, Any]) -> DailyReport:
    """Reconstruct a DailyReport from a dict."""
    return DailyReport(
        date=data.get("date", ""),
        regime=data.get("regime", "unknown"),
        regime_confidence=data.get("regime_confidence", 0.0),
        macro_summary=data.get("macro_summary", ""),
        risk_level=data.get("risk_level", "unknown"),
        signals=data.get("signals", []),
        new_predictions=data.get("new_predictions", []),
        resolved_predictions=data.get("resolved_predictions", []),
        brier_scorecard=data.get("brier_scorecard", {}),
        paper_portfolio_summary=data.get("paper_portfolio_summary"),
        sec_highlights=data.get("sec_highlights", []),
        generated_at=data.get("generated_at", ""),
    )


def save_report(report: DailyReport) -> Path:
    """Save the daily report in markdown, HTML, and JSON formats.

    Files are written to ~/.dharma/ginko/reports/ with the naming
    convention report_{YYYYMMDD}.{ext}.

    Args:
        report: The DailyReport to save.

    Returns:
        Path to the saved markdown file.
    """
    _ensure_dirs()
    date_str = report.date.replace("-", "")

    md_path = REPORTS_DIR / f"report_{date_str}.md"
    html_path = REPORTS_DIR / f"report_{date_str}.html"
    json_path = REPORTS_DIR / f"report_{date_str}.json"

    # Markdown
    try:
        md_content = format_report_markdown(report)
        md_path.write_text(md_content, encoding="utf-8")
        logger.info("Saved markdown report: %s", md_path)
    except Exception as exc:
        logger.error("Failed to save markdown report: %s", exc)

    # HTML
    try:
        html_content = format_report_html(report)
        html_path.write_text(html_content, encoding="utf-8")
        logger.info("Saved HTML report: %s", html_path)
    except Exception as exc:
        logger.error("Failed to save HTML report: %s", exc)

    # JSON
    try:
        json_content = json.dumps(_report_to_dict(report), indent=2, default=str)
        json_path.write_text(json_content, encoding="utf-8")
        logger.info("Saved JSON report: %s", json_path)
    except Exception as exc:
        logger.error("Failed to save JSON report: %s", exc)

    return md_path


def load_report(date_str: str) -> DailyReport | None:
    """Load a previously saved report by date.

    Args:
        date_str: Date in YYYYMMDD or YYYY-MM-DD format.

    Returns:
        The reconstructed DailyReport, or None if not found.
    """
    normalized = date_str.replace("-", "")
    json_path = REPORTS_DIR / f"report_{normalized}.json"

    if not json_path.exists():
        logger.warning("Report not found: %s", json_path)
        return None

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return _report_from_dict(data)
    except Exception as exc:
        logger.error("Failed to load report from %s: %s", json_path, exc)
        return None


def list_reports(limit: int = 30) -> list[dict[str, Any]]:
    """List recent report files with date and path.

    Args:
        limit: Maximum number of reports to return.

    Returns:
        List of dicts with 'date', 'md_path', 'html_path', 'json_path' keys,
        sorted newest first.
    """
    _ensure_dirs()
    json_files = sorted(REPORTS_DIR.glob("report_*.json"), reverse=True)

    results: list[dict[str, Any]] = []
    for jf in json_files[:limit]:
        # Extract date from filename: report_YYYYMMDD.json
        stem = jf.stem  # report_YYYYMMDD
        date_part = stem.replace("report_", "")
        if len(date_part) == 8:
            formatted_date = f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
        else:
            formatted_date = date_part

        md_path = jf.with_suffix(".md")
        html_path = jf.with_suffix(".html")

        results.append({
            "date": formatted_date,
            "json_path": str(jf),
            "md_path": str(md_path) if md_path.exists() else None,
            "html_path": str(html_path) if html_path.exists() else None,
        })

    return results


# ---------------------------------------------------------------------------
# Substack Formatting
# ---------------------------------------------------------------------------


def format_report_substack(report: DailyReport) -> str:
    """Format report for Substack newsletter distribution.

    Optimized for email/web reading:
    - Opening hook (biggest market move)
    - Regime box
    - Macro dashboard
    - Signal table with directional arrows
    - Prediction scorecard
    - Agent consensus placeholder
    - Risk assessment
    - SATYA disclosure
    - Disclaimer footer
    """
    lines: list[str] = []

    # Opening hook
    if report.signals:
        strongest = max(
            report.signals,
            key=lambda s: (
                s.get("confidence", 0)
                if isinstance(s, dict)
                else getattr(s, "confidence", 0)
            ),
        )
        sym = (
            strongest.get("symbol", "?")
            if isinstance(strongest, dict)
            else getattr(strongest, "symbol", "?")
        )
        direction = (
            strongest.get("direction", "?")
            if isinstance(strongest, dict)
            else getattr(strongest, "direction", "?")
        )
        conf = (
            strongest.get("confidence", 0)
            if isinstance(strongest, dict)
            else getattr(strongest, "confidence", 0)
        )
        lines.append(
            f"**Today's strongest signal: {sym} "
            f"-> {direction.upper()} ({conf:.0%} confidence)**\n"
        )

    # Regime box
    lines.append("---")
    lines.append(
        f"**MARKET REGIME: {report.regime.upper()}** "
        f"(confidence: {report.regime_confidence:.0%})"
    )
    lines.append(f"**Risk Level: {report.risk_level.upper()}**")
    lines.append("---\n")

    # Macro dashboard
    if report.macro_summary:
        lines.append("## Macro Dashboard")
        lines.append(f"{report.macro_summary}\n")

    # Signal table
    lines.append("## Today's Signals\n")
    lines.append("| Symbol | Direction | Strength | Confidence | Reason |")
    lines.append("|--------|-----------|----------|------------|--------|")
    for s in report.signals:
        if isinstance(s, dict):
            sym = s.get("symbol", "")
            d = s.get("direction", "")
            st = s.get("strength", "")
            c = s.get("confidence", 0)
            r = s.get("reason", "")
        else:
            sym = s.symbol
            d = s.direction
            st = s.strength
            c = s.confidence
            r = s.reason
        arrow = {"buy": "BUY", "sell": "SELL", "hold": "HOLD"}.get(d, d.upper())
        lines.append(f"| **{sym}** | {arrow} | {st} | {c:.0%} | {r[:60]} |")
    lines.append("")

    # Prediction scorecard
    brier = report.brier_scorecard
    lines.append("## Prediction Scorecard\n")
    lines.append(f"- **Total predictions**: {brier.get('total_predictions', 0)}")
    lines.append(f"- **Resolved**: {brier.get('resolved_predictions', 0)}")
    if brier.get("overall_brier") is not None:
        lines.append(
            f"- **Brier score**: {brier['overall_brier']:.4f} (target: < 0.125)"
        )
    if brier.get("win_rate") is not None:
        lines.append(f"- **Win rate**: {brier['win_rate']:.1%}")
    lines.append(
        f"- **Edge validated**: "
        f"{'YES' if brier.get('edge_validated') else 'NO'}"
    )
    lines.append("")

    # Paper portfolio
    if report.paper_portfolio_summary:
        pp = report.paper_portfolio_summary
        lines.append("## Paper Portfolio\n")
        lines.append(f"- **Value**: ${pp.get('total_value', 100000):,.0f}")
        lines.append(f"- **P&L**: {pp.get('total_pnl_pct', 0):+.2f}%")
        lines.append(f"- **Sharpe**: {pp.get('sharpe_ratio', 0):.2f}")
        lines.append(f"- **Open positions**: {pp.get('open_positions', 0)}")
        lines.append("")

    # Risk assessment
    lines.append("## Risk Assessment\n")
    risk_label = {"low": "LOW", "moderate": "MODERATE", "high": "HIGH",
                  "extreme": "EXTREME"}.get(report.risk_level, report.risk_level.upper())
    lines.append(f"**{risk_label}**\n")

    # SATYA disclosure
    lines.append("---")
    lines.append(SATYA_DISCLOSURE)
    lines.append("---\n")

    # Disclaimer
    lines.append(
        "*This is not financial advice. Past performance does not guarantee "
        "future results. Paper trading only -- no real capital at risk.*"
    )
    lines.append(
        f"\n*Generated by Dharmic Quant on {report.date} | dharma_swarm*"
    )

    return "\n".join(lines)


def format_report_email_subject(report: DailyReport) -> str:
    """Generate compelling email subject line for the daily report."""
    regime = report.regime.upper()
    n_signals = len(report.signals)
    brier = report.brier_scorecard.get("overall_brier")
    brier_str = f" | Brier: {brier:.3f}" if brier is not None else ""
    return f"[{regime}] {n_signals} signals{brier_str} -- Dharmic Quant {report.date}"
