"""OrganismRuntime — the living heartbeat with Gnani, algedonic, and samvara.

This is where the organism processes itself. Each heartbeat:
  1. IdentityMonitor measures TCS (trailing: GPR, BSI, RM)
  2. LiveCoherenceSensor measures present-moment state
  3. Blended coherence = 0.4 * live + 0.6 * trailing TCS
  4. Algedonic channel fires if thresholds crossed
  5. Gnani issues HOLD or PROCEED
  6. If HOLD: SamvaraEngine runs the appropriate power's cycle

Architecture: Beer S5 (identity) + Dada Bhagwan (witness-doer separation)
           + Sri Aurobindo (four powers of transformation).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from dharma_swarm.identity import IdentityMonitor, LiveCoherenceSensor
from dharma_swarm.samvara import DiagnosticResult, SamvaraEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Algedonic signals
# ---------------------------------------------------------------------------

@dataclass
class AlgedonicSignal:
    """A pain/pleasure signal that bypasses S1-S4 and reaches S5 directly."""
    kind: str          # telos_drift, omega_divergence, failure_rate, ontological_drift
    severity: str      # info, medium, critical
    action: str        # what the system should do
    value: float = 0.0
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Gnani verdict
# ---------------------------------------------------------------------------

@dataclass
class GnaniVerdict:
    """The witness's binary decision: HOLD or PROCEED."""
    decision: str  # "HOLD" or "PROCEED"
    reason: str
    coherence: float
    hold_count: int
    timestamp: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Heartbeat result
# ---------------------------------------------------------------------------

@dataclass
class HeartbeatResult:
    """Everything that happened in one heartbeat cycle."""
    cycle: int
    tcs: float
    live_score: float
    blended: float
    regime: str
    algedonic_signals: list[AlgedonicSignal] = field(default_factory=list)
    gnani_verdict: Optional[GnaniVerdict] = None
    samvara_diagnostic: Optional[DiagnosticResult] = None
    elapsed_ms: float = 0.0


# ---------------------------------------------------------------------------
# OrganismRuntime
# ---------------------------------------------------------------------------

class OrganismRuntime:
    """The living heartbeat loop.

    Ties together IdentityMonitor (trailing), LiveCoherenceSensor
    (present-moment), algedonic channel (pain signals), Gnani (witness
    verdict), and SamvaraEngine (transformation on HOLD).

    Usage:
        org = OrganismRuntime(state_dir)
        result = await org.heartbeat()
        # or
        results = await org.run(n_cycles=15)
    """

    # Algedonic thresholds
    TELOS_DRIFT_THRESHOLD: float = 0.4
    OMEGA_DIVERGENCE_THRESHOLD: float = 0.4

    # Blend weights: present-moment vs trailing
    LIVE_WEIGHT: float = 0.4
    TRAILING_WEIGHT: float = 0.6

    def __init__(
        self,
        state_dir: Optional[Path] = None,
        on_algedonic: Optional[Callable[[AlgedonicSignal], None]] = None,
        on_gnani: Optional[Callable[[GnaniVerdict], None]] = None,
    ) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._identity = IdentityMonitor(self._state_dir)
        self._live_sensor = LiveCoherenceSensor(self._state_dir)
        self._samvara = SamvaraEngine(self._state_dir)
        self._on_algedonic = on_algedonic
        self._on_gnani = on_gnani
        self._cycle = 0
        self._consecutive_holds = 0
        self._history: deque[HeartbeatResult] = deque(maxlen=1000)

    @property
    def cycle(self) -> int:
        return self._cycle

    @property
    def samvara(self) -> SamvaraEngine:
        return self._samvara

    @property
    def history(self) -> list[HeartbeatResult]:
        return list(self._history)

    async def heartbeat(self) -> HeartbeatResult:
        """Execute one heartbeat cycle. The organism processes itself."""
        t0 = time.monotonic()
        self._cycle += 1

        # 1. Trailing measurement (TCS from filesystem artifacts)
        identity_state = await self._identity.measure()
        tcs = identity_state.tcs

        # 2. Present-moment measurement
        live = self._live_sensor.measure()
        live_score = live["score"]

        # 3. Blend
        blended = self.LIVE_WEIGHT * live_score + self.TRAILING_WEIGHT * tcs

        # 4. Algedonic channel — fire pain signals if thresholds crossed
        signals = self._check_algedonic(blended, live_score, tcs)

        # 5. Gnani verdict
        verdict = self._gnani_verdict(blended, signals)

        # 6. Samvara engine — transform on HOLD
        diagnostic = None
        if verdict.decision == "HOLD":
            self._consecutive_holds += 1
            diagnostic = await self._samvara.on_hold(
                coherence=blended,
                live_metrics={
                    "daemon_alive": live.get("daemon_alive", False),
                    "freshness_ratio": live.get("freshness_ratio", 0.0),
                    "tcs": tcs,
                    "live_score": live_score,
                },
            )
        else:
            if self._consecutive_holds > 0:
                self._samvara.on_proceed()
            self._consecutive_holds = 0

        elapsed = (time.monotonic() - t0) * 1000

        result = HeartbeatResult(
            cycle=self._cycle,
            tcs=round(tcs, 4),
            live_score=round(live_score, 4),
            blended=round(blended, 4),
            regime=identity_state.regime,
            algedonic_signals=signals,
            gnani_verdict=verdict,
            samvara_diagnostic=diagnostic,
            elapsed_ms=round(elapsed, 2),
        )
        self._history.append(result)

        logger.info(
            "♥ Cycle %d | tcs=%.2f live=%.2f blended=%.2f | %s | %s | %.0fms",
            self._cycle, tcs, live_score, blended,
            verdict.decision,
            self._samvara.current_power.value if self._samvara.active else "—",
            elapsed,
        )

        return result

    async def run(self, n_cycles: int = 15) -> list[HeartbeatResult]:
        """Run n heartbeat cycles and return all results."""
        results = []
        for _ in range(n_cycles):
            results.append(await self.heartbeat())
        return results

    # -- Algedonic channel --------------------------------------------------

    def _check_algedonic(
        self, blended: float, live_score: float, tcs: float,
    ) -> list[AlgedonicSignal]:
        """Fire pain signals when the organism is incoherent."""
        signals: list[AlgedonicSignal] = []

        # Telos drift: blended coherence below threshold
        if blended < self.TELOS_DRIFT_THRESHOLD:
            sig = AlgedonicSignal(
                kind="telos_drift",
                severity="critical",
                action="gnani_checkpoint",
                value=blended,
            )
            signals.append(sig)
            if self._on_algedonic:
                self._on_algedonic(sig)

        # Omega divergence: live and trailing disagree strongly
        divergence = abs(live_score - tcs)
        if divergence > self.OMEGA_DIVERGENCE_THRESHOLD:
            sig = AlgedonicSignal(
                kind="omega_divergence",
                severity="medium",
                action="rebalance_priorities",
                value=divergence,
            )
            signals.append(sig)
            if self._on_algedonic:
                self._on_algedonic(sig)

        return signals

    # -- Gnani (witness) ----------------------------------------------------

    def _gnani_verdict(
        self, blended: float, signals: list[AlgedonicSignal],
    ) -> GnaniVerdict:
        """The witness observes and issues a binary verdict."""
        has_critical = any(s.severity == "critical" for s in signals)

        if has_critical or blended < self.TELOS_DRIFT_THRESHOLD:
            verdict = GnaniVerdict(
                decision="HOLD",
                reason=(
                    f"blended coherence {blended:.3f} below drift threshold "
                    f"{self.TELOS_DRIFT_THRESHOLD}"
                ),
                coherence=blended,
                hold_count=self._consecutive_holds + 1,
            )
        else:
            verdict = GnaniVerdict(
                decision="PROCEED",
                reason=f"blended coherence {blended:.3f} is stable",
                coherence=blended,
                hold_count=0,
            )

        if self._on_gnani:
            self._on_gnani(verdict)

        return verdict

    # -- Status -------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Full organism status snapshot."""
        return {
            "cycle": self._cycle,
            "consecutive_holds": self._consecutive_holds,
            "samvara_active": self._samvara.active,
            "samvara_power": self._samvara.current_power.value,
            "total_heartbeats": len(self._history),
            "last_blended": self._history[-1].blended if self._history else None,
            "last_verdict": (
                self._history[-1].gnani_verdict.decision
                if self._history and self._history[-1].gnani_verdict
                else None
            ),
        }
