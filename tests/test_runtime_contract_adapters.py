from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dharma_swarm.checkpoint import CheckpointStore as LoopCheckpointStore
from dharma_swarm.contracts import (
    AgentRuntime,
    A2A_TASK_PACKET_FORMAT,
    CheckpointStatus,
    GatewayAdapter,
    InteropAdapter,
    RunStatus,
    SandboxProvider,
)
from dharma_swarm.contracts.runtime import CheckpointStore as RuntimeCheckpointStore
from dharma_swarm.contracts.runtime_adapters import (
    A2A_TASK_PACKET_FORMAT as A2A_TASK_PACKET_FORMAT_DIRECT,
    FilesystemCheckpointStoreAdapter,
    LocalSandboxProviderAdapter,
    MessageBusGatewayAdapter,
    OPERATOR_BRIDGE_QUEUE_FORMAT,
    RUNTIME_SNAPSHOT_FORMAT,
    RuntimeStateAgentRuntimeAdapter,
    SovereignRuntimeInteropAdapter,
)
from dharma_swarm.contracts.common import (
    CheckpointRecord,
    ExecutionRequest,
    GatewayMessage,
    RunDescriptor,
)
from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import BRIDGE_STATUS_QUEUED, OperatorBridge
from dharma_swarm.runtime_state import RuntimeStateStore


@pytest.mark.asyncio
async def test_agent_runtime_adapter_round_trips_run_descriptor(tmp_path) -> None:
    runtime = RuntimeStateStore(tmp_path / "runtime.db")
    adapter = RuntimeStateAgentRuntimeAdapter(runtime)

    assert isinstance(adapter, AgentRuntime)

    created = await adapter.start_run(
        RunDescriptor(
            run_id="run-1",
            session_id="sess-1",
            task_id="task-1",
            agent_id="worker-1",
            status=RunStatus.QUEUED,
            metadata={
                "runtime": {
                    "assigned_by": "operator",
                    "requested_output": ["patch"],
                    "started_at": datetime(2026, 3, 19, tzinfo=timezone.utc).isoformat(),
                }
            },
        )
    )
    runtime_metadata = dict(created.metadata["runtime"])
    runtime_metadata["completed_at"] = datetime(
        2026, 3, 19, 12, 0, tzinfo=timezone.utc
    ).isoformat()
    updated = await adapter.update_run(
        RunDescriptor(
            run_id="run-1",
            session_id="sess-1",
            task_id="task-1",
            agent_id="worker-1",
            status=RunStatus.COMPLETED,
            current_artifact_id="artifact-1",
            metadata={
                **created.metadata,
                "runtime": runtime_metadata,
            },
        )
    )
    fetched = await adapter.get_run("run-1")
    listed = await adapter.list_runs(session_id="sess-1", limit=5)

    assert created.metadata["runtime"]["requested_output"] == ["patch"]
    assert updated.status == RunStatus.COMPLETED
    assert updated.current_artifact_id == "artifact-1"
    assert fetched is not None
    assert fetched.metadata["runtime"]["assigned_by"] == "operator"
    assert fetched.metadata["provenance"]["source_module"] == "dharma_swarm.runtime_state"
    assert [run.run_id for run in listed] == ["run-1"]


@pytest.mark.asyncio
async def test_gateway_and_sandbox_adapters_preserve_delivery_audit(tmp_path) -> None:
    bus = MessageBus(tmp_path / "messages.db")
    gateway = MessageBusGatewayAdapter(bus)
    sandbox = LocalSandboxProviderAdapter(default_workdir=tmp_path)

    assert isinstance(gateway, GatewayAdapter)
    assert isinstance(sandbox, SandboxProvider)

    sent_id = await gateway.send_message(
        GatewayMessage(
            message_id="msg-1",
            channel="runtime.audit",
            sender="operator",
            recipient="worker-1",
            body="run the runtime slice",
            metadata={"priority": "high", "subject": "Runtime Audit"},
        )
    )
    received = await gateway.receive_messages(
        recipient="worker-1",
        channel="runtime.audit",
        limit=5,
    )
    await gateway.acknowledge_delivery(
        message_id=sent_id,
        acknowledged_by="worker-1",
        metadata={"reason": "accepted"},
    )
    events = await bus.consume_events("gateway_delivery_acknowledged")
    channels = await gateway.list_channels()
    result = await sandbox.execute(
        ExecutionRequest(
            command="pwd",
            workdir=str(tmp_path),
            timeout_seconds=5,
        )
    )
    rejected = await sandbox.execute(
        ExecutionRequest(command="rm -rf /", timeout_seconds=5)
    )

    assert [message.message_id for message in received] == ["msg-1"]
    assert received[0].metadata["subject"] == "Runtime Audit"
    assert events[0]["payload"]["metadata"]["reason"] == "accepted"
    assert "runtime.audit" in channels
    assert result.exit_code == 0
    assert result.metadata["workdir"] == str(tmp_path)
    assert str(tmp_path) in result.stdout
    assert rejected.exit_code == -1
    assert rejected.metadata["rejected"] is True


@pytest.mark.asyncio
async def test_checkpoint_store_adapter_resolves_and_filters(tmp_path) -> None:
    adapter = FilesystemCheckpointStoreAdapter(
        LoopCheckpointStore(base_dir=tmp_path / "checkpoints")
    )

    assert isinstance(adapter, RuntimeCheckpointStore)

    saved = await adapter.save_checkpoint(
        CheckpointRecord(
            checkpoint_id="cp-1",
            session_id="sess-1",
            task_id="task-1",
            run_id="run-1",
            status=CheckpointStatus.READY,
            summary="Awaiting operator review",
            artifact_refs=("artifact-1",),
            metadata={
                "checkpoint": {"domain": "runtime"},
                "review_ticket": "RT-1",
            },
        )
    )
    approved = await adapter.resolve_checkpoint(
        checkpoint_id="cp-1",
        status="approved",
        resolved_by="operator",
        metadata={"decision_note": "ship it"},
    )
    listed = await adapter.list_checkpoints(
        session_id="sess-1",
        run_id="run-1",
        limit=5,
    )

    assert saved.status == CheckpointStatus.READY
    assert approved.status == CheckpointStatus.APPROVED
    assert approved.metadata["checkpoint"]["domain"] == "runtime"
    assert approved.metadata["resolution"]["resolved_by"] == "operator"
    assert approved.metadata["decision_note"] == "ship it"
    assert [record.checkpoint_id for record in listed] == ["cp-1"]


@pytest.mark.asyncio
async def test_runtime_interop_adapter_restores_sovereign_runtime_slice(tmp_path) -> None:
    source_runtime = RuntimeStateStore(tmp_path / "source_runtime.db")
    source_bus = MessageBus(tmp_path / "source_messages.db")
    source_loop_store = LoopCheckpointStore(base_dir=tmp_path / "source_checkpoints")
    source_bridge = OperatorBridge(
        message_bus=source_bus,
        ledger_dir=tmp_path / "source_ledgers",
        session_id="sess-interop",
        runtime_state=source_runtime,
    )
    await source_bridge.init_db()

    source_runs = RuntimeStateAgentRuntimeAdapter(source_runtime)
    source_gateway = MessageBusGatewayAdapter(source_bus)
    source_checkpoints = FilesystemCheckpointStoreAdapter(source_loop_store)
    source_interop = SovereignRuntimeInteropAdapter(
        runtime_state=source_runtime,
        message_bus=source_bus,
        checkpoint_store=source_loop_store,
        operator_bridge=source_bridge,
    )

    assert isinstance(source_interop, InteropAdapter)

    started = await source_runs.start_run(
        RunDescriptor(
            run_id="run-interop",
            session_id="sess-interop",
            task_id="task-interop",
            agent_id="worker-interop",
            status=RunStatus.IN_PROGRESS,
            metadata={"runtime": {"assigned_by": "operator"}},
        )
    )
    await source_gateway.send_message(
        GatewayMessage(
            message_id="msg-interop",
            channel="runtime.audit",
            sender="operator",
            recipient="worker-interop",
            body="handoff",
            metadata={"priority": "normal"},
        )
    )
    await source_checkpoints.save_checkpoint(
        CheckpointRecord(
            checkpoint_id="cp-interop",
            session_id="sess-interop",
            task_id="task-interop",
            run_id=started.run_id,
            status=CheckpointStatus.READY,
            summary="Paused for operator review",
            artifact_refs=("artifact-interop",),
            metadata={"checkpoint": {"domain": "runtime"}},
        )
    )
    await source_bridge.enqueue_task(
        task="interop follow-up",
        sender="operator",
        output=["report"],
        task_id="bridge-interop",
    )

    snapshot = await source_interop.export_snapshot(format_name=RUNTIME_SNAPSHOT_FORMAT)

    assert snapshot["format"] == RUNTIME_SNAPSHOT_FORMAT
    assert [item["id"] for item in snapshot["bridge_queue"]] == ["bridge-interop"]

    restored_runtime = RuntimeStateStore(tmp_path / "restored_runtime.db")
    restored_bus = MessageBus(tmp_path / "restored_messages.db")
    restored_loop_store = LoopCheckpointStore(base_dir=tmp_path / "restored_checkpoints")
    restored_bridge = OperatorBridge(
        message_bus=restored_bus,
        ledger_dir=tmp_path / "restored_ledgers",
        session_id="sess-interop",
        runtime_state=restored_runtime,
    )
    await restored_bridge.init_db()

    restored_runs = RuntimeStateAgentRuntimeAdapter(restored_runtime)
    restored_gateway = MessageBusGatewayAdapter(restored_bus)
    restored_checkpoints = FilesystemCheckpointStoreAdapter(restored_loop_store)
    restored_interop = SovereignRuntimeInteropAdapter(
        runtime_state=restored_runtime,
        message_bus=restored_bus,
        checkpoint_store=restored_loop_store,
        operator_bridge=restored_bridge,
    )

    result = await restored_interop.import_snapshot(
        snapshot,
        source=RUNTIME_SNAPSHOT_FORMAT,
    )
    restored_run = await restored_runs.get_run("run-interop")
    restored_messages = await restored_gateway.receive_messages(
        recipient="worker-interop",
        channel="runtime.audit",
        limit=5,
    )
    restored_checkpoint = await restored_checkpoints.get_checkpoint("cp-interop")
    restored_tasks = await restored_bridge.list_tasks(
        status=BRIDGE_STATUS_QUEUED,
        limit=10,
    )

    assert result["imported"]["runs"] >= 1
    assert result["imported"]["messages"] >= 1
    assert result["imported"]["checkpoints"] == 1
    assert result["imported"]["bridge_tasks"] == 1
    assert restored_run is not None
    assert restored_run.metadata["interop_import"]["source"] == RUNTIME_SNAPSHOT_FORMAT
    assert [message.message_id for message in restored_messages] == ["msg-interop"]
    assert restored_checkpoint is not None
    assert restored_checkpoint.metadata["interop_import"]["source"] == RUNTIME_SNAPSHOT_FORMAT
    assert [task.id for task in restored_tasks] == ["bridge-interop"]


@pytest.mark.asyncio
async def test_operator_bridge_queue_format_round_trips_queued_tasks_only(tmp_path) -> None:
    source_bus = MessageBus(tmp_path / "queue_source.db")
    source_runtime = RuntimeStateStore(tmp_path / "queue_source_runtime.db")
    source_bridge = OperatorBridge(
        message_bus=source_bus,
        ledger_dir=tmp_path / "queue_source_ledgers",
        session_id="sess-queue",
        runtime_state=source_runtime,
    )
    await source_bridge.init_db()
    await source_bridge.enqueue_task(
        task="queued task",
        sender="operator",
        task_id="queue-1",
    )

    source_interop = SovereignRuntimeInteropAdapter(
        runtime_state=source_runtime,
        message_bus=source_bus,
        checkpoint_store=LoopCheckpointStore(base_dir=tmp_path / "queue_source_checkpoints"),
        operator_bridge=source_bridge,
    )
    payload = await source_interop.export_snapshot(
        format_name=OPERATOR_BRIDGE_QUEUE_FORMAT
    )

    restored_bus = MessageBus(tmp_path / "queue_restored.db")
    restored_runtime = RuntimeStateStore(tmp_path / "queue_restored_runtime.db")
    restored_bridge = OperatorBridge(
        message_bus=restored_bus,
        ledger_dir=tmp_path / "queue_restored_ledgers",
        session_id="sess-queue",
        runtime_state=restored_runtime,
    )
    await restored_bridge.init_db()
    restored_interop = SovereignRuntimeInteropAdapter(
        runtime_state=restored_runtime,
        message_bus=restored_bus,
        checkpoint_store=LoopCheckpointStore(base_dir=tmp_path / "queue_restored_checkpoints"),
        operator_bridge=restored_bridge,
    )

    result = await restored_interop.import_snapshot(
        payload,
        source=OPERATOR_BRIDGE_QUEUE_FORMAT,
    )
    restored_tasks = await restored_bridge.list_tasks(
        status=BRIDGE_STATUS_QUEUED,
        limit=10,
    )

    assert result["imported"] == 1
    assert [task.id for task in restored_tasks] == ["queue-1"]


@pytest.mark.asyncio
async def test_a2a_task_packet_format_round_trips_bridge_task_context(tmp_path) -> None:
    source_runtime = RuntimeStateStore(tmp_path / "a2a_source_runtime.db")
    source_bus = MessageBus(tmp_path / "a2a_source_messages.db")
    source_loop_store = LoopCheckpointStore(base_dir=tmp_path / "a2a_source_checkpoints")
    source_bridge = OperatorBridge(
        message_bus=source_bus,
        ledger_dir=tmp_path / "a2a_source_ledgers",
        session_id="sess-a2a",
        runtime_state=source_runtime,
    )
    await source_bridge.init_db()

    source_runs = RuntimeStateAgentRuntimeAdapter(source_runtime)
    source_checkpoints = FilesystemCheckpointStoreAdapter(source_loop_store)
    source_interop = SovereignRuntimeInteropAdapter(
        runtime_state=source_runtime,
        message_bus=source_bus,
        checkpoint_store=source_loop_store,
        operator_bridge=source_bridge,
    )

    await source_runs.start_run(
        RunDescriptor(
            run_id="run-a2a",
            session_id="sess-a2a",
            task_id="bridge-a2a",
            agent_id="worker-a2a",
            status=RunStatus.QUEUED,
            metadata={"runtime": {"assigned_by": "operator"}},
        )
    )
    await source_checkpoints.save_checkpoint(
        CheckpointRecord(
            checkpoint_id="cp-a2a",
            session_id="sess-a2a",
            task_id="bridge-a2a",
            run_id="run-a2a",
            status=CheckpointStatus.READY,
            summary="Await operator handoff",
            artifact_refs=("artifact-a2a",),
            metadata={"checkpoint": {"domain": "runtime"}},
        )
    )
    await source_bridge.enqueue_task(
        task="handoff this task to another sovereign runtime",
        sender="operator",
        output=["report", "patch"],
        constraints=["keep_audit_trail"],
        payload={"priority": "high"},
        metadata={"handoff_kind": "a2a"},
        task_id="bridge-a2a",
    )

    payload = await source_interop.export_snapshot(format_name=A2A_TASK_PACKET_FORMAT)

    assert A2A_TASK_PACKET_FORMAT == A2A_TASK_PACKET_FORMAT_DIRECT
    assert payload["format"] == A2A_TASK_PACKET_FORMAT
    assert payload["agent_card"]["system"] == "dharma_swarm"
    assert payload["tasks"][0]["task_id"] == "bridge-a2a"
    assert payload["tasks"][0]["run"]["run_id"] == "run-a2a"
    assert payload["tasks"][0]["checkpoints"][0]["checkpoint_id"] == "cp-a2a"

    restored_runtime = RuntimeStateStore(tmp_path / "a2a_restored_runtime.db")
    restored_bus = MessageBus(tmp_path / "a2a_restored_messages.db")
    restored_loop_store = LoopCheckpointStore(base_dir=tmp_path / "a2a_restored_checkpoints")
    restored_bridge = OperatorBridge(
        message_bus=restored_bus,
        ledger_dir=tmp_path / "a2a_restored_ledgers",
        session_id="sess-a2a",
        runtime_state=restored_runtime,
    )
    await restored_bridge.init_db()
    restored_runs = RuntimeStateAgentRuntimeAdapter(restored_runtime)
    restored_checkpoints = FilesystemCheckpointStoreAdapter(restored_loop_store)
    restored_interop = SovereignRuntimeInteropAdapter(
        runtime_state=restored_runtime,
        message_bus=restored_bus,
        checkpoint_store=restored_loop_store,
        operator_bridge=restored_bridge,
    )

    result = await restored_interop.import_snapshot(
        payload,
        source=A2A_TASK_PACKET_FORMAT,
    )
    restored_run = await restored_runs.get_run("run-a2a")
    restored_task = await restored_bridge.get_task("bridge-a2a")
    restored_checkpoint = await restored_checkpoints.get_checkpoint("cp-a2a")

    assert result["imported"]["bridge_tasks"] == 1
    assert result["imported"]["runs"] == 1
    assert result["imported"]["checkpoints"] == 1
    assert restored_run is not None
    assert restored_run.metadata["interop_import"]["source"] == A2A_TASK_PACKET_FORMAT
    assert restored_task is not None
    assert restored_task.metadata["interop_import"]["source"] == A2A_TASK_PACKET_FORMAT
    assert restored_checkpoint is not None
    assert restored_checkpoint.metadata["interop_import"]["source"] == A2A_TASK_PACKET_FORMAT
