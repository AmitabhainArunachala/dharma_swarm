"""Ginko Regime Detection — HMM-based market regime classification + GARCH volatility.

Detects three regimes:
  - BULL: positive momentum, low volatility
  - BEAR: negative momentum, high volatility
  - SIDEWAYS: low momentum, moderate volatility

Uses hmmlearn for Hidden Markov Model state detection and
arch for GARCH(1,1) volatility forecasting.

Falls back to rule-based classification when libraries unavailable.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

GINKO_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko"
REGIME_DIR = GINKO_DIR / "regime"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MarketRegime(str, Enum):
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    UNKNOWN = "unknown"


@dataclass
class RegimeDetection:
    """Result of regime detection analysis."""
    regime: str
    confidence: float
    volatility_forecast: float | None
    volatility_current: float | None
    indicators: dict[str, float]
    method: str  # "hmm", "garch", "rule_based"
    timestamp: str


@dataclass
class ReturnSeries:
    """Time series of returns for regime analysis."""
    values: list[float]
    timestamps: list[str]
    symbol: str = "SPY"

    @property
    def array(self) -> np.ndarray:
        return np.array(self.values)

    @property
    def mean(self) -> float:
        return float(np.mean(self.values)) if self.values else 0.0

    @property
    def std(self) -> float:
        return float(np.std(self.values)) if self.values else 0.0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# HMM REGIME DETECTION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def detect_regime_hmm(
    returns: ReturnSeries,
    n_states: int = 3,
    n_iter: int = 100,
) -> RegimeDetection:
    """Detect market regime using Gaussian HMM.

    Fits a 3-state Hidden Markov Model to return data and classifies
    the current state based on the most recent observation.

    Args:
        returns: Historical return series (daily log returns).
        n_states: Number of hidden states (default 3: bull/bear/sideways).
        n_iter: Maximum EM iterations.

    Returns:
        RegimeDetection with regime label and confidence.
    """
    try:
        from hmmlearn.hmm import GaussianHMM
    except ImportError:
        logger.warning("hmmlearn not installed — falling back to rule-based")
        return detect_regime_rules(returns)

    if len(returns.values) < 30:
        logger.warning("Insufficient data for HMM (%d points) — using rules", len(returns.values))
        return detect_regime_rules(returns)

    X = returns.array.reshape(-1, 1)

    try:
        model = GaussianHMM(
            n_components=n_states,
            covariance_type="full",
            n_iter=n_iter,
            random_state=42,
        )
        model.fit(X)

        # Get state sequence
        states = model.predict(X)
        current_state = int(states[-1])

        # Compute state probabilities for current observation
        state_probs = model.predict_proba(X[-1:].reshape(1, -1))[0]
        confidence = float(state_probs[current_state])

        # Classify states by mean return: highest = bull, lowest = bear
        means = model.means_.flatten()
        variances = np.array([model.covars_[i][0][0] for i in range(n_states)])

        state_order = np.argsort(means)
        regime_map = {
            int(state_order[0]): MarketRegime.BEAR,
            int(state_order[-1]): MarketRegime.BULL,
        }
        for i in state_order[1:-1]:
            regime_map[int(i)] = MarketRegime.SIDEWAYS

        regime = regime_map.get(current_state, MarketRegime.UNKNOWN)

        return RegimeDetection(
            regime=regime.value,
            confidence=confidence,
            volatility_forecast=float(np.sqrt(variances[current_state]) * np.sqrt(252)),
            volatility_current=float(returns.std * np.sqrt(252)),
            indicators={
                "state_mean": float(means[current_state]),
                "state_variance": float(variances[current_state]),
                "n_states_detected": n_states,
                "log_likelihood": float(model.score(X)),
            },
            method="hmm",
            timestamp=_utc_now().isoformat(),
        )
    except Exception as e:
        logger.error("HMM regime detection failed: %s", e)
        return detect_regime_rules(returns)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# GARCH VOLATILITY FORECASTING
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def forecast_volatility_garch(
    returns: ReturnSeries,
    horizon: int = 5,
) -> tuple[float | None, dict[str, Any]]:
    """Forecast volatility using GARCH(1,1) model.

    Args:
        returns: Daily return series (percentage, not log).
        horizon: Forecast horizon in days.

    Returns:
        Tuple of (annualized vol forecast, model info dict).
    """
    try:
        from arch import arch_model
    except ImportError:
        logger.warning("arch package not installed — skipping GARCH")
        return None, {"error": "arch not installed"}

    if len(returns.values) < 50:
        return None, {"error": f"insufficient data ({len(returns.values)} < 50)"}

    try:
        # Scale returns to percentage
        scaled = returns.array * 100

        am = arch_model(scaled, vol="Garch", p=1, q=1, dist="normal")
        res = am.fit(disp="off")

        # Forecast
        forecasts = res.forecast(horizon=horizon)
        variance_forecast = forecasts.variance.values[-1, :]

        # Annualize: sqrt(252) * mean daily vol
        mean_daily_var = float(np.mean(variance_forecast))
        annualized_vol = float(np.sqrt(mean_daily_var) * np.sqrt(252) / 100)

        info = {
            "omega": float(res.params.get("omega", 0)),
            "alpha": float(res.params.get("alpha[1]", 0)),
            "beta": float(res.params.get("beta[1]", 0)),
            "persistence": float(
                res.params.get("alpha[1]", 0) + res.params.get("beta[1]", 0)
            ),
            "log_likelihood": float(res.loglikelihood),
            "aic": float(res.aic),
            "horizon_days": horizon,
        }

        return annualized_vol, info

    except Exception as e:
        logger.error("GARCH forecast failed: %s", e)
        return None, {"error": str(e)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RULE-BASED FALLBACK
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def detect_regime_rules(returns: ReturnSeries) -> RegimeDetection:
    """Simple rule-based regime detection as fallback.

    Uses 20-day momentum and realized volatility thresholds.
    """
    if len(returns.values) < 5:
        return RegimeDetection(
            regime=MarketRegime.UNKNOWN.value,
            confidence=0.0,
            volatility_forecast=None,
            volatility_current=None,
            indicators={},
            method="rule_based",
            timestamp=_utc_now().isoformat(),
        )

    # 20-day lookback (or all available)
    lookback = min(20, len(returns.values))
    recent = returns.values[-lookback:]

    momentum = sum(recent) / len(recent)
    vol = float(np.std(recent) * np.sqrt(252))

    # Thresholds (annualized)
    if momentum > 0.0005 and vol < 0.25:
        regime = MarketRegime.BULL
        confidence = min(0.8, abs(momentum) * 1000)
    elif momentum < -0.0005 and vol > 0.20:
        regime = MarketRegime.BEAR
        confidence = min(0.8, abs(momentum) * 1000)
    else:
        regime = MarketRegime.SIDEWAYS
        confidence = 0.5

    return RegimeDetection(
        regime=regime.value,
        confidence=confidence,
        volatility_forecast=vol,
        volatility_current=vol,
        indicators={
            "momentum_20d": momentum,
            "realized_vol_annualized": vol,
            "lookback_days": lookback,
        },
        method="rule_based",
        timestamp=_utc_now().isoformat(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# COMBINED REGIME ANALYSIS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def analyze_regime(
    returns: ReturnSeries,
    use_hmm: bool = True,
    use_garch: bool = True,
) -> RegimeDetection:
    """Run full regime analysis combining HMM + GARCH.

    Attempts HMM first, falls back to rules. Augments with GARCH
    volatility forecast if available.
    """
    if use_hmm:
        detection = detect_regime_hmm(returns)
    else:
        detection = detect_regime_rules(returns)

    # Augment with GARCH if available
    if use_garch and len(returns.values) >= 50:
        garch_vol, garch_info = forecast_volatility_garch(returns)
        if garch_vol is not None:
            detection.volatility_forecast = garch_vol
            detection.indicators["garch_vol_forecast"] = garch_vol
            detection.indicators.update({
                f"garch_{k}": v for k, v in garch_info.items()
                if isinstance(v, (int, float))
            })

    # Persist
    _persist_regime(detection)

    return detection


def _persist_regime(detection: RegimeDetection) -> None:
    """Append regime detection to JSONL log."""
    REGIME_DIR.mkdir(parents=True, exist_ok=True)
    log_file = REGIME_DIR / "regime_log.jsonl"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(detection), default=str) + "\n")
    except Exception as e:
        logger.error("Failed to persist regime detection: %s", e)


def load_regime_history(limit: int = 30) -> list[RegimeDetection]:
    """Load recent regime detections from log."""
    log_file = REGIME_DIR / "regime_log.jsonl"
    if not log_file.exists():
        return []

    try:
        lines = log_file.read_text(encoding="utf-8").strip().split("\n")
        recent = lines[-limit:] if len(lines) > limit else lines
        return [RegimeDetection(**json.loads(line)) for line in recent if line.strip()]
    except Exception as e:
        logger.error("Failed to load regime history: %s", e)
        return []
