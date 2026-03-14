"""S5 Computational Identity -- telos coherence tracking.

Beer's Viable System Model System 5: identity and purpose coherence.

Telos Coherence Score (TCS) = 0.35*GPR + 0.35*BSI + 0.30*RM

  - **GPR** -- Gate Passage Rate from witness logs.
  - **BSI** -- Behavioral Swabhaav Index (mean ``swabhaav_ratio`` across
    recent shared notes via :class:`~dharma_swarm.metrics.MetricsAnalyzer`).
  - **RM** -- Research Momentum (archive entries, stigmergy density,
    task completion signals).

Drift detection: TCS < 0.4 writes a ``.FOCUS`` correction directive.
S4 -> S5 feedback: zeitgeist threats boost RM weight.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from dharma_swarm.models import _new_id, _utc_now

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class IdentityState(BaseModel):
    """Snapshot of system identity coherence.

    Attributes:
        id: Unique snapshot identifier.
        tcs: Telos Coherence Score (weighted combination of GPR/BSI/RM).
        gpr: Gate Passage Rate -- fraction of recent gates that passed.
        bsi: Behavioral Swabhaav Index -- mean swabhaav_ratio.
        rm: Research Momentum -- normalized activity signal.
        regime: Current identity regime (stable / drifting / critical).
        correction_issued: Whether a ``.FOCUS`` file was written.
        timestamp: UTC timestamp of measurement.
    """

    id: str = Field(default_factory=_new_id)
    tcs: float = 0.5
    gpr: float = 0.5
    bsi: float = 0.5
    rm: float = 0.5
    regime: str = "stable"
    correction_issued: bool = False
    timestamp: datetime = Field(default_factory=_utc_now)


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------


class IdentityMonitor:
    """S5 identity monitor that tracks telos coherence over time.

    Computes TCS from three sub-metrics and issues correction directives
    when identity drift is detected.

    Args:
        state_dir: Root of the ``.dharma`` state tree.  Defaults to
            ``~/.dharma``.
    """

    # TCS weights (default, no threat boost)
    GPR_WEIGHT: float = 0.35
    BSI_WEIGHT: float = 0.35
    RM_WEIGHT: float = 0.30

    # Drift thresholds
    DRIFT_THRESHOLD: float = 0.4
    CRITICAL_THRESHOLD: float = 0.25

    def __init__(self, state_dir: Path | None = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")
        self._history: list[IdentityState] = []

    # -- public API ---------------------------------------------------------

    async def measure(self, *, threat_boost: bool = False) -> IdentityState:
        """Measure current telos coherence.

        Args:
            threat_boost: When ``True`` (e.g. zeitgeist threats detected),
                shifts weight toward RM (+0.15) at the expense of GPR and
                BSI (-0.075 each).

        Returns:
            An ``IdentityState`` snapshot.
        """
        gpr = await self._measure_gpr()
        bsi = await self._measure_bsi()
        rm = await self._measure_rm()

        # S4 -> S5 feedback: threats boost RM weight
        if threat_boost:
            rm_weight = min(0.50, self.RM_WEIGHT + 0.15)
            gpr_weight = self.GPR_WEIGHT - 0.075
            bsi_weight = self.BSI_WEIGHT - 0.075
        else:
            gpr_weight = self.GPR_WEIGHT
            bsi_weight = self.BSI_WEIGHT
            rm_weight = self.RM_WEIGHT

        tcs = gpr_weight * gpr + bsi_weight * bsi + rm_weight * rm

        # Determine regime
        if tcs < self.CRITICAL_THRESHOLD:
            regime = "critical"
        elif tcs < self.DRIFT_THRESHOLD:
            regime = "drifting"
        else:
            regime = "stable"

        # Issue correction if drifting
        correction_issued = False
        if regime in ("drifting", "critical"):
            correction_issued = self._issue_correction(tcs, gpr, bsi, rm)

        state = IdentityState(
            tcs=round(tcs, 4),
            gpr=round(gpr, 4),
            bsi=round(bsi, 4),
            rm=round(rm, 4),
            regime=regime,
            correction_issued=correction_issued,
        )
        self._history.append(state)
        return state

    @property
    def history(self) -> list[IdentityState]:
        """Return a copy of all recorded states."""
        return list(self._history)

    @property
    def current_tcs(self) -> float:
        """Return the most recent TCS, or 0.5 if no measurements taken."""
        return self._history[-1].tcs if self._history else 0.5

    # -- sub-metrics --------------------------------------------------------

    async def _measure_gpr(self) -> float:
        """Gate passage rate from witness logs.

        Reads the 20 most-recent JSON files from
        ``<state_dir>/witness/`` and counts those whose ``decision``
        field is one of ``allow``, ``PASS``, or ``ALLOW``.

        Returns:
            Float in [0.0, 1.0], defaulting to 0.5 when no data.
        """
        witness_dir = self._state_dir / "witness"
        if not witness_dir.exists():
            return 0.5

        try:
            log_files = sorted(
                witness_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:20]
            if not log_files:
                return 0.5

            total = 0
            passed = 0
            for lf in log_files:
                try:
                    data = json.loads(lf.read_text())
                    total += 1
                    decision = data.get("decision", "")
                    if decision in ("allow", "PASS", "ALLOW"):
                        passed += 1
                except Exception:
                    continue

            return passed / total if total > 0 else 0.5
        except Exception:
            return 0.5

    async def _measure_bsi(self) -> float:
        """Mean swabhaav_ratio from recent shared notes.

        Imports :class:`~dharma_swarm.metrics.MetricsAnalyzer` lazily to
        avoid circular imports and analyses the 10 most-recent Markdown
        notes in ``<state_dir>/shared/``.

        Returns:
            Float in [0.0, 1.0], defaulting to 0.5 when no data.
        """
        shared_dir = self._state_dir / "shared"
        if not shared_dir.exists():
            return 0.5

        try:
            from dharma_swarm.metrics import MetricsAnalyzer

            analyzer = MetricsAnalyzer()

            notes = sorted(
                shared_dir.glob("*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:10]
            if not notes:
                return 0.5

            ratios: list[float] = []
            for note in notes:
                try:
                    text = note.read_text()
                    if len(text) < 50:
                        continue
                    sig = analyzer.analyze(text)
                    ratios.append(sig.swabhaav_ratio)
                except Exception:
                    continue

            return sum(ratios) / len(ratios) if ratios else 0.5
        except Exception:
            return 0.5

    async def _measure_rm(self) -> float:
        """Research momentum from multiple signals.

        Combines:
        - Evolution archive entry count (normalized to 100).
        - Stigmergy mark density (normalized to 1000).
        - Shared note count (normalized to 50).

        Returns:
            Float in [0.0, 1.0], defaulting to 0.5 when no data.
        """
        signals: list[float] = []

        # Archive entries (recent activity = momentum)
        archive_path = self._state_dir / "evolution" / "archive.jsonl"
        if archive_path.exists():
            try:
                content = archive_path.read_text().strip()
                if content:
                    lines = content.split("\n")
                    signals.append(min(1.0, len(lines) / 100.0))
            except Exception:
                pass

        # Stigmergy density
        marks_path = self._state_dir / "stigmergy" / "marks.jsonl"
        if marks_path.exists():
            try:
                content = marks_path.read_text().strip()
                if content:
                    density = len(content.split("\n"))
                    signals.append(min(1.0, density / 1000.0))
            except Exception:
                pass

        # Shared notes count
        shared_dir = self._state_dir / "shared"
        if shared_dir.exists():
            count = len(list(shared_dir.glob("*.md")))
            signals.append(min(1.0, count / 50.0))

        return sum(signals) / len(signals) if signals else 0.5

    # -- correction ---------------------------------------------------------

    def _issue_correction(
        self, tcs: float, gpr: float, bsi: float, rm: float
    ) -> bool:
        """Write a ``.FOCUS`` correction directive.

        The file is placed at ``<state_dir>/.FOCUS`` and describes the
        weakest TCS dimension with a concrete remediation action.

        Returns:
            ``True`` if the file was written successfully.
        """
        focus_path = self._state_dir / ".FOCUS"
        try:
            weakest = min(
                [("GPR", gpr), ("BSI", bsi), ("RM", rm)], key=lambda x: x[1]
            )
            severity = (
                "CRITICAL" if tcs < self.CRITICAL_THRESHOLD else "DRIFTING"
            )
            content = (
                f"# FOCUS CORRECTION -- TCS={tcs:.3f} ({severity})\n"
                f"Generated: {_utc_now().isoformat()}\n\n"
                f"Weakest dimension: {weakest[0]}={weakest[1]:.3f}\n\n"
            )
            if weakest[0] == "GPR":
                content += (
                    "Action: Review gate failures. "
                    "Are proposals violating dharmic constraints?\n"
                )
            elif weakest[0] == "BSI":
                content += (
                    "Action: Agent outputs show low swabhaav. "
                    "Inject witness prompts.\n"
                )
            else:
                content += (
                    "Action: Research momentum is low. "
                    "Prioritize paper/experiment work.\n"
                )

            focus_path.write_text(content)
            return True
        except Exception as exc:
            logger.warning("Failed to write .FOCUS: %s", exc)
            return False

    # -- persistence --------------------------------------------------------

    def save_history(self, path: Path | None = None) -> None:
        """Persist measurement history to a JSONL file.

        Args:
            path: Override destination.  Defaults to
                ``<state_dir>/meta/identity_history.jsonl``.
        """
        dest = path or (self._state_dir / "meta" / "identity_history.jsonl")
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "a") as fh:
            for state in self._history:
                fh.write(state.model_dump_json() + "\n")

    def load_history(self, path: Path | None = None) -> list[IdentityState]:
        """Load previously persisted states from a JSONL file.

        Returns:
            List of ``IdentityState`` instances, oldest first.
        """
        src = path or (self._state_dir / "meta" / "identity_history.jsonl")
        states: list[IdentityState] = []
        if not src.exists():
            return states
        try:
            for line in src.read_text().strip().split("\n"):
                if line.strip():
                    states.append(IdentityState.model_validate_json(line))
        except Exception as exc:
            logger.warning("Failed to load identity history: %s", exc)
        return states
