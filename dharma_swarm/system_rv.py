"""System-level R_V -- the system measures its own geometric contraction.

Collects state vectors from existing stores, computes participation ratio (PR),
tracks R_V = PR(t) / PR(t-1) as a vital sign.  Pure Python -- no torch/numpy.

Regimes:
  R_V < 0.8  -> converging (exploit mode, reduce mutation: factor=0.7)
  R_V > 1.2  -> exploring  (natural, don't fight: factor=1.0)
  0.9 - 1.1  -> static     (stagnant, shake: factor=1.3)
  otherwise  -> transitional (factor=1.0)
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dharma_swarm.models import SystemVitals, _utc_now

logger = logging.getLogger(__name__)

STATE_DIR = Path.home() / ".dharma"
META_DIR = STATE_DIR / "meta"


class SystemRV:
    """Measures the system's geometric contraction/expansion over time.

    Collects a state vector from evolution archive, stigmergy, and shared
    notes, then computes participation ratio (PR) and the ratio R_V =
    PR(t) / PR(t-1).  This drives mutation rate modulation in the Darwin
    Engine: converging systems reduce mutation, stagnant systems increase it.
    """

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or STATE_DIR
        self._meta_dir = self._state_dir / "meta"
        self._history_path = self._meta_dir / "system_rv.json"
        self._history: list[dict[str, Any]] = []

    async def init(self) -> None:
        """Load history from disk, creating the meta directory if needed."""
        self._meta_dir.mkdir(parents=True, exist_ok=True)
        if self._history_path.exists():
            try:
                raw = self._history_path.read_text()
                self._history = json.loads(raw)
            except (json.JSONDecodeError, OSError):
                self._history = []

    def _compute_pr(self, vector: list[float]) -> float:
        """Participation ratio: PR = 1 / sum(p_i^2).

        Where p_i = v_i^2 / sum(v_j^2).  For a uniform vector of
        dimension N, PR = N.  For a one-hot vector, PR = 1.0.

        Returns:
            The participation ratio, or NaN if the vector has zero energy.
        """
        sq = [v * v for v in vector]
        total = sum(sq)
        if total < 1e-12:
            return float("nan")
        probs = [s / total for s in sq]
        sum_p_sq = sum(p * p for p in probs)
        if sum_p_sq < 1e-12:
            return float("nan")
        return 1.0 / sum_p_sq

    async def collect_state_vector(self) -> list[float]:
        """Collect state from existing stores into a flat vector.

        Sources (all optional -- gracefully degrades):
          - Evolution archive: last 5 entries' fitness scores (8 dims each)
          - Stigmergy: mark count (density)
          - Shared notes: file count

        Returns:
            A flat list of floats with at least 2 elements.
        """
        vector: list[float] = []

        # 1. Evolution archive fitness dimensions
        try:
            from dharma_swarm.archive import EvolutionArchive

            archive_path = self._state_dir / "evolution" / "archive.jsonl"
            if archive_path.exists():
                archive = EvolutionArchive(path=archive_path)
                await archive.load()
                entries = await archive.get_latest(n=5)
                for entry in entries:
                    fs = entry.fitness
                    vector.extend([
                        fs.correctness,
                        fs.dharmic_alignment,
                        fs.performance,
                        fs.utilization,
                        fs.economic_value,
                        fs.elegance,
                        fs.efficiency,
                        fs.safety,
                    ])
        except Exception as exc:
            logger.debug("Evolution archive unavailable: %s", exc)

        # 2. Stigmergy density
        try:
            from dharma_swarm.stigmergy import StigmergyStore

            store = StigmergyStore(base_path=self._state_dir / "stigmergy")
            density = store.density()
            vector.append(float(density))
        except Exception as exc:
            logger.debug("Stigmergy unavailable: %s", exc)

        # 3. Shared notes count
        try:
            shared_dir = self._state_dir / "shared"
            if shared_dir.exists():
                note_count = len(list(shared_dir.glob("*.md")))
                vector.append(float(note_count))
        except Exception:
            pass

        # Ensure minimum dimensionality
        if len(vector) < 2:
            vector = [1.0, 1.0]

        return vector

    @staticmethod
    def _classify_regime(
        system_rv: float,
    ) -> tuple[str, float]:
        """Classify the R_V value into a regime and exploration factor.

        Returns:
            Tuple of (regime_name, exploration_factor).
        """
        if system_rv < 0.8:
            return "converging", 0.7
        elif system_rv > 1.2:
            return "exploring", 1.0
        elif 0.9 <= system_rv <= 1.1:
            return "static", 1.3
        else:
            return "transitional", 1.0

    async def measure(self) -> SystemVitals:
        """Take one R_V measurement.

        Collects the current state vector, computes its participation
        ratio, computes R_V as the ratio to the previous PR, classifies
        the regime, persists to history, and returns SystemVitals.

        Returns:
            A SystemVitals instance with the current measurement.
        """
        vector = await self.collect_state_vector()
        pr_current = self._compute_pr(vector)

        # Get previous PR
        pr_previous = (
            self._history[-1]["pr"] if self._history else pr_current
        )

        # Compute R_V
        if (
            math.isnan(pr_current)
            or math.isnan(pr_previous)
            or pr_previous < 1e-12
        ):
            system_rv = 1.0
        else:
            system_rv = pr_current / pr_previous

        regime, exploration_factor = self._classify_regime(system_rv)

        vitals = SystemVitals(
            system_rv=round(system_rv, 4),
            pr_current=round(pr_current, 4),
            pr_previous=round(pr_previous, 4),
            regime=regime,
            exploration_factor=exploration_factor,
            dimension_count=len(vector),
        )

        # Persist to history
        self._history.append({
            "timestamp": _utc_now().isoformat(),
            "pr": pr_current,
            "rv": system_rv,
            "regime": regime,
            "dims": len(vector),
        })

        # Cap at 100 measurements
        self._history = self._history[-100:]
        self._save()

        return vitals

    def get_exploration_factor(self) -> float:
        """Get current exploration factor for mutation rate modulation.

        Based on the most recent R_V measurement.  Returns 1.0 if no
        measurements have been taken yet.
        """
        if not self._history:
            return 1.0
        last = self._history[-1]
        rv = last.get("rv", 1.0)
        _, factor = self._classify_regime(rv)
        return factor

    def _save(self) -> None:
        """Persist history to disk."""
        self._meta_dir.mkdir(parents=True, exist_ok=True)
        self._history_path.write_text(json.dumps(self._history, indent=2))

    @property
    def history(self) -> list[dict[str, Any]]:
        """Return a copy of the measurement history."""
        return list(self._history)
