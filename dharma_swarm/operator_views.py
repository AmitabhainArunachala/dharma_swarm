"""Operator-facing query helpers over the canonical runtime spine."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from dharma_swarm.operator_bridge import OperatorBridge
from dharma_swarm.runtime_state import DelegationRun, RuntimeStateStore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class QueueTaskView:
    task_id: str
    status: str
    sender: str
    claimed_by: str | None
    retry_count: int
    has_claim_ack: bool
    has_response: bool
    overdue_response_ack: bool
    last_heartbeat_at: str | None
    current_artifact_id: str | None
    summary: str


@dataclass(frozen=True)
class RuntimeOverview:
    sessions: int
    claims: int
    active_claims: int
    acknowledged_claims: int
    runs: int
    active_runs: int
    artifacts: int
    promoted_facts: int
    context_bundles: int
    operator_actions: int


class OperatorViews:
    """Thin operator/cockpit read model built on canonical runtime state."""

    def __init__(
        self,
        runtime_state: RuntimeStateStore,
        *,
        bridge: OperatorBridge | None = None,
    ) -> None:
        self.runtime_state = runtime_state
        self.bridge = bridge

    async def runtime_overview(self, *, session_id: str | None = None) -> RuntimeOverview:
        await self.runtime_state.init_db()
        clauses: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

        with sqlite3.connect(str(self.runtime_state.db_path)) as db:
            sessions = self._count(db, "sessions", where, params)
            claims = self._count(db, "task_claims", where, params)
            active_claims = self._count(
                db,
                "task_claims",
                self._augment_where(where, "status IN ('claimed','in_progress')"),
                params,
            )
            acknowledged_claims = self._count(
                db,
                "task_claims",
                self._augment_where(where, "status = 'acknowledged'"),
                params,
            )
            runs = self._count(db, "delegation_runs", where, params)
            active_runs = self._count(
                db,
                "delegation_runs",
                self._augment_where(where, "status NOT IN ('completed','failed','stale_recovered')"),
                params,
            )
            artifacts = self._count(db, "artifact_records", where, params)
            promoted_facts = self._count(
                db,
                "memory_facts",
                self._augment_where(where, "truth_state = 'promoted'"),
                params,
            )
            context_bundles = self._count(db, "context_bundles", where, params)
            operator_actions = self._count(db, "operator_actions", where, params)
        return RuntimeOverview(
            sessions=sessions,
            claims=claims,
            active_claims=active_claims,
            acknowledged_claims=acknowledged_claims,
            runs=runs,
            active_runs=active_runs,
            artifacts=artifacts,
            promoted_facts=promoted_facts,
            context_bundles=context_bundles,
            operator_actions=operator_actions,
        )

    async def active_runs(
        self,
        *,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[DelegationRun]:
        runs = await self.runtime_state.list_delegation_runs(
            session_id=session_id,
            limit=limit * 2,
        )
        return [
            run
            for run in runs
            if run.status not in {"completed", "failed", "stale_recovered"}
        ][: max(1, limit)]

    async def recent_operator_actions(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        actions = await self.runtime_state.list_operator_actions(
            session_id=session_id,
            task_id=task_id,
            limit=limit,
        )
        return [
            {
                "action_id": action.action_id,
                "action_name": action.action_name,
                "actor": action.actor,
                "task_id": action.task_id,
                "run_id": action.run_id,
                "reason": action.reason,
                "payload": action.payload,
                "created_at": action.created_at.isoformat(),
            }
            for action in actions
        ]

    async def bridge_queue(
        self,
        *,
        status: str | None = None,
        limit: int = 50,
        now: datetime | None = None,
    ) -> list[QueueTaskView]:
        if self.bridge is None:
            raise RuntimeError("bridge is required for bridge queue views")
        reference_now = now or _utc_now()
        tasks = await self.bridge.list_tasks(status=status, limit=limit)
        views: list[QueueTaskView] = []
        for task in tasks:
            last_heartbeat = task.metadata.get("last_heartbeat", {})
            delivery_ack = task.metadata.get("delivery_ack")
            deadline_raw = task.metadata.get("ack_deadline_at")
            deadline = None
            if isinstance(deadline_raw, str):
                try:
                    deadline = datetime.fromisoformat(deadline_raw)
                except ValueError:
                    deadline = None
            overdue_ack = (
                bool(task.response)
                and not bool(delivery_ack)
                and bool(task.metadata.get("require_delivery_ack", True))
                and deadline is not None
                and reference_now >= deadline
            )
            summary = task.response.summary if task.response is not None else task.task
            views.append(
                QueueTaskView(
                    task_id=task.id,
                    status=task.status,
                    sender=task.sender,
                    claimed_by=task.claimed_by,
                    retry_count=task.retry_count,
                    has_claim_ack=bool(task.metadata.get("claim_ack")),
                    has_response=task.response is not None,
                    overdue_response_ack=overdue_ack,
                    last_heartbeat_at=last_heartbeat.get("heartbeat_at") if isinstance(last_heartbeat, dict) else None,
                    current_artifact_id=str(task.metadata.get("current_artifact_id") or "") or None,
                    summary=summary,
                )
            )
        return views

    async def overdue_response_acks(
        self,
        *,
        limit: int = 50,
        now: datetime | None = None,
    ) -> list[QueueTaskView]:
        if self.bridge is None:
            raise RuntimeError("bridge is required for bridge queue views")
        pending = await self.bridge.list_unacknowledged_responses(
            limit=limit,
            now=now or _utc_now(),
        )
        by_id = {item.task_id: item for item in await self.bridge_queue(limit=max(100, limit), now=now)}
        return [by_id[item.id] for item in pending if item.id in by_id]

    @staticmethod
    def _count(
        db: sqlite3.Connection,
        table: str,
        where: str,
        params: list[Any],
    ) -> int:
        query = f"SELECT COUNT(*) FROM {table}{where}"
        return int(db.execute(query, params).fetchone()[0])

    @staticmethod
    def _augment_where(where: str, extra_clause: str) -> str:
        if where:
            return f"{where} AND {extra_clause}"
        return f" WHERE {extra_clause}"
