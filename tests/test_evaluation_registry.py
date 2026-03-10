from __future__ import annotations

import pytest

from dharma_swarm.evaluation_registry import EvaluationRegistry
from dharma_swarm.memory_lattice import MemoryLattice
from dharma_swarm.runtime_state import DelegationRun, RuntimeStateStore, SessionState


@pytest.mark.asyncio
async def test_evaluation_registry_records_flywheel_job_into_canonical_truth(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    runtime_state = RuntimeStateStore(db_path)
    memory_lattice = MemoryLattice(db_path=db_path, event_log_dir=tmp_path / "events")
    await runtime_state.init_db()
    await memory_lattice.init_db()

    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-eval",
            operator_id="operator",
            status="active",
            current_task_id="task-eval",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-eval",
            session_id="sess-eval",
            task_id="task-eval",
            assigned_to="agent-eval",
            assigned_by="operator",
            status="completed",
            metadata={"trace_id": "trace-eval"},
        )
    )

    registry = EvaluationRegistry(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        workspace_root=tmp_path / "workspace" / "sessions",
        provenance_root=tmp_path / "workspace" / "sessions",
    )
    result = await registry.record_flywheel_job(
        {
            "id": "job-42",
            "status": "completed",
            "workload_id": "canonical-dgc",
            "client_id": "operator",
            "recommended_model": "openai/gpt-5-mini",
        },
        run_id="run-eval",
        created_by="codex",
    )

    artifact_path = tmp_path / "workspace" / "sessions" / "sess-eval" / "artifacts" / "evaluations"
    provenance_log = tmp_path / "workspace" / "sessions" / "sess-eval" / "provenance" / "log.jsonl"
    stream_rows = memory_lattice.event_log.read_envelopes(
        stream="flywheel_evaluations",
        session_id="sess-eval",
    )
    persisted_artifact = await runtime_state.get_artifact(result.artifact.artifact_id)

    assert persisted_artifact is not None
    assert persisted_artifact.artifact_kind == "flywheel_job_result"
    assert artifact_path.exists()
    assert result.manifest_path.exists()
    assert {fact.fact_kind for fact in result.facts} == {"evaluation_status", "provider_recommendation"}
    assert any(fact.truth_state == "promoted" for fact in result.facts)
    assert any("Prefer model openai/gpt-5-mini" in fact.text for fact in result.facts)
    assert stream_rows[-1]["payload"]["job_id"] == "job-42"
    assert provenance_log.exists()
    assert "flywheel_job_recorded" in provenance_log.read_text(encoding="utf-8")

    await memory_lattice.close()


@pytest.mark.asyncio
async def test_evaluation_registry_requires_canonical_binding(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    runtime_state = RuntimeStateStore(db_path)
    memory_lattice = MemoryLattice(db_path=db_path, event_log_dir=tmp_path / "events")
    await runtime_state.init_db()
    await memory_lattice.init_db()

    registry = EvaluationRegistry(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        workspace_root=tmp_path / "workspace" / "sessions",
    )

    with pytest.raises(ValueError, match="session_id or run_id"):
        await registry.record_flywheel_job(
            {"id": "job-missing", "status": "completed"},
            created_by="codex",
        )

    await memory_lattice.close()
