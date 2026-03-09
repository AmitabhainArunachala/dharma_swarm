"""Canonical operator bridge lifecycle on top of MessageBus + SessionLedger.

This reimplements the legacy bridge queue semantics without reviving the
filesystem inbox/state/outbox transport. Live queue state is stored in a
dedicated SQLite table inside the canonical message-bus database, while
request/response notifications flow through the bus and append-only audit facts
flow through the session ledger.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any

import aiosqlite

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.models import Message, MessagePriority, _new_id
from dharma_swarm.session_ledger import SessionLedger

BRIDGE_STATUS_QUEUED = "queued"
BRIDGE_STATUS_IN_PROGRESS = "in_progress"
DEFAULT_CLAIM_TIMEOUT_SECONDS = 30 * 60

_TASKS_DDL = """
CREATE TABLE IF NOT EXISTS operator_bridge_tasks (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    sender TEXT NOT NULL,
    task TEXT NOT NULL,
    scope TEXT NOT NULL DEFAULT '[]',
    output TEXT NOT NULL DEFAULT '[]',
    constraints TEXT NOT NULL DEFAULT '[]',
    payload TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    claim_timeout_seconds INTEGER NOT NULL DEFAULT 1800,
    claimed_at TEXT,
    claimed_by TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    recovered_at TEXT,
    recovery_reason TEXT,
    completed_at TEXT,
    request_message_id TEXT,
    response TEXT,
    metadata TEXT NOT NULL DEFAULT '{}'
)"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_operator_bridge_status_created ON operator_bridge_tasks(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_operator_bridge_claimed_at ON operator_bridge_tasks(claimed_at)",
    "CREATE INDEX IF NOT EXISTS idx_operator_bridge_sender ON operator_bridge_tasks(sender)",
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def _json_load(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _bridge_task_id() -> str:
    return f"bridge_{_new_id()}"


@dataclass
class OperatorBridgeResponse:
    status: str
    summary: str
    report_path: str | None = None
    patch_path: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    responded_at: datetime = field(default_factory=_utc_now)
    response_message_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "report_path": self.report_path,
            "patch_path": self.patch_path,
            "error": self.error,
            "metadata": self.metadata,
            "responded_at": self.responded_at.isoformat(),
            "response_message_id": self.response_message_id,
        }


@dataclass
class OperatorBridgeTask:
    id: str
    created_at: datetime
    updated_at: datetime
    sender: str
    task: str
    scope: tuple[str, ...] = ()
    output: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = BRIDGE_STATUS_QUEUED
    claim_timeout_seconds: int = DEFAULT_CLAIM_TIMEOUT_SECONDS
    claimed_at: datetime | None = None
    claimed_by: str | None = None
    retry_count: int = 0
    recovered_at: datetime | None = None
    recovery_reason: str | None = None
    completed_at: datetime | None = None
    request_message_id: str | None = None
    response: OperatorBridgeResponse | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def render_work_order(self) -> str:
        sections = [
            "# Operator Bridge Task",
            "",
            "## Task",
            self.task,
            "",
            "## Scope",
            ", ".join(self.scope) or "(none)",
            "",
            "## Constraints",
            ", ".join(self.constraints) or "(none)",
            "",
            "## Expected Output",
            ", ".join(self.output) or "(none)",
            "",
            "## Payload",
            json.dumps(self.payload, indent=2, ensure_ascii=True, sort_keys=True),
        ]
        return "\n".join(sections)


def _response_from_raw(raw: str | None) -> OperatorBridgeResponse | None:
    data = _json_load(raw, None)
    if not isinstance(data, dict):
        return None
    return OperatorBridgeResponse(
        status=str(data.get("status", "")),
        summary=str(data.get("summary", "")),
        report_path=data.get("report_path"),
        patch_path=data.get("patch_path"),
        error=data.get("error"),
        metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
        responded_at=_parse_ts(data.get("responded_at")) or _utc_now(),
        response_message_id=data.get("response_message_id"),
    )


def _row_to_task(row: aiosqlite.Row) -> OperatorBridgeTask:
    return OperatorBridgeTask(
        id=row["id"],
        created_at=_parse_ts(row["created_at"]) or _utc_now(),
        updated_at=_parse_ts(row["updated_at"]) or _utc_now(),
        sender=row["sender"],
        task=row["task"],
        scope=tuple(_json_load(row["scope"], [])),
        output=tuple(_json_load(row["output"], [])),
        constraints=tuple(_json_load(row["constraints"], [])),
        payload=_json_load(row["payload"], {}),
        status=row["status"],
        claim_timeout_seconds=int(row["claim_timeout_seconds"] or DEFAULT_CLAIM_TIMEOUT_SECONDS),
        claimed_at=_parse_ts(row["claimed_at"]),
        claimed_by=row["claimed_by"],
        retry_count=int(row["retry_count"] or 0),
        recovered_at=_parse_ts(row["recovered_at"]),
        recovery_reason=row["recovery_reason"],
        completed_at=_parse_ts(row["completed_at"]),
        request_message_id=row["request_message_id"],
        response=_response_from_raw(row["response"]),
        metadata=_json_load(row["metadata"], {}),
    )


class OperatorBridge:
    """Stateful operator task bridge using canonical bus and ledger seams."""

    def __init__(
        self,
        *,
        message_bus: MessageBus,
        ledger: SessionLedger | None = None,
        ledger_dir: Path | None = None,
        session_id: str | None = None,
        bridge_agent_id: str = "operator_bridge",
        lifecycle_topic: str = "operator.bridge.lifecycle",
    ) -> None:
        self._bus = message_bus
        self._ledger = ledger or SessionLedger(
            base_dir=ledger_dir,
            session_id=session_id,
        )
        self.bridge_agent_id = bridge_agent_id
        self.lifecycle_topic = lifecycle_topic
        self._initialized = False

    async def init_db(self) -> None:
        if self._initialized:
            return
        await self._bus.init_db()
        async with aiosqlite.connect(self._bus.db_path) as db:
            await db.execute(_TASKS_DDL)
            for index in _INDEXES:
                await db.execute(index)
            await db.commit()
        self._initialized = True

    async def enqueue_task(
        self,
        *,
        task: str,
        sender: str = "operator",
        scope: list[str] | None = None,
        output: list[str] | None = None,
        constraints: list[str] | None = None,
        payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        claim_timeout_seconds: int = DEFAULT_CLAIM_TIMEOUT_SECONDS,
        priority: MessagePriority = MessagePriority.NORMAL,
        task_id: str | None = None,
    ) -> OperatorBridgeTask:
        await self.init_db()
        now_iso = _utc_now_iso()
        record_id = task_id or _bridge_task_id()
        payload_dict = dict(payload or {})
        metadata_dict = dict(metadata or {})

        async with aiosqlite.connect(self._bus.db_path) as db:
            await db.execute(
                "INSERT INTO operator_bridge_tasks"
                " (id, created_at, updated_at, sender, task, scope, output,"
                " constraints, payload, status, claim_timeout_seconds,"
                " request_message_id, response, metadata)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record_id,
                    now_iso,
                    now_iso,
                    sender,
                    task,
                    _json_dump(scope or []),
                    _json_dump(output or []),
                    _json_dump(constraints or []),
                    _json_dump(payload_dict),
                    BRIDGE_STATUS_QUEUED,
                    int(claim_timeout_seconds),
                    None,
                    None,
                    _json_dump(metadata_dict),
                ),
            )
            await db.commit()

        task_record = await self.get_task(record_id)
        assert task_record is not None

        request_message_id: str | None = None
        try:
            request_message_id = await self._bus.send(
                Message(
                    from_agent=sender,
                    to_agent=self.bridge_agent_id,
                    subject=f"Bridge task: {record_id}",
                    body=task_record.render_work_order(),
                    priority=priority,
                    metadata={
                        "bridge_event": "bridge_task_enqueued",
                        "bridge_task_id": record_id,
                        "claim_timeout_seconds": int(claim_timeout_seconds),
                        "scope": list(task_record.scope),
                        "output": list(task_record.output),
                        "constraints": list(task_record.constraints),
                        "payload": payload_dict,
                        **metadata_dict,
                    },
                )
            )
        except Exception:
            request_message_id = None

        if request_message_id is not None:
            await self._set_request_message_id(record_id, request_message_id)
            task_record.request_message_id = request_message_id

        self._record_task_event(
            "bridge_task_enqueued",
            task_id=record_id,
            sender=sender,
            claim_timeout_seconds=int(claim_timeout_seconds),
        )
        await self._publish_lifecycle(
            "bridge_task_enqueued",
            task_record,
            extra={"sender": sender},
        )
        return task_record

    async def list_tasks(
        self,
        *,
        status: str | None = None,
        sender: str | None = None,
        limit: int = 50,
    ) -> list[OperatorBridgeTask]:
        await self.init_db()
        query = (
            "SELECT id, created_at, updated_at, sender, task, scope, output,"
            " constraints, payload, status, claim_timeout_seconds, claimed_at,"
            " claimed_by, retry_count, recovered_at, recovery_reason,"
            " completed_at, request_message_id, response, metadata"
            " FROM operator_bridge_tasks WHERE 1=1"
        )
        params: list[Any] = []
        if status is not None:
            query += " AND status = ?"
            params.append(status)
        if sender is not None:
            query += " AND sender = ?"
            params.append(sender)
        query += " ORDER BY created_at ASC LIMIT ?"
        params.append(limit)
        async with aiosqlite.connect(self._bus.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [_row_to_task(row) for row in rows]

    async def get_task(self, task_id: str) -> OperatorBridgeTask | None:
        await self.init_db()
        async with aiosqlite.connect(self._bus.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, created_at, updated_at, sender, task, scope, output,"
                " constraints, payload, status, claim_timeout_seconds, claimed_at,"
                " claimed_by, retry_count, recovered_at, recovery_reason,"
                " completed_at, request_message_id, response, metadata"
                " FROM operator_bridge_tasks WHERE id = ?",
                (task_id,),
            )
            row = await cursor.fetchone()
        return _row_to_task(row) if row is not None else None

    async def claim_task(
        self,
        *,
        claimed_by: str,
        task_id: str | None = None,
        now: datetime | None = None,
    ) -> OperatorBridgeTask | None:
        await self.init_db()
        claim_dt = now or _utc_now()
        claim_iso = claim_dt.isoformat()

        async with aiosqlite.connect(self._bus.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            if task_id is not None:
                cursor = await db.execute(
                    "SELECT id, created_at, updated_at, sender, task, scope, output,"
                    " constraints, payload, status, claim_timeout_seconds, claimed_at,"
                    " claimed_by, retry_count, recovered_at, recovery_reason,"
                    " completed_at, request_message_id, response, metadata"
                    " FROM operator_bridge_tasks WHERE id = ? AND status = ?",
                    (task_id, BRIDGE_STATUS_QUEUED),
                )
            else:
                cursor = await db.execute(
                    "SELECT id, created_at, updated_at, sender, task, scope, output,"
                    " constraints, payload, status, claim_timeout_seconds, claimed_at,"
                    " claimed_by, retry_count, recovered_at, recovery_reason,"
                    " completed_at, request_message_id, response, metadata"
                    " FROM operator_bridge_tasks WHERE status = ?"
                    " ORDER BY created_at ASC LIMIT 1",
                    (BRIDGE_STATUS_QUEUED,),
                )
            row = await cursor.fetchone()
            if row is None:
                await db.rollback()
                return None

            result = await db.execute(
                "UPDATE operator_bridge_tasks"
                " SET status = ?, claimed_at = ?, claimed_by = ?, updated_at = ?"
                " WHERE id = ? AND status = ?",
                (
                    BRIDGE_STATUS_IN_PROGRESS,
                    claim_iso,
                    claimed_by,
                    claim_iso,
                    row["id"],
                    BRIDGE_STATUS_QUEUED,
                ),
            )
            if result.rowcount != 1:
                await db.rollback()
                return None

            cursor = await db.execute(
                "SELECT id, created_at, updated_at, sender, task, scope, output,"
                " constraints, payload, status, claim_timeout_seconds, claimed_at,"
                " claimed_by, retry_count, recovered_at, recovery_reason,"
                " completed_at, request_message_id, response, metadata"
                " FROM operator_bridge_tasks WHERE id = ?",
                (row["id"],),
            )
            claimed_row = await cursor.fetchone()
            await db.commit()

        claimed_task = _row_to_task(claimed_row)
        self._record_task_event(
            "bridge_task_claimed",
            task_id=claimed_task.id,
            claimed_by=claimed_by,
            retry_count=claimed_task.retry_count,
        )
        await self._publish_lifecycle(
            "bridge_task_claimed",
            claimed_task,
            extra={"claimed_by": claimed_by},
        )
        return claimed_task

    async def recover_stale_tasks(
        self,
        *,
        now: datetime | None = None,
        timeout_seconds: int | None = None,
    ) -> list[OperatorBridgeTask]:
        await self.init_db()
        recovery_dt = now or _utc_now()
        recovery_iso = recovery_dt.isoformat()
        recovered_ids: list[str] = []

        async with aiosqlite.connect(self._bus.db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT id, created_at, updated_at, sender, task, scope, output,"
                " constraints, payload, status, claim_timeout_seconds, claimed_at,"
                " claimed_by, retry_count, recovered_at, recovery_reason,"
                " completed_at, request_message_id, response, metadata"
                " FROM operator_bridge_tasks WHERE status = ?",
                (BRIDGE_STATUS_IN_PROGRESS,),
            )
            rows = await cursor.fetchall()
            for row in rows:
                task_record = _row_to_task(row)
                if not self._is_stale(task_record, now=recovery_dt, timeout_seconds=timeout_seconds):
                    continue
                reason = self._stale_reason(
                    task_record,
                    now=recovery_dt,
                    timeout_seconds=timeout_seconds,
                )
                result = await db.execute(
                    "UPDATE operator_bridge_tasks"
                    " SET status = ?, claimed_at = NULL, claimed_by = NULL,"
                    " retry_count = retry_count + 1, recovered_at = ?,"
                    " recovery_reason = ?, updated_at = ?"
                    " WHERE id = ? AND status = ?",
                    (
                        BRIDGE_STATUS_QUEUED,
                        recovery_iso,
                        reason,
                        recovery_iso,
                        task_record.id,
                        BRIDGE_STATUS_IN_PROGRESS,
                    ),
                )
                if result.rowcount == 1:
                    recovered_ids.append(task_record.id)
            await db.commit()

        recovered = [task for task_id in recovered_ids if (task := await self.get_task(task_id))]
        for task_record in recovered:
            self._record_task_event(
                "bridge_task_recovered",
                task_id=task_record.id,
                retry_count=task_record.retry_count,
                recovery_reason=task_record.recovery_reason,
            )
            await self._publish_lifecycle(
                "bridge_task_recovered",
                task_record,
                extra={"retry_count": task_record.retry_count},
            )
        return recovered

    async def respond_task(
        self,
        *,
        task_id: str,
        status: str,
        summary: str,
        claimed_by: str | None = None,
        report_path: str | None = None,
        patch_path: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OperatorBridgeTask:
        await self.init_db()
        existing = await self.get_task(task_id)
        if existing is None:
            raise KeyError(f"Bridge task {task_id} not found")

        responded_by = claimed_by or existing.claimed_by or self.bridge_agent_id
        completed_dt = _utc_now()
        incoming_metadata = dict(metadata or {})
        require_delivery_ack = bool(
            incoming_metadata.pop(
                "require_delivery_ack",
                existing.metadata.get("require_delivery_ack", True),
            )
        )
        ack_timeout_raw = incoming_metadata.pop(
            "ack_timeout_seconds",
            existing.metadata.get("ack_timeout_seconds", 300),
        )
        try:
            ack_timeout_seconds = max(1, int(ack_timeout_raw))
        except Exception:
            ack_timeout_seconds = 300
        ack_deadline_at = (
            completed_dt + timedelta(seconds=ack_timeout_seconds)
        ).isoformat() if require_delivery_ack else None
        response_metadata = {
            "responded_by": responded_by,
            "require_delivery_ack": require_delivery_ack,
            **incoming_metadata,
        }
        if require_delivery_ack:
            response_metadata["ack_timeout_seconds"] = ack_timeout_seconds
            response_metadata["ack_deadline_at"] = ack_deadline_at

        task_metadata = dict(existing.metadata)
        task_metadata["require_delivery_ack"] = require_delivery_ack
        if require_delivery_ack:
            task_metadata["ack_timeout_seconds"] = ack_timeout_seconds
            task_metadata["ack_deadline_at"] = ack_deadline_at
            task_metadata.pop("delivery_ack", None)
        response = OperatorBridgeResponse(
            status=status,
            summary=summary,
            report_path=report_path,
            patch_path=patch_path,
            error=error,
            metadata=response_metadata,
            responded_at=completed_dt,
        )

        async with aiosqlite.connect(self._bus.db_path) as db:
            await db.execute(
                "UPDATE operator_bridge_tasks"
                " SET status = ?, completed_at = ?, updated_at = ?, response = ?, metadata = ?"
                " WHERE id = ?",
                (
                    status,
                    completed_dt.isoformat(),
                    completed_dt.isoformat(),
                    _json_dump(response.as_dict()),
                    _json_dump(task_metadata),
                    task_id,
                ),
            )
            await db.commit()

        response_message_id: str | None = None
        try:
            response_message_id = await self._bus.send(
                Message(
                    from_agent=responded_by,
                    to_agent=existing.sender,
                    subject=f"Bridge response: {task_id}",
                    body=summary,
                    priority=MessagePriority.HIGH if status != "done" else MessagePriority.NORMAL,
                    reply_to=existing.request_message_id,
                    metadata={
                        "bridge_event": "bridge_task_responded",
                        "bridge_task_id": task_id,
                        "bridge_status": status,
                        "require_delivery_ack": require_delivery_ack,
                        "ack_deadline_at": ack_deadline_at,
                        "report_path": report_path,
                        "patch_path": patch_path,
                        "error": error,
                        "retry_count": existing.retry_count,
                        **response.metadata,
                    },
                )
            )
        except Exception:
            response_message_id = None

        if response_message_id is not None:
            response.response_message_id = response_message_id
            await self._set_response(task_id, response)

        updated = await self.get_task(task_id)
        assert updated is not None

        self._record_task_event(
            "bridge_task_responded",
            task_id=task_id,
            status=status,
            responded_by=responded_by,
        )
        self._record_progress_event(
            "bridge_response_emitted",
            task_id=task_id,
            status=status,
            responded_by=responded_by,
        )
        await self._publish_lifecycle(
            "bridge_task_responded",
            updated,
            extra={"status": status, "responded_by": responded_by},
        )
        return updated

    async def acknowledge_response(
        self,
        *,
        task_id: str,
        acknowledged_by: str,
        note: str = "",
    ) -> OperatorBridgeTask:
        """Confirm response delivery so the bridge can detect silent drop-off."""
        await self.init_db()
        existing = await self.get_task(task_id)
        if existing is None:
            raise KeyError(f"Bridge task {task_id} not found")
        if existing.response is None:
            raise ValueError(f"Bridge task {task_id} has no response to acknowledge")

        ack = {
            "acknowledged_by": acknowledged_by,
            "acknowledged_at": _utc_now_iso(),
            "note": note,
        }
        metadata = dict(existing.metadata)
        metadata["delivery_ack"] = ack

        async with aiosqlite.connect(self._bus.db_path) as db:
            await db.execute(
                "UPDATE operator_bridge_tasks SET metadata = ?, updated_at = ? WHERE id = ?",
                (_json_dump(metadata), _utc_now_iso(), task_id),
            )
            await db.commit()

        updated = await self.get_task(task_id)
        assert updated is not None
        self._record_task_event(
            "bridge_response_acknowledged",
            task_id=task_id,
            acknowledged_by=acknowledged_by,
        )
        self._record_progress_event(
            "bridge_response_acknowledged",
            task_id=task_id,
            acknowledged_by=acknowledged_by,
        )
        await self._publish_lifecycle(
            "bridge_response_acknowledged",
            updated,
            extra={"acknowledged_by": acknowledged_by},
        )
        return updated

    async def list_unacknowledged_responses(
        self,
        *,
        limit: int = 50,
        now: datetime | None = None,
    ) -> list[OperatorBridgeTask]:
        """List tasks with emitted responses that still lack delivery acknowledgement."""
        await self.init_db()
        reference_now = now or _utc_now()
        all_tasks = await self.list_tasks(limit=1000)
        pending: list[OperatorBridgeTask] = []
        for task in all_tasks:
            if task.response is None:
                continue
            if task.status in {BRIDGE_STATUS_QUEUED, BRIDGE_STATUS_IN_PROGRESS}:
                continue
            if task.metadata.get("delivery_ack"):
                continue
            if not bool(task.metadata.get("require_delivery_ack", True)):
                continue
            deadline_raw = task.metadata.get("ack_deadline_at")
            deadline = _parse_ts(str(deadline_raw)) if deadline_raw else None
            if deadline and reference_now < deadline:
                continue
            pending.append(task)
            if len(pending) >= limit:
                break
        return pending

    async def _set_request_message_id(self, task_id: str, request_message_id: str) -> None:
        async with aiosqlite.connect(self._bus.db_path) as db:
            await db.execute(
                "UPDATE operator_bridge_tasks"
                " SET request_message_id = ?, updated_at = ? WHERE id = ?",
                (request_message_id, _utc_now_iso(), task_id),
            )
            await db.commit()

    async def _set_response(self, task_id: str, response: OperatorBridgeResponse) -> None:
        async with aiosqlite.connect(self._bus.db_path) as db:
            await db.execute(
                "UPDATE operator_bridge_tasks SET response = ?, updated_at = ? WHERE id = ?",
                (_json_dump(response.as_dict()), _utc_now_iso(), task_id),
            )
            await db.commit()

    def _record_task_event(self, event: str, **payload: Any) -> None:
        self._ledger.task_event(event, **payload)

    def _record_progress_event(self, event: str, **payload: Any) -> None:
        self._ledger.progress_event(event, **payload)

    async def _publish_lifecycle(
        self,
        event: str,
        task: OperatorBridgeTask,
        *,
        extra: dict[str, Any] | None = None,
    ) -> None:
        metadata = {
            "bridge_event": event,
            "bridge_task_id": task.id,
            "bridge_status": task.status,
            "sender": task.sender,
            **(extra or {}),
        }
        try:
            await self._bus.publish(
                self.lifecycle_topic,
                Message(
                    from_agent=self.bridge_agent_id,
                    to_agent="",
                    subject=f"Bridge lifecycle: {event}",
                    body=f"{event} task={task.id} status={task.status}",
                    metadata=metadata,
                ),
            )
        except Exception:
            return

    @staticmethod
    def _is_stale(
        task: OperatorBridgeTask,
        *,
        now: datetime,
        timeout_seconds: int | None,
    ) -> bool:
        if task.status != BRIDGE_STATUS_IN_PROGRESS:
            return False
        if task.claimed_at is None:
            return True
        allowed_age = timeout_seconds if timeout_seconds is not None else task.claim_timeout_seconds
        age_seconds = (now - task.claimed_at).total_seconds()
        return age_seconds > float(allowed_age)

    @staticmethod
    def _stale_reason(
        task: OperatorBridgeTask,
        *,
        now: datetime,
        timeout_seconds: int | None,
    ) -> str:
        if task.claimed_at is None:
            return "stale claim with missing claimed_at"
        allowed_age = timeout_seconds if timeout_seconds is not None else task.claim_timeout_seconds
        age_seconds = max(0, int((now - task.claimed_at).total_seconds()))
        return f"stale after {age_seconds}s (timeout={int(allowed_age)}s)"
