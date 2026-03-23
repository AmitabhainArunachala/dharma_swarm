from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dharma_swarm.message_bus import MessageBus
from dharma_swarm.operator_bridge import OperatorBridge
from dharma_swarm.telemetry_plane import TelemetryPlaneStore


@pytest.mark.asyncio
async def test_operator_bridge_lifecycle_writes_telemetry_records(tmp_path) -> None:
    telemetry = TelemetryPlaneStore(tmp_path / "runtime.db")
    bus = MessageBus(tmp_path / "bridge.db")
    bridge = OperatorBridge(
        message_bus=bus,
        ledger_dir=tmp_path / "ledgers",
        session_id="sess_bridge_telemetry",
        telemetry=telemetry,
    )
    await bridge.init_db()

    record = await bridge.enqueue_task(
        task="Stabilize the canonical dashboard shell",
        sender="operator",
        output=["patch", "report"],
    )
    await bridge.claim_task(claimed_by="codex-runner", task_id=record.id)
    await bridge.acknowledge_task_claim(
        task_id=record.id,
        acknowledged_by="codex-runner",
        note="work order accepted",
    )
    await bridge.heartbeat_task(
        task_id=record.id,
        heartbeat_by="codex-runner",
        summary="halfway done",
        progress=0.5,
    )
    await bridge.respond_task(
        task_id=record.id,
        status="done",
        summary="Shipped the dashboard stabilization slice.",
    )
    await bridge.acknowledge_response(
        task_id=record.id,
        acknowledged_by="operator",
        note="received",
    )

    bridge_identity = await telemetry.get_agent_identity("operator_bridge")
    worker_identity = await telemetry.get_agent_identity("codex-runner")
    sender_identity = await telemetry.get_agent_identity("operator")
    outcomes = await telemetry.list_external_outcomes(
        session_id="sess_bridge_telemetry",
        limit=20,
    )
    progress_scores = await telemetry.list_workflow_scores(
        workflow_id=record.id,
        score_name="bridge_progress",
        limit=10,
    )
    interventions = await telemetry.list_intervention_outcomes(
        task_id=record.id,
        operator_id="operator",
        limit=10,
    )

    outcome_kinds = {item.outcome_kind for item in outcomes}
    assert bridge_identity is not None
    assert worker_identity is not None
    assert sender_identity is not None
    assert {
        "bridge_task_enqueued",
        "bridge_task_claimed",
        "bridge_task_acknowledged",
        "bridge_task_heartbeat",
        "bridge_task_responded",
        "bridge_response_acknowledged",
    }.issubset(outcome_kinds)
    assert len(progress_scores) == 1
    assert progress_scores[0].score_value == pytest.approx(0.5)
    assert len(interventions) == 1
    assert interventions[0].intervention_type == "bridge_response_acknowledged"


@pytest.mark.asyncio
async def test_operator_bridge_recovery_writes_recovered_outcome(tmp_path) -> None:
    telemetry = TelemetryPlaneStore(tmp_path / "runtime.db")
    bus = MessageBus(tmp_path / "bridge.db")
    bridge = OperatorBridge(
        message_bus=bus,
        ledger_dir=tmp_path / "ledgers",
        session_id="sess_bridge_recovery",
        telemetry=telemetry,
    )
    await bridge.init_db()

    record = await bridge.enqueue_task(
        task="Recover stale bridge work",
        sender="operator",
        claim_timeout_seconds=30,
    )
    claimed = await bridge.claim_task(
        claimed_by="codex-runner",
        task_id=record.id,
        now=datetime.now(timezone.utc) - timedelta(minutes=5),
    )

    assert claimed is not None
    recovered = await bridge.recover_stale_tasks(now=datetime.now(timezone.utc))
    outcomes = await telemetry.list_external_outcomes(
        session_id="sess_bridge_recovery",
        limit=20,
    )

    assert [task.id for task in recovered] == [record.id]
    assert any(
        item.outcome_kind == "bridge_task_recovered" and item.subject_id == record.id
        for item in outcomes
    )
