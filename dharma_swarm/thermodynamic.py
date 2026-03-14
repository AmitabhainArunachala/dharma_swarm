"""Thermodynamic awareness -- efficiency monitoring and stopping criteria.

Tracks quality_delta / tokens_used per iteration to detect wasteful compute.

Stopping criteria (exempt during warmup):
  Carnot limit:  EMA efficiency < 1e-7 --> STOP
  Diminishing returns:  3 consecutive sub-epsilon iterations --> STOP
  Warmup:  first 2 iterations exempt from all stopping criteria.

Per-domain budget multipliers allow differentiated resource allocation.

Storage: ~/.dharma/meta/efficiency.json
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import _utc_now

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-domain budget multipliers
# ---------------------------------------------------------------------------

DOMAIN_BUDGETS: dict[str, float] = {
    "evolution": 1.0,
    "autoresearch": 1.5,
    "pulse": 0.3,
    "cascade": 1.0,
    "recognition": 0.5,
    "audit": 0.2,
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class EfficiencyReading(BaseModel):
    """A single efficiency measurement for one iteration."""

    iteration: int = 0
    quality_delta: float = 0.0
    tokens_used: int = 0
    efficiency: float = 0.0  # quality_delta / tokens_used
    ema_efficiency: float = 0.0
    domain: str = "default"
    should_stop: bool = False
    stop_reason: str = ""
    timestamp: str = Field(default_factory=lambda: _utc_now().isoformat())


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------


class ThermodynamicMonitor:
    """Tracks compute efficiency and triggers stopping criteria.

    The monitor records (quality_delta, tokens_used) pairs for each iteration
    and maintains an exponential moving average (EMA) of efficiency.  After a
    warmup period two stopping rules apply:

    1. *Carnot limit* -- the EMA drops below a tiny threshold, meaning the
       system is producing negligible quality improvement per token.
    2. *Diminishing returns* -- several consecutive iterations fail to produce
       a quality delta above ``EPSILON``.

    Attributes:
        CARNOT_LIMIT: EMA threshold below which iteration is wasteful.
        EPSILON: Minimum meaningful quality delta.
        WARMUP_ITERATIONS: Number of initial iterations exempt from stopping.
        CONSECUTIVE_STOP: Required consecutive sub-epsilon iterations to stop.
        EMA_ALPHA: Smoothing factor for the exponential moving average.
    """

    CARNOT_LIMIT: float = 1e-7
    EPSILON: float = 0.001  # minimum meaningful quality delta
    WARMUP_ITERATIONS: int = 2
    CONSECUTIVE_STOP: int = 3  # stop after N consecutive sub-epsilon
    EMA_ALPHA: float = 0.3  # EMA smoothing factor

    def __init__(
        self,
        *,
        domain: str = "default",
        persist_path: Path | None = None,
    ) -> None:
        self.domain = domain
        self._persist_path = persist_path or (
            Path.home() / ".dharma" / "meta" / "efficiency.json"
        )
        self._readings: list[EfficiencyReading] = []
        self._ema: float = 0.0
        self._consecutive_sub_epsilon: int = 0
        self._budget_multiplier: float = DOMAIN_BUDGETS.get(domain, 1.0)

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    def record(self, quality_delta: float, tokens_used: int) -> EfficiencyReading:
        """Record an iteration and check stopping criteria.

        Args:
            quality_delta: Change in quality metric since last iteration.
            tokens_used: Number of tokens consumed in this iteration.

        Returns:
            An ``EfficiencyReading`` with ``should_stop`` and ``stop_reason``
            populated when a stopping criterion fires.
        """
        iteration = len(self._readings)

        # Compute raw efficiency
        if tokens_used > 0:
            efficiency = quality_delta / tokens_used
        else:
            efficiency = 0.0

        # Update EMA
        if iteration == 0:
            self._ema = efficiency
        else:
            self._ema = (
                self.EMA_ALPHA * efficiency + (1.0 - self.EMA_ALPHA) * self._ema
            )

        # Track consecutive sub-epsilon iterations
        if abs(quality_delta) < self.EPSILON:
            self._consecutive_sub_epsilon += 1
        else:
            self._consecutive_sub_epsilon = 0

        # Evaluate stopping criteria (warmup is exempt)
        should_stop = False
        stop_reason = ""

        if iteration >= self.WARMUP_ITERATIONS:
            if abs(self._ema) < self.CARNOT_LIMIT:
                should_stop = True
                stop_reason = (
                    f"Carnot limit: EMA efficiency {self._ema:.2e} "
                    f"< {self.CARNOT_LIMIT:.0e}"
                )
            elif self._consecutive_sub_epsilon >= self.CONSECUTIVE_STOP:
                should_stop = True
                stop_reason = (
                    f"Diminishing returns: {self._consecutive_sub_epsilon} "
                    f"consecutive sub-epsilon iterations"
                )

        reading = EfficiencyReading(
            iteration=iteration,
            quality_delta=round(quality_delta, 6),
            tokens_used=tokens_used,
            efficiency=round(efficiency, 10),
            ema_efficiency=round(self._ema, 10),
            domain=self.domain,
            should_stop=should_stop,
            stop_reason=stop_reason,
        )
        self._readings.append(reading)
        return reading

    # ------------------------------------------------------------------
    # Budget suggestions
    # ------------------------------------------------------------------

    def suggest_budget_reallocation(self) -> dict[str, float]:
        """Suggest budget redistribution based on actual efficiency.

        Domains with positive average efficiency get their budget scaled up
        (capped at 2.0); domains with zero or negative efficiency get scaled
        down (floored at 0.1).  Only the current domain is adjusted; other
        domains keep their baseline multiplier.

        Returns:
            Dict mapping domain names to suggested budget multipliers.
        """
        if not self._readings:
            return dict(DOMAIN_BUDGETS)

        avg_eff = sum(r.efficiency for r in self._readings) / len(self._readings)

        suggestions: dict[str, float] = {}
        for domain, base in DOMAIN_BUDGETS.items():
            if domain == self.domain:
                if avg_eff > 0:
                    suggestions[domain] = min(2.0, base * 1.5)
                else:
                    suggestions[domain] = max(0.1, base * 0.5)
            else:
                suggestions[domain] = base
        return suggestions

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self) -> None:
        """Persist readings to disk as JSON."""
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "domain": self.domain,
            "readings": [r.model_dump() for r in self._readings],
            "ema": self._ema,
            "saved_at": _utc_now().isoformat(),
        }
        self._persist_path.write_text(json.dumps(data, indent=2))
        logger.debug("Saved %d readings to %s", len(self._readings), self._persist_path)

    def load(self) -> bool:
        """Load readings from disk.

        Returns:
            True if data was loaded successfully, False otherwise.
        """
        if not self._persist_path.exists():
            return False
        try:
            data = json.loads(self._persist_path.read_text())
            self._readings = [
                EfficiencyReading(**r) for r in data.get("readings", [])
            ]
            self._ema = data.get("ema", 0.0)
            logger.debug(
                "Loaded %d readings from %s", len(self._readings), self._persist_path
            )
            return True
        except Exception:
            logger.warning("Failed to load efficiency data from %s", self._persist_path)
            return False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def readings(self) -> list[EfficiencyReading]:
        """Return a copy of all recorded readings."""
        return list(self._readings)

    @property
    def total_tokens(self) -> int:
        """Total tokens consumed across all recorded iterations."""
        return sum(r.tokens_used for r in self._readings)

    @property
    def current_ema(self) -> float:
        """Current EMA efficiency value."""
        return self._ema

    @property
    def budget_multiplier(self) -> float:
        """Budget multiplier for the configured domain."""
        return self._budget_multiplier

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all state to initial values."""
        self._readings.clear()
        self._ema = 0.0
        self._consecutive_sub_epsilon = 0
