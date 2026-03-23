"""Samvara Engine — four-power HOLD cascade with altitude escalation.

When the Gnani says HOLD, this is what happens. Not inert passivity —
active transformation. Each consecutive HOLD deepens the altitude.

The Four Powers (from Sri Aurobindo's "The Mother"):

  1. Mahasaraswati — precise seeing at ground level (technical diagnostics)
  2. Mahalakshmi  — coherence and connection (are the parts talking?)
  3. Mahakali     — dissolution of the false (cut what isn't real)
  4. Maheshwari   — vast seeing, full field (single most leveraged action)

Altitude escalation is fluid — the system watches coherence delta after
each power's cycle and learns where the natural boundaries are.

Architecture principle: P3 (Gates embody downward causation) +
Axiom 17 (Witness-Doer Separation) + Axiom 18 (Samvara — no ungated mutations).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Powers
# ---------------------------------------------------------------------------

class Power(str, Enum):
    """The four powers of transformation, in order of altitude."""
    MAHASARASWATI = "mahasaraswati"  # precise, ground-level
    MAHALAKSHMI = "mahalakshmi"      # coherence, connection
    MAHAKALI = "mahakali"            # dissolution of false
    MAHESHWARI = "maheshwari"        # vast seeing, full field

    @classmethod
    def from_hold_count(cls, n: int) -> "Power":
        """Fluid altitude: escalate based on consecutive HOLD count."""
        if n <= 0:
            return cls.MAHASARASWATI
        # Fluid thresholds — will be tuned by observation
        if n <= 3:
            return cls.MAHASARASWATI
        if n <= 6:
            return cls.MAHALAKSHMI
        if n <= 9:
            return cls.MAHAKALI
        return cls.MAHESHWARI


# ---------------------------------------------------------------------------
# Diagnostic results
# ---------------------------------------------------------------------------

@dataclass
class DiagnosticResult:
    """What a power's cycle found and did."""
    power: Power
    hold_count: int
    findings: list[str] = field(default_factory=list)
    corrections: list[str] = field(default_factory=list)
    coherence_before: float = 0.0
    coherence_after: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def delta(self) -> float:
        return self.coherence_after - self.coherence_before

    def to_dict(self) -> dict[str, Any]:
        return {
            "power": self.power.value,
            "hold_count": self.hold_count,
            "findings": self.findings,
            "corrections": self.corrections,
            "coherence_before": self.coherence_before,
            "coherence_after": self.coherence_after,
            "delta": round(self.delta, 4),
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Samvara Mode state
# ---------------------------------------------------------------------------

@dataclass
class SamvaraState:
    """Tracks the organism's samvara mode."""
    active: bool = False
    consecutive_holds: int = 0
    current_power: Power = Power.MAHASARASWATI
    history: list[DiagnosticResult] = field(default_factory=list)
    entered_at: Optional[float] = None
    exited_at: Optional[float] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "consecutive_holds": self.consecutive_holds,
            "current_power": self.current_power.value,
            "history_len": len(self.history),
            "entered_at": self.entered_at,
            "exited_at": self.exited_at,
        }


# ---------------------------------------------------------------------------
# The Engine
# ---------------------------------------------------------------------------

class SamvaraEngine:
    """Four-power HOLD cascade with fluid altitude escalation.

    Usage:
        engine = SamvaraEngine(state_dir)
        result = await engine.on_hold(coherence=0.35, identity_state=state)
        # or
        engine.on_proceed()  # resets consecutive holds

    The engine does NOT decide whether to HOLD — the Gnani does that.
    The engine decides what TRANSFORMATION happens during a HOLD.
    """

    # How many consecutive HOLDs before entering samvara_mode
    ACTIVATION_THRESHOLD: int = 2

    def __init__(self, state_dir: Optional[Path] = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._state = SamvaraState()

    @property
    def state(self) -> SamvaraState:
        return self._state

    @property
    def active(self) -> bool:
        return self._state.active

    @property
    def current_power(self) -> Power:
        return self._state.current_power

    async def on_hold(
        self,
        coherence: float,
        *,
        live_metrics: Optional[dict[str, Any]] = None,
    ) -> DiagnosticResult:
        """Called when the Gnani says HOLD. Runs the appropriate power's cycle.

        Args:
            coherence: Current TCS value.
            live_metrics: Optional dict of live sensor readings for deeper diagnosis.

        Returns:
            DiagnosticResult from the power's cycle.
        """
        self._state.consecutive_holds += 1
        n = self._state.consecutive_holds

        # Activate samvara_mode if threshold crossed
        if not self._state.active and n >= self.ACTIVATION_THRESHOLD:
            self._state.active = True
            self._state.entered_at = time.time()
            logger.info("SAMVARA MODE ACTIVATED — hold #%d", n)

        # Determine altitude
        power = Power.from_hold_count(n)
        self._state.current_power = power

        # Run the power's diagnostic cycle
        result = await self._run_power(power, n, coherence, live_metrics)
        self._state.history.append(result)

        # Persist
        self._persist()

        return result

    def on_proceed(self) -> None:
        """Called when the Gnani says PROCEED. Resets the cascade."""
        if self._state.active:
            self._state.exited_at = time.time()
            logger.info(
                "SAMVARA MODE DEACTIVATED — %d holds, %d diagnostics",
                self._state.consecutive_holds,
                len(self._state.history),
            )
        self._state.active = False
        self._state.consecutive_holds = 0
        self._state.current_power = Power.MAHASARASWATI
        self._persist()

    # -- Power cycles -------------------------------------------------------

    async def _run_power(
        self,
        power: Power,
        hold_count: int,
        coherence: float,
        live_metrics: Optional[dict[str, Any]],
    ) -> DiagnosticResult:
        """Dispatch to the appropriate power's diagnostic cycle."""
        dispatch = {
            Power.MAHASARASWATI: self._mahasaraswati,
            Power.MAHALAKSHMI: self._mahalakshmi,
            Power.MAHAKALI: self._mahakali,
            Power.MAHESHWARI: self._maheshwari,
        }
        runner = dispatch[power]
        return await runner(hold_count, coherence, live_metrics or {})

    async def _mahasaraswati(
        self, hold_count: int, coherence: float, live: dict[str, Any]
    ) -> DiagnosticResult:
        """Precise seeing at ground level. What's technically broken?"""
        findings: list[str] = []
        corrections: list[str] = []

        # Check sensor health
        witness_dir = self._state_dir / "witness"
        if witness_dir.exists():
            jsonl_count = len(list(witness_dir.glob("*.jsonl")))
            json_count = len(list(witness_dir.glob("*.json")))
            if jsonl_count > 0 and json_count == 0:
                findings.append(
                    f"witness logs are JSONL ({jsonl_count} files), "
                    "GPR glob reads *.json — sensor is blind"
                )
                corrections.append("GPR must read *.jsonl, parse 'outcome' field")
        else:
            findings.append("no witness directory — GPR has no data source")

        # Check shared notes for BSI signal
        shared_dir = self._state_dir / "shared"
        if shared_dir.exists():
            notes = list(shared_dir.glob("*.md"))
            if notes:
                # Sample one note for swabhaav signal
                sample = notes[0].read_text()[:500] if notes else ""
                if sample and all(
                    kw not in sample.lower()
                    for kw in ("telos", "witness", "gate", "dharma", "coherence")
                ):
                    findings.append(
                        "shared notes lack telos-relevant language — "
                        "BSI measures nothing meaningful"
                    )

        # Check stigmergy for corruption
        marks_path = self._state_dir / "stigmergy" / "marks.jsonl"
        if marks_path.exists():
            try:
                lines = marks_path.read_text().strip().split("\n")
                corrupt = 0
                for line in lines[-100:]:  # sample last 100
                    try:
                        json.loads(line)
                    except (json.JSONDecodeError, Exception):
                        corrupt += 1
                if corrupt > 10:
                    findings.append(
                        f"{corrupt}/100 recent stigmergy marks are corrupt JSON"
                    )
                    corrections.append("RM must filter corrupt entries")
            except Exception:
                logger.debug("Stigmergy marks unreadable", exc_info=True)
                findings.append("stigmergy marks unreadable")

        # Live metrics checks
        if live:
            if live.get("agents_running", 0) == 0:
                findings.append("no agents currently running")
            if live.get("daemon_alive") is False:
                findings.append("daemon is not running")
                corrections.append("restart daemon")

        return DiagnosticResult(
            power=Power.MAHASARASWATI,
            hold_count=hold_count,
            findings=findings,
            corrections=corrections,
            coherence_before=coherence,
            coherence_after=coherence,  # Mahasaraswati observes, doesn't change
        )

    async def _mahalakshmi(
        self, hold_count: int, coherence: float, _live: dict[str, Any]
    ) -> DiagnosticResult:
        """Coherence and connection. Are the parts talking to each other?"""
        findings: list[str] = []
        corrections: list[str] = []

        # Check cross-subsystem wiring
        wiring_checks = [
            ("evolution → dispatch", self._state_dir / "evolution" / "archive.jsonl"),
            ("stigmergy → marks", self._state_dir / "stigmergy" / "marks.jsonl"),
            ("pulse → log", self._state_dir / "pulse.log"),
            ("memory → db", self._state_dir / "db" / "memory.db"),
            ("identity → history", self._state_dir / "meta" / "identity_history.jsonl"),
        ]

        connected = 0
        for name, path in wiring_checks:
            if path.exists() and path.stat().st_size > 0:
                # Check freshness — is it being written to?
                age_hours = (time.time() - path.stat().st_mtime) / 3600
                if age_hours < 24:
                    connected += 1
                else:
                    findings.append(f"{name}: stale ({age_hours:.0f}h old)")
            else:
                findings.append(f"{name}: missing or empty")

        wiring_ratio = connected / len(wiring_checks) if wiring_checks else 0
        if wiring_ratio < 0.6:
            corrections.append(
                f"wiring ratio {wiring_ratio:.0%} — subsystems are isolated"
            )

        # Check if identity history tracks any trend
        history_path = self._state_dir / "meta" / "identity_history.jsonl"
        if history_path.exists():
            try:
                lines = history_path.read_text().strip().split("\n")
                if len(lines) >= 5:
                    recent = [json.loads(l) for l in lines[-5:]]
                    tcs_values = [r.get("tcs", 0.5) for r in recent]
                    trend = tcs_values[-1] - tcs_values[0]
                    if trend < -0.1:
                        findings.append(
                            f"TCS trending down: {tcs_values[0]:.2f} → {tcs_values[-1]:.2f}"
                        )
            except Exception:
                logger.debug("Identity history read failed", exc_info=True)

        return DiagnosticResult(
            power=Power.MAHALAKSHMI,
            hold_count=hold_count,
            findings=findings,
            corrections=corrections,
            coherence_before=coherence,
            coherence_after=coherence,
        )

    async def _mahakali(
        self, hold_count: int, coherence: float, _live: dict[str, Any]
    ) -> DiagnosticResult:
        """Dissolution of the false. What is the system doing that it thinks
        is real work but isn't?"""
        findings: list[str] = []
        corrections: list[str] = []

        # Detect metric inflation
        marks_path = self._state_dir / "stigmergy" / "marks.jsonl"
        if marks_path.exists():
            try:
                lines = marks_path.read_text().strip().split("\n")
                total = len(lines)
                valid = 0
                for line in lines[-200:]:
                    try:
                        entry = json.loads(line)
                        if entry.get("observation", ""):
                            valid += 1
                    except Exception:
                        continue
                sample_size = min(200, total)
                if sample_size > 0:
                    validity_rate = valid / sample_size
                    if validity_rate < 0.8:
                        findings.append(
                            f"stigmergy validity {validity_rate:.0%} — "
                            f"RM is inflated by noise"
                        )
                        corrections.append("purge corrupt stigmergy entries")
            except Exception:
                logger.debug("Stigmergy validity check failed", exc_info=True)

        # Detect stale shared notes masking as activity
        shared_dir = self._state_dir / "shared"
        if shared_dir.exists():
            notes = sorted(
                shared_dir.glob("*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if len(notes) > 50:
                old_notes = [
                    n for n in notes[50:]
                    if (time.time() - n.stat().st_mtime) > 7 * 86400
                ]
                if len(old_notes) > 100:
                    findings.append(
                        f"{len(old_notes)} shared notes older than 7 days — "
                        "volume masquerading as momentum"
                    )

        # Check for repeated identical marks (busy without progress)
        if marks_path.exists():
            try:
                lines = marks_path.read_text().strip().split("\n")[-50:]
                observations = []
                for line in lines:
                    try:
                        entry = json.loads(line)
                        obs = entry.get("observation", "")[:80]
                        if obs:
                            observations.append(obs)
                    except Exception:
                        continue
                if observations:
                    unique = len(set(observations))
                    if unique < len(observations) * 0.5:
                        findings.append(
                            f"stigmergy repetition: {unique}/{len(observations)} "
                            "unique observations — system is looping"
                        )
                        corrections.append("break repetition cycle")
            except Exception:
                logger.debug("Stigmergy repetition check failed", exc_info=True)

        return DiagnosticResult(
            power=Power.MAHAKALI,
            hold_count=hold_count,
            findings=findings,
            corrections=corrections,
            coherence_before=coherence,
            coherence_after=coherence,
        )

    async def _maheshwari(
        self, hold_count: int, coherence: float, _live: dict[str, Any]
    ) -> DiagnosticResult:
        """Vast seeing, full field. What is the single most leveraged action?"""
        findings: list[str] = []
        corrections: list[str] = []

        # Gather all prior diagnostics from this cascade
        prior_findings: list[str] = []
        for prev in self._state.history:
            prior_findings.extend(prev.findings)

        if prior_findings:
            findings.append(
                f"accumulated {len(prior_findings)} findings across "
                f"{len(self._state.history)} prior power cycles"
            )

            # Categorize
            sensor_issues = [f for f in prior_findings if "blind" in f or "sensor" in f]
            wiring_issues = [f for f in prior_findings if "stale" in f or "missing" in f or "isolated" in f]
            false_issues = [f for f in prior_findings if "inflated" in f or "noise" in f or "looping" in f]

            # Determine most leveraged
            if sensor_issues:
                corrections.append(
                    "LEVERAGED: fix sensors first — the organism cannot see itself"
                )
            elif wiring_issues:
                corrections.append(
                    "LEVERAGED: restore subsystem wiring — coherence requires connection"
                )
            elif false_issues:
                corrections.append(
                    "LEVERAGED: dissolve false metrics — truth before progress"
                )
            else:
                corrections.append(
                    "LEVERAGED: no clear single point — consider structural redesign"
                )
        else:
            findings.append("no prior findings — organism may be genuinely healthy")
            corrections.append("coherence is real — PROCEED")

        return DiagnosticResult(
            power=Power.MAHESHWARI,
            hold_count=hold_count,
            findings=findings,
            corrections=corrections,
            coherence_before=coherence,
            coherence_after=coherence,
        )

    # -- Persistence --------------------------------------------------------

    def _persist(self) -> None:
        """Write samvara state to disk."""
        path = self._state_dir / "meta" / "samvara_state.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(json.dumps(self._state.to_dict(), indent=2))
        except Exception as exc:
            logger.warning("Failed to persist samvara state: %s", exc)

    def load_state(self) -> SamvaraState:
        """Load persisted samvara state."""
        path = self._state_dir / "meta" / "samvara_state.json"
        if not path.exists():
            return self._state
        try:
            data = json.loads(path.read_text())
            self._state.active = data.get("active", False)
            self._state.consecutive_holds = data.get("consecutive_holds", 0)
            power_name = data.get("current_power", "mahasaraswati")
            self._state.current_power = Power(power_name)
            self._state.entered_at = data.get("entered_at")
            self._state.exited_at = data.get("exited_at")
        except Exception as exc:
            logger.warning("Failed to load samvara state: %s", exc)
        return self._state
