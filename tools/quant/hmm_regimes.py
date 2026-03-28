"""Hidden Markov Model -- Market Regime Detection.

Fits a Gaussian HMM to return series. States are automatically
labeled by mean return: bear (lowest mean), neutral, bull (highest mean).

The HMM models returns as emissions from a latent Markov chain:
    P(r_t | state_t = k) = N(mu_k, sigma_k^2)
    P(state_t = k | state_{t-1} = j) = A_{j,k}

Inference via Baum-Welch (EM) yields:
    - Transition matrix A
    - Emission means mu_k and stds sigma_k
    - Most likely state sequence (Viterbi decoding)

Uses hmmlearn.GaussianHMM if available. Falls back to a simple
threshold-based detector (mean +/- 0.5*std boundaries) if not.

Usage:
    from tools.quant.hmm_regimes import fit_regimes, RegimeResult
    result = fit_regimes(returns, n_states=3)
    print(result.current_regime)  # 'bull', 'bear', or 'neutral'
    print(result.regime_history)  # array of regime labels per period
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import List, Optional

import numpy as np
from numpy.typing import ArrayLike

# Labels assigned by sorting states on mean return
_REGIME_LABELS_3 = ["bear", "neutral", "bull"]
_REGIME_LABELS_2 = ["bear", "bull"]


def _assign_labels(n_states: int, state_means: np.ndarray) -> List[str]:
    """Assign human-readable labels by sorting states on mean.

    For n_states=3: bear, neutral, bull (ascending mean).
    For n_states=2: bear, bull.
    For n_states>3: bear, state_1, ..., state_{n-2}, bull.

    Args:
        n_states: Number of HMM states.
        state_means: Mean return per state, shape (n_states,).

    Returns:
        List of string labels ordered by original state index.
    """
    order = np.argsort(state_means)
    labels = [""] * n_states

    if n_states == 2:
        base = _REGIME_LABELS_2
    elif n_states == 3:
        base = _REGIME_LABELS_3
    else:
        base = (
            ["bear"]
            + [f"state_{i}" for i in range(1, n_states - 1)]
            + ["bull"]
        )

    for rank, state_idx in enumerate(order):
        labels[state_idx] = base[rank]

    return labels


@dataclass(frozen=True)
class RegimeResult:
    """Result of HMM regime fitting.

    Attributes:
        regime_history: Array of string labels per period, shape (T,).
        state_sequence: Array of integer state indices per period, shape (T,).
        transition_matrix: State transition probability matrix, shape (K, K).
        state_means: Mean return per state, shape (K,).
        state_stds: Std dev of return per state, shape (K,).
        state_labels: Human-readable label per state index.
        current_regime: Label of the final period's regime.
        method: 'hmmlearn' or 'threshold' indicating which backend was used.
    """

    regime_history: np.ndarray
    state_sequence: np.ndarray
    transition_matrix: np.ndarray
    state_means: np.ndarray
    state_stds: np.ndarray
    state_labels: List[str]
    current_regime: str
    method: str

    def __str__(self) -> str:
        lines = [
            f"RegimeResult (method={self.method}, {len(self.state_labels)} states, T={len(self.regime_history)})",
            f"  Current regime: {self.current_regime}",
            "",
        ]
        for i, label in enumerate(self.state_labels):
            count = int(np.sum(self.state_sequence == i))
            pct = 100.0 * count / len(self.state_sequence) if len(self.state_sequence) > 0 else 0.0
            lines.append(
                f"  {label:<10}: mean={self.state_means[i]:+.6f}, "
                f"std={self.state_stds[i]:.6f}, count={count} ({pct:.1f}%)"
            )
        lines.append("")
        lines.append("  Transition matrix:")
        for i, label in enumerate(self.state_labels):
            row = "  ".join(f"{self.transition_matrix[i, j]:.3f}" for j in range(len(self.state_labels)))
            lines.append(f"    {label:<10}: [{row}]")
        return "\n".join(lines)


def _fit_hmmlearn(
    returns: np.ndarray,
    n_states: int,
    n_iter: int,
    random_state: Optional[int],
) -> RegimeResult:
    """Fit Gaussian HMM using hmmlearn.

    Args:
        returns: 1-D return array, shape (T,).
        n_states: Number of hidden states.
        n_iter: Maximum EM iterations.
        random_state: Random seed for reproducibility.

    Returns:
        RegimeResult with full HMM outputs.
    """
    from hmmlearn.hmm import GaussianHMM

    X = returns.reshape(-1, 1)

    best_model = None
    best_score = -np.inf

    # Run multiple initializations to avoid local optima.
    # Attempt 0: spread means evenly across data range.
    # Attempts 1+: random initialization with different seeds.
    n_attempts = 5

    for attempt in range(n_attempts):
        model = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=n_iter,
            random_state=(random_state + attempt) if random_state is not None else attempt,
        )

        if attempt == 0:
            # Evenly spaced initial means across the data range
            data_min, data_max = float(np.min(returns)), float(np.max(returns))
            model.means_ = np.linspace(data_min, data_max, n_states + 2)[1:-1].reshape(-1, 1)
            model.init_params = "stc"
        # else: let hmmlearn initialize randomly via init_params="stmc" (default)

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                model.fit(X)
                score = model.score(X)
                if score > best_score:
                    best_score = score
                    best_model = model
            except Exception:
                continue

    if best_model is None:
        raise RuntimeError("HMM fitting failed across all initialization attempts")

    state_sequence = best_model.predict(X)
    state_means = best_model.means_.ravel()
    # For diag covariance, covars_ is shape (n_states, n_features)
    state_stds = np.sqrt(best_model.covars_.ravel())
    transition_matrix = best_model.transmat_

    labels = _assign_labels(n_states, state_means)
    regime_history = np.array([labels[s] for s in state_sequence])

    return RegimeResult(
        regime_history=regime_history,
        state_sequence=state_sequence,
        transition_matrix=transition_matrix,
        state_means=state_means,
        state_stds=state_stds,
        state_labels=labels,
        current_regime=labels[state_sequence[-1]],
        method="hmmlearn",
    )


def _fit_threshold(
    returns: np.ndarray,
    n_states: int,
) -> RegimeResult:
    """Threshold-based regime detection fallback.

    Assigns regimes based on rolling z-score boundaries. For 3 states,
    boundaries are at mean +/- 0.5*std of the return series.

    This is a crude approximation when hmmlearn is unavailable. It does
    not model state persistence or transition probabilities from data;
    the transition matrix is estimated empirically from the assigned
    sequence.

    Args:
        returns: 1-D return array, shape (T,).
        n_states: Number of regimes (only 2 or 3 are well-supported).

    Returns:
        RegimeResult with threshold-based assignments.
    """
    mu = float(np.mean(returns))
    sigma = float(np.std(returns, ddof=1))

    if n_states == 2:
        boundaries = [mu]
    elif n_states == 3:
        boundaries = [mu - 0.5 * sigma, mu + 0.5 * sigma]
    else:
        # Evenly spaced quantile boundaries
        quantiles = np.linspace(0, 100, n_states + 1)[1:-1]
        boundaries = list(np.percentile(returns, quantiles))

    state_sequence = np.zeros(len(returns), dtype=int)
    for b in boundaries:
        state_sequence += (returns > b).astype(int)

    # Compute per-state statistics
    state_means = np.zeros(n_states)
    state_stds = np.zeros(n_states)
    for k in range(n_states):
        mask = state_sequence == k
        if np.any(mask):
            state_means[k] = np.mean(returns[mask])
            state_stds[k] = np.std(returns[mask], ddof=1) if np.sum(mask) > 1 else 0.0

    # Empirical transition matrix
    transition_matrix = np.zeros((n_states, n_states), dtype=np.float64)
    for t in range(len(state_sequence) - 1):
        transition_matrix[state_sequence[t], state_sequence[t + 1]] += 1.0
    row_sums = transition_matrix.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums == 0, 1.0, row_sums)
    transition_matrix /= row_sums

    labels = _assign_labels(n_states, state_means)
    regime_history = np.array([labels[s] for s in state_sequence])

    return RegimeResult(
        regime_history=regime_history,
        state_sequence=state_sequence,
        transition_matrix=transition_matrix,
        state_means=state_means,
        state_stds=state_stds,
        state_labels=labels,
        current_regime=labels[state_sequence[-1]],
        method="threshold",
    )


def fit_regimes(
    returns: ArrayLike,
    n_states: int = 3,
    n_iter: int = 100,
    random_state: Optional[int] = 42,
    force_threshold: bool = False,
) -> RegimeResult:
    """Detect market regimes from a return series.

    Fits a Gaussian Hidden Markov Model with ``n_states`` states.
    States are automatically labeled by ascending mean return.

    Args:
        returns: 1-D array-like of period returns (e.g. daily log returns).
        n_states: Number of hidden states (default 3: bear/neutral/bull).
        n_iter: Maximum EM iterations for hmmlearn (ignored for threshold).
        random_state: Random seed for hmmlearn reproducibility.
        force_threshold: If True, skip hmmlearn and use threshold fallback.

    Returns:
        RegimeResult with regime assignments and transition dynamics.

    Raises:
        ValueError: If fewer than 10 observations or n_states < 2.
    """
    r = np.asarray(returns, dtype=np.float64).ravel()
    if r.shape[0] < 10:
        raise ValueError(f"Need >= 10 observations, got {r.shape[0]}")
    if n_states < 2:
        raise ValueError(f"n_states must be >= 2, got {n_states}")

    if force_threshold:
        return _fit_threshold(r, n_states)

    try:
        return _fit_hmmlearn(r, n_states, n_iter, random_state)
    except ImportError:
        warnings.warn(
            "hmmlearn not installed. Falling back to threshold-based regime detection. "
            "Install with: pip install hmmlearn",
            stacklevel=2,
        )
        return _fit_threshold(r, n_states)
