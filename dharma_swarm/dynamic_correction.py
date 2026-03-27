"""dynamic_correction.py — Isara-style monitoring + auto-correction.

The Gnani becomes a course-corrector, not just an evaluator. Drift detection,
stuck-agent recovery, output quality gating, auto-rerouting.

Runs as part of the organism heartbeat. Each tick:
1. Collect signals from all active agents
2. Detect drift patterns
3. Apply correction policies
4. Log everything for audit

This closes the gap identified in the synthesis:
"Dynamic Correction = This is the gap."
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment config
# ---------------------------------------------------------------------------

ENABLE_DYNAMIC_CORRECTION = os.environ.get(
    "ENABLE_DYNAMIC_CORRECTION", "true"
).strip().lower() in ("1", "true", "yes", "on")
CORRECTION_COOLDOWN_MINUTES = int(
    os.environ.get("CORRECTION_COOLDOWN_MINUTES", "5")
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DriftType(str, Enum):
    """Types of agent drift that trigger correction."""

    QUALITY_DEGRADATION = "quality_degradation"
    BUDGET_OVERRUN = "budget_overrun"
    STUCK_AGENT = "stuck_agent"
    DHARMIC_DRIFT = "dharmic_drift"
    LOOP_DETECTED = "loop_detected"
    ERROR_CASCADE = "error_cascade"


class CorrectionAction(str, Enum):
    """Actions the correction system can take."""

    WARN = "warn"
    THROTTLE = "throttle"
    REROUTE = "reroute"
    RESTART = "restart"
    ESCALATE = "escalate"
    HIBERNATE = "hibernate"
    EVOLVE = "evolve"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class DriftSignal:
    """A detected drift event."""

    id: str = ""
    agent_id: str = ""
    drift_type: DriftType = DriftType.QUALITY_DEGRADATION
    severity: float = 0.0
    details: str = ""
    detected_at: str = ""
    corrective_action: Optional[CorrectionAction] = None
    resolved: bool = False

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.detected_at:
            self.detected_at = datetime.now(timezone.utc).isoformat()


@dataclass
class CorrectionPolicy:
    """Policy mapping drift types to corrective actions based on severity."""

    drift_type: DriftType
    severity_thresholds: Dict[float, CorrectionAction] = field(default_factory=dict)
    cooldown_minutes: int = CORRECTION_COOLDOWN_MINUTES


# ---------------------------------------------------------------------------
# Default policies
# ---------------------------------------------------------------------------

DEFAULT_POLICIES: List[CorrectionPolicy] = [
    CorrectionPolicy(
        drift_type=DriftType.QUALITY_DEGRADATION,
        severity_thresholds={
            0.3: CorrectionAction.WARN,
            0.6: CorrectionAction.THROTTLE,
            0.9: CorrectionAction.REROUTE,
        },
    ),
    CorrectionPolicy(
        drift_type=DriftType.BUDGET_OVERRUN,
        severity_thresholds={
            0.5: CorrectionAction.THROTTLE,
            0.8: CorrectionAction.HIBERNATE,
        },
    ),
    CorrectionPolicy(
        drift_type=DriftType.STUCK_AGENT,
        severity_thresholds={
            0.4: CorrectionAction.WARN,
            0.7: CorrectionAction.RESTART,
            0.95: CorrectionAction.REROUTE,
        },
    ),
    CorrectionPolicy(
        drift_type=DriftType.DHARMIC_DRIFT,
        severity_thresholds={
            0.3: CorrectionAction.WARN,
            0.5: CorrectionAction.THROTTLE,
            0.7: CorrectionAction.ESCALATE,
        },
    ),
    CorrectionPolicy(
        drift_type=DriftType.LOOP_DETECTED,
        severity_thresholds={
            0.5: CorrectionAction.WARN,
            0.8: CorrectionAction.RESTART,
        },
    ),
    CorrectionPolicy(
        drift_type=DriftType.ERROR_CASCADE,
        severity_thresholds={
            0.4: CorrectionAction.WARN,
            0.6: CorrectionAction.REROUTE,
            0.9: CorrectionAction.EVOLVE,
        },
    ),
]


# ---------------------------------------------------------------------------
# SQLite DDL for correction audit trail
# ---------------------------------------------------------------------------

_CORRECTION_DDL = """\
CREATE TABLE IF NOT EXISTS correction_events (
    id             TEXT    PRIMARY KEY,
    agent_id       TEXT    NOT NULL,
    drift_type     TEXT    NOT NULL,
    severity       REAL    NOT NULL,
    details        TEXT    NOT NULL DEFAULT '',
    action_taken   TEXT    NOT NULL DEFAULT '',
    resolved       INTEGER NOT NULL DEFAULT 0,
    detected_at    TEXT    NOT NULL,
    resolved_at    TEXT    NOT NULL DEFAULT ''
);
"""


# ---------------------------------------------------------------------------
# Dynamic Correction Engine
# ---------------------------------------------------------------------------


class DynamicCorrectionEngine:
    """Isara-style monitoring + auto-correction for the swarm.

    Runs as part of the organism heartbeat. Each tick:
    1. Collect signals from all active agents
    2. Detect drift patterns
    3. Apply correction policies
    4. Log everything for audit
    """

    def __init__(
        self,
        economic_spine: Any = None,
        dharma_attractor: Any = None,
        policies: Optional[List[CorrectionPolicy]] = None,
        db_path: str = ":memory:",
    ) -> None:
        self.economic_spine = economic_spine
        self.dharma_attractor = dharma_attractor
        self._policies = {
            p.drift_type: p
            for p in (DEFAULT_POLICIES if policies is None else policies)
        }
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.executescript(_CORRECTION_DDL)
        self._conn.commit()

        # Track last correction per agent to enforce cooldowns
        self._last_correction: Dict[str, datetime] = {}
        # In-memory signals for current tick
        self._active_signals: List[DriftSignal] = []
        # Escalation flag for organism-level attention
        self.escalation_flag: bool = False

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Drift detectors
    # ------------------------------------------------------------------

    def detect_quality_degradation(
        self, agent_id: str, recent_scores: List[float]
    ) -> Optional[DriftSignal]:
        """Detect declining quality trend.

        Uses rolling window: if last N scores trend downward significantly.
        """
        if len(recent_scores) < 3:
            return None

        # Check if trending down: compare first half avg to second half avg
        mid = len(recent_scores) // 2
        first_half = sum(recent_scores[:mid]) / max(mid, 1)
        second_half = sum(recent_scores[mid:]) / max(len(recent_scores) - mid, 1)

        if second_half >= first_half:
            return None  # Not degrading

        drop = first_half - second_half
        # Scale severity: 0.1 drop → ~0.3 severity, 0.3 drop → ~0.9
        severity = min(drop * 3.0, 1.0)

        if severity < 0.1:
            return None

        return DriftSignal(
            agent_id=agent_id,
            drift_type=DriftType.QUALITY_DEGRADATION,
            severity=severity,
            details=f"Quality drop: {first_half:.2f} → {second_half:.2f} (Δ={drop:.2f})",
        )

    def detect_budget_overrun(
        self,
        agent_id: str,
        budget: Any,
        current_mission: Any = None,
    ) -> Optional[DriftSignal]:
        """Detect if agent is spending faster than its budget allows."""
        if budget is None:
            return None

        remaining = getattr(budget, "tokens_remaining", None)
        allocated = getattr(budget, "total_tokens_allocated", None)
        if remaining is None or allocated is None or allocated <= 0:
            return None

        usage_ratio = 1.0 - (remaining / allocated)
        if usage_ratio < 0.7:
            return None  # Under 70% used, no overrun

        # Severity scales from 0.5 at 70% usage to 1.0 at 100%+
        severity = min((usage_ratio - 0.5) * 2.0, 1.0)

        return DriftSignal(
            agent_id=agent_id,
            drift_type=DriftType.BUDGET_OVERRUN,
            severity=severity,
            details=f"Budget {usage_ratio*100:.0f}% used ({remaining} remaining of {allocated})",
        )

    def detect_stuck_agent(
        self,
        agent_id: str,
        last_action_at: Optional[datetime] = None,
        tick_interval: Optional[timedelta] = None,
    ) -> Optional[DriftSignal]:
        """Detect if agent hasn't produced output in N ticks."""
        if last_action_at is None:
            return None

        now = datetime.now(timezone.utc)
        elapsed = now - last_action_at
        threshold = (tick_interval or timedelta(minutes=1)) * 3

        if elapsed < threshold:
            return None

        # Severity scales with how long stuck
        stuck_ratio = elapsed / threshold
        severity = min(stuck_ratio * 0.3, 1.0)

        return DriftSignal(
            agent_id=agent_id,
            drift_type=DriftType.STUCK_AGENT,
            severity=severity,
            details=f"No output for {elapsed.total_seconds():.0f}s (threshold: {threshold.total_seconds():.0f}s)",
        )

    def detect_dharmic_drift(
        self, agent_id: str, alignment_score: float
    ) -> Optional[DriftSignal]:
        """Detect if agent's dharmic alignment is dropping."""
        if alignment_score >= 0.7:
            return None  # Acceptable alignment

        # Severity: 0.7 → 0, 0.0 → 1.0
        severity = max(1.0 - alignment_score / 0.7, 0.0)
        severity = min(severity, 1.0)

        return DriftSignal(
            agent_id=agent_id,
            drift_type=DriftType.DHARMIC_DRIFT,
            severity=severity,
            details=f"Alignment score {alignment_score:.2f} below threshold 0.7",
        )

    def detect_loop(
        self, agent_id: str, recent_actions: List[str]
    ) -> Optional[DriftSignal]:
        """Detect if agent is repeating the same actions."""
        if len(recent_actions) < 4:
            return None

        # Count action frequencies
        counts = Counter(recent_actions[-10:])
        if not counts:
            return None

        most_common_action, most_common_count = counts.most_common(1)[0]
        total = len(recent_actions[-10:])
        repetition_ratio = most_common_count / total

        if repetition_ratio < 0.5:
            return None  # Less than 50% repetition, not a loop

        severity = min(repetition_ratio, 1.0)

        return DriftSignal(
            agent_id=agent_id,
            drift_type=DriftType.LOOP_DETECTED,
            severity=severity,
            details=f"Action '{most_common_action}' repeated {most_common_count}/{total} times",
        )

    def detect_error_cascade(
        self, agent_id: str, recent_errors: List[dict]
    ) -> Optional[DriftSignal]:
        """Detect consecutive failures that indicate systemic problem."""
        if len(recent_errors) < 3:
            return None

        # Count errors in last N entries
        error_count = len(recent_errors)
        # Severity scales with consecutive errors: 3→0.4, 5→0.7, 8+→1.0
        severity = min(error_count * 0.13, 1.0)

        return DriftSignal(
            agent_id=agent_id,
            drift_type=DriftType.ERROR_CASCADE,
            severity=severity,
            details=f"{error_count} consecutive errors detected",
        )

    # ------------------------------------------------------------------
    # Policy matching
    # ------------------------------------------------------------------

    def match_policy(self, signal: DriftSignal) -> Optional[CorrectionAction]:
        """Determine corrective action based on severity thresholds."""
        policy = self._policies.get(signal.drift_type)
        if policy is None:
            return None

        action: Optional[CorrectionAction] = None
        for threshold in sorted(policy.severity_thresholds.keys()):
            if signal.severity >= threshold:
                action = policy.severity_thresholds[threshold]

        return action

    # ------------------------------------------------------------------
    # Correction engine
    # ------------------------------------------------------------------

    def evaluate_and_correct(
        self, agent_id: str, agent_state: dict
    ) -> List[DriftSignal]:
        """Run all drift detectors for an agent, apply corrections.

        Called from organism heartbeat each tick.
        Returns list of drift signals detected (may be empty).
        """
        signals: List[DriftSignal] = []

        # Quality degradation
        recent_scores = agent_state.get("recent_quality_scores", [])
        if recent_scores:
            sig = self.detect_quality_degradation(agent_id, recent_scores)
            if sig:
                signals.append(sig)

        # Budget overrun
        budget = agent_state.get("budget")
        mission = agent_state.get("current_mission")
        if budget is not None:
            sig = self.detect_budget_overrun(agent_id, budget, mission)
            if sig:
                signals.append(sig)

        # Stuck agent
        last_action = agent_state.get("last_action_at")
        tick_interval = agent_state.get("tick_interval")
        if last_action is not None:
            sig = self.detect_stuck_agent(agent_id, last_action, tick_interval)
            if sig:
                signals.append(sig)

        # Dharmic drift
        alignment = agent_state.get("alignment_score")
        if alignment is not None:
            sig = self.detect_dharmic_drift(agent_id, alignment)
            if sig:
                signals.append(sig)

        # Loop detection
        recent_actions = agent_state.get("recent_actions", [])
        if recent_actions:
            sig = self.detect_loop(agent_id, recent_actions)
            if sig:
                signals.append(sig)

        # Error cascade
        recent_errors = agent_state.get("recent_errors", [])
        if recent_errors:
            sig = self.detect_error_cascade(agent_id, recent_errors)
            if sig:
                signals.append(sig)

        # Apply corrections
        for signal in signals:
            action = self.match_policy(signal)
            if action:
                signal.corrective_action = action
                self.apply_correction(signal)

        self._active_signals.extend(signals)
        return signals

    def apply_correction(self, signal: DriftSignal) -> bool:
        """Execute the corrective action.

        Returns True if correction was applied, False if on cooldown.
        """
        if not signal.corrective_action:
            return False

        # Check cooldown
        policy = self._policies.get(signal.drift_type)
        cooldown_minutes = policy.cooldown_minutes if policy else CORRECTION_COOLDOWN_MINUTES
        cooldown_key = f"{signal.agent_id}:{signal.drift_type.value}"
        last = self._last_correction.get(cooldown_key)
        now = datetime.now(timezone.utc)

        if last is not None:
            elapsed = now - last
            if elapsed < timedelta(minutes=cooldown_minutes):
                logger.debug(
                    "Correction cooldown active for %s (%.0fs remaining)",
                    cooldown_key,
                    (timedelta(minutes=cooldown_minutes) - elapsed).total_seconds(),
                )
                return False

        # Record the correction time
        self._last_correction[cooldown_key] = now

        action = signal.corrective_action

        if action == CorrectionAction.WARN:
            logger.warning(
                "DRIFT WARNING [%s] agent=%s severity=%.2f: %s",
                signal.drift_type.value,
                signal.agent_id,
                signal.severity,
                signal.details,
            )

        elif action == CorrectionAction.THROTTLE:
            logger.warning(
                "THROTTLE [%s] agent=%s: reducing budget",
                signal.drift_type.value,
                signal.agent_id,
            )
            if self.economic_spine is not None:
                budget = self.economic_spine.get_or_create_budget(signal.agent_id)
                # Reduce allocation by 20%
                new_alloc = int(budget.total_tokens_allocated * 0.8)
                budget.total_tokens_allocated = max(new_alloc, 1000)
                self.economic_spine._save_budget(budget)

        elif action == CorrectionAction.REROUTE:
            logger.warning(
                "REROUTE [%s] agent=%s: marking mission for reassignment",
                signal.drift_type.value,
                signal.agent_id,
            )

        elif action == CorrectionAction.RESTART:
            logger.warning(
                "RESTART [%s] agent=%s: requesting agent restart",
                signal.drift_type.value,
                signal.agent_id,
            )

        elif action == CorrectionAction.ESCALATE:
            logger.warning(
                "ESCALATE [%s] agent=%s: organism-level alert",
                signal.drift_type.value,
                signal.agent_id,
            )
            self.escalation_flag = True

        elif action == CorrectionAction.HIBERNATE:
            logger.warning(
                "HIBERNATE [%s] agent=%s: requesting hibernation",
                signal.drift_type.value,
                signal.agent_id,
            )

        elif action == CorrectionAction.EVOLVE:
            logger.warning(
                "EVOLVE [%s] agent=%s: queuing for re-evolution",
                signal.drift_type.value,
                signal.agent_id,
            )

        # Persist to audit trail
        self._record_correction(signal)
        return True

    # ------------------------------------------------------------------
    # Audit trail
    # ------------------------------------------------------------------

    def _record_correction(self, signal: DriftSignal) -> None:
        """Persist correction event to SQLite."""
        try:
            self._conn.execute(
                "INSERT INTO correction_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    signal.id,
                    signal.agent_id,
                    signal.drift_type.value,
                    signal.severity,
                    signal.details,
                    signal.corrective_action.value if signal.corrective_action else "",
                    1 if signal.resolved else 0,
                    signal.detected_at,
                    "",
                ),
            )
            self._conn.commit()
        except Exception as exc:
            logger.debug("Failed to record correction event: %s", exc)

    def get_correction_history(
        self, agent_id: Optional[str] = None, limit: int = 50
    ) -> List[DriftSignal]:
        """Retrieve correction history, optionally filtered by agent."""
        if agent_id:
            rows = self._conn.execute(
                "SELECT * FROM correction_events WHERE agent_id = ? ORDER BY detected_at DESC LIMIT ?",
                (agent_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM correction_events ORDER BY detected_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            DriftSignal(
                id=r[0],
                agent_id=r[1],
                drift_type=DriftType(r[2]),
                severity=r[3],
                details=r[4],
                corrective_action=CorrectionAction(r[5]) if r[5] else None,
                resolved=bool(r[6]),
                detected_at=r[7],
            )
            for r in rows
        ]

    def get_swarm_health(self) -> dict:
        """Aggregate health: active drifts, corrections applied, resolution rate."""
        total = self._conn.execute(
            "SELECT COUNT(*) FROM correction_events"
        ).fetchone()[0]
        resolved = self._conn.execute(
            "SELECT COUNT(*) FROM correction_events WHERE resolved = 1"
        ).fetchone()[0]

        # Count by drift type
        by_type = {}
        for row in self._conn.execute(
            "SELECT drift_type, COUNT(*) FROM correction_events GROUP BY drift_type"
        ).fetchall():
            by_type[row[0]] = row[1]

        # Count by action
        by_action = {}
        for row in self._conn.execute(
            "SELECT action_taken, COUNT(*) FROM correction_events WHERE action_taken != '' GROUP BY action_taken"
        ).fetchall():
            by_action[row[0]] = row[1]

        return {
            "total_corrections": total,
            "resolved": resolved,
            "resolution_rate": round(resolved / max(total, 1), 4),
            "active_signals": len(self._active_signals),
            "escalation_flag": self.escalation_flag,
            "corrections_by_type": by_type,
            "corrections_by_action": by_action,
        }

    def resolve_signal(self, signal_id: str) -> None:
        """Mark a drift signal as resolved."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE correction_events SET resolved = 1, resolved_at = ? WHERE id = ?",
            (now, signal_id),
        )
        self._conn.commit()
        self._active_signals = [
            s for s in self._active_signals if s.id != signal_id
        ]
