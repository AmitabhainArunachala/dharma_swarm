"""Ginko Portfolio Risk Management -- portfolio-level risk metrics.

Provides Value-at-Risk, Conditional VaR, correlation analysis,
beta computation, sector exposure monitoring, concentration risk
(Herfindahl-Hirschman Index), and composite risk scoring.

This module fills the gap between position-level stops (ginko_paper_trade.py)
and portfolio-level risk awareness. No position-level risk is portfolio-level
risk -- correlations, concentration, and tail events kill portfolios, not
individual positions.

Integrates with:
  - ginko_paper_trade.py (Position, PaperPortfolio)
  - ginko_orchestrator.py (position sizing, telos gates)
  - telos_gates.py (AHIMSA -- portfolio-level constraint enforcement)

Risk score thresholds:
  CRITICAL: VaR95 > 5% of portfolio OR concentration > 0.5
  HIGH:     VaR95 > 3% OR any sector > 40%
  MEDIUM:   VaR95 > 1.5% OR concentration > 0.3
  LOW:      everything else
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Try numpy; fall back to pure Python
# ---------------------------------------------------------------------------

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Default sector map for common US equity tickers
# ---------------------------------------------------------------------------

DEFAULT_SECTOR_MAP: dict[str, str] = {
    # Technology
    "AAPL": "Technology",
    "MSFT": "Technology",
    "GOOGL": "Technology",
    "GOOG": "Technology",
    "META": "Technology",
    "NVDA": "Technology",
    "AMD": "Technology",
    "INTC": "Technology",
    "CRM": "Technology",
    "ADBE": "Technology",
    "ORCL": "Technology",
    "CSCO": "Technology",
    "AVGO": "Technology",
    "QCOM": "Technology",
    "TSM": "Technology",
    # Financials
    "JPM": "Financials",
    "BAC": "Financials",
    "WFC": "Financials",
    "GS": "Financials",
    "MS": "Financials",
    "C": "Financials",
    "BLK": "Financials",
    "SCHW": "Financials",
    "AXP": "Financials",
    "V": "Financials",
    "MA": "Financials",
    # Healthcare
    "JNJ": "Healthcare",
    "UNH": "Healthcare",
    "PFE": "Healthcare",
    "ABBV": "Healthcare",
    "MRK": "Healthcare",
    "LLY": "Healthcare",
    "TMO": "Healthcare",
    "ABT": "Healthcare",
    "BMY": "Healthcare",
    "AMGN": "Healthcare",
    # Consumer Discretionary
    "AMZN": "Consumer Discretionary",
    "TSLA": "Consumer Discretionary",
    "HD": "Consumer Discretionary",
    "NKE": "Consumer Discretionary",
    "MCD": "Consumer Discretionary",
    "SBUX": "Consumer Discretionary",
    "TGT": "Consumer Discretionary",
    "LOW": "Consumer Discretionary",
    # Consumer Staples
    "PG": "Consumer Staples",
    "KO": "Consumer Staples",
    "PEP": "Consumer Staples",
    "WMT": "Consumer Staples",
    "COST": "Consumer Staples",
    "CL": "Consumer Staples",
    "PM": "Consumer Staples",
    # Energy
    "XOM": "Energy",
    "CVX": "Energy",
    "COP": "Energy",
    "SLB": "Energy",
    "EOG": "Energy",
    "OXY": "Energy",
    # Industrials
    "BA": "Industrials",
    "CAT": "Industrials",
    "UPS": "Industrials",
    "HON": "Industrials",
    "GE": "Industrials",
    "RTX": "Industrials",
    "LMT": "Industrials",
    "DE": "Industrials",
    # Utilities
    "NEE": "Utilities",
    "DUK": "Utilities",
    "SO": "Utilities",
    "D": "Utilities",
    "AEP": "Utilities",
    # Real Estate
    "AMT": "Real Estate",
    "PLD": "Real Estate",
    "CCI": "Real Estate",
    "SPG": "Real Estate",
    "O": "Real Estate",
    # Materials
    "LIN": "Materials",
    "APD": "Materials",
    "SHW": "Materials",
    "FCX": "Materials",
    "NEM": "Materials",
    # Communication Services
    "DIS": "Communication Services",
    "NFLX": "Communication Services",
    "CMCSA": "Communication Services",
    "T": "Communication Services",
    "VZ": "Communication Services",
    "TMUS": "Communication Services",
    # Crypto (common tickers)
    "BTC": "Crypto",
    "ETH": "Crypto",
    "SOL": "Crypto",
    "BTC-USD": "Crypto",
    "ETH-USD": "Crypto",
    # Indices / ETFs
    "SPY": "Index ETF",
    "QQQ": "Index ETF",
    "IWM": "Index ETF",
    "DIA": "Index ETF",
    "TLT": "Fixed Income ETF",
    "GLD": "Commodities ETF",
    "SLV": "Commodities ETF",
    "USO": "Commodities ETF",
}


# ---------------------------------------------------------------------------
# RiskReport dataclass
# ---------------------------------------------------------------------------


@dataclass
class RiskReport:
    """Portfolio-level risk assessment."""

    var_95: float = 0.0  # Dollar VaR at 95% confidence
    var_99: float = 0.0  # Dollar VaR at 99% confidence
    cvar_95: float = 0.0  # Conditional VaR (Expected Shortfall) at 95%
    portfolio_beta: float = 0.0  # Beta relative to benchmark
    correlation_matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    sector_exposures: dict[str, float] = field(default_factory=dict)
    sector_warnings: list[str] = field(default_factory=list)
    concentration_risk: float = 0.0  # HHI: 0 = diversified, 1 = single position
    max_single_position_pct: float = 0.0
    num_positions: int = 0
    portfolio_value: float = 0.0
    risk_score: str = "LOW"  # LOW / MEDIUM / HIGH / CRITICAL

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict for JSON persistence."""
        return {
            "var_95": round(self.var_95, 2),
            "var_99": round(self.var_99, 2),
            "cvar_95": round(self.cvar_95, 2),
            "portfolio_beta": round(self.portfolio_beta, 4),
            "correlation_matrix": {
                k: {k2: round(v2, 4) for k2, v2 in v.items()}
                for k, v in self.correlation_matrix.items()
            },
            "sector_exposures": {
                k: round(v, 4) for k, v in self.sector_exposures.items()
            },
            "sector_warnings": self.sector_warnings,
            "concentration_risk": round(self.concentration_risk, 4),
            "max_single_position_pct": round(self.max_single_position_pct, 4),
            "num_positions": self.num_positions,
            "portfolio_value": round(self.portfolio_value, 2),
            "risk_score": self.risk_score,
        }


# ---------------------------------------------------------------------------
# Pure-math helpers (numpy or manual fallback)
# ---------------------------------------------------------------------------


def _mean(values: list[float]) -> float:
    """Arithmetic mean."""
    if not values:
        return 0.0
    return sum(values) / len(values)


def _variance(values: list[float], ddof: int = 1) -> float:
    """Sample variance with Bessel's correction (ddof=1)."""
    n = len(values)
    if n < 2:
        return 0.0
    m = _mean(values)
    return sum((x - m) ** 2 for x in values) / (n - ddof)


def _std(values: list[float], ddof: int = 1) -> float:
    """Sample standard deviation."""
    v = _variance(values, ddof=ddof)
    return math.sqrt(v) if v > 0 else 0.0


def _covariance(x: list[float], y: list[float], ddof: int = 1) -> float:
    """Sample covariance between two series of equal length."""
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    mx = _mean(x[:n])
    my = _mean(y[:n])
    return sum((x[i] - mx) * (y[i] - my) for i in range(n)) / (n - ddof)


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient between two series."""
    n = min(len(x), len(y))
    if n < 2:
        return 0.0
    sx = _std(x[:n])
    sy = _std(y[:n])
    if sx == 0.0 or sy == 0.0:
        return 0.0
    cov = _covariance(x[:n], y[:n])
    return cov / (sx * sy)


def _percentile(sorted_values: list[float], pct: float) -> float:
    """Linear interpolation percentile on pre-sorted values.

    Uses the same method as numpy's default (linear interpolation).
    pct is in [0, 100].
    """
    if not sorted_values:
        return 0.0
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    # Rank position (0-indexed float)
    pos = (pct / 100.0) * (n - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, n - 1)
    frac = pos - lo
    return sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo])


# ---------------------------------------------------------------------------
# Core risk functions
# ---------------------------------------------------------------------------


def compute_var(
    daily_returns: list[float],
    confidence: float = 0.95,
    portfolio_value: float = 100_000.0,
) -> float:
    """Historical Value-at-Risk.

    Sorts daily returns, takes the (1 - confidence) percentile,
    and converts to a dollar loss amount.

    Args:
        daily_returns: List of daily fractional returns (e.g. -0.02 = -2%).
        confidence: Confidence level (default 0.95 for 95% VaR).
        portfolio_value: Current portfolio value in dollars.

    Returns:
        Dollar amount at risk (positive number = potential loss).
        Returns 0.0 if insufficient data (< 5 observations).
    """
    if len(daily_returns) < 5:
        return 0.0

    pct = (1.0 - confidence) * 100.0  # e.g. 5th percentile for 95% VaR

    if _HAS_NUMPY:
        arr = np.array(daily_returns, dtype=np.float64)
        var_return = float(np.percentile(arr, pct))
    else:
        sorted_ret = sorted(daily_returns)
        var_return = _percentile(sorted_ret, pct)

    # VaR is reported as a positive dollar loss
    return abs(var_return) * portfolio_value


def compute_cvar(
    daily_returns: list[float],
    confidence: float = 0.95,
    portfolio_value: float = 100_000.0,
) -> float:
    """Conditional Value-at-Risk (Expected Shortfall).

    Mean of all returns that fall below the VaR threshold.
    Answers: "Given that we're in the worst (1 - confidence) of days,
    what is the average loss?"

    Args:
        daily_returns: List of daily fractional returns.
        confidence: Confidence level (default 0.95).
        portfolio_value: Current portfolio value in dollars.

    Returns:
        Dollar expected shortfall (positive number = potential loss).
        Returns 0.0 if insufficient data.
    """
    if len(daily_returns) < 5:
        return 0.0

    pct = (1.0 - confidence) * 100.0

    if _HAS_NUMPY:
        arr = np.array(daily_returns, dtype=np.float64)
        var_threshold = float(np.percentile(arr, pct))
        tail = arr[arr <= var_threshold]
        if len(tail) == 0:
            return compute_var(daily_returns, confidence, portfolio_value)
        cvar_return = float(np.mean(tail))
    else:
        sorted_ret = sorted(daily_returns)
        var_threshold = _percentile(sorted_ret, pct)
        tail = [r for r in sorted_ret if r <= var_threshold]
        if not tail:
            return compute_var(daily_returns, confidence, portfolio_value)
        cvar_return = _mean(tail)

    return abs(cvar_return) * portfolio_value


def compute_correlation_matrix(
    price_histories: dict[str, list[float]],
) -> dict[str, dict[str, float]]:
    """Pairwise Pearson correlation between all symbols.

    Converts price series to return series, then computes correlations.
    Only symbols with >= 5 price observations are included.

    Args:
        price_histories: Dict of symbol -> list of historical prices
            (chronological order, oldest first).

    Returns:
        Nested dict: {symbol_a: {symbol_b: correlation, ...}, ...}
        Values range from -1.0 (perfect inverse) to 1.0 (perfect positive).
    """
    # Convert prices to returns
    return_series: dict[str, list[float]] = {}
    for sym, prices in price_histories.items():
        if len(prices) < 5:
            continue
        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0:
                returns.append((prices[i] - prices[i - 1]) / prices[i - 1])
        if len(returns) >= 4:
            return_series[sym] = returns

    symbols = sorted(return_series.keys())
    matrix: dict[str, dict[str, float]] = {}

    if _HAS_NUMPY and len(symbols) >= 2:
        # Align series to minimum common length
        min_len = min(len(return_series[s]) for s in symbols)
        if min_len >= 4:
            data = np.array(
                [return_series[s][:min_len] for s in symbols], dtype=np.float64
            )
            corr = np.corrcoef(data)
            for i, sym_a in enumerate(symbols):
                matrix[sym_a] = {}
                for j, sym_b in enumerate(symbols):
                    val = float(corr[i, j])
                    # Clamp NaN to 0.0
                    matrix[sym_a][sym_b] = 0.0 if math.isnan(val) else val
            return matrix

    # Pure Python fallback (or single symbol)
    for sym_a in symbols:
        matrix[sym_a] = {}
        for sym_b in symbols:
            if sym_a == sym_b:
                matrix[sym_a][sym_b] = 1.0
            else:
                matrix[sym_a][sym_b] = _pearson_correlation(
                    return_series[sym_a], return_series[sym_b]
                )

    return matrix


def compute_portfolio_beta(
    portfolio_returns: list[float],
    benchmark_returns: list[float],
) -> float:
    """Portfolio beta relative to a benchmark.

    Beta = Cov(portfolio, benchmark) / Var(benchmark)

    Args:
        portfolio_returns: Daily portfolio returns.
        benchmark_returns: Daily benchmark returns (e.g. SPY).

    Returns:
        Beta coefficient. > 1 = more volatile than benchmark.
        Returns 0.0 if insufficient data or zero benchmark variance.
    """
    n = min(len(portfolio_returns), len(benchmark_returns))
    if n < 5:
        return 0.0

    p = portfolio_returns[:n]
    b = benchmark_returns[:n]

    if _HAS_NUMPY:
        p_arr = np.array(p, dtype=np.float64)
        b_arr = np.array(b, dtype=np.float64)
        b_var = float(np.var(b_arr, ddof=1))
        if b_var == 0.0:
            return 0.0
        cov_matrix = np.cov(p_arr, b_arr, ddof=1)
        return float(cov_matrix[0, 1]) / b_var
    else:
        b_var = _variance(b)
        if b_var == 0.0:
            return 0.0
        cov = _covariance(p, b)
        return cov / b_var


def check_sector_exposure(
    positions: dict[str, Any],
    sector_map: dict[str, str] | None = None,
    max_pct: float = 0.30,
) -> list[str]:
    """Check for sector concentration exceeding threshold.

    Args:
        positions: Dict of symbol -> Position (or any object with
            current_price and quantity attributes).
        sector_map: Mapping of symbol -> sector name.
            Defaults to DEFAULT_SECTOR_MAP.
        max_pct: Maximum allowed sector exposure as fraction (default 30%).

    Returns:
        List of warning strings for sectors exceeding max_pct.
        Empty list = all sectors within limits.
    """
    if sector_map is None:
        sector_map = DEFAULT_SECTOR_MAP

    if not positions:
        return []

    # Compute position values
    position_values: dict[str, float] = {}
    for sym, pos in positions.items():
        price = getattr(pos, "current_price", 0.0) or getattr(pos, "entry_price", 0.0)
        qty = getattr(pos, "quantity", 0.0)
        position_values[sym] = price * qty

    total_value = sum(position_values.values())
    if total_value <= 0:
        return []

    # Aggregate by sector
    sector_values: dict[str, float] = {}
    for sym, val in position_values.items():
        sector = sector_map.get(sym, "Unknown")
        sector_values[sector] = sector_values.get(sector, 0.0) + val

    warnings: list[str] = []
    for sector, val in sorted(sector_values.items(), key=lambda x: -x[1]):
        pct = val / total_value
        if pct > max_pct:
            warnings.append(
                f"Sector '{sector}' at {pct:.1%} exceeds {max_pct:.0%} limit "
                f"(${val:,.0f} of ${total_value:,.0f})"
            )

    return warnings


def compute_sector_exposures(
    positions: dict[str, Any],
    sector_map: dict[str, str] | None = None,
) -> dict[str, float]:
    """Compute sector exposure percentages.

    Args:
        positions: Dict of symbol -> Position.
        sector_map: Symbol -> sector mapping (defaults to DEFAULT_SECTOR_MAP).

    Returns:
        Dict of sector -> percentage of portfolio (0.0 to 1.0).
    """
    if sector_map is None:
        sector_map = DEFAULT_SECTOR_MAP

    if not positions:
        return {}

    position_values: dict[str, float] = {}
    for sym, pos in positions.items():
        price = getattr(pos, "current_price", 0.0) or getattr(pos, "entry_price", 0.0)
        qty = getattr(pos, "quantity", 0.0)
        position_values[sym] = price * qty

    total_value = sum(position_values.values())
    if total_value <= 0:
        return {}

    sector_values: dict[str, float] = {}
    for sym, val in position_values.items():
        sector = sector_map.get(sym, "Unknown")
        sector_values[sector] = sector_values.get(sector, 0.0) + val

    return {sector: val / total_value for sector, val in sector_values.items()}


def compute_concentration_risk(positions: dict[str, Any]) -> float:
    """Herfindahl-Hirschman Index of position weights.

    HHI = sum(w_i^2) where w_i is the weight of position i.

    Args:
        positions: Dict of symbol -> Position (needs current_price, quantity).

    Returns:
        HHI value from 0.0 (perfectly diversified, infinite positions)
        to 1.0 (single position).
        Returns 0.0 if no positions.
    """
    if not positions:
        return 0.0

    values: list[float] = []
    for pos in positions.values():
        price = getattr(pos, "current_price", 0.0) or getattr(pos, "entry_price", 0.0)
        qty = getattr(pos, "quantity", 0.0)
        values.append(price * qty)

    total = sum(values)
    if total <= 0:
        return 0.0

    weights = [v / total for v in values]
    return sum(w * w for w in weights)


# ---------------------------------------------------------------------------
# Master assessment
# ---------------------------------------------------------------------------


def _classify_risk_score(
    var_95_pct: float,
    concentration: float,
    max_sector_pct: float,
) -> str:
    """Determine composite risk score from metrics.

    Thresholds:
        CRITICAL: VaR95 > 5% of portfolio OR concentration > 0.5
        HIGH:     VaR95 > 3% OR any sector > 40%
        MEDIUM:   VaR95 > 1.5% OR concentration > 0.3
        LOW:      everything else

    Args:
        var_95_pct: VaR95 as a fraction of portfolio value.
        concentration: HHI concentration risk.
        max_sector_pct: Highest sector exposure as fraction.

    Returns:
        Risk score string.
    """
    if var_95_pct > 0.05 or concentration > 0.5:
        return "CRITICAL"
    if var_95_pct > 0.03 or max_sector_pct > 0.40:
        return "HIGH"
    if var_95_pct > 0.015 or concentration > 0.3:
        return "MEDIUM"
    return "LOW"


def assess_portfolio_risk(
    positions: dict[str, Any],
    daily_returns: list[float],
    portfolio_value: float,
    benchmark_returns: list[float] | None = None,
    price_histories: dict[str, list[float]] | None = None,
    sector_map: dict[str, str] | None = None,
    max_sector_pct: float = 0.30,
) -> RiskReport:
    """Master risk assessment -- computes all portfolio-level metrics.

    This is the primary entry point. Computes VaR, CVaR, correlation,
    beta, sector exposure, concentration, and assigns a composite
    risk score.

    Args:
        positions: Dict of symbol -> Position.
        daily_returns: Portfolio-level daily returns (fractional).
        portfolio_value: Current total portfolio value in dollars.
        benchmark_returns: Daily benchmark returns for beta calculation.
            If None, beta defaults to 0.0.
        price_histories: Dict of symbol -> price history for correlation.
            If None, correlation matrix is empty.
        sector_map: Symbol -> sector mapping. Defaults to DEFAULT_SECTOR_MAP.
        max_sector_pct: Maximum sector exposure threshold (default 30%).

    Returns:
        Fully populated RiskReport.
    """
    # VaR and CVaR
    var_95 = compute_var(daily_returns, confidence=0.95, portfolio_value=portfolio_value)
    var_99 = compute_var(daily_returns, confidence=0.99, portfolio_value=portfolio_value)
    cvar_95 = compute_cvar(
        daily_returns, confidence=0.95, portfolio_value=portfolio_value
    )

    # Beta
    beta = 0.0
    if benchmark_returns:
        beta = compute_portfolio_beta(daily_returns, benchmark_returns)

    # Correlation matrix
    corr_matrix: dict[str, dict[str, float]] = {}
    if price_histories:
        corr_matrix = compute_correlation_matrix(price_histories)

    # Sector exposure
    sector_exposures = compute_sector_exposures(positions, sector_map)
    sector_warnings = check_sector_exposure(positions, sector_map, max_sector_pct)

    # Concentration
    concentration = compute_concentration_risk(positions)

    # Max single position percentage
    max_pos_pct = 0.0
    if positions and portfolio_value > 0:
        for pos in positions.values():
            price = getattr(pos, "current_price", 0.0) or getattr(
                pos, "entry_price", 0.0
            )
            qty = getattr(pos, "quantity", 0.0)
            pos_pct = (price * qty) / portfolio_value
            if pos_pct > max_pos_pct:
                max_pos_pct = pos_pct

    # Risk score classification
    var_95_pct = var_95 / portfolio_value if portfolio_value > 0 else 0.0
    max_sector = max(sector_exposures.values()) if sector_exposures else 0.0
    risk_score = _classify_risk_score(var_95_pct, concentration, max_sector)

    return RiskReport(
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        portfolio_beta=beta,
        correlation_matrix=corr_matrix,
        sector_exposures=sector_exposures,
        sector_warnings=sector_warnings,
        concentration_risk=concentration,
        max_single_position_pct=max_pos_pct,
        num_positions=len(positions),
        portfolio_value=portfolio_value,
        risk_score=risk_score,
    )


# ---------------------------------------------------------------------------
# Human-readable report formatting
# ---------------------------------------------------------------------------


def format_risk_report(report: RiskReport) -> str:
    """Format a RiskReport into a human-readable string.

    Args:
        report: A computed RiskReport.

    Returns:
        Multi-line formatted risk report.
    """
    lines = [
        "=" * 60,
        "PORTFOLIO RISK REPORT",
        "=" * 60,
        "",
        f"Risk Score: {report.risk_score}",
        f"Portfolio Value: ${report.portfolio_value:,.2f}",
        f"Open Positions: {report.num_positions}",
        "",
        "--- Value at Risk ---",
        f"  VaR 95%:  ${report.var_95:,.2f}  "
        f"({report.var_95 / report.portfolio_value:.2%} of portfolio)"
        if report.portfolio_value > 0
        else f"  VaR 95%:  ${report.var_95:,.2f}",
        f"  VaR 99%:  ${report.var_99:,.2f}  "
        f"({report.var_99 / report.portfolio_value:.2%} of portfolio)"
        if report.portfolio_value > 0
        else f"  VaR 99%:  ${report.var_99:,.2f}",
        f"  CVaR 95%: ${report.cvar_95:,.2f}  "
        f"({report.cvar_95 / report.portfolio_value:.2%} of portfolio)"
        if report.portfolio_value > 0
        else f"  CVaR 95%: ${report.cvar_95:,.2f}",
        "",
        "--- Portfolio Metrics ---",
        f"  Beta:              {report.portfolio_beta:.4f}",
        f"  Concentration HHI: {report.concentration_risk:.4f}",
        f"  Max Position:      {report.max_single_position_pct:.2%}",
    ]

    if report.sector_exposures:
        lines.append("")
        lines.append("--- Sector Exposure ---")
        for sector, pct in sorted(
            report.sector_exposures.items(), key=lambda x: -x[1]
        ):
            bar_len = int(pct * 40)
            bar = "#" * bar_len
            lines.append(f"  {sector:<25s} {pct:6.1%}  {bar}")

    if report.sector_warnings:
        lines.append("")
        lines.append("--- SECTOR WARNINGS ---")
        for warning in report.sector_warnings:
            lines.append(f"  [!] {warning}")

    if report.correlation_matrix:
        symbols = sorted(report.correlation_matrix.keys())
        if len(symbols) <= 10:
            lines.append("")
            lines.append("--- Correlation Matrix ---")
            # Header
            header = "         " + "  ".join(f"{s:>7s}" for s in symbols)
            lines.append(header)
            for sym_a in symbols:
                row_vals = []
                for sym_b in symbols:
                    val = report.correlation_matrix.get(sym_a, {}).get(sym_b, 0.0)
                    row_vals.append(f"{val:7.3f}")
                lines.append(f"  {sym_a:<6s} " + "  ".join(row_vals))
        else:
            lines.append("")
            lines.append(
                f"--- Correlation Matrix ({len(symbols)} symbols, "
                f"too large to display) ---"
            )
            # Show highest positive and negative correlations
            pairs: list[tuple[str, str, float]] = []
            for sym_a in symbols:
                for sym_b in symbols:
                    if sym_a < sym_b:
                        val = report.correlation_matrix.get(sym_a, {}).get(
                            sym_b, 0.0
                        )
                        pairs.append((sym_a, sym_b, val))
            if pairs:
                pairs.sort(key=lambda x: x[2])
                lines.append("  Most negative:")
                for a, b, v in pairs[:3]:
                    lines.append(f"    {a} / {b}: {v:.3f}")
                lines.append("  Most positive:")
                for a, b, v in pairs[-3:]:
                    lines.append(f"    {a} / {b}: {v:.3f}")

    # Risk score explanation
    lines.append("")
    lines.append("--- Risk Classification ---")
    var_pct = (
        report.var_95 / report.portfolio_value if report.portfolio_value > 0 else 0.0
    )
    lines.append(f"  VaR95 as % of portfolio: {var_pct:.2%}")
    lines.append(f"  Concentration (HHI):     {report.concentration_risk:.4f}")
    max_sec = max(report.sector_exposures.values()) if report.sector_exposures else 0.0
    lines.append(f"  Max sector exposure:     {max_sec:.1%}")

    thresholds = [
        "  Thresholds: CRITICAL (VaR>5% or HHI>0.5), "
        "HIGH (VaR>3% or sector>40%),",
        "              MEDIUM (VaR>1.5% or HHI>0.3), LOW (else)",
    ]
    lines.extend(thresholds)

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)
