"""Concrete runtime-side implementations for sovereign contracts.

These adapters keep the sovereign contracts authoritative while mapping onto
the current DHARMA runtime modules.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import aiosqlite

from dharma_swarm.checkpoint import (
    CheckpointStore as LoopCheckpointStore,
    LoopCheckpoint,
)
from dharma_swarm.message_bus import MessageBus
from dharma_swarm.models import Message, MessagePriority, MessageStatus
from dharma_swarm.operator_bridge import BRIDGE_STATUS_QUEUED, OperatorBridge
from dharma_swarm.runtime_state import DelegationRun, RuntimeStateStore
from dharma_swarm.sandbox import LocalSandbox, SandboxError

from .common import (
    CheckpointRecord,
    CheckpointStatus,
    ExecutionRequest,
    ExecutionResult,
    GatewayMessage,
    RunDescriptor,
    RunStatus,
)

RUNTIME_SNAPSHOT_FORMAT = "runtime_snapshot_v1"
OPERATOR_BRIDGE_QUEUE_FORMAT = "operator_bridge_queue_v1"
A2A_TASK_PACKET_FORMAT = "a2a_task_packet_v1"

_DEFAULT_CHANNEL = "direct"
_CHECKPOINT_PAYLOAD_KIND = "dharma_swarm.checkpoint_record.v1"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _ensure_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _ensure_str_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]


def _parse_datetime(raw: Any) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None
    return None


def _iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _with_provenance(
    metadata: dict[str, Any],
    *,
    source_module: str,
    **details: Any,
) -> dict[str, Any]:
    merged = dict(metadata)
    provenance = _ensure_dict(merged.get("provenance"))
    provenance["source_module"] = source_module
    for key, value in details.items():
        if value not in (None, "", [], {}):
            provenance[key] = value
    merged["provenance"] = provenance
    return merged


def _with_import_marker(metadata: dict[str, Any], *, source: str) -> dict[str, Any]:
    merged = dict(metadata)
    merged["interop_import"] = {
        "source": source,
        "imported_at": _utc_now_iso(),
    }
    return merged


def _coerce_run_status(raw: str) -> RunStatus:
    try:
        return RunStatus(raw)
    except ValueError:
        if raw == "acknowledged":
            return RunStatus.CLAIMED
        if raw == "recovered":
            return RunStatus.STALE_RECOVERED
        return RunStatus.IN_PROGRESS


def _parse_run_status(raw: str) -> RunStatus:
    try:
        return RunStatus(raw)
    except ValueError as exc:
        raise ValueError(f"Unsupported sovereign run status: {raw!r}") from exc


def _coerce_checkpoint_status(raw: str) -> CheckpointStatus:
    try:
        return CheckpointStatus(raw)
    except ValueError:
        return CheckpointStatus.DRAFT


def _parse_checkpoint_status(raw: str) -> CheckpointStatus:
    try:
        return CheckpointStatus(raw)
    except ValueError as exc:
        raise ValueError(f"Unsupported sovereign checkpoint status: {raw!r}") from exc


def _message_priority_from_metadata(metadata: dict[str, Any]) -> MessagePriority:
    raw = str(metadata.get("priority", MessagePriority.NORMAL.value))
    try:
        return MessagePriority(raw)
    except ValueError:
        return MessagePriority.NORMAL


def _message_status_from_metadata(metadata: dict[str, Any]) -> MessageStatus:
    raw = str(metadata.get("status", MessageStatus.UNREAD.value))
    try:
        return MessageStatus(raw)
    except ValueError:
        return MessageStatus.UNREAD


def _runtime_hints(metadata: dict[str, Any]) -> dict[str, Any]:
    hints = _ensure_dict(metadata.get("runtime"))
    if hints:
        return hints
    return metadata


def _delegation_run_from_descriptor(run: RunDescriptor) -> DelegationRun:
    metadata = dict(run.metadata)
    hints = _runtime_hints(metadata)
    return DelegationRun(
        run_id=run.run_id,
        session_id=run.session_id,
        task_id=run.task_id,
        assigned_to=run.agent_id,
        claim_id=str(hints.get("claim_id", "")),
        parent_run_id=run.parent_run_id,
        assigned_by=str(hints.get("assigned_by", "")),
        requested_output=_ensure_str_list(hints.get("requested_output")),
        current_artifact_id=run.current_artifact_id,
        status=run.status.value,
        started_at=_parse_datetime(hints.get("started_at")) or _utc_now(),
        completed_at=_parse_datetime(hints.get("completed_at")),
        failure_code=str(hints.get("failure_code", "")),
        metadata=_with_provenance(
            metadata,
            source_module="dharma_swarm.runtime_state",
            backing_store="delegation_runs",
        ),
    )


def _descriptor_from_delegation_run(run: DelegationRun) -> RunDescriptor:
    metadata = dict(run.metadata)
    runtime_metadata = _ensure_dict(metadata.get("runtime"))
    runtime_metadata.update(
        {
            "claim_id": run.claim_id,
            "assigned_by": run.assigned_by,
            "requested_output": list(run.requested_output),
            "failure_code": run.failure_code,
            "started_at": run.started_at.isoformat(),
            "completed_at": _iso_or_none(run.completed_at),
        }
    )
    metadata["runtime"] = runtime_metadata
    metadata = _with_provenance(
        metadata,
        source_module="dharma_swarm.runtime_state",
        backing_store="delegation_runs",
    )
    return RunDescriptor(
        run_id=run.run_id,
        session_id=run.session_id,
        task_id=run.task_id,
        agent_id=run.assigned_to,
        parent_run_id=run.parent_run_id,
        status=_coerce_run_status(run.status),
        current_artifact_id=run.current_artifact_id,
        metadata=metadata,
    )


def _message_from_gateway(gateway_message: GatewayMessage) -> Message:
    metadata = dict(gateway_message.metadata)
    metadata["channel"] = gateway_message.channel or _DEFAULT_CHANNEL
    metadata = _with_provenance(
        metadata,
        source_module="dharma_swarm.message_bus",
        backing_store="messages",
    )
    kwargs: dict[str, Any] = {
        "from_agent": gateway_message.sender,
        "to_agent": gateway_message.recipient,
        "subject": metadata.get("subject"),
        "body": gateway_message.body,
        "priority": _message_priority_from_metadata(metadata),
        "status": _message_status_from_metadata(metadata),
        "created_at": _parse_datetime(metadata.get("created_at")) or _utc_now(),
        "reply_to": metadata.get("reply_to"),
        "metadata": metadata,
    }
    if gateway_message.message_id:
        kwargs["id"] = gateway_message.message_id
    return Message(**kwargs)


def _gateway_from_message(message: Message) -> GatewayMessage:
    metadata = dict(message.metadata)
    channel = str(metadata.get("channel") or metadata.get("topic") or _DEFAULT_CHANNEL)
    metadata["priority"] = message.priority.value
    metadata["status"] = message.status.value
    metadata["created_at"] = message.created_at.isoformat()
    if message.subject:
        metadata["subject"] = message.subject
    if message.reply_to:
        metadata["reply_to"] = message.reply_to
    metadata = _with_provenance(
        metadata,
        source_module="dharma_swarm.message_bus",
        backing_store="messages",
    )
    return GatewayMessage(
        message_id=message.id,
        channel=channel,
        sender=message.from_agent,
        recipient=message.to_agent,
        body=message.body,
        metadata=metadata,
    )


def _checkpoint_status_from_loop(checkpoint: LoopCheckpoint) -> CheckpointStatus:
    current = checkpoint.current if isinstance(checkpoint.current, dict) else {}
    if current.get("kind") == _CHECKPOINT_PAYLOAD_KIND:
        return _coerce_checkpoint_status(str(current.get("status", CheckpointStatus.DRAFT.value)))
    if checkpoint.converged:
        return CheckpointStatus.APPROVED
    if checkpoint.interrupted:
        return CheckpointStatus.READY
    return CheckpointStatus.DRAFT


def _loop_checkpoint_from_record(record: CheckpointRecord) -> LoopCheckpoint:
    metadata = dict(record.metadata)
    checkpoint_meta = _ensure_dict(metadata.get("checkpoint"))
    domain = str(
        checkpoint_meta.get("domain")
        or metadata.get("domain")
        or record.session_id
        or "runtime"
    )
    payload = {
        "kind": _CHECKPOINT_PAYLOAD_KIND,
        "checkpoint_id": record.checkpoint_id,
        "session_id": record.session_id,
        "task_id": record.task_id,
        "run_id": record.run_id,
        "status": record.status.value,
        "summary": record.summary,
        "artifact_refs": list(record.artifact_refs),
        "metadata": _with_provenance(
            metadata,
            source_module="dharma_swarm.checkpoint",
            backing_store="filesystem",
            domain=domain,
        ),
    }
    return LoopCheckpoint(
        domain=domain,
        cycle_id=record.checkpoint_id,
        iteration=int(checkpoint_meta.get("iteration", 0) or 0),
        current=payload,
        previous=_ensure_dict(checkpoint_meta.get("previous")) or None,
        candidates=[
            dict(value)
            for value in checkpoint_meta.get("candidates", [])
            if isinstance(value, dict)
        ],
        best_score=float(checkpoint_meta.get("best_score", 0.0) or 0.0),
        fitness_trajectory=[
            float(value)
            for value in checkpoint_meta.get("fitness_trajectory", [])
            if isinstance(value, (int, float))
        ],
        eigenform_trajectory=[
            float(value)
            for value in checkpoint_meta.get("eigenform_trajectory", [])
            if isinstance(value, (int, float))
        ],
        elapsed_seconds=float(checkpoint_meta.get("elapsed_seconds", 0.0) or 0.0),
        converged=record.status == CheckpointStatus.APPROVED,
        convergence_reason=record.summary if record.status == CheckpointStatus.APPROVED else "",
        interrupted=record.status in {
            CheckpointStatus.DRAFT,
            CheckpointStatus.READY,
            CheckpointStatus.REJECTED,
            CheckpointStatus.RESUMED,
        },
        interrupt_reason=record.summary if record.status != CheckpointStatus.APPROVED else "",
        version=str(checkpoint_meta.get("version", "sovereign-runtime-v1")),
        saved_at=str(checkpoint_meta.get("saved_at") or _utc_now_iso()),
    )


def _record_from_loop_checkpoint(checkpoint: LoopCheckpoint) -> CheckpointRecord:
    current = checkpoint.current if isinstance(checkpoint.current, dict) else {}
    metadata = _ensure_dict(current.get("metadata"))
    checkpoint_meta = _ensure_dict(metadata.get("checkpoint"))
    checkpoint_meta.update(
        {
            "domain": checkpoint.domain,
            "iteration": checkpoint.iteration,
            "saved_at": checkpoint.saved_at,
            "elapsed_seconds": checkpoint.elapsed_seconds,
            "fitness_trajectory": list(checkpoint.fitness_trajectory),
            "eigenform_trajectory": list(checkpoint.eigenform_trajectory),
            "version": checkpoint.version,
        }
    )
    metadata["checkpoint"] = checkpoint_meta
    metadata = _with_provenance(
        metadata,
        source_module="dharma_swarm.checkpoint",
        backing_store="filesystem",
        domain=checkpoint.domain,
    )
    return CheckpointRecord(
        checkpoint_id=str(current.get("checkpoint_id") or checkpoint.cycle_id),
        session_id=str(current.get("session_id") or ""),
        task_id=str(current.get("task_id") or ""),
        run_id=str(current.get("run_id") or ""),
        status=_checkpoint_status_from_loop(checkpoint),
        summary=str(
            current.get("summary")
            or checkpoint.interrupt_reason
            or checkpoint.convergence_reason
            or ""
        ),
        artifact_refs=tuple(_ensure_str_list(current.get("artifact_refs"))),
        metadata=metadata,
    )


def _run_descriptor_to_dict(run: RunDescriptor) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "session_id": run.session_id,
        "task_id": run.task_id,
        "agent_id": run.agent_id,
        "parent_run_id": run.parent_run_id,
        "status": run.status.value,
        "current_artifact_id": run.current_artifact_id,
        "metadata": dict(run.metadata),
    }


def _run_descriptor_from_dict(data: dict[str, Any]) -> RunDescriptor:
    return RunDescriptor(
        run_id=str(data["run_id"]),
        session_id=str(data.get("session_id", "")),
        task_id=str(data.get("task_id", "")),
        agent_id=str(data.get("agent_id", "")),
        parent_run_id=str(data.get("parent_run_id", "")),
        status=_parse_run_status(str(data.get("status", RunStatus.QUEUED.value))),
        current_artifact_id=str(data.get("current_artifact_id", "")),
        metadata=_ensure_dict(data.get("metadata")),
    )


def _gateway_message_to_dict(message: GatewayMessage) -> dict[str, Any]:
    return {
        "message_id": message.message_id,
        "channel": message.channel,
        "sender": message.sender,
        "recipient": message.recipient,
        "body": message.body,
        "metadata": dict(message.metadata),
    }


def _gateway_message_from_dict(data: dict[str, Any]) -> GatewayMessage:
    return GatewayMessage(
        message_id=str(data.get("message_id", "")),
        channel=str(data.get("channel") or _DEFAULT_CHANNEL),
        sender=str(data.get("sender", "")),
        recipient=str(data.get("recipient", "")),
        body=str(data.get("body", "")),
        metadata=_ensure_dict(data.get("metadata")),
    )


def _checkpoint_record_to_dict(record: CheckpointRecord) -> dict[str, Any]:
    return {
        "checkpoint_id": record.checkpoint_id,
        "session_id": record.session_id,
        "task_id": record.task_id,
        "run_id": record.run_id,
        "status": record.status.value,
        "summary": record.summary,
        "artifact_refs": list(record.artifact_refs),
        "metadata": dict(record.metadata),
    }


def _checkpoint_record_from_dict(data: dict[str, Any]) -> CheckpointRecord:
    return CheckpointRecord(
        checkpoint_id=str(data["checkpoint_id"]),
        session_id=str(data.get("session_id", "")),
        task_id=str(data.get("task_id", "")),
        run_id=str(data.get("run_id", "")),
        status=_parse_checkpoint_status(str(data.get("status", CheckpointStatus.DRAFT.value))),
        summary=str(data.get("summary", "")),
        artifact_refs=tuple(_ensure_str_list(data.get("artifact_refs"))),
        metadata=_ensure_dict(data.get("metadata")),
    )


def _bridge_task_to_dict(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "sender": task.sender,
        "task": task.task,
        "scope": list(task.scope),
        "output": list(task.output),
        "constraints": list(task.constraints),
        "payload": dict(task.payload),
        "status": task.status,
        "claim_timeout_seconds": task.claim_timeout_seconds,
        "metadata": dict(task.metadata),
        "created_at": task.created_at.isoformat(),
        "updated_at": task.updated_at.isoformat(),
    }


def _merge_checkpoint_records(*groups: list[CheckpointRecord]) -> list[CheckpointRecord]:
    merged: list[CheckpointRecord] = []
    seen: set[str] = set()
    for group in groups:
        for record in group:
            if record.checkpoint_id in seen:
                continue
            seen.add(record.checkpoint_id)
            merged.append(record)
    return merged


class RuntimeStateAgentRuntimeAdapter:
    """Sovereign run lifecycle adapter backed by RuntimeStateStore."""

    def __init__(self, runtime_state: RuntimeStateStore) -> None:
        self._runtime_state = runtime_state

    async def start_run(self, run: RunDescriptor) -> RunDescriptor:
        stored = await self._runtime_state.record_delegation_run(
            _delegation_run_from_descriptor(run)
        )
        return _descriptor_from_delegation_run(stored)

    async def update_run(self, run: RunDescriptor) -> RunDescriptor:
        stored = await self._runtime_state.record_delegation_run(
            _delegation_run_from_descriptor(run)
        )
        return _descriptor_from_delegation_run(stored)

    async def get_run(self, run_id: str) -> RunDescriptor | None:
        stored = await self._runtime_state.get_delegation_run(run_id)
        if stored is None:
            return None
        return _descriptor_from_delegation_run(stored)

    async def list_runs(
        self,
        *,
        session_id: str | None = None,
        task_id: str | None = None,
        limit: int = 50,
    ) -> list[RunDescriptor]:
        runs = await self._runtime_state.list_delegation_runs(
            session_id=session_id,
            task_id=task_id,
            limit=max(1, limit),
        )
        return [_descriptor_from_delegation_run(run) for run in runs]


class MessageBusGatewayAdapter:
    """Sovereign messaging adapter backed by MessageBus."""

    def __init__(
        self,
        message_bus: MessageBus,
        *,
        default_channel: str = _DEFAULT_CHANNEL,
    ) -> None:
        self._message_bus = message_bus
        self._default_channel = default_channel

    async def send_message(self, message: GatewayMessage) -> str:
        await self._message_bus.init_db()
        return await self._message_bus.send(_message_from_gateway(message))

    async def receive_messages(
        self,
        *,
        recipient: str,
        channel: str | None = None,
        limit: int = 50,
    ) -> list[GatewayMessage]:
        await self._message_bus.init_db()
        messages = await self._message_bus.receive(
            recipient,
            status="",
            limit=max(1, limit),
        )
        mapped = [_gateway_from_message(message) for message in messages]
        if channel is not None:
            mapped = [message for message in mapped if message.channel == channel]
        return mapped[: max(1, limit)]

    async def acknowledge_delivery(
        self,
        *,
        message_id: str,
        acknowledged_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._message_bus.init_db()
        await self._message_bus.mark_read(message_id)
        await self._message_bus.emit_event(
            "gateway_delivery_acknowledged",
            agent_id=acknowledged_by,
            payload={
                "message_id": message_id,
                "acknowledged_by": acknowledged_by,
                "metadata": _ensure_dict(metadata),
                "source_module": "dharma_swarm.message_bus",
            },
        )

    async def list_channels(self) -> list[str]:
        await self._message_bus.init_db()
        channels = {self._default_channel}
        async with aiosqlite.connect(self._message_bus.db_path) as db:
            subscription_rows = await (
                await db.execute("SELECT topic FROM subscriptions")
            ).fetchall()
            channels.update(str(row[0]) for row in subscription_rows if row and row[0])

            message_rows = await (
                await db.execute(
                    "SELECT metadata FROM messages ORDER BY created_at DESC LIMIT 500"
                )
            ).fetchall()
        for row in message_rows:
            raw = row[0]
            if not raw:
                continue
            try:
                metadata = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(metadata, dict):
                channel = metadata.get("channel") or metadata.get("topic")
                if channel:
                    channels.add(str(channel))
        return sorted(channels)


class FilesystemCheckpointStoreAdapter:
    """Sovereign checkpoint adapter backed by filesystem LoopCheckpointStore."""

    def __init__(self, store: LoopCheckpointStore) -> None:
        self._store = store

    @property
    def base_dir(self) -> Path:
        return self._store.base_dir

    async def _all_records(self) -> list[CheckpointRecord]:
        checkpoints = await asyncio.to_thread(self._store.list_checkpoints)
        return [_record_from_loop_checkpoint(checkpoint) for checkpoint in checkpoints]

    async def save_checkpoint(self, checkpoint: CheckpointRecord) -> CheckpointRecord:
        await asyncio.to_thread(self._store.save, _loop_checkpoint_from_record(checkpoint))
        loaded = await self.get_checkpoint(checkpoint.checkpoint_id)
        assert loaded is not None
        return loaded

    async def get_checkpoint(self, checkpoint_id: str) -> CheckpointRecord | None:
        for checkpoint in await self._all_records():
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint
        return None

    async def list_checkpoints(
        self,
        *,
        session_id: str | None = None,
        run_id: str | None = None,
        limit: int = 50,
    ) -> list[CheckpointRecord]:
        records = await self._all_records()
        if session_id is not None:
            records = [record for record in records if record.session_id == session_id]
        if run_id is not None:
            records = [record for record in records if record.run_id == run_id]
        return records[: max(1, limit)]

    async def resolve_checkpoint(
        self,
        *,
        checkpoint_id: str,
        status: str,
        resolved_by: str,
        metadata: dict[str, Any] | None = None,
    ) -> CheckpointRecord:
        existing = await self.get_checkpoint(checkpoint_id)
        if existing is None:
            raise KeyError(f"Checkpoint {checkpoint_id} not found")
        merged_metadata = dict(existing.metadata)
        merged_metadata.update(_ensure_dict(metadata))
        merged_metadata["resolution"] = {
            "status": _parse_checkpoint_status(status).value,
            "resolved_by": resolved_by,
            "resolved_at": _utc_now_iso(),
        }
        return await self.save_checkpoint(
            CheckpointRecord(
                checkpoint_id=existing.checkpoint_id,
                session_id=existing.session_id,
                task_id=existing.task_id,
                run_id=existing.run_id,
                status=_parse_checkpoint_status(status),
                summary=existing.summary,
                artifact_refs=existing.artifact_refs,
                metadata=merged_metadata,
            )
        )


class LocalSandboxProviderAdapter:
    """Sovereign execution adapter backed by LocalSandbox."""

    def __init__(self, *, default_workdir: Path | None = None) -> None:
        self._default_workdir = Path(default_workdir) if default_workdir else None

    async def execute(self, request: ExecutionRequest) -> ExecutionResult:
        workdir = Path(request.workdir) if request.workdir else self._default_workdir
        sandbox = LocalSandbox(workdir=workdir) if workdir is not None else LocalSandbox()
        try:
            result = await sandbox.execute(
                request.command,
                timeout=request.timeout_seconds,
            )
            metadata = dict(request.metadata)
            metadata.update(
                {
                    "backend": "local",
                    "workdir": str(sandbox.workdir),
                    "source_module": "dharma_swarm.sandbox",
                }
            )
            return ExecutionResult(
                exit_code=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                timed_out=result.timed_out,
                duration_seconds=result.duration_seconds,
                metadata=metadata,
            )
        except SandboxError as exc:
            metadata = dict(request.metadata)
            metadata.update(
                {
                    "backend": "local",
                    "rejected": True,
                    "source_module": "dharma_swarm.sandbox",
                }
            )
            if workdir is not None:
                metadata["workdir"] = str(workdir)
            return ExecutionResult(
                exit_code=-1,
                stderr=str(exc),
                timed_out=False,
                duration_seconds=0.0,
                metadata=metadata,
            )
        finally:
            await sandbox.cleanup()

    async def describe_capabilities(self) -> dict[str, Any]:
        return {
            "backend": "local",
            "supports_timeout": True,
            "supports_python": True,
            "isolation": "asyncio_subprocess",
            "default_workdir": str(self._default_workdir) if self._default_workdir else "",
            "source_module": "dharma_swarm.sandbox",
        }


class SovereignRuntimeInteropAdapter:
    """Interop snapshots for sovereign runtime contract slices."""

    def __init__(
        self,
        *,
        runtime_state: RuntimeStateStore,
        message_bus: MessageBus,
        checkpoint_store: LoopCheckpointStore,
        operator_bridge: OperatorBridge | None = None,
        snapshot_limit: int = 200,
    ) -> None:
        self._runtime = RuntimeStateAgentRuntimeAdapter(runtime_state)
        self._gateway = MessageBusGatewayAdapter(message_bus)
        self._checkpoint_store = FilesystemCheckpointStoreAdapter(checkpoint_store)
        self._runtime_state = runtime_state
        self._message_bus = message_bus
        self._operator_bridge = operator_bridge
        self._snapshot_limit = max(1, snapshot_limit)

    async def export_snapshot(self, *, format_name: str) -> dict[str, Any]:
        if format_name == RUNTIME_SNAPSHOT_FORMAT:
            return await self._export_runtime_snapshot()
        if format_name == OPERATOR_BRIDGE_QUEUE_FORMAT:
            return await self._export_operator_bridge_queue()
        if format_name == A2A_TASK_PACKET_FORMAT:
            return await self._export_a2a_task_packet()
        raise ValueError(f"Unsupported runtime interop format: {format_name!r}")

    async def import_snapshot(
        self,
        payload: dict[str, Any],
        *,
        source: str,
    ) -> dict[str, Any]:
        format_name = str(payload.get("format") or source)
        if format_name == RUNTIME_SNAPSHOT_FORMAT:
            return await self._import_runtime_snapshot(payload, source=source)
        if format_name == OPERATOR_BRIDGE_QUEUE_FORMAT:
            return await self._import_operator_bridge_queue(payload, source=source)
        if format_name == A2A_TASK_PACKET_FORMAT:
            return await self._import_a2a_task_packet(payload, source=source)
        raise ValueError(f"Unsupported runtime interop format: {format_name!r}")

    async def _export_runtime_snapshot(self) -> dict[str, Any]:
        runs = await self._runtime.list_runs(limit=self._snapshot_limit)
        messages = await self._message_bus.list_messages(limit=self._snapshot_limit)
        checkpoints = await self._checkpoint_store.list_checkpoints(limit=self._snapshot_limit)

        payload: dict[str, Any] = {
            "format": RUNTIME_SNAPSHOT_FORMAT,
            "exported_at": _utc_now_iso(),
            "runs": [_run_descriptor_to_dict(run) for run in runs],
            "messages": [
                _gateway_message_to_dict(_gateway_from_message(message))
                for message in messages
            ],
            "checkpoints": [
                _checkpoint_record_to_dict(checkpoint) for checkpoint in checkpoints
            ],
            "provenance": {
                "source_module": "dharma_swarm.contracts.runtime_adapters",
                "runtime_state_db": str(self._runtime_state.db_path),
                "message_bus_db": str(self._message_bus.db_path),
                "checkpoint_dir": str(self._checkpoint_store.base_dir),
            },
        }
        if self._operator_bridge is not None:
            payload["bridge_queue"] = [
                _bridge_task_to_dict(task)
                for task in await self._operator_bridge.list_tasks(
                    status=BRIDGE_STATUS_QUEUED,
                    limit=self._snapshot_limit,
                )
            ]
        return payload

    async def _export_operator_bridge_queue(self) -> dict[str, Any]:
        if self._operator_bridge is None:
            raise ValueError("operator_bridge_queue_v1 requires an OperatorBridge")
        tasks = await self._operator_bridge.list_tasks(
            status=BRIDGE_STATUS_QUEUED,
            limit=self._snapshot_limit,
        )
        return {
            "format": OPERATOR_BRIDGE_QUEUE_FORMAT,
            "exported_at": _utc_now_iso(),
            "tasks": [_bridge_task_to_dict(task) for task in tasks],
            "provenance": {
                "source_module": "dharma_swarm.operator_bridge",
            },
        }

    async def _export_a2a_task_packet(self) -> dict[str, Any]:
        if self._operator_bridge is None:
            raise ValueError("a2a_task_packet_v1 requires an OperatorBridge")

        tasks = await self._operator_bridge.list_tasks(
            status=BRIDGE_STATUS_QUEUED,
            limit=self._snapshot_limit,
        )
        messages = await self._message_bus.list_messages(limit=self._snapshot_limit)
        runs = await self._runtime.list_runs(limit=self._snapshot_limit)
        checkpoints = await self._checkpoint_store.list_checkpoints(limit=self._snapshot_limit)

        gateway_messages = [_gateway_from_message(message) for message in messages]
        messages_by_id = {
            message.message_id: message
            for message in gateway_messages
            if message.message_id
        }
        runs_by_task: dict[str, RunDescriptor] = {}
        for run in runs:
            if run.task_id and run.task_id not in runs_by_task:
                runs_by_task[run.task_id] = run
        checkpoints_by_task: dict[str, list[CheckpointRecord]] = {}
        checkpoints_by_run: dict[str, list[CheckpointRecord]] = {}
        for checkpoint in checkpoints:
            if checkpoint.task_id:
                checkpoints_by_task.setdefault(checkpoint.task_id, []).append(checkpoint)
            if checkpoint.run_id:
                checkpoints_by_run.setdefault(checkpoint.run_id, []).append(checkpoint)

        task_packets: list[dict[str, Any]] = []
        for task in tasks:
            run = runs_by_task.get(task.id)
            related_checkpoints = _merge_checkpoint_records(
                checkpoints_by_task.get(task.id, []),
                checkpoints_by_run.get(run.run_id, []) if run is not None else [],
            )
            request_message = (
                messages_by_id.get(task.request_message_id or "")
                if task.request_message_id
                else None
            )
            response_message_id = (
                task.response.response_message_id
                if task.response is not None
                else None
            )
            response_message = (
                messages_by_id.get(response_message_id or "")
                if response_message_id
                else None
            )
            task_packets.append(
                {
                    "task_id": task.id,
                    "status": task.status,
                    "sender": task.sender,
                    "summary": task.task,
                    "scope": list(task.scope),
                    "requested_output": list(task.output),
                    "constraints": list(task.constraints),
                    "payload": dict(task.payload),
                    "metadata": dict(task.metadata),
                    "request_message": (
                        _gateway_message_to_dict(request_message)
                        if request_message is not None
                        else None
                    ),
                    "response_message": (
                        _gateway_message_to_dict(response_message)
                        if response_message is not None
                        else None
                    ),
                    "run": _run_descriptor_to_dict(run) if run is not None else None,
                    "checkpoints": [
                        _checkpoint_record_to_dict(checkpoint)
                        for checkpoint in related_checkpoints
                    ],
                }
            )

        return {
            "format": A2A_TASK_PACKET_FORMAT,
            "exported_at": _utc_now_iso(),
            "agent_card": {
                "system": "dharma_swarm",
                "agent_id": self._operator_bridge.bridge_agent_id,
                "capabilities": [
                    "task_handoff",
                    "checkpoint_transfer",
                    "gateway_message_transfer",
                    "runtime_run_transfer",
                ],
                "supported_formats": [
                    A2A_TASK_PACKET_FORMAT,
                    RUNTIME_SNAPSHOT_FORMAT,
                    OPERATOR_BRIDGE_QUEUE_FORMAT,
                ],
            },
            "tasks": task_packets,
            "provenance": {
                "source_module": "dharma_swarm.contracts.runtime_adapters",
                "bridge_agent_id": self._operator_bridge.bridge_agent_id,
                "runtime_state_db": str(self._runtime_state.db_path),
                "message_bus_db": str(self._message_bus.db_path),
            },
        }

    async def _import_runtime_snapshot(
        self,
        payload: dict[str, Any],
        *,
        source: str,
    ) -> dict[str, Any]:
        counts = {
            "runs": 0,
            "messages": 0,
            "checkpoints": 0,
            "bridge_tasks": 0,
            "skipped_existing_messages": 0,
            "skipped_existing_bridge_tasks": 0,
        }
        for run_data in payload.get("runs", []):
            run = _run_descriptor_from_dict(_ensure_dict(run_data))
            imported = RunDescriptor(
                run_id=run.run_id,
                session_id=run.session_id,
                task_id=run.task_id,
                agent_id=run.agent_id,
                parent_run_id=run.parent_run_id,
                status=run.status,
                current_artifact_id=run.current_artifact_id,
                metadata=_with_import_marker(run.metadata, source=source),
            )
            existing = await self._runtime.get_run(imported.run_id)
            if existing is None:
                await self._runtime.start_run(imported)
            else:
                await self._runtime.update_run(imported)
            counts["runs"] += 1

        for message_data in payload.get("messages", []):
            message = _gateway_message_from_dict(_ensure_dict(message_data))
            if await self._message_exists(message.message_id):
                counts["skipped_existing_messages"] += 1
                continue
            imported = GatewayMessage(
                message_id=message.message_id,
                channel=message.channel,
                sender=message.sender,
                recipient=message.recipient,
                body=message.body,
                metadata=_with_import_marker(message.metadata, source=source),
            )
            await self._gateway.send_message(imported)
            counts["messages"] += 1

        for checkpoint_data in payload.get("checkpoints", []):
            checkpoint = _checkpoint_record_from_dict(_ensure_dict(checkpoint_data))
            imported = CheckpointRecord(
                checkpoint_id=checkpoint.checkpoint_id,
                session_id=checkpoint.session_id,
                task_id=checkpoint.task_id,
                run_id=checkpoint.run_id,
                status=checkpoint.status,
                summary=checkpoint.summary,
                artifact_refs=checkpoint.artifact_refs,
                metadata=_with_import_marker(checkpoint.metadata, source=source),
            )
            await self._checkpoint_store.save_checkpoint(imported)
            counts["checkpoints"] += 1

        if "bridge_queue" in payload:
            bridge_result = await self._import_bridge_tasks(
                payload={"tasks": payload["bridge_queue"]},
                source=source,
            )
            counts["bridge_tasks"] = int(bridge_result.get("imported", 0))
            counts["skipped_existing_bridge_tasks"] = int(
                bridge_result.get("skipped_existing", 0)
            )

        return {
            "format": RUNTIME_SNAPSHOT_FORMAT,
            "source": source,
            "imported": counts,
        }

    async def _import_operator_bridge_queue(
        self,
        payload: dict[str, Any],
        *,
        source: str,
    ) -> dict[str, Any]:
        result = await self._import_bridge_tasks(payload=payload, source=source)
        return {
            "format": OPERATOR_BRIDGE_QUEUE_FORMAT,
            "source": source,
            **result,
        }

    async def _import_a2a_task_packet(
        self,
        payload: dict[str, Any],
        *,
        source: str,
    ) -> dict[str, Any]:
        if self._operator_bridge is None:
            raise ValueError("a2a_task_packet_v1 requires an OperatorBridge")

        counts = {
            "runs": 0,
            "messages": 0,
            "checkpoints": 0,
            "bridge_tasks": 0,
            "skipped_existing_messages": 0,
            "skipped_existing_bridge_tasks": 0,
            "skipped_non_queued_tasks": 0,
        }

        for item in payload.get("tasks", []):
            task = _ensure_dict(item)
            task_id = str(task.get("task_id") or "")
            request_message = _ensure_dict(task.get("request_message"))
            response_message = _ensure_dict(task.get("response_message"))
            for message_payload in (request_message, response_message):
                if not message_payload:
                    continue
                message = _gateway_message_from_dict(message_payload)
                if await self._message_exists(message.message_id):
                    counts["skipped_existing_messages"] += 1
                    continue
                imported_message = GatewayMessage(
                    message_id=message.message_id,
                    channel=message.channel,
                    sender=message.sender,
                    recipient=message.recipient,
                    body=message.body,
                    metadata=_with_import_marker(message.metadata, source=source),
                )
                await self._gateway.send_message(imported_message)
                counts["messages"] += 1

            run_payload = _ensure_dict(task.get("run"))
            if run_payload:
                run = _run_descriptor_from_dict(run_payload)
                imported_run = RunDescriptor(
                    run_id=run.run_id,
                    session_id=run.session_id,
                    task_id=run.task_id,
                    agent_id=run.agent_id,
                    parent_run_id=run.parent_run_id,
                    status=run.status,
                    current_artifact_id=run.current_artifact_id,
                    metadata=_with_import_marker(run.metadata, source=source),
                )
                existing = await self._runtime.get_run(imported_run.run_id)
                if existing is None:
                    await self._runtime.start_run(imported_run)
                else:
                    await self._runtime.update_run(imported_run)
                counts["runs"] += 1

            for checkpoint_payload in task.get("checkpoints", []):
                checkpoint = _checkpoint_record_from_dict(_ensure_dict(checkpoint_payload))
                imported_checkpoint = CheckpointRecord(
                    checkpoint_id=checkpoint.checkpoint_id,
                    session_id=checkpoint.session_id,
                    task_id=checkpoint.task_id,
                    run_id=checkpoint.run_id,
                    status=checkpoint.status,
                    summary=checkpoint.summary,
                    artifact_refs=checkpoint.artifact_refs,
                    metadata=_with_import_marker(checkpoint.metadata, source=source),
                )
                await self._checkpoint_store.save_checkpoint(imported_checkpoint)
                counts["checkpoints"] += 1

            status = str(task.get("status", BRIDGE_STATUS_QUEUED))
            if status != BRIDGE_STATUS_QUEUED:
                counts["skipped_non_queued_tasks"] += 1
                continue
            if task_id and await self._operator_bridge.get_task(task_id) is not None:
                counts["skipped_existing_bridge_tasks"] += 1
                continue
            await self._operator_bridge.enqueue_task(
                task=str(task.get("summary", "")),
                sender=str(task.get("sender", "operator")),
                scope=_ensure_str_list(task.get("scope")),
                output=_ensure_str_list(task.get("requested_output")),
                constraints=_ensure_str_list(task.get("constraints")),
                payload=_ensure_dict(task.get("payload")),
                metadata=_with_import_marker(_ensure_dict(task.get("metadata")), source=source),
                task_id=task_id or None,
            )
            counts["bridge_tasks"] += 1

        return {
            "format": A2A_TASK_PACKET_FORMAT,
            "source": source,
            "imported": counts,
        }

    async def _import_bridge_tasks(
        self,
        *,
        payload: dict[str, Any],
        source: str,
    ) -> dict[str, Any]:
        if self._operator_bridge is None:
            raise ValueError("Bridge task import requires an OperatorBridge")
        imported = 0
        skipped_existing = 0
        skipped_non_queued = 0
        for item in payload.get("tasks", []):
            task = _ensure_dict(item)
            if str(task.get("status", BRIDGE_STATUS_QUEUED)) != BRIDGE_STATUS_QUEUED:
                skipped_non_queued += 1
                continue
            task_id = str(task["id"])
            if await self._operator_bridge.get_task(task_id) is not None:
                skipped_existing += 1
                continue
            metadata = _with_import_marker(_ensure_dict(task.get("metadata")), source=source)
            await self._operator_bridge.enqueue_task(
                task=str(task.get("task", "")),
                sender=str(task.get("sender", "operator")),
                scope=_ensure_str_list(task.get("scope")),
                output=_ensure_str_list(task.get("output")),
                constraints=_ensure_str_list(task.get("constraints")),
                payload=_ensure_dict(task.get("payload")),
                metadata=metadata,
                claim_timeout_seconds=int(task.get("claim_timeout_seconds", 1800)),
                task_id=task_id,
            )
            imported += 1
        return {
            "imported": imported,
            "skipped_existing": skipped_existing,
            "skipped_non_queued": skipped_non_queued,
        }

    async def _message_exists(self, message_id: str) -> bool:
        if not message_id:
            return False
        await self._message_bus.init_db()
        async with aiosqlite.connect(self._message_bus.db_path) as db:
            row = await (
                await db.execute(
                    "SELECT 1 FROM messages WHERE id = ?",
                    (message_id,),
                )
            ).fetchone()
        return row is not None
