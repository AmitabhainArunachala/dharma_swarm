"""Graduation engine for operator autonomy levels.

State machine: HUMAN_ON_LOOP(2) → AUTONOMOUS_ALERT(3) → FULLY_AUTONOMOUS(4).

Promotion requires sustained quality (consecutive successes with high YSD scores).
Demotion is immediate on failure streaks or gate blocks. Level 1 (MANUAL) exists
but is only set by explicit human override. CRITICAL actions always need approval
regardless of level — hardcoded, not graduated.
"""

from __future__ import annotations

import logging
import time
from enum import IntEnum
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)


class AutonomyLevel(IntEnum):
    MANUAL = 1            # Everything needs approval (human override only)
    HUMAN_ON_LOOP = 2     # MEDIUM+ needs approval
    AUTONOMOUS_ALERT = 3  # MEDIUM auto-approved, HIGH needs approval
    FULLY_AUTONOMOUS = 4  # Everything except CRITICAL auto-approved


class RiskLevel(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# Promotion thresholds
_PROMOTE_TO_3_SUCCESSES = 50
_PROMOTE_TO_3_MIN_YSD = 5.08
_PROMOTE_TO_4_SUCCESSES = 200
_PROMOTE_TO_4_MIN_YSD = 5.10

# Demotion trigger
_DEMOTION_FAILURES = 3

_STATE_DDL = """
CREATE TABLE IF NOT EXISTS graduation_state (
    id INTEGER PRIMARY KEY CHECK(id = 1),
    current_level INTEGER NOT NULL DEFAULT 2,
    consecutive_successes INTEGER NOT NULL DEFAULT 0,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    ysd_sum REAL NOT NULL DEFAULT 0.0,
    ysd_count INTEGER NOT NULL DEFAULT 0,
    last_promotion_at TEXT,
    last_demotion_at TEXT,
    updated_at TEXT NOT NULL
)"""

_HISTORY_DDL = """
CREATE TABLE IF NOT EXISTS graduation_history (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    action_type TEXT NOT NULL,
    success INTEGER NOT NULL,
    ysd_score REAL NOT NULL DEFAULT 0.0,
    gate_blocked INTEGER NOT NULL DEFAULT 0,
    level_before INTEGER NOT NULL,
    level_after INTEGER NOT NULL
)"""


class GraduationEngine:
    """Manages operator autonomy graduation via YSD quality scoring."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (Path.home() / ".dharma" / "db" / "runtime.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db: aiosqlite.Connection | None = None

        # In-memory cache of current state
        self.level = AutonomyLevel.HUMAN_ON_LOOP
        self.consecutive_successes = 0
        self.consecutive_failures = 0
        self._ysd_sum = 0.0
        self._ysd_count = 0

    @property
    def mean_ysd(self) -> float:
        return self._ysd_sum / self._ysd_count if self._ysd_count > 0 else 5.0

    async def init_db(self) -> None:
        self._db = await aiosqlite.connect(str(self.db_path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute(_STATE_DDL)
        await self._db.execute(_HISTORY_DDL)
        await self._db.commit()
        await self._load_state()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def _load_state(self) -> None:
        if not self._db:
            return
        async with self._db.execute("SELECT * FROM graduation_state WHERE id = 1") as cur:
            row = await cur.fetchone()
        if row:
            self.level = AutonomyLevel(row["current_level"])
            self.consecutive_successes = row["consecutive_successes"]
            self.consecutive_failures = row["consecutive_failures"]
            self._ysd_sum = row["ysd_sum"]
            self._ysd_count = row["ysd_count"]
        else:
            await self._save_state()

    async def _save_state(self) -> None:
        if not self._db:
            return
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        await self._db.execute(
            "INSERT OR REPLACE INTO graduation_state "
            "(id, current_level, consecutive_successes, consecutive_failures, "
            "ysd_sum, ysd_count, updated_at) VALUES (1, ?, ?, ?, ?, ?, ?)",
            (
                int(self.level), self.consecutive_successes,
                self.consecutive_failures, self._ysd_sum, self._ysd_count, now,
            ),
        )
        await self._db.commit()

    async def record_action(
        self,
        action_type: str,
        success: bool,
        ysd_score: float = 5.0,
        gate_blocked: bool = False,
    ) -> AutonomyLevel:
        """Record an action outcome and return the (possibly changed) autonomy level."""
        level_before = self.level

        if gate_blocked or not success:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
        else:
            self.consecutive_successes += 1
            self.consecutive_failures = 0
            self._ysd_sum += ysd_score
            self._ysd_count += 1

        # Check demotion first (takes priority)
        if self.consecutive_failures >= _DEMOTION_FAILURES or gate_blocked:
            if self.level > AutonomyLevel.HUMAN_ON_LOOP:
                self.level = AutonomyLevel(max(int(self.level) - 1, 2))
                self.consecutive_successes = 0
                self._ysd_sum = 0.0
                self._ysd_count = 0
                logger.warning(
                    "Graduation DEMOTION: %s → %s (failures=%d, gate_blocked=%s)",
                    level_before.name, self.level.name,
                    self.consecutive_failures, gate_blocked,
                )

        # Check promotion
        elif self.level == AutonomyLevel.HUMAN_ON_LOOP:
            if (self.consecutive_successes >= _PROMOTE_TO_3_SUCCESSES
                    and self.mean_ysd >= _PROMOTE_TO_3_MIN_YSD):
                self.level = AutonomyLevel.AUTONOMOUS_ALERT
                self.consecutive_successes = 0
                self._ysd_sum = 0.0
                self._ysd_count = 0
                logger.info("Graduation PROMOTION: HUMAN_ON_LOOP → AUTONOMOUS_ALERT")

        elif self.level == AutonomyLevel.AUTONOMOUS_ALERT:
            if (self.consecutive_successes >= _PROMOTE_TO_4_SUCCESSES
                    and self.mean_ysd >= _PROMOTE_TO_4_MIN_YSD):
                self.level = AutonomyLevel.FULLY_AUTONOMOUS
                logger.info("Graduation PROMOTION: AUTONOMOUS_ALERT → FULLY_AUTONOMOUS")

        # Persist
        await self._save_state()
        await self._record_history(action_type, success, ysd_score, gate_blocked, level_before)

        return self.level

    async def _record_history(
        self, action_type: str, success: bool, ysd_score: float,
        gate_blocked: bool, level_before: AutonomyLevel,
    ) -> None:
        if not self._db:
            return
        from dharma_swarm.models import _new_id
        await self._db.execute(
            "INSERT INTO graduation_history "
            "(id, timestamp, action_type, success, ysd_score, gate_blocked, "
            "level_before, level_after) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _new_id(), time.time(), action_type, int(success),
                ysd_score, int(gate_blocked), int(level_before), int(self.level),
            ),
        )
        await self._db.commit()

    def should_require_approval(self, risk: RiskLevel) -> bool:
        """Check if the current autonomy level requires human approval for this risk."""
        # CRITICAL always needs approval — hardcoded, never graduated
        if risk == RiskLevel.CRITICAL:
            return True

        if self.level == AutonomyLevel.MANUAL:
            return True
        elif self.level == AutonomyLevel.HUMAN_ON_LOOP:
            return risk >= RiskLevel.MEDIUM
        elif self.level == AutonomyLevel.AUTONOMOUS_ALERT:
            return risk >= RiskLevel.HIGH
        else:  # FULLY_AUTONOMOUS
            return False

    def status_dict(self) -> dict[str, Any]:
        return {
            "level": self.level.name,
            "level_value": int(self.level),
            "consecutive_successes": self.consecutive_successes,
            "consecutive_failures": self.consecutive_failures,
            "mean_ysd": round(self.mean_ysd, 4),
            "ysd_count": self._ysd_count,
        }


__all__ = ["GraduationEngine", "AutonomyLevel", "RiskLevel"]
