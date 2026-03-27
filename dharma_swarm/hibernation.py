"""Hibernate-and-Wake State Machine for DHARMA SWARM.

Enables agents to hibernate (persist full state) when waiting for external
conditions, and automatically resume when conditions are met.  Inspired by
Meta's REA agent pattern for multi-day autonomous operation.

Integration points:
    - Organism heartbeat: ``check_conditions()`` called each tick
    - Orchestrator tick: ``get_ready_jobs()`` checked before dispatch
    - Agent runner: ``hibernate()`` called when agent needs to wait

Persistence: SQLite via aiosqlite, following the same patterns as
``runtime_state.py`` and ``graph_store.py``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ── Enums ──────────────────────────────────────────────────────────────

class JobState(str, Enum):
    """Lifecycle states for a hibernateable job."""
    PENDING = "pending"
    RUNNING = "running"
    WAITING_EXTERNAL = "waiting_external"
    READY_TO_RESUME = "ready_to_resume"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Valid state transitions
_VALID_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.PENDING: {JobState.RUNNING, JobState.CANCELLED},
    JobState.RUNNING: {
        JobState.WAITING_EXTERNAL,
        JobState.COMPLETED,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.WAITING_EXTERNAL: {
        JobState.READY_TO_RESUME,
        JobState.FAILED,
        JobState.CANCELLED,
    },
    JobState.READY_TO_RESUME: {JobState.RUNNING, JobState.CANCELLED},
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
    JobState.CANCELLED: set(),
}


# ── Data classes ───────────────────────────────────────────────────────

@dataclass
class WakeCondition:
    """Defines what triggers an agent to resume from hibernation.

    Attributes:
        condition_type: Kind of condition — "time", "file_exists",
            "api_response", "evolution_complete", "training_done", "custom".
        check_fn: Name of a registered check function (for ``custom`` type).
        params: Condition-specific parameters (e.g. ``{"wait_seconds": 3600}``).
        poll_interval_seconds: How often to check (during heartbeat ticks).
    """
    condition_type: str
    check_fn: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    poll_interval_seconds: int = 60

    def to_dict(self) -> dict[str, Any]:
        return {
            "condition_type": self.condition_type,
            "check_fn": self.check_fn,
            "params": self.params,
            "poll_interval_seconds": self.poll_interval_seconds,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WakeCondition:
        return cls(
            condition_type=data.get("condition_type", "custom"),
            check_fn=data.get("check_fn"),
            params=data.get("params", {}),
            poll_interval_seconds=data.get("poll_interval_seconds", 60),
        )


@dataclass
class HibernateableJob:
    """A job that supports hibernate-and-wake lifecycle.

    Attributes:
        job_id: Unique identifier.
        state: Current lifecycle state.
        agent_id: Which agent owns this job.
        context_snapshot: Full agent context at hibernation time.
        wake_condition: What must be true to resume.
        hibernated_at: When the agent went to sleep.
        resumed_at: When the agent woke up.
        max_wait_seconds: Timeout for external waits.
        retry_count: How many times this job has been retried.
        metadata: Arbitrary job metadata.
        created_at: When the job was first created.
    """
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    state: JobState = JobState.PENDING
    agent_id: str = ""
    context_snapshot: dict[str, Any] = field(default_factory=dict)
    wake_condition: WakeCondition | None = None
    hibernated_at: datetime | None = None
    resumed_at: datetime | None = None
    max_wait_seconds: int = 86400  # 24 hours default
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state.value,
            "agent_id": self.agent_id,
            "context_snapshot": self.context_snapshot,
            "wake_condition": self.wake_condition.to_dict() if self.wake_condition else None,
            "hibernated_at": self.hibernated_at.isoformat() if self.hibernated_at else None,
            "resumed_at": self.resumed_at.isoformat() if self.resumed_at else None,
            "max_wait_seconds": self.max_wait_seconds,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HibernateableJob:
        wake_cond = data.get("wake_condition")
        return cls(
            job_id=data["job_id"],
            state=JobState(data["state"]),
            agent_id=data.get("agent_id", ""),
            context_snapshot=data.get("context_snapshot", {}),
            wake_condition=WakeCondition.from_dict(wake_cond) if wake_cond else None,
            hibernated_at=(
                datetime.fromisoformat(data["hibernated_at"])
                if data.get("hibernated_at")
                else None
            ),
            resumed_at=(
                datetime.fromisoformat(data["resumed_at"])
                if data.get("resumed_at")
                else None
            ),
            max_wait_seconds=data.get("max_wait_seconds", 86400),
            retry_count=data.get("retry_count", 0),
            metadata=data.get("metadata", {}),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if data.get("created_at")
                else datetime.now(timezone.utc)
            ),
        )


# ── Condition checkers ─────────────────────────────────────────────────

# Registry for custom check functions.
_CONDITION_REGISTRY: dict[str, Callable[..., bool]] = {}


def register_condition(name: str, fn: Callable[..., bool]) -> None:
    """Register a named condition checker for use in WakeCondition."""
    _CONDITION_REGISTRY[name] = fn


def _check_time_condition(params: dict[str, Any], hibernated_at: datetime | None) -> bool:
    """True when ``wait_seconds`` have elapsed since hibernation."""
    wait = params.get("wait_seconds", 0)
    if hibernated_at is None:
        return False
    elapsed = (datetime.now(timezone.utc) - hibernated_at).total_seconds()
    return elapsed >= wait


def _check_file_exists_condition(params: dict[str, Any], **_: Any) -> bool:
    """True when a specified file path exists."""
    path = params.get("path", "")
    return bool(path) and Path(path).exists()


def _default_check(condition: WakeCondition, job: HibernateableJob) -> bool:
    """Evaluate a WakeCondition against a HibernateableJob."""
    ctype = condition.condition_type.lower()
    if ctype == "time":
        return _check_time_condition(condition.params, job.hibernated_at)
    if ctype == "file_exists":
        return _check_file_exists_condition(condition.params)
    if ctype in ("custom", "api_response", "evolution_complete", "training_done"):
        fn_name = condition.check_fn or ctype
        fn = _CONDITION_REGISTRY.get(fn_name)
        if fn is not None:
            try:
                return bool(fn(condition.params, job=job))
            except Exception as exc:
                logger.debug("Condition check %r failed: %s", fn_name, exc)
                return False
        logger.debug("No registered checker for %r", fn_name)
        return False
    logger.debug("Unknown condition type %r", ctype)
    return False


# ── HibernationManager ─────────────────────────────────────────────────

class HibernationManager:
    """Manages the hibernate-and-wake lifecycle for swarm jobs.

    Persists job state to SQLite.  Designed to be called from:
        - organism heartbeat  → ``check_conditions()``
        - orchestrator tick   → ``get_ready_jobs()``
        - agent runner        → ``hibernate()``

    Args:
        state_dir: Directory for the SQLite database file.
    """

    _DDL = """\
    CREATE TABLE IF NOT EXISTS hibernation_jobs (
        job_id          TEXT PRIMARY KEY,
        state           TEXT NOT NULL DEFAULT 'pending',
        agent_id        TEXT NOT NULL DEFAULT '',
        context_snapshot TEXT NOT NULL DEFAULT '{}',
        wake_condition  TEXT,
        hibernated_at   TEXT,
        resumed_at      TEXT,
        max_wait_seconds INTEGER NOT NULL DEFAULT 86400,
        retry_count     INTEGER NOT NULL DEFAULT 0,
        metadata        TEXT NOT NULL DEFAULT '{}',
        created_at      TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS idx_hib_state ON hibernation_jobs(state);
    CREATE INDEX IF NOT EXISTS idx_hib_agent ON hibernation_jobs(agent_id);
    """

    def __init__(self, state_dir: str | Path | None = None) -> None:
        if state_dir is None:
            state_dir = os.environ.get(
                "DHARMA_STATE_DIR",
                str(Path.home() / ".dharma" / "state"),
            )
        self._state_dir = Path(state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = self._state_dir / "hibernation.db"
        self._db: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()
        self._initialized = False

    # ── Lifecycle ──────────────────────────────────────────────────

    async def init_db(self) -> None:
        """Initialise the SQLite database (idempotent)."""
        if self._initialized:
            return
        async with self._lock:
            if self._initialized:
                return
            try:
                import aiosqlite

                db = await aiosqlite.connect(str(self._db_path))
                await db.execute("PRAGMA journal_mode=WAL")
                await db.execute("PRAGMA foreign_keys=ON")
                await db.execute("PRAGMA synchronous=NORMAL")
                await db.executescript(self._DDL)
                await db.commit()
                self._db = db  # type: ignore[assignment]
                self._initialized = True
                logger.info("HibernationManager DB ready: %s", self._db_path)
            except ImportError:
                # Fall back to sync sqlite3 when aiosqlite is not available
                db = sqlite3.connect(str(self._db_path))
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA synchronous=NORMAL")
                db.executescript(self._DDL)
                db.commit()
                self._db = db
                self._initialized = True
                logger.info(
                    "HibernationManager DB ready (sync fallback): %s",
                    self._db_path,
                )

    async def close(self) -> None:
        if self._db is not None:
            try:
                if hasattr(self._db, "close"):
                    result = self._db.close()  # type: ignore[union-attr]
                    if asyncio.iscoroutine(result):
                        await result
            except Exception:
                pass
            self._db = None
            self._initialized = False

    # ── Core operations ────────────────────────────────────────────

    async def create_job(
        self,
        *,
        agent_id: str,
        context_snapshot: dict[str, Any] | None = None,
        max_wait_seconds: int = 86400,
        metadata: dict[str, Any] | None = None,
    ) -> HibernateableJob:
        """Create a new hibernateable job in PENDING state."""
        await self.init_db()
        job = HibernateableJob(
            agent_id=agent_id,
            context_snapshot=context_snapshot or {},
            max_wait_seconds=max_wait_seconds,
            metadata=metadata or {},
        )
        await self._save_job(job)
        logger.info("Created hibernateable job %s for agent %s", job.job_id, agent_id)
        return job

    async def hibernate(
        self,
        job_id: str,
        context_snapshot: dict[str, Any],
        wake_condition: WakeCondition,
    ) -> HibernateableJob:
        """Transition a job to WAITING_EXTERNAL (hibernate).

        Persists the full agent context and the condition that must be met
        before the job can resume.
        """
        await self.init_db()
        job = await self.get_job(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        self._validate_transition(job.state, JobState.WAITING_EXTERNAL)
        job.state = JobState.WAITING_EXTERNAL
        job.context_snapshot = context_snapshot
        job.wake_condition = wake_condition
        job.hibernated_at = datetime.now(timezone.utc)
        await self._save_job(job)
        logger.info(
            "Job %s hibernated (agent=%s, condition=%s)",
            job_id,
            job.agent_id,
            wake_condition.condition_type,
        )
        return job

    async def wake(self, job_id: str) -> HibernateableJob:
        """Transition a job to READY_TO_RESUME (wake)."""
        await self.init_db()
        job = await self.get_job(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        self._validate_transition(job.state, JobState.READY_TO_RESUME)
        job.state = JobState.READY_TO_RESUME
        job.resumed_at = datetime.now(timezone.utc)
        await self._save_job(job)
        logger.info("Job %s ready to resume (agent=%s)", job_id, job.agent_id)
        return job

    async def transition(self, job_id: str, new_state: JobState) -> HibernateableJob:
        """Generic state transition with validation."""
        await self.init_db()
        job = await self.get_job(job_id)
        if job is None:
            raise ValueError(f"Job {job_id} not found")
        self._validate_transition(job.state, new_state)
        job.state = new_state
        await self._save_job(job)
        logger.info("Job %s → %s", job_id, new_state.value)
        return job

    async def check_conditions(self) -> int:
        """Check all WAITING_EXTERNAL jobs and wake those whose conditions are met.

        Called from the organism heartbeat.  Returns the number of jobs woken.
        """
        await self.init_db()
        waiting = await self.list_jobs(state=JobState.WAITING_EXTERNAL)
        woken = 0
        for job in waiting:
            if job.wake_condition is None:
                continue
            try:
                if _default_check(job.wake_condition, job):
                    await self.wake(job.job_id)
                    woken += 1
            except Exception as exc:
                logger.debug("Condition check failed for job %s: %s", job.job_id, exc)
        return woken

    async def timeout_check(self) -> int:
        """Fail jobs that have exceeded their max_wait_seconds.

        Returns the number of jobs timed out.
        """
        await self.init_db()
        waiting = await self.list_jobs(state=JobState.WAITING_EXTERNAL)
        timed_out = 0
        now = datetime.now(timezone.utc)
        for job in waiting:
            if job.hibernated_at is None:
                continue
            elapsed = (now - job.hibernated_at).total_seconds()
            if elapsed > job.max_wait_seconds:
                try:
                    job.state = JobState.FAILED
                    job.metadata["failure_reason"] = "timeout"
                    job.metadata["elapsed_seconds"] = elapsed
                    await self._save_job(job)
                    timed_out += 1
                    logger.warning(
                        "Job %s timed out after %.0fs (max=%ds)",
                        job.job_id,
                        elapsed,
                        job.max_wait_seconds,
                    )
                except Exception as exc:
                    logger.debug("Timeout transition failed for %s: %s", job.job_id, exc)
        return timed_out

    async def get_ready_jobs(self) -> list[HibernateableJob]:
        """Return all jobs in READY_TO_RESUME state (for orchestrator dispatch)."""
        return await self.list_jobs(state=JobState.READY_TO_RESUME)

    # ── Query helpers ──────────────────────────────────────────────

    async def get_job(self, job_id: str) -> HibernateableJob | None:
        """Fetch a single job by ID."""
        await self.init_db()
        row = await self._fetchone(
            "SELECT * FROM hibernation_jobs WHERE job_id = ?", (job_id,),
        )
        if row is None:
            return None
        return self._row_to_job(row)

    async def list_jobs(
        self,
        *,
        state: JobState | None = None,
        agent_id: str | None = None,
        limit: int = 100,
    ) -> list[HibernateableJob]:
        """List jobs with optional state/agent filter."""
        await self.init_db()
        clauses: list[str] = []
        params: list[Any] = []
        if state is not None:
            clauses.append("state = ?")
            params.append(state.value)
        if agent_id is not None:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"SELECT * FROM hibernation_jobs{where} ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self._fetchall(sql, tuple(params))
        return [self._row_to_job(row) for row in rows]

    async def count_jobs(self, state: JobState | None = None) -> int:
        """Count jobs, optionally filtered by state."""
        await self.init_db()
        if state is not None:
            row = await self._fetchone(
                "SELECT COUNT(*) FROM hibernation_jobs WHERE state = ?",
                (state.value,),
            )
        else:
            row = await self._fetchone("SELECT COUNT(*) FROM hibernation_jobs", ())
        return row[0] if row else 0

    # ── Internals ──────────────────────────────────────────────────

    @staticmethod
    def _validate_transition(current: JobState, target: JobState) -> None:
        allowed = _VALID_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid state transition: {current.value} → {target.value}"
            )

    async def _save_job(self, job: HibernateableJob) -> None:
        sql = """\
        INSERT INTO hibernation_jobs
            (job_id, state, agent_id, context_snapshot, wake_condition,
             hibernated_at, resumed_at, max_wait_seconds, retry_count,
             metadata, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(job_id) DO UPDATE SET
            state = excluded.state,
            agent_id = excluded.agent_id,
            context_snapshot = excluded.context_snapshot,
            wake_condition = excluded.wake_condition,
            hibernated_at = excluded.hibernated_at,
            resumed_at = excluded.resumed_at,
            max_wait_seconds = excluded.max_wait_seconds,
            retry_count = excluded.retry_count,
            metadata = excluded.metadata
        """
        params = (
            job.job_id,
            job.state.value,
            job.agent_id,
            json.dumps(job.context_snapshot),
            json.dumps(job.wake_condition.to_dict()) if job.wake_condition else None,
            job.hibernated_at.isoformat() if job.hibernated_at else None,
            job.resumed_at.isoformat() if job.resumed_at else None,
            job.max_wait_seconds,
            job.retry_count,
            json.dumps(job.metadata),
            job.created_at.isoformat(),
        )
        await self._execute(sql, params)

    async def _execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        assert self._db is not None, "DB not initialised — call init_db() first"
        try:
            if hasattr(self._db, "execute_insert"):
                # aiosqlite
                await self._db.execute(sql, params)  # type: ignore[union-attr]
                await self._db.commit()  # type: ignore[union-attr]
            else:
                # sync sqlite3
                self._db.execute(sql, params)
                self._db.commit()
        except Exception:
            logger.debug("SQL execute failed", exc_info=True)
            raise

    async def _fetchone(
        self, sql: str, params: tuple[Any, ...] = (),
    ) -> Any:
        assert self._db is not None, "DB not initialised — call init_db() first"
        if hasattr(self._db, "execute_fetchall"):
            # aiosqlite
            cursor = await self._db.execute(sql, params)  # type: ignore[union-attr]
            return await cursor.fetchone()
        else:
            cursor = self._db.execute(sql, params)
            return cursor.fetchone()

    async def _fetchall(
        self, sql: str, params: tuple[Any, ...] = (),
    ) -> list[Any]:
        assert self._db is not None, "DB not initialised — call init_db() first"
        if hasattr(self._db, "execute_fetchall"):
            # aiosqlite
            cursor = await self._db.execute(sql, params)  # type: ignore[union-attr]
            return await cursor.fetchall()
        else:
            cursor = self._db.execute(sql, params)
            return cursor.fetchall()

    @staticmethod
    def _row_to_job(row: Any) -> HibernateableJob:
        """Convert a SQLite row to a HibernateableJob."""
        # Row indices match column order in _DDL
        wake_raw = row[4]
        return HibernateableJob(
            job_id=row[0],
            state=JobState(row[1]),
            agent_id=row[2],
            context_snapshot=json.loads(row[3]) if row[3] else {},
            wake_condition=(
                WakeCondition.from_dict(json.loads(wake_raw)) if wake_raw else None
            ),
            hibernated_at=(
                datetime.fromisoformat(row[5]) if row[5] else None
            ),
            resumed_at=(
                datetime.fromisoformat(row[6]) if row[6] else None
            ),
            max_wait_seconds=row[7],
            retry_count=row[8],
            metadata=json.loads(row[9]) if row[9] else {},
            created_at=datetime.fromisoformat(row[10]),
        )
