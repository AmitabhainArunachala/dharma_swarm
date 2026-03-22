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
import logging
import os
from pathlib import Path
from typing import Any

import aiosqlite

logger = logging.getLogger(__name__)

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.models import Message, MessagePriority, _new_id
from dharma_swarm.runtime_state import (
    ArtifactRecord,
    DelegationRun,
    OperatorAction,
    RuntimeStateStore,
    SessionState,
    TaskClaim,
)
from dharma_swarm.session_ledger import SessionLedger
from dharma_swarm.telemetry_plane import (
    AgentIdentityRecord,
    ExternalOutcomeRecord,
    InterventionOutcomeRecord,
    TelemetryPlaneStore,
    WorkflowScoreRecord,
)

BRIDGE_STATUS_QUEUED = "queued"
BRIDGE_STATUS_IN_PROGRESS = "in_progress"
BRIDGE_STATUS_ACKNOWLEDGED = "acknowledged"
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
        runtime_state: RuntimeStateStore | None = None,
        telemetry: TelemetryPlaneStore | None = None,
        telemetry_enabled: bool | None = None,
        telemetry_db_path: Path | None = None,
    ) -> None:
        self._bus = message_bus
        self._ledger = ledger or SessionLedger(
            base_dir=ledger_dir,
            session_id=session_id,
        )
        self._runtime_state = runtime_state
        self.bridge_agent_id = bridge_agent_id
        self.lifecycle_topic = lifecycle_topic
        self._initialized = False
        telemetry_enabled_env = os.environ.get("DGC_ROUTER_TELEMETRY_ENABLE", "").strip()
        env_telemetry_db = os.environ.get("DGC_ROUTER_TELEMETRY_DB", "").strip()
        telemetry_requested = telemetry_db_path is not None or bool(env_telemetry_db)
        if telemetry is not None:
            self._telemetry = telemetry
            self._telemetry_enabled = (
                bool(telemetry_enabled) if telemetry_enabled is not None else True
            )
        else:
            if telemetry_enabled is None:
                self._telemetry_enabled = (
                    telemetry_enabled_env.lower() in {"1", "true", "yes", "on"}
                    or telemetry_requested
                )
            else:
                self._telemetry_enabled = bool(telemetry_enabled)
            if self._telemetry_enabled:
                configured_telemetry_path = telemetry_db_path
                if configured_telemetry_path is None and env_telemetry_db:
                    configured_telemetry_path = Path(env_telemetry_db)
                self._telemetry = (
                    TelemetryPlaneStore(configured_telemetry_path)
                    if configured_telemetry_path is not None
                    else TelemetryPlaneStore()
                )
            else:
                self._telemetry = None

    async def init_db(self) -> None:
        if self._initialized:
            return
        await self._bus.init_db()
        async with aiosqlite.connect(self._bus.db_path) as db:
            await db.execute(_TASKS_DDL)
            for index in _INDEXES:
                await db.execute(index)
            await db.commit()
        if self._runtime_state is not None:
            await self._runtime_state.init_db()
            await self._runtime_state.upsert_session(
                SessionState(
                    session_id=self._ledger.session_id,
                    operator_id="operator",
                    status="active",
                    current_task_id="",
                    metadata={"bridge_agent_id": self.bridge_agent_id},
                )
            )
        await self._upsert_telemetry_agent(
            self.bridge_agent_id,
            role="bridge",
            metadata={"source": "operator_bridge"},
        )
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

        await self._mirror_runtime_enqueued(task_record)

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
        claimed_task = await self._mirror_runtime_claimed(claimed_task)
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

    async def acknowledge_task_claim(
        self,
        *,
        task_id: str,
        acknowledged_by: str,
        note: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> OperatorBridgeTask:
        """Record that a claimed worker parsed and accepted the work order."""
        await self.init_db()
        existing = await self.get_task(task_id)
        if existing is None:
            raise KeyError(f"Bridge task {task_id} not found")
        if existing.status != BRIDGE_STATUS_IN_PROGRESS:
            raise ValueError(f"Bridge task {task_id} is not in progress")
        if existing.claimed_by and existing.claimed_by != acknowledged_by:
            raise ValueError(
                f"Bridge task {task_id} claimed by {existing.claimed_by}, not {acknowledged_by}"
            )

        claim_ack = {
            "acknowledged_by": acknowledged_by,
            "acknowledged_at": _utc_now_iso(),
            "note": note,
            **dict(metadata or {}),
        }
        task_metadata = dict(existing.metadata)
        task_metadata["claim_ack"] = claim_ack
        await self._set_metadata(task_id, task_metadata)

        updated = await self.get_task(task_id)
        assert updated is not None
        await self._mirror_runtime_acknowledged(updated, acknowledged_by=acknowledged_by, note=note)
        self._record_task_event(
            "bridge_task_acknowledged",
            task_id=task_id,
            acknowledged_by=acknowledged_by,
        )
        self._record_progress_event(
            "bridge_task_acknowledged",
            task_id=task_id,
            acknowledged_by=acknowledged_by,
        )
        await self._publish_lifecycle(
            "bridge_task_acknowledged",
            updated,
            extra={"acknowledged_by": acknowledged_by, "note": note},
        )
        return updated

    async def heartbeat_task(
        self,
        *,
        task_id: str,
        heartbeat_by: str,
        summary: str = "",
        progress: float | None = None,
        current_artifact_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> OperatorBridgeTask:
        """Emit an explicit bridge heartbeat/progress checkpoint."""
        await self.init_db()
        existing = await self.get_task(task_id)
        if existing is None:
            raise KeyError(f"Bridge task {task_id} not found")
        if existing.status != BRIDGE_STATUS_IN_PROGRESS:
            raise ValueError(f"Bridge task {task_id} is not in progress")
        if existing.claimed_by and existing.claimed_by != heartbeat_by:
            raise ValueError(
                f"Bridge task {task_id} claimed by {existing.claimed_by}, not {heartbeat_by}"
            )

        beat = {
            "heartbeat_by": heartbeat_by,
            "heartbeat_at": _utc_now_iso(),
            "summary": summary,
            "progress": progress,
            "current_artifact_id": current_artifact_id,
            **dict(metadata or {}),
        }
        task_metadata = dict(existing.metadata)
        history = list(task_metadata.get("progress_log", []))
        history.append(beat)
        task_metadata["progress_log"] = history[-10:]
        task_metadata["last_heartbeat"] = beat
        if current_artifact_id:
            task_metadata["current_artifact_id"] = current_artifact_id
        await self._set_metadata(task_id, task_metadata)

        updated = await self.get_task(task_id)
        assert updated is not None
        await self._mirror_runtime_heartbeat(
            updated,
            heartbeat_by=heartbeat_by,
            summary=summary,
            progress=progress,
            current_artifact_id=current_artifact_id,
        )
        self._record_progress_event(
            "bridge_task_heartbeat",
            task_id=task_id,
            heartbeat_by=heartbeat_by,
            summary=summary,
            progress=progress,
        )
        await self._publish_lifecycle(
            "bridge_task_heartbeat",
            updated,
            extra={
                "heartbeat_by": heartbeat_by,
                "summary": summary,
                "progress": progress,
            },
        )
        return updated

    async def record_partial_artifact(
        self,
        *,
        task_id: str,
        artifact_kind: str,
        path: str,
        summary: str = "",
        checksum: str = "",
        promotion_state: str = "ephemeral",
        metadata: dict[str, Any] | None = None,
    ) -> OperatorBridgeTask:
        """Record a checkpoint artifact before task completion."""
        await self.init_db()
        existing = await self.get_task(task_id)
        if existing is None:
            raise KeyError(f"Bridge task {task_id} not found")

        artifact_entry = {
            "artifact_kind": artifact_kind,
            "path": path,
            "summary": summary,
            "checksum": checksum,
            "promotion_state": promotion_state,
            "recorded_at": _utc_now_iso(),
            **dict(metadata or {}),
        }
        task_metadata = dict(existing.metadata)
        partials = list(task_metadata.get("partial_artifacts", []))
        partials.append(artifact_entry)
        task_metadata["partial_artifacts"] = partials[-12:]
        await self._set_metadata(task_id, task_metadata)

        updated = await self.get_task(task_id)
        assert updated is not None
        updated = await self._mirror_runtime_partial_artifact(
            updated,
            artifact_kind=artifact_kind,
            path=path,
            summary=summary,
            checksum=checksum,
            promotion_state=promotion_state,
            metadata=dict(metadata or {}),
        )
        self._record_progress_event(
            "bridge_partial_artifact_recorded",
            task_id=task_id,
            artifact_kind=artifact_kind,
            path=path,
        )
        await self._publish_lifecycle(
            "bridge_partial_artifact_recorded",
            updated,
            extra={
                "artifact_kind": artifact_kind,
                "path": path,
            },
        )
        return updated

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
            await self._mirror_runtime_recovered(task_record)
            self._record_task_event(
                "bridge_task_recovered",
                task_id=task_record.id,
                retry_count=task_record.retry_count,
                recovery_reason=task_record.recovery_reason,
            )
            await self._publish_lifecycle(
                "bridge_task_recovered",
                task_record,
                extra={
                    "retry_count": task_record.retry_count,
                    "recovery_reason": task_record.recovery_reason,
                },
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
        await self._mirror_runtime_responded(updated)

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
            extra={
                "status": status,
                "responded_by": responded_by,
                "summary": summary,
                "error": error,
            },
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
        await self._mirror_runtime_response_ack(updated, acknowledged_by=acknowledged_by, note=note)
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
            extra={"acknowledged_by": acknowledged_by, "note": note},
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

    async def _set_metadata(self, task_id: str, metadata: dict[str, Any]) -> None:
        async with aiosqlite.connect(self._bus.db_path) as db:
            await db.execute(
                "UPDATE operator_bridge_tasks SET metadata = ?, updated_at = ? WHERE id = ?",
                (_json_dump(metadata), _utc_now_iso(), task_id),
            )
            await db.commit()

    async def _mirror_runtime_enqueued(self, task: OperatorBridgeTask) -> None:
        if self._runtime_state is None:
            return
        await self._upsert_runtime_session(current_task_id="")
        await self._record_runtime_action(
            task=task,
            action_name="bridge_task_enqueued",
            actor=task.sender,
            payload={
                "scope": list(task.scope),
                "output": list(task.output),
                "constraints": list(task.constraints),
            },
        )

    async def _mirror_runtime_claimed(self, task: OperatorBridgeTask) -> OperatorBridgeTask:
        if self._runtime_state is None:
            return task

        metadata = dict(task.metadata)
        changed = False
        claim_id = str(metadata.get("runtime_claim_id", "") or "")
        if not claim_id:
            claim_id = self._runtime_state.new_claim_id()
            metadata["runtime_claim_id"] = claim_id
            changed = True
        run_id = str(metadata.get("runtime_run_id", "") or "")
        if not run_id:
            run_id = self._runtime_state.new_run_id()
            metadata["runtime_run_id"] = run_id
            changed = True
        if changed:
            await self._set_metadata(task.id, metadata)
            refreshed = await self.get_task(task.id)
            if refreshed is not None:
                task = refreshed

        claimed_at = task.claimed_at or _utc_now()
        stale_after = claimed_at + timedelta(seconds=task.claim_timeout_seconds)
        await self._runtime_state.record_task_claim(
            TaskClaim(
                claim_id=claim_id,
                task_id=task.id,
                session_id=self._ledger.session_id,
                agent_id=task.claimed_by or self.bridge_agent_id,
                status="claimed",
                claimed_at=claimed_at,
                stale_after=stale_after,
                metadata={
                    "bridge_task_id": task.id,
                    "sender": task.sender,
                    "scope": list(task.scope),
                    "output": list(task.output),
                    "constraints": list(task.constraints),
                },
            )
        )
        existing_run = await self._runtime_state.get_delegation_run(run_id)
        await self._runtime_state.record_delegation_run(
            DelegationRun(
                run_id=run_id,
                session_id=self._ledger.session_id,
                task_id=task.id,
                claim_id=claim_id,
                parent_run_id=existing_run.parent_run_id if existing_run else "",
                assigned_by=task.sender,
                assigned_to=task.claimed_by or self.bridge_agent_id,
                requested_output=list(task.output),
                current_artifact_id=str(task.metadata.get("current_artifact_id", "") or ""),
                status="claimed",
                started_at=existing_run.started_at if existing_run else claimed_at,
                completed_at=existing_run.completed_at if existing_run else None,
                failure_code=existing_run.failure_code if existing_run else "",
                metadata={
                    **(existing_run.metadata if existing_run else {}),
                    "bridge_task_id": task.id,
                    "scope": list(task.scope),
                    "constraints": list(task.constraints),
                },
            )
        )
        await self._upsert_runtime_session(current_task_id=task.id)
        await self._record_runtime_action(
            task=task,
            action_name="bridge_task_claimed",
            actor=task.claimed_by or self.bridge_agent_id,
            payload={"claim_id": claim_id, "run_id": run_id},
        )
        return task

    async def _mirror_runtime_acknowledged(
        self,
        task: OperatorBridgeTask,
        *,
        acknowledged_by: str,
        note: str,
    ) -> None:
        if self._runtime_state is None:
            return
        claim_id, run_id = self._runtime_ids(task)
        if claim_id:
            await self._runtime_state.acknowledge_task_claim(
                claim_id,
                status=BRIDGE_STATUS_ACKNOWLEDGED,
                metadata={"note": note, "acknowledged_by": acknowledged_by},
            )
        if run_id:
            existing_run = await self._runtime_state.get_delegation_run(run_id)
            if existing_run is not None:
                await self._runtime_state.record_delegation_run(
                    DelegationRun(
                        run_id=existing_run.run_id,
                        session_id=existing_run.session_id,
                        task_id=existing_run.task_id,
                        claim_id=existing_run.claim_id,
                        parent_run_id=existing_run.parent_run_id,
                        assigned_by=existing_run.assigned_by,
                        assigned_to=existing_run.assigned_to,
                        requested_output=existing_run.requested_output,
                        current_artifact_id=existing_run.current_artifact_id,
                        status=BRIDGE_STATUS_ACKNOWLEDGED,
                        started_at=existing_run.started_at,
                        completed_at=existing_run.completed_at,
                        failure_code=existing_run.failure_code,
                        metadata={
                            **existing_run.metadata,
                            "claim_ack": task.metadata.get("claim_ack", {}),
                        },
                    )
                )
        await self._record_runtime_action(
            task=task,
            action_name="bridge_task_acknowledged",
            actor=acknowledged_by,
            payload={"note": note},
        )

    async def _mirror_runtime_heartbeat(
        self,
        task: OperatorBridgeTask,
        *,
        heartbeat_by: str,
        summary: str,
        progress: float | None,
        current_artifact_id: str | None,
    ) -> None:
        if self._runtime_state is None:
            return
        claim_id, run_id = self._runtime_ids(task)
        heartbeat_payload = {
            "summary": summary,
            "progress": progress,
            "current_artifact_id": current_artifact_id,
        }
        if claim_id:
            existing_claim = await self._runtime_state.get_task_claim(claim_id)
            status = (
                BRIDGE_STATUS_ACKNOWLEDGED
                if task.metadata.get("claim_ack")
                else (existing_claim.status if existing_claim is not None else BRIDGE_STATUS_IN_PROGRESS)
            )
            await self._runtime_state.heartbeat_task_claim(
                claim_id,
                status=status,
                metadata={
                    **(existing_claim.metadata if existing_claim is not None else {}),
                    **heartbeat_payload,
                    "heartbeat_by": heartbeat_by,
                },
            )
        if run_id:
            existing_run = await self._runtime_state.get_delegation_run(run_id)
            if existing_run is not None:
                await self._runtime_state.record_delegation_run(
                    DelegationRun(
                        run_id=existing_run.run_id,
                        session_id=existing_run.session_id,
                        task_id=existing_run.task_id,
                        claim_id=existing_run.claim_id,
                        parent_run_id=existing_run.parent_run_id,
                        assigned_by=existing_run.assigned_by,
                        assigned_to=existing_run.assigned_to,
                        requested_output=existing_run.requested_output,
                        current_artifact_id=current_artifact_id or existing_run.current_artifact_id,
                        status=BRIDGE_STATUS_IN_PROGRESS,
                        started_at=existing_run.started_at,
                        completed_at=existing_run.completed_at,
                        failure_code=existing_run.failure_code,
                        metadata={
                            **existing_run.metadata,
                            "last_heartbeat": {
                                **heartbeat_payload,
                                "heartbeat_by": heartbeat_by,
                                "heartbeat_at": _utc_now_iso(),
                            },
                        },
                    )
                )
        await self._record_runtime_action(
            task=task,
            action_name="bridge_task_heartbeat",
            actor=heartbeat_by,
            payload=heartbeat_payload,
        )

    async def _mirror_runtime_partial_artifact(
        self,
        task: OperatorBridgeTask,
        *,
        artifact_kind: str,
        path: str,
        summary: str,
        checksum: str,
        promotion_state: str,
        metadata: dict[str, Any],
    ) -> OperatorBridgeTask:
        if self._runtime_state is None:
            return task
        _claim_id, run_id = self._runtime_ids(task)
        artifact_id = self._runtime_state.new_artifact_id()
        await self._runtime_state.record_artifact(
            ArtifactRecord(
                artifact_id=artifact_id,
                artifact_kind=artifact_kind,
                session_id=self._ledger.session_id,
                task_id=task.id,
                run_id=run_id,
                payload_path=path,
                checksum=checksum,
                promotion_state=promotion_state,
                metadata={
                    **metadata,
                    "bridge_task_id": task.id,
                    "summary": summary,
                },
            )
        )
        task_metadata = dict(task.metadata)
        task_metadata["current_artifact_id"] = artifact_id
        partial_ids = list(task_metadata.get("runtime_partial_artifact_ids", []))
        partial_ids.append(artifact_id)
        task_metadata["runtime_partial_artifact_ids"] = partial_ids[-12:]
        await self._set_metadata(task.id, task_metadata)
        refreshed = await self.get_task(task.id)
        if refreshed is not None:
            task = refreshed
        if run_id:
            existing_run = await self._runtime_state.get_delegation_run(run_id)
            if existing_run is not None:
                await self._runtime_state.record_delegation_run(
                    DelegationRun(
                        run_id=existing_run.run_id,
                        session_id=existing_run.session_id,
                        task_id=existing_run.task_id,
                        claim_id=existing_run.claim_id,
                        parent_run_id=existing_run.parent_run_id,
                        assigned_by=existing_run.assigned_by,
                        assigned_to=existing_run.assigned_to,
                        requested_output=existing_run.requested_output,
                        current_artifact_id=artifact_id,
                        status=existing_run.status,
                        started_at=existing_run.started_at,
                        completed_at=existing_run.completed_at,
                        failure_code=existing_run.failure_code,
                        metadata={
                            **existing_run.metadata,
                            "last_partial_artifact_id": artifact_id,
                        },
                    )
                )
        await self._record_runtime_action(
            task=task,
            action_name="bridge_partial_artifact_recorded",
            actor=task.claimed_by or self.bridge_agent_id,
            payload={
                "artifact_id": artifact_id,
                "artifact_kind": artifact_kind,
                "path": path,
                "promotion_state": promotion_state,
            },
        )
        return task

    async def _mirror_runtime_recovered(self, task: OperatorBridgeTask) -> None:
        if self._runtime_state is None:
            return
        claim_id, run_id = self._runtime_ids(task)
        if claim_id:
            existing_claim = await self._runtime_state.get_task_claim(claim_id)
            if existing_claim is not None:
                await self._runtime_state.record_task_claim(
                    TaskClaim(
                        claim_id=existing_claim.claim_id,
                        task_id=existing_claim.task_id,
                        session_id=existing_claim.session_id,
                        agent_id=existing_claim.agent_id,
                        status="recovered",
                        claimed_at=existing_claim.claimed_at,
                        acked_at=existing_claim.acked_at,
                        heartbeat_at=existing_claim.heartbeat_at,
                        stale_after=existing_claim.stale_after,
                        recovered_at=task.recovered_at or _utc_now(),
                        retry_count=task.retry_count,
                        metadata={
                            **existing_claim.metadata,
                            "recovery_reason": task.recovery_reason or "",
                        },
                    )
                )
        if run_id:
            existing_run = await self._runtime_state.get_delegation_run(run_id)
            if existing_run is not None:
                await self._runtime_state.record_delegation_run(
                    DelegationRun(
                        run_id=existing_run.run_id,
                        session_id=existing_run.session_id,
                        task_id=existing_run.task_id,
                        claim_id=existing_run.claim_id,
                        parent_run_id=existing_run.parent_run_id,
                        assigned_by=existing_run.assigned_by,
                        assigned_to=existing_run.assigned_to,
                        requested_output=existing_run.requested_output,
                        current_artifact_id=existing_run.current_artifact_id,
                        status="stale_recovered",
                        started_at=existing_run.started_at,
                        completed_at=existing_run.completed_at,
                        failure_code=existing_run.failure_code,
                        metadata={
                            **existing_run.metadata,
                            "recovery_reason": task.recovery_reason or "",
                            "retry_count": task.retry_count,
                        },
                    )
                )
        await self._record_runtime_action(
            task=task,
            action_name="bridge_task_recovered",
            actor=self.bridge_agent_id,
            payload={"recovery_reason": task.recovery_reason or "", "retry_count": task.retry_count},
        )

    async def _mirror_runtime_responded(self, task: OperatorBridgeTask) -> None:
        if self._runtime_state is None:
            return
        claim_id, run_id = self._runtime_ids(task)
        completed_at = task.completed_at or _utc_now()
        response_status = self._runtime_completion_status(task)
        if claim_id:
            existing_claim = await self._runtime_state.get_task_claim(claim_id)
            if existing_claim is not None:
                await self._runtime_state.record_task_claim(
                    TaskClaim(
                        claim_id=existing_claim.claim_id,
                        task_id=existing_claim.task_id,
                        session_id=existing_claim.session_id,
                        agent_id=existing_claim.agent_id,
                        status=response_status,
                        claimed_at=existing_claim.claimed_at,
                        acked_at=existing_claim.acked_at,
                        heartbeat_at=completed_at,
                        stale_after=existing_claim.stale_after,
                        recovered_at=existing_claim.recovered_at,
                        retry_count=existing_claim.retry_count,
                        metadata={
                            **existing_claim.metadata,
                            "bridge_status": task.status,
                        },
                    )
                )
        if run_id:
            existing_run = await self._runtime_state.get_delegation_run(run_id)
            if existing_run is not None:
                await self._runtime_state.record_delegation_run(
                    DelegationRun(
                        run_id=existing_run.run_id,
                        session_id=existing_run.session_id,
                        task_id=existing_run.task_id,
                        claim_id=existing_run.claim_id,
                        parent_run_id=existing_run.parent_run_id,
                        assigned_by=existing_run.assigned_by,
                        assigned_to=existing_run.assigned_to,
                        requested_output=existing_run.requested_output,
                        current_artifact_id=str(task.metadata.get("current_artifact_id", "") or existing_run.current_artifact_id),
                        status=response_status,
                        started_at=existing_run.started_at,
                        completed_at=completed_at,
                        failure_code=task.response.error if task.response and task.response.error else "",
                        metadata={
                            **existing_run.metadata,
                            "bridge_status": task.status,
                            "response_summary": task.response.summary if task.response else "",
                        },
                    )
                )
        if task.response is not None:
            artifact_paths = [
                ("report", task.response.report_path),
                ("patch", task.response.patch_path),
            ]
            promotion_state = "published" if response_status == "completed" else "ephemeral"
            for artifact_kind, artifact_path in artifact_paths:
                if not artifact_path:
                    continue
                await self._runtime_state.record_artifact(
                    ArtifactRecord(
                        artifact_id=self._runtime_state.new_artifact_id(),
                        artifact_kind=artifact_kind,
                        session_id=self._ledger.session_id,
                        task_id=task.id,
                        run_id=run_id,
                        payload_path=artifact_path,
                        promotion_state=promotion_state,
                        metadata={
                            "bridge_task_id": task.id,
                            "response_status": task.status,
                            "summary": task.response.summary,
                        },
                    )
                )
        await self._record_runtime_action(
            task=task,
            action_name="bridge_task_responded",
            actor=(task.response.metadata.get("responded_by") if task.response else None) or task.claimed_by or self.bridge_agent_id,
            payload={"bridge_status": task.status},
        )
        if response_status in {"completed", "failed"}:
            await self._upsert_runtime_session(current_task_id="")

    async def _mirror_runtime_response_ack(
        self,
        task: OperatorBridgeTask,
        *,
        acknowledged_by: str,
        note: str,
    ) -> None:
        if self._runtime_state is None:
            return
        claim_id, run_id = self._runtime_ids(task)
        if run_id:
            existing_run = await self._runtime_state.get_delegation_run(run_id)
            if existing_run is not None:
                await self._runtime_state.record_delegation_run(
                    DelegationRun(
                        run_id=existing_run.run_id,
                        session_id=existing_run.session_id,
                        task_id=existing_run.task_id,
                        claim_id=existing_run.claim_id,
                        parent_run_id=existing_run.parent_run_id,
                        assigned_by=existing_run.assigned_by,
                        assigned_to=existing_run.assigned_to,
                        requested_output=existing_run.requested_output,
                        current_artifact_id=existing_run.current_artifact_id,
                        status=existing_run.status,
                        started_at=existing_run.started_at,
                        completed_at=existing_run.completed_at,
                        failure_code=existing_run.failure_code,
                        metadata={
                            **existing_run.metadata,
                            "delivery_ack": task.metadata.get("delivery_ack", {}),
                        },
                    )
                )
        await self._record_runtime_action(
            task=task,
            action_name="bridge_response_acknowledged",
            actor=acknowledged_by,
            payload={"note": note, "claim_id": claim_id, "run_id": run_id},
        )

    async def _upsert_runtime_session(self, *, current_task_id: str) -> None:
        if self._runtime_state is None:
            return
        existing = await self._runtime_state.get_session(self._ledger.session_id)
        if existing is None:
            await self._runtime_state.upsert_session(
                SessionState(
                    session_id=self._ledger.session_id,
                    operator_id="operator",
                    status="active",
                    current_task_id=current_task_id,
                    metadata={"bridge_agent_id": self.bridge_agent_id},
                )
            )
            return
        await self._runtime_state.upsert_session(
            SessionState(
                session_id=existing.session_id,
                operator_id=existing.operator_id,
                status=existing.status,
                current_task_id=current_task_id,
                active_bundle_id=existing.active_bundle_id,
                metadata=existing.metadata,
                created_at=existing.created_at,
                updated_at=_utc_now(),
            )
        )

    async def _record_runtime_action(
        self,
        *,
        task: OperatorBridgeTask,
        action_name: str,
        actor: str | None,
        payload: dict[str, Any],
    ) -> None:
        if self._runtime_state is None:
            return
        _claim_id, run_id = self._runtime_ids(task)
        await self._runtime_state.record_operator_action(
            OperatorAction(
                action_id=self._runtime_state.new_action_id(),
                session_id=self._ledger.session_id,
                task_id=task.id,
                run_id=run_id,
                action_name=action_name,
                actor=actor or self.bridge_agent_id,
                payload=payload,
            )
        )

    @staticmethod
    def _runtime_ids(task: OperatorBridgeTask) -> tuple[str, str]:
        metadata = task.metadata if isinstance(task.metadata, dict) else {}
        claim_id = str(metadata.get("runtime_claim_id", "") or "")
        run_id = str(metadata.get("runtime_run_id", "") or "")
        return (claim_id, run_id)

    @staticmethod
    def _runtime_completion_status(task: OperatorBridgeTask) -> str:
        status = str(task.status or "").strip().lower()
        if status in {"done", "completed", "success"}:
            return "completed"
        if status in {"failed", "fail", "error", "cancelled", "canceled"}:
            return "failed"
        if task.response is not None and task.response.error:
            return "failed"
        return status or "completed"

    def _record_task_event(self, event: str, **payload: Any) -> None:
        self._ledger.task_event(event, **payload)

    def _record_progress_event(self, event: str, **payload: Any) -> None:
        self._ledger.progress_event(event, **payload)

    @staticmethod
    def _telemetry_id(prefix: str) -> str:
        return f"{prefix}_{_new_id()}"

    async def _upsert_telemetry_agent(
        self,
        agent_id: str,
        *,
        role: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._telemetry is None:
            return
        cleaned = str(agent_id).strip()
        if not cleaned:
            return
        try:
            await self._telemetry.upsert_agent_identity(
                AgentIdentityRecord(
                    agent_id=cleaned,
                    codename=cleaned,
                    specialization=role,
                    status="active",
                    last_active=_utc_now(),
                    metadata=dict(metadata or {}),
                )
            )
        except Exception:
            return

    async def _record_bridge_lifecycle_telemetry(
        self,
        *,
        event: str,
        task: OperatorBridgeTask,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self._telemetry is None:
            return
        merged_extra = dict(extra or {})
        run_id = str(task.metadata.get("runtime_run_id") or "")

        await self._upsert_telemetry_agent(
            task.sender,
            role="operator",
            metadata={"source": "operator_bridge", "bridge_event": event},
        )
        if task.claimed_by:
            await self._upsert_telemetry_agent(
                task.claimed_by,
                role="worker",
                metadata={"source": "operator_bridge", "bridge_event": event},
            )

        for actor_key, role in (
            ("sender", "operator"),
            ("claimed_by", "worker"),
            ("acknowledged_by", "worker"),
            ("heartbeat_by", "worker"),
            ("responded_by", "worker"),
        ):
            actor = merged_extra.get(actor_key)
            if actor:
                await self._upsert_telemetry_agent(
                    str(actor),
                    role=role,
                    metadata={"source": "operator_bridge", "bridge_event": event},
                )

        summary = (
            merged_extra.get("summary")
            or (task.response.summary if task.response is not None else "")
            or task.task
        )
        progress = merged_extra.get("progress")
        value = float(progress) if isinstance(progress, (int, float)) else 1.0
        unit = "progress_ratio" if isinstance(progress, (int, float)) else "event"
        status = str(task.status or event)
        metadata = {
            "bridge_event": event,
            "bridge_status": task.status,
            "sender": task.sender,
            "claimed_by": task.claimed_by or "",
            "retry_count": task.retry_count,
            "scope": list(task.scope),
            "output": list(task.output),
            "constraints": list(task.constraints),
            "payload": dict(task.payload),
            "task_metadata": dict(task.metadata),
            **merged_extra,
        }
        try:
            await self._telemetry.record_external_outcome(
                ExternalOutcomeRecord(
                    outcome_id=self._telemetry_id("bridge"),
                    outcome_kind=event,
                    value=value,
                    unit=unit,
                    confidence=1.0,
                    status=status,
                    subject_id=task.id,
                    summary=str(summary or task.task),
                    session_id=self._ledger.session_id,
                    task_id=task.id,
                    run_id=run_id,
                    metadata=metadata,
                )
            )
            if isinstance(progress, (int, float)):
                await self._telemetry.record_workflow_score(
                    WorkflowScoreRecord(
                        score_id=self._telemetry_id("workflow"),
                        workflow_id=task.id,
                        score_name="bridge_progress",
                        score_value=float(progress),
                        session_id=self._ledger.session_id,
                        task_id=task.id,
                        run_id=run_id,
                        metadata={"bridge_event": event, **merged_extra},
                    )
                )
            if event == "bridge_response_acknowledged":
                acknowledged_by = str(merged_extra.get("acknowledged_by") or "")
                if acknowledged_by:
                    await self._telemetry.record_intervention_outcome(
                        InterventionOutcomeRecord(
                            intervention_id=self._telemetry_id("intervention"),
                            intervention_type="bridge_response_acknowledged",
                            outcome_status="helpful",
                            operator_id=acknowledged_by,
                            summary=str(summary or task.task),
                            session_id=self._ledger.session_id,
                            task_id=task.id,
                            run_id=run_id,
                            metadata=metadata,
                        )
                    )
        except Exception:
            return

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
            logger.debug("Operator bridge emit failed", exc_info=True)
        await self._record_bridge_lifecycle_telemetry(
            event=event,
            task=task,
            extra=extra,
        )

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
