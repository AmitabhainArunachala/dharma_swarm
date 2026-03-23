"""S5 Computational Identity -- telos coherence tracking.

Beer's Viable System Model System 5: identity and purpose coherence.

TCS = 0.35*GPR + 0.35*BSI + 0.30*RM

  - **GPR** -- Gate Passage Rate from witness JSONL logs (``outcome`` field).
  - **BSI** -- Behavioral Swabhaav Index: four proxy metrics measuring
    multi-altitude reasoning, cross-domain connection, teleological grounding,
    and gap quality.  Replaces the old dead ``swabhaav_ratio`` sensor.
  - **RM** -- Research Momentum (archive entries, *valid* stigmergy density,
    task completion signals).  Filters corrupt JSON.

Present-moment layer: ``LiveCoherenceSensor`` measures the organism's
real-time state (daemon health, subsystem freshness, agent activity)
and blends it with the trailing filesystem metrics.

Drift detection: TCS < 0.4 writes a ``.FOCUS`` correction directive.
S4 -> S5 feedback: zeitgeist threats boost RM weight.
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

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
        self._history: deque[IdentityState] = deque(maxlen=1000)

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
        """Gate passage rate from witness JSONL logs.

        Reads the 10 most-recent JSONL files from ``<state_dir>/witness/``
        and parses the last 150 entries.  Counts those whose ``outcome``
        field is ``PASS`` or ``ALLOW`` (the actual field name in live logs).

        Returns:
            Float in [0.0, 1.0], defaulting to 0.5 when no data.
        """
        witness_dir = self._state_dir / "witness"
        if not witness_dir.exists():
            return 0.5

        try:
            log_files = sorted(
                witness_dir.glob("*.jsonl"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:10]
            if not log_files:
                return 0.5

            total = 0
            passed = 0
            for lf in log_files:
                try:
                    for line in lf.read_text().strip().split("\n")[-50:]:
                        if not line.strip():
                            continue
                        try:
                            entry = json.loads(line)
                        except (json.JSONDecodeError, Exception):
                            continue
                        total += 1
                        outcome = entry.get("outcome", entry.get("decision", ""))
                        if outcome in ("PASS", "ALLOW", "allow"):
                            passed += 1
                        if total >= 150:
                            break
                except Exception:
                    continue
                if total >= 150:
                    break

            return passed / total if total > 0 else 0.5
        except Exception:
            return 0.5

    async def _measure_bsi(self) -> float:
        """Behavioral Swabhaav Index via four structural proxy metrics.

        Replaces the old dead swabhaav_ratio sensor with measurements of
        the CONDITIONS for high-quality awareness:

        1. Multi-altitude reasoning — does the text connect immediate
           action to telos-level purpose?  (2+ altitude spans)
        2. Cross-domain connection — does the text bring distinct domains
           into genuine contact?
        3. Teleological grounding — does the text reference specific
           current system state, not generic purpose-language?
        4. Gap quality — concision without loss.  Low I-density, high
           type-token ratio, low hedging.

        Returns:
            Float in [0.0, 1.0], defaulting to 0.5 when no data.
        """
        shared_dir = self._state_dir / "shared"
        if not shared_dir.exists():
            return 0.5

        try:
            notes = sorted(
                shared_dir.glob("*.md"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )[:10]
            if not notes:
                return 0.5

            scores: list[float] = []
            for note in notes:
                try:
                    text = note.read_text()
                    if len(text) < 50:
                        continue
                    scores.append(_bsi_proxy_score(text))
                except Exception:
                    continue

            return sum(scores) / len(scores) if scores else 0.5
        except Exception:
            return 0.5

    async def _measure_rm(self) -> float:
        """Research momentum from multiple signals.

        Combines:
        - Evolution archive entry count (normalized to 100).
        - *Valid* stigmergy mark density (corrupt JSON filtered out).
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
                logger.debug("Evolution archive read failed", exc_info=True)

        # Stigmergy density — VALID entries only
        marks_path = self._state_dir / "stigmergy" / "marks.jsonl"
        if marks_path.exists():
            try:
                content = marks_path.read_text().strip()
                if content:
                    lines = content.split("\n")
                    valid = 0
                    for line in lines:
                        try:
                            json.loads(line)
                            valid += 1
                        except (json.JSONDecodeError, Exception):
                            pass
                    signals.append(min(1.0, valid / 1000.0))
            except Exception:
                logger.debug("Stigmergy density read failed", exc_info=True)

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


# ---------------------------------------------------------------------------
# BSI Proxy Metrics — the four invariant conditions
# ---------------------------------------------------------------------------

# Altitude keywords by level: ground → telos
_ALTITUDE_GROUND = {"fix", "bug", "test", "error", "path", "import", "config"}
_ALTITUDE_SYSTEM = {"daemon", "agent", "dispatch", "provider", "router", "cron"}
_ALTITUDE_SEMANTIC = {
    "coherence", "stigmergy", "evolution", "witness", "gate", "ontology",
    "identity", "telos", "dharma", "kernel",
}
_ALTITUDE_META = {
    "moksha", "jagat", "kalyan", "swabhaav", "visheshbhaav", "prakriti",
    "shakti", "saraswati", "maheshwari", "overmind", "supramental",
}

# Cross-domain keyword sets
_DOMAIN_TECHNICAL = {"api", "test", "build", "deploy", "daemon", "cron", "sql"}
_DOMAIN_SEMANTIC = {"ontology", "telos", "gate", "witness", "dharma", "pillar"}
_DOMAIN_CONTEMPLATIVE = {
    "witness", "swabhaav", "moksha", "pratikraman", "samvara", "nirjara",
    "akram", "vignan", "karma", "jiva",
}
_DOMAIN_SCIENTIFIC = {
    "friston", "varela", "beer", "kauffman", "levin", "deacon",
    "autopoiesis", "vsm", "entropy", "free energy",
}
_DOMAINS = [_DOMAIN_TECHNICAL, _DOMAIN_SEMANTIC, _DOMAIN_CONTEMPLATIVE, _DOMAIN_SCIENTIFIC]

# Hedging words
_HEDGES = {"might", "could", "perhaps", "possibly", "maybe", "seems", "appears"}


def _bsi_proxy_score(text: str) -> float:
    """Compute BSI from four structural proxy metrics.

    Returns float in [0, 1].  Each sub-metric contributes 0.25 max.
    """
    words = text.lower().split()
    n = len(words)
    if n < 10:
        return 0.0

    word_set = set(words)

    # 1. Multi-altitude reasoning (0-0.25)
    altitudes_hit = 0
    for level in (_ALTITUDE_GROUND, _ALTITUDE_SYSTEM, _ALTITUDE_SEMANTIC, _ALTITUDE_META):
        if word_set & level:
            altitudes_hit += 1
    altitude_score = min(1.0, (altitudes_hit - 1) / 2.0) if altitudes_hit > 1 else 0.0

    # 2. Cross-domain connection (0-0.25)
    domains_hit = sum(1 for d in _DOMAINS if word_set & d)
    domain_score = min(1.0, (domains_hit - 1) / 2.0) if domains_hit > 1 else 0.0

    # 3. Teleological grounding (0-0.25)
    # Presence of specific state references (not generic purpose language)
    telos_markers = _ALTITUDE_SEMANTIC | {"because", "since", "therefore", "so that"}
    telos_count = sum(1 for w in words if w in telos_markers)
    telos_score = min(1.0, telos_count / max(1, n * 0.03))

    # 4. Gap quality (0-0.25)
    # Low I-density, high type-token ratio, low hedging
    i_count = sum(1 for w in words if w == "i")
    i_density = i_count / n
    ttr = len(word_set) / n  # type-token ratio
    hedge_count = sum(1 for w in words if w in _HEDGES)
    hedge_density = hedge_count / n

    # Low I-density is good (< 0.03), high TTR is good (> 0.5), low hedge is good
    gap_score = (
        (1.0 if i_density < 0.03 else max(0.0, 1.0 - i_density * 20)) * 0.33
        + min(1.0, ttr / 0.6) * 0.34
        + (1.0 if hedge_density < 0.01 else max(0.0, 1.0 - hedge_density * 50)) * 0.33
    )

    return (altitude_score + domain_score + telos_score + gap_score) / 4.0


# ---------------------------------------------------------------------------
# Live Coherence Sensor — present-moment awareness
# ---------------------------------------------------------------------------


class LiveCoherenceSensor:
    """Measures the organism's real-time state.

    Not what files exist — what's ALIVE right now.  Checks:
    - Daemon health (PID alive, recent heartbeat)
    - Subsystem freshness (how recently each subsystem wrote data)
    - Agent activity (any agents currently dispatched)

    Returns a float in [0, 1] that blends with trailing TCS.
    """

    # Subsystems and their data paths (relative to state_dir)
    SUBSYSTEMS = {
        "pulse": "pulse.log",
        "stigmergy": "stigmergy/marks.jsonl",
        "evolution": "evolution/archive.jsonl",
        "memory": "db/memory.db",
        "identity": "meta/identity_history.jsonl",
    }

    # How many hours before a subsystem is considered stale
    FRESHNESS_HOURS: float = 24.0

    def __init__(self, state_dir: Optional[Path] = None) -> None:
        self._state_dir = state_dir or (Path.home() / ".dharma")

    def measure(self) -> dict[str, Any]:
        """Measure present-moment coherence.

        Returns:
            Dict with ``score`` (float 0-1), ``daemon_alive`` (bool),
            ``subsystem_freshness`` (dict), ``freshness_ratio`` (float).
        """
        daemon_alive = self._check_daemon()
        freshness = self._check_freshness()

        fresh_count = sum(1 for v in freshness.values() if v)
        freshness_ratio = fresh_count / len(freshness) if freshness else 0.0

        # Score: 40% daemon, 60% subsystem freshness
        score = (0.4 if daemon_alive else 0.0) + 0.6 * freshness_ratio

        return {
            "score": round(score, 4),
            "daemon_alive": daemon_alive,
            "subsystem_freshness": freshness,
            "freshness_ratio": round(freshness_ratio, 4),
        }

    def _check_daemon(self) -> bool:
        """Check if the daemon PID is alive."""
        pid_path = self._state_dir / "daemon.pid"
        if not pid_path.exists():
            return False
        try:
            import os
            pid = int(pid_path.read_text().strip())
            os.kill(pid, 0)  # signal 0 = check if alive
            return True
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            return False

    def _check_freshness(self) -> dict[str, bool]:
        """Check how recently each subsystem wrote data."""
        now = time.time()
        cutoff = self.FRESHNESS_HOURS * 3600
        result: dict[str, bool] = {}
        for name, rel_path in self.SUBSYSTEMS.items():
            path = self._state_dir / rel_path
            if path.exists():
                age = now - path.stat().st_mtime
                result[name] = age < cutoff
            else:
                result[name] = False
        return result
