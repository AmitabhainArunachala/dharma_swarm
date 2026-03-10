from __future__ import annotations

import json

import pytest

from dharma_swarm.artifact_store import RuntimeArtifactStore
from dharma_swarm.flywheel_exporter import FlywheelExporter
from dharma_swarm.memory_lattice import MemoryLattice
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType
from dharma_swarm.runtime_state import (
    ContextBundleRecord,
    DelegationRun,
    OperatorAction,
    RuntimeStateStore,
    SessionState,
    WorkspaceLease,
)


@pytest.mark.asyncio
async def test_flywheel_exporter_builds_manifest_backed_export_and_receipt(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    runtime_state = RuntimeStateStore(db_path)
    memory_lattice = MemoryLattice(db_path=db_path, event_log_dir=tmp_path / "events")
    artifact_store = RuntimeArtifactStore(
        base_dir=tmp_path / "workspace" / "sessions",
        runtime_state=runtime_state,
    )
    await runtime_state.init_db()
    await memory_lattice.init_db()

    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-fly",
            operator_id="operator",
            status="active",
            current_task_id="task-fly",
        )
    )
    stored = await artifact_store.create_text_artifact_async(
        session_id="sess-fly",
        artifact_type="documents",
        artifact_kind="report",
        content="# Export Source\n\nShip the canonical flywheel seam.",
        created_by="codex",
        task_id="task-fly",
        run_id="run-fly",
        trace_id="trace-fly",
        promotion_state="published",
        metadata={"topic": "flywheel"},
        provenance={"source": "test"},
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-fly",
            session_id="sess-fly",
            task_id="task-fly",
            assigned_to="agent-fly",
            assigned_by="operator",
            requested_output=["report", "eval"],
            current_artifact_id=stored.record.artifact_id,
            status="completed",
            metadata={"trace_id": "trace-fly"},
        )
    )
    await runtime_state.record_workspace_lease(
        WorkspaceLease(
            lease_id="lease-fly",
            zone_path=str(tmp_path / "workspace" / "sessions" / "sess-fly"),
            holder_run_id="run-fly",
            mode="write",
        )
    )
    await runtime_state.record_context_bundle(
        ContextBundleRecord(
            bundle_id="bundle-fly",
            session_id="sess-fly",
            task_id="task-fly",
            run_id="run-fly",
            token_budget=240,
            rendered_text="Operator Intent: export the canonical workload.",
            sections=[{"name": "Task", "content": "task-fly"}],
            source_refs=[f"artifact://{stored.record.artifact_id}"],
            checksum="ctx-fly",
        )
    )
    await runtime_state.record_operator_action(
        OperatorAction(
            action_id="act-fly",
            action_name="approve_export",
            actor="operator",
            session_id="sess-fly",
            task_id="task-fly",
            run_id="run-fly",
            reason="ready for accelerator lane",
            payload={"decision": "ship"},
        )
    )
    await memory_lattice.ingest_runtime_envelope(
        RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="orchestrator.lifecycle",
            agent_id="agent-fly",
            session_id="sess-fly",
            trace_id="trace-fly",
            event_id="evt-fly-1",
            payload={
                "action_name": "claim",
                "decision": "recorded",
                "confidence": 1.0,
                "task_id": "task-fly",
                "run_id": "run-fly",
            },
        )
    )
    await memory_lattice.ingest_runtime_envelope(
        RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="operator.bridge",
            agent_id="agent-fly",
            session_id="sess-fly",
            trace_id="trace-fly",
            event_id="evt-fly-2",
            payload={
                "action_name": "respond",
                "decision": "recorded",
                "confidence": 1.0,
                "task_id": "task-fly",
                "current_artifact_id": stored.record.artifact_id,
            },
        )
    )
    promoted = await memory_lattice.record_fact(
        "Export only promoted runtime facts into the flywheel lane.",
        fact_kind="policy",
        truth_state="promoted",
        confidence=0.95,
        session_id="sess-fly",
        task_id="task-fly",
        source_event_id="evt-fly-2",
        source_artifact_id=stored.record.artifact_id,
    )
    await memory_lattice.record_fact(
        "Candidate note should not leave the sovereign runtime by default.",
        fact_kind="policy",
        truth_state="candidate",
        confidence=0.4,
        session_id="sess-fly",
        task_id="task-fly",
    )

    exporter = FlywheelExporter(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        export_root=tmp_path / "exports",
    )
    result = await exporter.export_run(
        run_id="run-fly",
        workload_id="canonical-dgc",
        client_id="operator",
        created_by="codex",
    )

    data = json.loads(result.export_path.read_text(encoding="utf-8"))
    receipt_rows = exporter.event_log.read_envelopes(
        stream="flywheel_exports",
        session_id="sess-fly",
    )
    persisted_export = await runtime_state.get_artifact(result.artifact.artifact_id)

    assert result.export_path.exists()
    assert result.manifest_path.exists()
    assert data["workload_id"] == "canonical-dgc"
    assert data["trace_id"] == "trace-fly"
    assert data["metadata"]["event_scope"] == "trace"
    assert data["artifact_id"] == result.record.export_id
    assert data["metrics"]["artifact_count"] == 1
    assert data["metrics"]["fact_count"] == 1
    assert {item["fact_id"] for item in data["memory_facts"]} == {promoted.fact_id}
    assert data["artifacts"][0]["manifest"]["trace_id"] == "trace-fly"
    assert data["job_request"] == {"workload_id": "canonical-dgc", "client_id": "operator"}
    assert receipt_rows[-1]["payload"]["export_id"] == result.record.export_id
    assert receipt_rows[-1]["payload"]["artifact_id"] == result.artifact.artifact_id
    assert persisted_export is not None
    assert persisted_export.artifact_kind == "flywheel_export"

    await memory_lattice.close()


@pytest.mark.asyncio
async def test_flywheel_exporter_filters_session_events_when_trace_is_missing(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    runtime_state = RuntimeStateStore(db_path)
    memory_lattice = MemoryLattice(db_path=db_path, event_log_dir=tmp_path / "events")
    artifact_store = RuntimeArtifactStore(
        base_dir=tmp_path / "workspace" / "sessions",
        runtime_state=runtime_state,
    )
    await runtime_state.init_db()
    await memory_lattice.init_db()

    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-no-trace",
            operator_id="operator",
            status="active",
            current_task_id="task-no-trace",
        )
    )
    stored = await artifact_store.create_text_artifact_async(
        session_id="sess-no-trace",
        artifact_type="documents",
        artifact_kind="checkpoint",
        content="checkpoint",
        created_by="codex",
        task_id="task-no-trace",
        run_id="run-no-trace",
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-no-trace",
            session_id="sess-no-trace",
            task_id="task-no-trace",
            assigned_to="agent-fallback",
            assigned_by="operator",
            current_artifact_id=stored.record.artifact_id,
            status="in_progress",
        )
    )
    await memory_lattice.ingest_runtime_envelope(
        RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="operator.bridge",
            agent_id="agent-fallback",
            session_id="sess-no-trace",
            event_id="evt-related-task",
            payload={
                "action_name": "claim",
                "decision": "recorded",
                "confidence": 1.0,
                "task_id": "task-no-trace",
            },
        )
    )
    await memory_lattice.ingest_runtime_envelope(
        RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="operator.bridge",
            agent_id="agent-fallback",
            session_id="sess-no-trace",
            event_id="evt-related-artifact",
            payload={
                "action_name": "heartbeat",
                "decision": "recorded",
                "confidence": 1.0,
                "current_artifact_id": stored.record.artifact_id,
            },
        )
    )
    await memory_lattice.ingest_runtime_envelope(
        RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="operator.bridge",
            agent_id="agent-fallback",
            session_id="sess-no-trace",
            event_id="evt-unrelated",
            payload={
                "action_name": "claim",
                "decision": "recorded",
                "confidence": 1.0,
                "task_id": "other-task",
            },
        )
    )

    exporter = FlywheelExporter(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        export_root=tmp_path / "exports",
    )
    result = await exporter.export_run(
        run_id="run-no-trace",
        workload_id="fallback-case",
        client_id="operator",
        created_by="codex",
    )

    data = json.loads(result.export_path.read_text(encoding="utf-8"))
    exported_event_ids = {item["event_id"] for item in data["events"]}

    assert data["metadata"]["event_scope"] == "session_filtered"
    assert exported_event_ids == {"evt-related-task", "evt-related-artifact"}

    await memory_lattice.close()
