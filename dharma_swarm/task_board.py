"""Async task management with CRUD, dependency tracking, and status FSM.

Persistence via aiosqlite. Status transitions validated against an explicit
finite-state machine so illegal moves (e.g. COMPLETED -> PENDING) raise.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import aiosqlite

from dharma_swarm.models import Task, TaskPriority, TaskStatus, _new_id, _utc_now
from dharma_swarm.telos_gates import check_with_reflective_reroute

_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.ASSIGNED, TaskStatus.CANCELLED},
    TaskStatus.ASSIGNED: {TaskStatus.RUNNING, TaskStatus.CANCELLED, TaskStatus.PENDING},
    TaskStatus.RUNNING: {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED},
    TaskStatus.COMPLETED: set(),
    TaskStatus.FAILED: {TaskStatus.PENDING},
    TaskStatus.CANCELLED: {TaskStatus.PENDING},
}

_CREATE_TASKS = """
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending', priority TEXT NOT NULL DEFAULT 'normal',
    assigned_to TEXT, created_by TEXT NOT NULL DEFAULT 'system',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    result TEXT, metadata TEXT NOT NULL DEFAULT '{}')"""

_CREATE_DEPS = """
CREATE TABLE IF NOT EXISTS task_dependencies (
    task_id TEXT NOT NULL, depends_on_id TEXT NOT NULL,
    PRIMARY KEY (task_id, depends_on_id),
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (depends_on_id) REFERENCES tasks(id))"""

_READY_QUERY = """
SELECT t.* FROM tasks t
WHERE t.status = ?
  AND NOT EXISTS (
      SELECT 1 FROM task_dependencies d
      JOIN tasks dep ON dep.id = d.depends_on_id
      WHERE d.task_id = t.id AND dep.status != ?)
ORDER BY CASE t.priority
    WHEN 'urgent' THEN 0 WHEN 'high' THEN 1
    WHEN 'normal' THEN 2 WHEN 'low' THEN 3 END,
  t.created_at ASC"""


class TaskBoardError(Exception):
    """Raised on invalid task operations."""


class TaskBoard:
    """Async task board backed by SQLite."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path

    async def init_db(self) -> None:
        """Create tasks and task_dependencies tables."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(_CREATE_TASKS)
            await db.execute(_CREATE_DEPS)
            await db.commit()

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _row_to_task(row: aiosqlite.Row, deps: list[str]) -> Task:
        """Convert a database row + dependency list into a Task."""
        return Task(
            id=row[0], title=row[1], description=row[2],
            status=TaskStatus(row[3]), priority=TaskPriority(row[4]),
            assigned_to=row[5], created_by=row[6],
            created_at=datetime.fromisoformat(row[7]),
            updated_at=datetime.fromisoformat(row[8]),
            result=row[9], metadata=json.loads(row[10]), depends_on=deps,
        )

    @staticmethod
    async def _fetch_deps(db: aiosqlite.Connection, task_id: str) -> list[str]:
        cur = await db.execute(
            "SELECT depends_on_id FROM task_dependencies WHERE task_id = ?",
            (task_id,),
        )
        return [r[0] for r in await cur.fetchall()]

    _ALLOWED_COLUMNS = frozenset({
        "title", "description", "priority", "assigned_to",
        "created_by", "result", "metadata",
    })

    @staticmethod
    def _coerce_db_value(col: str, val: Any) -> Any:
        """Normalize Python values for SQLite writes."""
        if col != "metadata":
            return val
        if val is None:
            return json.dumps({}, ensure_ascii=True)
        if isinstance(val, str):
            return val
        return json.dumps(val, ensure_ascii=True)

    async def _set_status(self, task_id: str, new: TaskStatus, **fields: Any) -> Task:
        """Validate and apply a status transition with optional field updates."""
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
            row = await cur.fetchone()
            if row is None:
                raise TaskBoardError(f"Task {task_id!r} not found")
            current = TaskStatus(row[0])
            if new not in _TRANSITIONS.get(current, set()):
                raise TaskBoardError(
                    f"Invalid transition: {current.value} -> {new.value}"
                )
            now = _utc_now().isoformat()
            sets = ["status = ?", "updated_at = ?"]
            params: list[Any] = [new.value, now]
            for col, val in fields.items():
                if col not in self._ALLOWED_COLUMNS:
                    raise TaskBoardError(f"Invalid column: {col!r}")
                sets.append(f"{col} = ?")
                params.append(self._coerce_db_value(col, val))
            params.append(task_id)
            await db.execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params,
            )
            await db.commit()
            cur = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            updated = await cur.fetchone()
            deps = await self._fetch_deps(db, task_id)
            return self._row_to_task(updated, deps)  # type: ignore[arg-type]

    async def _load_rows(self, db: aiosqlite.Connection, rows: list[Any]) -> list[Task]:
        tasks: list[Task] = []
        for row in rows:
            deps = await self._fetch_deps(db, row[0])
            tasks.append(self._row_to_task(row, deps))
        return tasks

    async def _witness_transition(
        self,
        *,
        task_id: str,
        action: str,
        think_phase: str,
        reflection: str,
    ) -> None:
        """Apply bounded reflective checkpoint to task status transitions."""
        gate = check_with_reflective_reroute(
            action=action,
            think_phase=think_phase,
            reflection=reflection,
            max_reroutes=1,
            requirement_refs=[f"task:{task_id}"],
        )
        if gate.result.decision.value == "block":
            raise TaskBoardError(
                f"Telos blocked transition ({think_phase}): {gate.result.reason}"
            )

    # -- CRUD ---------------------------------------------------------------

    async def create(
        self,
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.NORMAL,
        created_by: str = "system",
        depends_on: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Create a new task and persist it."""
        task_id = _new_id()
        now = _utc_now()
        dep_ids: list[str] = depends_on or []
        meta = dict(metadata or {})
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (task_id, title, description, TaskStatus.PENDING.value,
                 priority.value, None, created_by, now.isoformat(),
                 now.isoformat(), None, json.dumps(meta, ensure_ascii=True)),
            )
            for dep_id in dep_ids:
                await db.execute(
                    "INSERT INTO task_dependencies VALUES (?,?)", (task_id, dep_id),
                )
            await db.commit()
        return Task(
            id=task_id, title=title, description=description,
            priority=priority, created_by=created_by,
            created_at=now, updated_at=now, depends_on=dep_ids,
            metadata=meta,
        )

    async def create_batch(
        self,
        tasks: list[dict[str, Any]],
    ) -> list[Task]:
        """Create multiple tasks in a single transaction.

        JIKOKU-optimized: Batches all inserts into one transaction,
        eliminating SQLite write lock contention.

        Args:
            tasks: List of task specs, each dict with keys:
                   {title, description?, priority?, created_by?, depends_on?}

        Returns:
            List of created Task objects.
        """
        if not tasks:
            return []

        now = _utc_now()
        created_tasks: list[Task] = []

        async with aiosqlite.connect(self._db_path) as db:
            # Single transaction for all tasks
            for spec in tasks:
                task_id = _new_id()
                title = spec["title"]
                description = spec.get("description", "")
                priority = spec.get("priority", TaskPriority.NORMAL)
                created_by = spec.get("created_by", "system")
                dep_ids = spec.get("depends_on") or []
                metadata = dict(spec.get("metadata") or {})

                await db.execute(
                    "INSERT INTO tasks VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (task_id, title, description, TaskStatus.PENDING.value,
                     priority.value, None, created_by, now.isoformat(),
                     now.isoformat(), None, json.dumps(metadata, ensure_ascii=True)),
                )

                for dep_id in dep_ids:
                    await db.execute(
                        "INSERT INTO task_dependencies VALUES (?,?)",
                        (task_id, dep_id),
                    )

                created_tasks.append(Task(
                    id=task_id, title=title, description=description,
                    priority=priority, created_by=created_by,
                    created_at=now, updated_at=now, depends_on=dep_ids,
                    metadata=metadata,
                ))

            # Single commit for entire batch
            await db.commit()

        return created_tasks

    async def get(self, task_id: str) -> Task | None:
        """Retrieve a single task by ID, or None if missing."""
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            row = await cur.fetchone()
            if row is None:
                return None
            deps = await self._fetch_deps(db, task_id)
            return self._row_to_task(row, deps)

    async def list_tasks(
        self,
        status: TaskStatus | None = None,
        assigned_to: str | None = None,
        limit: int = 50,
    ) -> list[Task]:
        """List tasks with optional status/assignee filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if assigned_to is not None:
            clauses.append("assigned_to = ?")
            params.append(assigned_to)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                f"SELECT * FROM tasks {where} ORDER BY created_at DESC LIMIT ?",
                params,
            )
            return await self._load_rows(db, await cur.fetchall())

    async def update_task(self, task_id: str, **fields: Any) -> None:
        """Generic update (orchestrator interface).

        Routes to the appropriate specific method based on the ``status``
        field, or does a raw column update for non-status fields.
        """
        status = fields.pop("status", None)
        if status is not None:
            if status == TaskStatus.ASSIGNED:
                await self.assign(
                    task_id,
                    fields.get("assigned_to", ""),
                    metadata=fields.get("metadata"),
                )
            elif status == TaskStatus.RUNNING:
                await self.start(task_id, metadata=fields.get("metadata"))
            elif status == TaskStatus.COMPLETED:
                await self.complete(
                    task_id,
                    fields.get("result", ""),
                    metadata=fields.get("metadata"),
                )
            elif status == TaskStatus.FAILED:
                await self.fail(
                    task_id,
                    fields.get("result", ""),
                    metadata=fields.get("metadata"),
                )
            elif status == TaskStatus.CANCELLED:
                await self.cancel(task_id, metadata=fields.get("metadata"))
            elif status == TaskStatus.PENDING:
                await self.requeue(
                    task_id,
                    reason=fields.get("result", ""),
                    metadata=fields.get("metadata"),
                )
        elif fields:
            # Raw column update (no status change)
            async with aiosqlite.connect(self._db_path) as db:
                sets = []
                params: list[Any] = []
                for col, val in fields.items():
                    if col not in self._ALLOWED_COLUMNS:
                        raise TaskBoardError(f"Invalid column: {col!r}")
                    sets.append(f"{col} = ?")
                    params.append(self._coerce_db_value(col, val))
                params.append(task_id)
                await db.execute(
                    f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params,
                )
                await db.commit()

    # -- status transitions -------------------------------------------------

    async def assign(
        self,
        task_id: str,
        agent_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Assign to an agent (PENDING -> ASSIGNED)."""
        fields: dict[str, Any] = {"assigned_to": agent_id}
        if metadata is not None:
            fields["metadata"] = metadata
        return await self._set_status(task_id, TaskStatus.ASSIGNED, **fields)

    async def start(
        self,
        task_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Mark running (ASSIGNED -> RUNNING)."""
        fields: dict[str, Any] = {}
        if metadata is not None:
            fields["metadata"] = metadata
        return await self._set_status(task_id, TaskStatus.RUNNING, **fields)

    async def complete(
        self,
        task_id: str,
        result: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Mark completed (RUNNING -> COMPLETED)."""
        await self._witness_transition(
            task_id=task_id,
            action=f"complete task {task_id}",
            think_phase="before_complete",
            reflection=(
                f"Completing task {task_id}. Result captured with "
                f"{len((result or '').strip())} chars. Verify requirement coverage."
            ),
        )
        fields: dict[str, Any] = {"result": result}
        if metadata is not None:
            fields["metadata"] = metadata
        return await self._set_status(task_id, TaskStatus.COMPLETED, **fields)

    async def fail(
        self,
        task_id: str,
        error: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Mark failed (RUNNING -> FAILED)."""
        await self._witness_transition(
            task_id=task_id,
            action=f"pivot task {task_id}",
            think_phase="before_pivot",
            reflection=(
                f"Task {task_id} failed with error context. "
                "Summarize failure signature and define pivot strategy."
            ),
        )
        fields: dict[str, Any] = {"result": error}
        if metadata is not None:
            fields["metadata"] = metadata
        return await self._set_status(task_id, TaskStatus.FAILED, **fields)

    async def cancel(
        self,
        task_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Cancel (PENDING|ASSIGNED|RUNNING -> CANCELLED)."""
        fields: dict[str, Any] = {}
        if metadata is not None:
            fields["metadata"] = metadata
        return await self._set_status(task_id, TaskStatus.CANCELLED, **fields)

    async def requeue(
        self,
        task_id: str,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Requeue a task back to pending with optional metadata merge."""
        task = await self.get(task_id)
        if task is None:
            raise TaskBoardError(f"Task {task_id!r} not found")

        merged_meta = dict(task.metadata or {})
        if isinstance(metadata, dict):
            merged_meta.update(metadata)

        if task.status == TaskStatus.PENDING:
            await self.update_task(
                task_id,
                assigned_to=None,
                result=reason,
                metadata=merged_meta,
            )
            refreshed = await self.get(task_id)
            assert refreshed is not None
            return refreshed

        if task.status == TaskStatus.RUNNING:
            await self._set_status(
                task_id,
                TaskStatus.FAILED,
                result=reason,
                metadata=merged_meta,
            )
            return await self._set_status(
                task_id,
                TaskStatus.PENDING,
                assigned_to=None,
                result=reason,
                metadata=merged_meta,
            )

        if task.status in {TaskStatus.FAILED, TaskStatus.CANCELLED, TaskStatus.ASSIGNED}:
            return await self._set_status(
                task_id,
                TaskStatus.PENDING,
                assigned_to=None,
                result=reason,
                metadata=merged_meta,
            )

        raise TaskBoardError(
            f"Cannot requeue task {task_id!r} from status {task.status.value}"
        )

    # -- dependency management ----------------------------------------------

    async def add_dependency(self, task_id: str, depends_on_id: str) -> None:
        """Add a dependency edge: task_id depends on depends_on_id."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO task_dependencies VALUES (?,?)",
                (task_id, depends_on_id),
            )
            await db.commit()

    async def get_dependencies(self, task_id: str) -> list[str]:
        """Return task IDs that task_id depends on."""
        async with aiosqlite.connect(self._db_path) as db:
            return await self._fetch_deps(db, task_id)

    async def get_ready_tasks(self) -> list[Task]:
        """Return PENDING tasks whose dependencies are all COMPLETED."""
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute(
                _READY_QUERY, (TaskStatus.PENDING.value, TaskStatus.COMPLETED.value),
            )
            return await self._load_rows(db, await cur.fetchall())

    # -- analytics ----------------------------------------------------------

    async def stats(self) -> dict[str, int]:
        """Return task counts grouped by status."""
        async with aiosqlite.connect(self._db_path) as db:
            cur = await db.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
            counts = {s.value: 0 for s in TaskStatus}
            for status_val, count in await cur.fetchall():
                counts[status_val] = count
            counts["total"] = sum(counts.values())
            return counts
