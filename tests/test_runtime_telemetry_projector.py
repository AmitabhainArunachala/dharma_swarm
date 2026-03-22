from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dharma_swarm.runtime_state import (
    DelegationRun,
    OperatorAction,
    RuntimeStateStore,
    SessionEventRecord,
    SessionState,
    TaskClaim,
)
from dharma_swarm.runtime_telemetry_projector import RuntimeTelemetryProjector
from dharma_swarm.telemetry_plane import TelemetryPlaneStore


@pytest.mark.asyncio
async def test_runtime_telemetry_projector_backfills_runtime_records(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    runtime = RuntimeStateStore(db_path)
    telemetry = TelemetryPlaneStore(db_path)
    await runtime.init_db()
    await telemetry.init_db()

    await runtime.upsert_session(
        SessionState(
            session_id="sess-1",
            operator_id="operator",
            status="active",
            current_task_id="task-1",
            metadata={"bridge_agent_id": "operator_bridge"},
        )
    )
    await runtime.record_task_claim(
        TaskClaim(
            claim_id="claim-1",
            task_id="task-1",
            session_id="sess-1",
            agent_id="worker-1",
            status="acknowledged",
            retry_count=1,
        )
    )
    await runtime.record_delegation_run(
        DelegationRun(
            run_id="run-1",
            session_id="sess-1",
            task_id="task-1",
            claim_id="claim-1",
            assigned_by="operator",
            assigned_to="worker-1",
            status="completed",
            requested_output=["patch", "report"],
            metadata={
                "route_path": "bridge->worker",
                "selected_provider": "anthropic",
                "selected_model_hint": "claude-sonnet",
                "confidence": 0.82,
            },
        )
    )
    await runtime.record_operator_action(
        OperatorAction(
            action_id="action-1",
            action_name="bridge_response_acknowledged",
            actor="operator",
            session_id="sess-1",
            task_id="task-1",
            run_id="run-1",
            payload={"progress": 0.75, "note": "accepted"},
        )
    )
    await runtime.record_session_event(
        SessionEventRecord(
            event_id="event-1",
            session_id="sess-1",
            ledger_kind="task",
            event_name="task_enqueued",
            task_id="task-1",
            agent_id="worker-1",
            summary="task queued for worker",
            payload={"status": "queued"},
            created_at=datetime(2026, 3, 20, tzinfo=timezone.utc),
        )
    )

    projector = RuntimeTelemetryProjector(runtime_state=runtime, telemetry=telemetry)

    first = await projector.project_recent()
    second = await projector.project_recent()

    assert sum(first.values()) >= 5
    assert sum(second.values()) == 0

    agents = await telemetry.list_agent_identities(limit=10)
    routes = await telemetry.list_routing_decisions(limit=10)
    interventions = await telemetry.list_intervention_outcomes(limit=10)
    outcomes = await telemetry.list_external_outcomes(limit=20)
    workflow_scores = await telemetry.list_workflow_scores(limit=20)

    agent_ids = {item.agent_id for item in agents}
    outcome_kinds = {item.outcome_kind for item in outcomes}
    score_names = {item.score_name for item in workflow_scores}

    assert {"operator", "operator_bridge", "worker-1"}.issubset(agent_ids)
    assert any(item.selected_provider == "anthropic" for item in routes)
    assert any(item.route_path == "bridge->worker" for item in routes)
    assert interventions[0].operator_id == "operator"
    assert "runtime_session_state" in outcome_kinds
    assert "task_enqueued" in outcome_kinds
    assert "run_completion_score" in score_names
    assert "operator_action_progress" in score_names
