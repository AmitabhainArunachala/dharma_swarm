from __future__ import annotations

import pytest

from dharma_swarm.contracts import (
    AgentRuntime,
    CheckpointStore as RuntimeCheckpointStore,
    CheckpointStatus,
    GatewayAdapter,
    InteropAdapter,
    RUNTIME_SNAPSHOT_FORMAT,
    RunStatus,
    build_sovereign_runtime_layer,
)
from dharma_swarm.contracts.common import (
    CheckpointRecord,
    GatewayMessage,
    RunDescriptor,
)
from dharma_swarm.resident_operator import ResidentOperator


@pytest.mark.asyncio
async def test_resident_operator_bootstrap_adopts_sovereign_runtime_layer(tmp_path) -> None:
    state_dir = tmp_path / ".dharma"
    operator = ResidentOperator(state_dir=state_dir)
    operator._conversations = _make_mock_store(tmp_path)
    operator._graduation = _make_mock_graduation(tmp_path)

    await operator.start()
    try:
        runtime = operator.runtime_contracts()

        assert isinstance(runtime.agent_runtime, AgentRuntime)
        assert isinstance(runtime.gateway, GatewayAdapter)
        assert isinstance(runtime.checkpoints, RuntimeCheckpointStore)
        assert isinstance(runtime.interop, InteropAdapter)

        created = await runtime.agent_runtime.start_run(
            RunDescriptor(
                run_id="run-resident",
                session_id="sess-resident",
                task_id="task-resident",
                agent_id="worker-runtime",
                status=RunStatus.IN_PROGRESS,
                metadata={"runtime": {"assigned_by": "resident_operator"}},
            )
        )
        await runtime.gateway.send_message(
            GatewayMessage(
                message_id="msg-resident",
                channel="runtime.audit",
                sender="resident_operator",
                recipient="worker-runtime",
                body="runtime layer adopted",
                metadata={"priority": "normal"},
            )
        )
        await runtime.checkpoints.save_checkpoint(
            CheckpointRecord(
                checkpoint_id="cp-resident",
                session_id=created.session_id,
                task_id=created.task_id,
                run_id=created.run_id,
                status=CheckpointStatus.READY,
                summary="resident operator runtime checkpoint",
                artifact_refs=("artifact-resident",),
                metadata={"checkpoint": {"domain": "resident_operator"}},
            )
        )
        snapshot = await runtime.export_snapshot(format_name=RUNTIME_SNAPSHOT_FORMAT)

        restored = await build_sovereign_runtime_layer(
            state_dir=tmp_path / ".restored",
            session_id="sess-restored",
        )
        await restored.import_snapshot(snapshot, source=RUNTIME_SNAPSHOT_FORMAT)

        restored_run = await restored.agent_runtime.get_run("run-resident")
        restored_messages = await restored.gateway.receive_messages(
            recipient="worker-runtime",
            channel="runtime.audit",
            limit=10,
        )
        restored_checkpoint = await restored.checkpoints.get_checkpoint("cp-resident")

        assert restored_run is not None
        assert restored_run.metadata["interop_import"]["source"] == RUNTIME_SNAPSHOT_FORMAT
        assert [message.message_id for message in restored_messages] == ["msg-resident"]
        assert restored_checkpoint is not None
        assert restored_checkpoint.status == CheckpointStatus.READY
        assert restored_checkpoint.metadata["interop_import"]["source"] == RUNTIME_SNAPSHOT_FORMAT
        assert snapshot["provenance"]["message_bus_db"] == str(
            state_dir / "db" / "messages.db"
        )
    finally:
        await operator.stop()


def _make_mock_store(tmp_path):
    from dharma_swarm.conversation_store import ConversationStore

    return ConversationStore(db_path=tmp_path / "resident_adoption_conv.db")


def _make_mock_graduation(tmp_path):
    from dharma_swarm.graduation_engine import GraduationEngine

    return GraduationEngine(db_path=tmp_path / "resident_adoption_grad.db")
