"""Fama-MacBeth Cross-Sectional Regression.

Pass 1 (Time-Series): For each asset i, regress its return series on K factors:
    r_{i,t} = alpha_i + beta_{i,1}*F_{1,t} + ... + beta_{i,K}*F_{K,t} + eps_{i,t}
    This yields a (N x K) matrix of factor loadings (betas).

Pass 2 (Cross-Section): For each time period t, regress the cross-section
of returns on the estimated betas:
    r_{i,t} = lambda_{0,t} + lambda_{1,t}*beta_{i,1} + ... + lambda_{K,t}*beta_{i,K} + eta_{i,t}
    This yields a (T x K) matrix of risk premia (lambdas).

Result: The average lambda across time is the estimated risk premium.
Statistical significance is assessed with Newey-West t-statistics that
correct for serial correlation in the lambda series.

If |t-stat| < 2.0, the factor does not earn a significant premium.

Usage:
    from tools.quant.fama_macbeth import fama_macbeth
    result = fama_macbeth(returns_TxN, factors_TxK)
    print(result.lambda_means, result.t_stats)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
from numpy.typing import ArrayLike


@dataclass(frozen=True)
class FamaMacBethResult:
    """Results from Fama-MacBeth two-pass regression.

    Attributes:
        lambda_means: Mean risk premium for each factor (K,).
            Includes intercept as element 0 if include_intercept=True.
        lambda_stds: Standard deviation of lambda series (K,).
        t_stats: Newey-West corrected t-statistics (K,).
        r_squared_avg: Average cross-sectional R-squared across periods.
        n_assets: Number of assets (N).
        n_periods: Number of time periods (T).
        n_factors: Number of factors (K, excluding intercept).
        betas: First-pass beta estimates, shape (N, K+1) with intercept column.
        lambdas: Second-pass lambda series, shape (T, K+1) with intercept column.
    """

    lambda_means: np.ndarray
    lambda_stds: np.ndarray
    t_stats: np.ndarray
    r_squared_avg: float
    n_assets: int
    n_periods: int
    n_factors: int
    betas: np.ndarray
    lambdas: np.ndarray

    def __str__(self) -> str:
        lines = [
            f"Fama-MacBeth Results ({self.n_assets} assets, {self.n_periods} periods, {self.n_factors} factors)",
            f"  Avg cross-sectional R^2: {self.r_squared_avg:.4f}",
            "",
            f"  {'Factor':<12} {'Lambda':>10} {'Std':>10} {'t-stat':>10} {'Sig?':>6}",
            f"  {'-'*12} {'-'*10} {'-'*10} {'-'*10} {'-'*6}",
        ]
        labels = ["Intercept"] + [f"Factor_{i}" for i in range(1, self.n_factors + 1)]
        for i, label in enumerate(labels):
            sig = "***" if abs(self.t_stats[i]) > 2.576 else (
                "**" if abs(self.t_stats[i]) > 1.96 else (
                    "*" if abs(self.t_stats[i]) > 1.645 else ""
                )
            )
            lines.append(
                f"  {label:<12} {self.lambda_means[i]:>10.6f} "
                f"{self.lambda_stds[i]:>10.6f} {self.t_stats[i]:>10.3f} {sig:>6}"
            )
        return "\n".join(lines)


def _ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    """Ordinary least squares via normal equations.

    Solves beta = (X'X)^{-1} X'y using numpy's lstsq for numerical stability.

    Args:
        y: Dependent variable, shape (n,).
        X: Design matrix, shape (n, k).

    Returns:
        Coefficient vector, shape (k,).
    """
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def _r_squared(y: np.ndarray, X: np.ndarray, beta: np.ndarray) -> float:
    """Compute R-squared for a fitted regression.

    R^2 = 1 - SS_res / SS_tot

    Args:
        y: Observed values.
        X: Design matrix.
        beta: Fitted coefficients.

    Returns:
        R-squared value, clipped to [0, 1].
    """
    y_hat = X @ beta
    ss_res = float(np.sum((y - y_hat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    if ss_tot < 1e-15:
        return 0.0
    return max(0.0, min(1.0, 1.0 - ss_res / ss_tot))


def _newey_west_se(
    series: np.ndarray,
    n_lags: Optional[int] = None,
) -> np.ndarray:
    """Newey-West HAC standard errors for a time series of estimates.

    Corrects for heteroskedasticity and autocorrelation in the lambda
    series. The bandwidth defaults to floor(4 * (T/100)^{2/9}).

    The HAC variance estimator for the mean of a stationary series x_t is:
        V = gamma_0 + 2 * sum_{j=1}^{L} (1 - j/(L+1)) * gamma_j
    where gamma_j = (1/T) * sum_{t=j+1}^{T} (x_t - x_bar)(x_{t-j} - x_bar).

    The Bartlett kernel weight (1 - j/(L+1)) ensures positive semi-definiteness.

    Args:
        series: Array of shape (T,) or (T, K) -- a time series of estimates.
        n_lags: Number of lags for HAC correction. None = automatic bandwidth.

    Returns:
        Standard errors, shape (K,) or scalar.
    """
    if series.ndim == 1:
        series = series[:, np.newaxis]

    T, K = series.shape

    if n_lags is None:
        n_lags = int(np.floor(4.0 * (T / 100.0) ** (2.0 / 9.0)))
    n_lags = max(0, min(n_lags, T - 1))

    means = np.mean(series, axis=0)
    demeaned = series - means

    # Gamma_0: variance
    gamma_0 = np.sum(demeaned**2, axis=0) / T

    # Autocovariance terms with Bartlett kernel
    correction = np.zeros(K, dtype=np.float64)
    for j in range(1, n_lags + 1):
        weight = 1.0 - j / (n_lags + 1.0)
        gamma_j = np.sum(demeaned[j:] * demeaned[:-j], axis=0) / T
        correction += 2.0 * weight * gamma_j

    variance = (gamma_0 + correction) / T
    # Guard against negative variance from finite-sample issues
    variance = np.maximum(variance, 1e-20)
    return np.sqrt(variance)


def fama_macbeth(
    returns: ArrayLike,
    factors: ArrayLike,
    n_lags: Optional[int] = None,
) -> FamaMacBethResult:
    """Run Fama-MacBeth two-pass cross-sectional regression.

    Args:
        returns: Asset returns, shape (T, N). T time periods, N assets.
        factors: Factor returns, shape (T, K). T periods, K factors.
        n_lags: Newey-West lag count. None = automatic bandwidth selection.

    Returns:
        FamaMacBethResult with risk premia estimates and Newey-West t-stats.

    Raises:
        ValueError: If dimensions are inconsistent or too few observations.
    """
    R = np.asarray(returns, dtype=np.float64)
    F = np.asarray(factors, dtype=np.float64)

    if R.ndim != 2:
        raise ValueError(f"returns must be 2-D (T, N), got shape {R.shape}")
    if F.ndim == 1:
        F = F[:, np.newaxis]
    if F.ndim != 2:
        raise ValueError(f"factors must be 2-D (T, K), got shape {F.shape}")

    T, N = R.shape
    T_f, K = F.shape

    if T != T_f:
        raise ValueError(
            f"returns has {T} periods but factors has {T_f} periods"
        )
    if T < K + 2:
        raise ValueError(
            f"Need T >= K+2 for first-pass regression. T={T}, K={K}"
        )
    if N < K + 2:
        raise ValueError(
            f"Need N >= K+2 for second-pass regression. N={N}, K={K}"
        )

    # ---- Pass 1: Time-series regressions ----
    # For each asset, regress returns on factors to get betas.
    # Design matrix includes intercept.
    F_with_intercept = np.column_stack([np.ones(T), F])  # (T, K+1)
    betas = np.zeros((N, K + 1), dtype=np.float64)

    for i in range(N):
        betas[i] = _ols(R[:, i], F_with_intercept)

    # ---- Pass 2: Cross-sectional regressions ----
    # For each time period, regress returns on betas.
    # Use full betas (intercept + factor betas) as regressors.
    lambdas = np.zeros((T, K + 1), dtype=np.float64)
    r_squareds = np.zeros(T, dtype=np.float64)

    for t in range(T):
        lam = _ols(R[t, :], betas)
        lambdas[t] = lam
        r_squareds[t] = _r_squared(R[t, :], betas, lam)

    # ---- Statistics ----
    lambda_means = np.mean(lambdas, axis=0)
    lambda_stds = np.std(lambdas, axis=0, ddof=1)
    nw_se = _newey_west_se(lambdas, n_lags=n_lags)

    # t-stat = mean / NW_se
    t_stats = lambda_means / nw_se

    return FamaMacBethResult(
        lambda_means=lambda_means,
        lambda_stds=lambda_stds,
        t_stats=t_stats,
        r_squared_avg=float(np.mean(r_squareds)),
        n_assets=N,
        n_periods=T,
        n_factors=K,
        betas=betas,
        lambdas=lambdas,
    )
