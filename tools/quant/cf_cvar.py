"""Cornish-Fisher Conditional Value at Risk.

Standard VaR assumes normal returns. Real returns have fat tails.
Cornish-Fisher expansion adjusts quantiles using skewness (S) and
excess kurtosis (K):

    z_cf = z + (z^2 - 1)*S/6 + (z^3 - 3z)*K/24 - (2z^3 - 5z)*S^2/36

CVaR (Expected Shortfall) = mean of returns below CF-adjusted VaR.

Usage:
    from tools.quant.cf_cvar import cornish_fisher_var, cornish_fisher_cvar
    var = cornish_fisher_var(returns, confidence=0.99)
    cvar = cornish_fisher_cvar(returns, confidence=0.99)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike
from scipy import stats


def _validate_returns(returns: ArrayLike) -> np.ndarray:
    """Convert input to 1-D float64 array and validate.

    Args:
        returns: Array-like of asset returns.

    Returns:
        Cleaned 1-D numpy array.

    Raises:
        ValueError: If fewer than 4 observations (need skew + kurtosis).
    """
    arr = np.asarray(returns, dtype=np.float64).ravel()
    if arr.shape[0] < 4:
        raise ValueError(
            f"Need >= 4 observations for Cornish-Fisher expansion, got {arr.shape[0]}"
        )
    return arr


def _cornish_fisher_z(confidence: float, skew: float, excess_kurt: float) -> float:
    """Compute Cornish-Fisher adjusted z-score.

    The expansion corrects the Gaussian quantile for non-normality:

        z_cf = z + (z^2 - 1) * S / 6
                 + (z^3 - 3z) * K / 24
                 - (2z^3 - 5z) * S^2 / 36

    where z = Phi^{-1}(1 - confidence), S = skewness, K = excess kurtosis.

    Args:
        confidence: VaR confidence level (e.g. 0.95 or 0.99).
        skew: Sample skewness.
        excess_kurt: Sample excess kurtosis (Fisher definition, normal = 0).

    Returns:
        Cornish-Fisher adjusted z-score (negative for losses).
    """
    z = stats.norm.ppf(1.0 - confidence)
    z2 = z * z
    z3 = z2 * z

    z_cf = (
        z
        + (z2 - 1.0) * skew / 6.0
        + (z3 - 3.0 * z) * excess_kurt / 24.0
        - (2.0 * z3 - 5.0 * z) * skew**2 / 36.0
    )
    return float(z_cf)


def cornish_fisher_var(
    returns: ArrayLike,
    confidence: float = 0.99,
) -> float:
    """Cornish-Fisher adjusted Value at Risk.

    VaR_CF = -(mu + sigma * z_cf)

    where z_cf is the Cornish-Fisher adjusted quantile incorporating
    skewness and excess kurtosis of the return distribution.

    Positive VaR means a loss (sign convention: VaR > 0 is bad).

    Args:
        returns: Array-like of period returns (e.g. daily log returns).
        confidence: Confidence level, default 0.99 (99th percentile).

    Returns:
        Cornish-Fisher VaR as a positive number representing loss.

    Raises:
        ValueError: If confidence not in (0, 1) or too few observations.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    r = _validate_returns(returns)
    mu = float(np.mean(r))
    sigma = float(np.std(r, ddof=1))
    skew = float(stats.skew(r, bias=False))
    excess_kurt = float(stats.kurtosis(r, bias=False))  # Fisher = excess

    z_cf = _cornish_fisher_z(confidence, skew, excess_kurt)
    var = -(mu + sigma * z_cf)
    return var


def cornish_fisher_cvar(
    returns: ArrayLike,
    confidence: float = 0.99,
) -> float:
    """Cornish-Fisher adjusted Conditional Value at Risk (Expected Shortfall).

    CVaR = mean of all returns that fall below the CF-adjusted VaR threshold.
    Returned as a positive number (loss magnitude).

    If no observations fall below the CF-VaR threshold (possible for small
    samples or low confidence), falls back to the single worst return.

    Args:
        returns: Array-like of period returns.
        confidence: Confidence level, default 0.99.

    Returns:
        Cornish-Fisher CVaR as a positive number.

    Raises:
        ValueError: If confidence not in (0, 1) or too few observations.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")

    r = _validate_returns(returns)
    var = cornish_fisher_var(r, confidence)
    threshold = -var  # VaR is positive loss; threshold is the negative return level
    tail = r[r <= threshold]

    if tail.size == 0:
        # No observations in the tail -- use the worst observation
        return float(-np.min(r))

    return float(-np.mean(tail))


def normal_var(returns: ArrayLike, confidence: float = 0.99) -> float:
    """Standard parametric (Gaussian) VaR.

    VaR_normal = -(mu + sigma * z)

    where z = Phi^{-1}(1 - confidence).

    Args:
        returns: Array-like of period returns.
        confidence: Confidence level.

    Returns:
        Normal VaR as a positive number.
    """
    r = _validate_returns(returns)
    mu = float(np.mean(r))
    sigma = float(np.std(r, ddof=1))
    z = stats.norm.ppf(1.0 - confidence)
    return float(-(mu + sigma * z))


def historical_var(returns: ArrayLike, confidence: float = 0.99) -> float:
    """Historical (empirical quantile) VaR.

    Simply the (1 - confidence) percentile of the return distribution.

    Args:
        returns: Array-like of period returns.
        confidence: Confidence level.

    Returns:
        Historical VaR as a positive number.
    """
    r = _validate_returns(returns)
    quantile = np.percentile(r, (1.0 - confidence) * 100.0)
    return float(-quantile)


@dataclass(frozen=True)
class VarComparison:
    """Side-by-side VaR/CVaR comparison across methods.

    Attributes:
        confidence: The confidence level used.
        n_obs: Number of observations.
        skewness: Sample skewness.
        excess_kurtosis: Sample excess kurtosis.
        normal_var: Gaussian parametric VaR.
        historical_var: Empirical quantile VaR.
        cf_var: Cornish-Fisher adjusted VaR.
        cf_cvar: Cornish-Fisher adjusted CVaR (Expected Shortfall).
    """

    confidence: float
    n_obs: int
    skewness: float
    excess_kurtosis: float
    normal_var: float
    historical_var: float
    cf_var: float
    cf_cvar: float

    def __str__(self) -> str:
        lines = [
            f"VaR Comparison (confidence={self.confidence:.2%}, n={self.n_obs})",
            f"  Skewness:        {self.skewness:+.4f}",
            f"  Excess Kurtosis: {self.excess_kurtosis:+.4f}",
            f"  Normal VaR:      {self.normal_var:.6f}",
            f"  Historical VaR:  {self.historical_var:.6f}",
            f"  CF VaR:          {self.cf_var:.6f}",
            f"  CF CVaR:         {self.cf_cvar:.6f}",
        ]
        return "\n".join(lines)


def compare_var_methods(
    returns: ArrayLike,
    confidence: float = 0.99,
) -> VarComparison:
    """Compare Normal, Historical, and Cornish-Fisher VaR side by side.

    Useful for seeing how much fat tails inflate risk relative to
    the Gaussian assumption.

    Args:
        returns: Array-like of period returns.
        confidence: Confidence level, default 0.99.

    Returns:
        VarComparison dataclass with all three methods plus CF-CVaR.
    """
    r = _validate_returns(returns)
    return VarComparison(
        confidence=confidence,
        n_obs=r.shape[0],
        skewness=float(stats.skew(r, bias=False)),
        excess_kurtosis=float(stats.kurtosis(r, bias=False)),
        normal_var=normal_var(r, confidence),
        historical_var=historical_var(r, confidence),
        cf_var=cornish_fisher_var(r, confidence),
        cf_cvar=cornish_fisher_cvar(r, confidence),
    )
