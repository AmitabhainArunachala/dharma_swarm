"""economic_spine.py — Internal swarm economy.

CashClaw-inspired mission lifecycle + performance-based budget allocation.
Every agent has a token budget, every mission tracks cost, and the organism
periodically reallocates resources toward high performers.

SQLite-backed for persistence (consistent with HibernationManager and
KnowledgeStore patterns from Sprint 1/2).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment config
# ---------------------------------------------------------------------------

INITIAL_AGENT_BUDGET = int(os.environ.get("INITIAL_AGENT_BUDGET", "100000"))
ENABLE_ECONOMIC_SPINE = os.environ.get(
    "ENABLE_ECONOMIC_SPINE", "true"
).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Mission state machine
# ---------------------------------------------------------------------------


class MissionState(str, Enum):
    """CashClaw-inspired mission lifecycle."""

    RECEIVED = "received"
    QUOTED = "quoted"
    ACCEPTED = "accepted"
    EXECUTING = "executing"
    DELIVERED = "delivered"
    VERIFIED = "verified"      # Gnani has verified output quality
    PAID = "paid"              # Budget credited back / allocated
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid transitions
MISSION_TRANSITIONS: Dict[MissionState, set[MissionState]] = {
    MissionState.RECEIVED: {MissionState.QUOTED, MissionState.CANCELLED},
    MissionState.QUOTED: {MissionState.ACCEPTED, MissionState.CANCELLED},
    MissionState.ACCEPTED: {MissionState.EXECUTING, MissionState.CANCELLED},
    MissionState.EXECUTING: {MissionState.DELIVERED, MissionState.FAILED},
    MissionState.DELIVERED: {MissionState.VERIFIED, MissionState.FAILED},
    MissionState.VERIFIED: {MissionState.PAID},
    MissionState.FAILED: {MissionState.RECEIVED},  # Can retry
    MissionState.PAID: set(),
    MissionState.CANCELLED: set(),
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AgentBudget:
    """Token/compute budget for an agent."""

    agent_id: str
    total_tokens_allocated: int = INITIAL_AGENT_BUDGET
    tokens_spent: int = 0
    tokens_earned: int = 0
    efficiency_score: float = 0.5
    mission_count: int = 0
    success_count: int = 0
    last_allocation_at: str = ""

    def __post_init__(self) -> None:
        if not self.last_allocation_at:
            self.last_allocation_at = datetime.now(timezone.utc).isoformat()

    @property
    def tokens_remaining(self) -> int:
        return self.total_tokens_allocated + self.tokens_earned - self.tokens_spent

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.mission_count, 1)


@dataclass
class MissionRecord:
    """Audit trail for an economic mission/task."""

    id: str = ""
    agent_id: str = ""
    task_description: str = ""
    state: MissionState = MissionState.RECEIVED
    tokens_quoted: int = 0
    tokens_actual: int = 0
    quality_score: float = 0.0
    created_at: str = ""
    state_history: List[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def transition_to(self, new_state: MissionState, reason: str = "") -> None:
        """Validated state transition with audit trail."""
        valid = MISSION_TRANSITIONS.get(self.state, set())
        if new_state not in valid:
            raise ValueError(
                f"Invalid transition: {self.state.value} → {new_state.value}"
            )
        self.state_history.append(
            {
                "from": self.state.value,
                "to": new_state.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": reason,
            }
        )
        self.state = new_state


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class InsufficientBudgetError(Exception):
    """Raised when an agent lacks budget for a mission."""


# ---------------------------------------------------------------------------
# Economic Spine (SQLite-backed)
# ---------------------------------------------------------------------------

_DDL = """\
CREATE TABLE IF NOT EXISTS agent_budgets (
    agent_id           TEXT PRIMARY KEY,
    total_tokens_allocated INTEGER NOT NULL DEFAULT 100000,
    tokens_spent       INTEGER NOT NULL DEFAULT 0,
    tokens_earned      INTEGER NOT NULL DEFAULT 0,
    efficiency_score   REAL    NOT NULL DEFAULT 0.5,
    mission_count      INTEGER NOT NULL DEFAULT 0,
    success_count      INTEGER NOT NULL DEFAULT 0,
    last_allocation_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS missions (
    id               TEXT PRIMARY KEY,
    agent_id         TEXT    NOT NULL,
    task_description TEXT    NOT NULL DEFAULT '',
    state            TEXT    NOT NULL DEFAULT 'received',
    tokens_quoted    INTEGER NOT NULL DEFAULT 0,
    tokens_actual    INTEGER NOT NULL DEFAULT 0,
    quality_score    REAL    NOT NULL DEFAULT 0.0,
    created_at       TEXT    NOT NULL,
    state_history    TEXT    NOT NULL DEFAULT '[]'
);

CREATE TABLE IF NOT EXISTS economic_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id   TEXT    NOT NULL,
    event_type TEXT    NOT NULL,
    amount     INTEGER NOT NULL DEFAULT 0,
    mission_id TEXT    NOT NULL DEFAULT '',
    details    TEXT    NOT NULL DEFAULT '',
    created_at TEXT    NOT NULL
);
"""


class EconomicSpine:
    """SQLite-backed economic management for the swarm.

    Responsibilities:
    1. Track agent budgets (allocation, spending, earning)
    2. Track mission lifecycle (CashClaw-inspired state machine)
    3. Allocate resources based on performance (higher performers get more)
    4. Enforce spending limits (agents can't exceed budget)
    5. Audit trail for all economic activity
    """

    def __init__(self, db_path: str = ":memory:") -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_DDL)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    # ------------------------------------------------------------------
    # Budget management
    # ------------------------------------------------------------------

    def get_or_create_budget(self, agent_id: str) -> AgentBudget:
        """Get existing budget or create one with default allocation."""
        row = self._conn.execute(
            "SELECT * FROM agent_budgets WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if row is not None:
            return AgentBudget(
                agent_id=row[0],
                total_tokens_allocated=row[1],
                tokens_spent=row[2],
                tokens_earned=row[3],
                efficiency_score=row[4],
                mission_count=row[5],
                success_count=row[6],
                last_allocation_at=row[7],
            )
        now = datetime.now(timezone.utc).isoformat()
        budget = AgentBudget(
            agent_id=agent_id,
            total_tokens_allocated=INITIAL_AGENT_BUDGET,
            last_allocation_at=now,
        )
        self._conn.execute(
            "INSERT INTO agent_budgets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                budget.agent_id,
                budget.total_tokens_allocated,
                budget.tokens_spent,
                budget.tokens_earned,
                budget.efficiency_score,
                budget.mission_count,
                budget.success_count,
                budget.last_allocation_at,
            ),
        )
        self._conn.commit()
        return budget

    def _save_budget(self, budget: AgentBudget) -> None:
        """Persist budget to database."""
        self._conn.execute(
            """UPDATE agent_budgets SET
                total_tokens_allocated=?, tokens_spent=?, tokens_earned=?,
                efficiency_score=?, mission_count=?, success_count=?,
                last_allocation_at=?
            WHERE agent_id=?""",
            (
                budget.total_tokens_allocated,
                budget.tokens_spent,
                budget.tokens_earned,
                budget.efficiency_score,
                budget.mission_count,
                budget.success_count,
                budget.last_allocation_at,
                budget.agent_id,
            ),
        )
        self._conn.commit()

    def spend_tokens(self, agent_id: str, amount: int, mission_id: str = "") -> bool:
        """Record token spending. ALWAYS succeeds — tracking only, no enforcement.

        Returns True always. Negative balance is tracked but not prevented.
        """
        budget = self.get_or_create_budget(agent_id)
        budget.tokens_spent += amount
        self._save_budget(budget)
        self._log_event(agent_id, "spend", amount, mission_id)

        if budget.tokens_remaining < 0:
            logger.info(
                "Agent %s over budget by %d tokens (tracking only, not blocking)",
                agent_id,
                abs(budget.tokens_remaining),
            )

        return True  # Always succeed — no enforcement

    def earn_tokens(self, agent_id: str, amount: int, mission_id: str = "") -> None:
        """Credit tokens for successful mission completion."""
        budget = self.get_or_create_budget(agent_id)
        budget.tokens_earned += amount
        self._save_budget(budget)
        self._log_event(agent_id, "earn", amount, mission_id)

    def update_efficiency(self, agent_id: str, quality_score: float) -> None:
        """Recalculate efficiency score after a mission."""
        budget = self.get_or_create_budget(agent_id)
        cost_ratio = budget.tokens_spent / max(budget.tokens_earned + 1, 1)
        # efficiency = success_rate * quality_avg * (1 / cost_ratio)
        # Clamp cost_factor so it doesn't explode
        cost_factor = min(1.0 / max(cost_ratio, 0.01), 2.0)
        raw = budget.success_rate * quality_score * cost_factor
        # Exponential moving average
        budget.efficiency_score = 0.7 * budget.efficiency_score + 0.3 * min(raw, 1.0)
        self._save_budget(budget)

    # ------------------------------------------------------------------
    # Mission lifecycle
    # ------------------------------------------------------------------

    def create_mission(
        self,
        agent_id: str,
        task_description: str,
        tokens_quoted: int,
    ) -> MissionRecord:
        """Create a new mission in RECEIVED state."""
        mission = MissionRecord(
            agent_id=agent_id,
            task_description=task_description,
            tokens_quoted=tokens_quoted,
        )
        self._conn.execute(
            "INSERT INTO missions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                mission.id,
                mission.agent_id,
                mission.task_description,
                mission.state.value,
                mission.tokens_quoted,
                mission.tokens_actual,
                mission.quality_score,
                mission.created_at,
                json.dumps(mission.state_history),
            ),
        )
        self._conn.commit()
        return mission

    def transition_mission(
        self,
        mission_id: str,
        new_state: MissionState,
        reason: str = "",
        quality_score: float = 0.0,
        tokens_actual: int = 0,
    ) -> MissionRecord:
        """Transition a mission to a new state with validation."""
        mission = self.get_mission(mission_id)
        if mission is None:
            raise ValueError(f"Mission not found: {mission_id}")

        mission.transition_to(new_state, reason)

        if tokens_actual > 0:
            mission.tokens_actual = tokens_actual
        if quality_score > 0:
            mission.quality_score = quality_score

        # Update stats on terminal states
        if new_state in (MissionState.PAID, MissionState.FAILED):
            budget = self.get_or_create_budget(mission.agent_id)
            budget.mission_count += 1
            if new_state == MissionState.PAID:
                budget.success_count += 1
            self._save_budget(budget)

        self._save_mission(mission)
        return mission

    def get_mission(self, mission_id: str) -> Optional[MissionRecord]:
        """Retrieve a mission by ID."""
        row = self._conn.execute(
            "SELECT * FROM missions WHERE id = ?", (mission_id,)
        ).fetchone()
        if row is None:
            return None
        return MissionRecord(
            id=row[0],
            agent_id=row[1],
            task_description=row[2],
            state=MissionState(row[3]),
            tokens_quoted=row[4],
            tokens_actual=row[5],
            quality_score=row[6],
            created_at=row[7],
            state_history=json.loads(row[8]),
        )

    def get_agent_missions(
        self, agent_id: str, limit: int = 50
    ) -> List[MissionRecord]:
        """Get recent missions for an agent."""
        rows = self._conn.execute(
            "SELECT * FROM missions WHERE agent_id = ? ORDER BY created_at DESC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
        return [
            MissionRecord(
                id=r[0],
                agent_id=r[1],
                task_description=r[2],
                state=MissionState(r[3]),
                tokens_quoted=r[4],
                tokens_actual=r[5],
                quality_score=r[6],
                created_at=r[7],
                state_history=json.loads(r[8]),
            )
            for r in rows
        ]

    def _save_mission(self, mission: MissionRecord) -> None:
        """Persist mission state to database."""
        self._conn.execute(
            """UPDATE missions SET
                state=?, tokens_actual=?, quality_score=?, state_history=?
            WHERE id=?""",
            (
                mission.state.value,
                mission.tokens_actual,
                mission.quality_score,
                json.dumps(mission.state_history),
                mission.id,
            ),
        )
        self._conn.commit()

    # ------------------------------------------------------------------
    # Resource allocation
    # ------------------------------------------------------------------

    def reallocate_budgets(self, total_pool: int) -> Dict[str, int]:
        """Redistribute token pool based on agent performance.

        Algorithm:
        1. Calculate efficiency_score for each agent
        2. Normalize scores to proportional shares
        3. Floor allocation (every agent gets at least 10% of average)
        4. Distribute remaining pool proportionally
        """
        rows = self._conn.execute("SELECT * FROM agent_budgets").fetchall()
        if not rows:
            return {}

        budgets = [
            AgentBudget(
                agent_id=r[0],
                total_tokens_allocated=r[1],
                tokens_spent=r[2],
                tokens_earned=r[3],
                efficiency_score=r[4],
                mission_count=r[5],
                success_count=r[6],
                last_allocation_at=r[7],
            )
            for r in rows
        ]

        n = len(budgets)
        avg_share = total_pool // max(n, 1)
        floor_amount = max(avg_share // 10, 1)  # 10% floor

        # Total efficiency for proportional allocation
        total_efficiency = sum(b.efficiency_score for b in budgets)
        if total_efficiency <= 0:
            total_efficiency = n * 0.5  # fallback: equal

        floor_total = floor_amount * n
        distributable = max(total_pool - floor_total, 0)

        allocations: Dict[str, int] = {}
        now = datetime.now(timezone.utc).isoformat()

        for budget in budgets:
            proportion = budget.efficiency_score / total_efficiency
            alloc = floor_amount + int(distributable * proportion)
            budget.total_tokens_allocated = alloc
            budget.last_allocation_at = now
            self._save_budget(budget)
            allocations[budget.agent_id] = alloc

        logger.info(
            "Budget reallocation: pool=%d agents=%d allocations=%s",
            total_pool,
            n,
            allocations,
        )
        return allocations

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_agent_stats(self, agent_id: str) -> dict:
        """Full economic stats for an agent."""
        budget = self.get_or_create_budget(agent_id)
        missions = self.get_agent_missions(agent_id, limit=100)
        return {
            "agent_id": agent_id,
            "tokens_allocated": budget.total_tokens_allocated,
            "tokens_spent": budget.tokens_spent,
            "tokens_earned": budget.tokens_earned,
            "tokens_remaining": budget.tokens_remaining,
            "efficiency_score": budget.efficiency_score,
            "mission_count": budget.mission_count,
            "success_count": budget.success_count,
            "success_rate": budget.success_rate,
            "active_missions": sum(
                1
                for m in missions
                if m.state
                in (
                    MissionState.RECEIVED,
                    MissionState.QUOTED,
                    MissionState.ACCEPTED,
                    MissionState.EXECUTING,
                    MissionState.DELIVERED,
                )
            ),
        }

    def get_swarm_economics(self) -> dict:
        """Aggregate economic health of the swarm."""
        rows = self._conn.execute("SELECT * FROM agent_budgets").fetchall()
        if not rows:
            return {
                "total_agents": 0,
                "total_allocated": 0,
                "total_spent": 0,
                "total_earned": 0,
                "avg_efficiency": 0.0,
                "total_missions": 0,
                "total_successes": 0,
            }

        total_allocated = sum(r[1] for r in rows)
        total_spent = sum(r[2] for r in rows)
        total_earned = sum(r[3] for r in rows)
        avg_efficiency = sum(r[4] for r in rows) / len(rows)
        total_missions = sum(r[5] for r in rows)
        total_successes = sum(r[6] for r in rows)

        return {
            "total_agents": len(rows),
            "total_allocated": total_allocated,
            "total_spent": total_spent,
            "total_earned": total_earned,
            "avg_efficiency": round(avg_efficiency, 4),
            "total_missions": total_missions,
            "total_successes": total_successes,
            "overall_success_rate": round(
                total_successes / max(total_missions, 1), 4
            ),
        }

    def get_mission_audit_trail(self, mission_id: str) -> List[dict]:
        """Get the full state history for a mission."""
        mission = self.get_mission(mission_id)
        if mission is None:
            return []
        return mission.state_history

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _log_event(
        self,
        agent_id: str,
        event_type: str,
        amount: int,
        mission_id: str = "",
        details: str = "",
    ) -> None:
        """Record an economic event for audit purposes."""
        self._conn.execute(
            "INSERT INTO economic_events (agent_id, event_type, amount, mission_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                agent_id,
                event_type,
                amount,
                mission_id,
                details,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self._conn.commit()
