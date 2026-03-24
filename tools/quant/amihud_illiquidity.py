"""Amihud Illiquidity Ratio.

Measures price impact per unit of trading volume:

    ILLIQ_t = |r_t| / volume_t

The aggregate ratio over a window:

    ILLIQ = (1/T) * sum_{t=1}^{T} (|r_t| / volume_t) * 10^6

High ILLIQ = illiquid (large price moves per unit volume).
Low ILLIQ = liquid (volume absorbs price impact).

Most backtests ignore liquidity and fail live. Amihud's ratio
is the standard academic measure (Amihud 2002, JFM) and requires
only returns and volume -- no bid-ask spread data needed.

Usage:
    from tools.quant.amihud_illiquidity import amihud_ratio, flag_illiquid
    ratio = amihud_ratio(returns, volumes, window=20)
    illiquid_mask = flag_illiquid(returns, volumes, threshold_pct=90)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import ArrayLike


def _validate_inputs(
    returns: ArrayLike,
    volumes: ArrayLike,
) -> tuple[np.ndarray, np.ndarray]:
    """Validate and align returns and volumes arrays.

    Args:
        returns: Array-like of asset returns.
        volumes: Array-like of trading volumes (must be positive).

    Returns:
        Tuple of (returns, volumes) as 1-D float64 arrays.

    Raises:
        ValueError: If arrays have different lengths or volumes are non-positive.
    """
    r = np.asarray(returns, dtype=np.float64).ravel()
    v = np.asarray(volumes, dtype=np.float64).ravel()

    if r.shape[0] != v.shape[0]:
        raise ValueError(
            f"returns length ({r.shape[0]}) != volumes length ({v.shape[0]})"
        )
    if r.shape[0] == 0:
        raise ValueError("Empty arrays provided")
    if np.any(v <= 0):
        raise ValueError("All volumes must be strictly positive")

    return r, v


def amihud_ratio(
    returns: ArrayLike,
    volumes: ArrayLike,
    window: Optional[int] = None,
    scale: float = 1e6,
) -> float:
    """Compute Amihud illiquidity ratio over a window.

    ILLIQ = (scale / T) * sum_{t=1}^{T} |r_t| / volume_t

    The default scale factor of 10^6 follows the convention from
    Amihud (2002) to produce human-readable numbers.

    Args:
        returns: Array-like of period returns.
        volumes: Array-like of trading volumes (shares or dollars).
        window: Number of most recent periods to use. None = all data.
        scale: Multiplier for readability (default 1e6).

    Returns:
        Scalar illiquidity ratio (higher = less liquid).

    Raises:
        ValueError: If inputs are invalid or window exceeds data length.
    """
    r, v = _validate_inputs(returns, volumes)

    if window is not None:
        if window < 1:
            raise ValueError(f"window must be >= 1, got {window}")
        if window > r.shape[0]:
            raise ValueError(
                f"window ({window}) exceeds data length ({r.shape[0]})"
            )
        r = r[-window:]
        v = v[-window:]

    daily_illiq = np.abs(r) / v
    return float(scale * np.mean(daily_illiq))


def rolling_amihud(
    returns: ArrayLike,
    volumes: ArrayLike,
    window: int = 20,
    scale: float = 1e6,
) -> np.ndarray:
    """Compute rolling Amihud illiquidity ratio.

    For each period t, computes the Amihud ratio over the trailing
    ``window`` periods [t-window+1, t]. The first (window-1) values
    are NaN (insufficient history).

    Args:
        returns: Array-like of period returns.
        volumes: Array-like of trading volumes.
        window: Rolling window size (default 20 = ~1 month of trading days).
        scale: Multiplier (default 1e6).

    Returns:
        Array of rolling Amihud ratios, shape (T,). Leading NaN values
        where insufficient history exists.
    """
    r, v = _validate_inputs(returns, volumes)

    if window < 1:
        raise ValueError(f"window must be >= 1, got {window}")

    T = r.shape[0]
    daily_illiq = np.abs(r) / v
    result = np.full(T, np.nan, dtype=np.float64)

    # Efficient rolling mean via cumulative sum
    if T >= window:
        cumsum = np.cumsum(daily_illiq)
        result[window - 1] = cumsum[window - 1] / window
        for t in range(window, T):
            result[t] = (cumsum[t] - cumsum[t - window]) / window

    result *= scale
    return result


def flag_illiquid(
    returns: ArrayLike,
    volumes: ArrayLike,
    window: int = 20,
    threshold_pct: float = 90.0,
    scale: float = 1e6,
) -> np.ndarray:
    """Flag periods with abnormally high illiquidity.

    Computes rolling Amihud ratio and flags periods where it exceeds
    the ``threshold_pct`` percentile of the full rolling series.

    Args:
        returns: Array-like of period returns.
        volumes: Array-like of trading volumes.
        window: Rolling window for Amihud ratio (default 20).
        threshold_pct: Percentile above which periods are flagged (default 90).
        scale: Multiplier (default 1e6).

    Returns:
        Boolean array, shape (T,). True = illiquid period.
    """
    if not 0.0 < threshold_pct < 100.0:
        raise ValueError(f"threshold_pct must be in (0, 100), got {threshold_pct}")

    rolling = rolling_amihud(returns, volumes, window=window, scale=scale)
    valid = rolling[~np.isnan(rolling)]

    if valid.size == 0:
        return np.zeros(rolling.shape[0], dtype=bool)

    threshold = float(np.percentile(valid, threshold_pct))
    return ~np.isnan(rolling) & (rolling > threshold)


@dataclass(frozen=True)
class AmihudSummary:
    """Summary statistics for Amihud illiquidity analysis.

    Attributes:
        overall_ratio: Full-sample Amihud ratio.
        mean_rolling: Mean of rolling Amihud series (excluding NaN).
        median_rolling: Median of rolling Amihud series.
        p90_rolling: 90th percentile of rolling series.
        p99_rolling: 99th percentile of rolling series.
        pct_illiquid: Percentage of periods flagged as illiquid.
        n_periods: Total number of periods.
        window: Rolling window used.
    """

    overall_ratio: float
    mean_rolling: float
    median_rolling: float
    p90_rolling: float
    p99_rolling: float
    pct_illiquid: float
    n_periods: int
    window: int

    def __str__(self) -> str:
        return (
            f"Amihud Illiquidity Summary (n={self.n_periods}, window={self.window})\n"
            f"  Overall ratio:    {self.overall_ratio:.4f}\n"
            f"  Rolling mean:     {self.mean_rolling:.4f}\n"
            f"  Rolling median:   {self.median_rolling:.4f}\n"
            f"  Rolling P90:      {self.p90_rolling:.4f}\n"
            f"  Rolling P99:      {self.p99_rolling:.4f}\n"
            f"  % illiquid (>P90): {self.pct_illiquid:.1f}%"
        )


def summarize(
    returns: ArrayLike,
    volumes: ArrayLike,
    window: int = 20,
    scale: float = 1e6,
) -> AmihudSummary:
    """Produce summary statistics for Amihud illiquidity analysis.

    Args:
        returns: Array-like of period returns.
        volumes: Array-like of trading volumes.
        window: Rolling window size.
        scale: Multiplier.

    Returns:
        AmihudSummary dataclass.
    """
    r, v = _validate_inputs(returns, volumes)
    rolling = rolling_amihud(r, v, window=window, scale=scale)
    valid = rolling[~np.isnan(rolling)]
    illiquid_mask = flag_illiquid(r, v, window=window, scale=scale)

    if valid.size == 0:
        return AmihudSummary(
            overall_ratio=amihud_ratio(r, v, scale=scale),
            mean_rolling=0.0,
            median_rolling=0.0,
            p90_rolling=0.0,
            p99_rolling=0.0,
            pct_illiquid=0.0,
            n_periods=r.shape[0],
            window=window,
        )

    return AmihudSummary(
        overall_ratio=amihud_ratio(r, v, scale=scale),
        mean_rolling=float(np.mean(valid)),
        median_rolling=float(np.median(valid)),
        p90_rolling=float(np.percentile(valid, 90)),
        p99_rolling=float(np.percentile(valid, 99)),
        pct_illiquid=float(100.0 * np.sum(illiquid_mask) / r.shape[0]),
        n_periods=r.shape[0],
        window=window,
    )
