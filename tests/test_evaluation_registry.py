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


@pytest.mark.asyncio
async def test_evaluation_registry_records_reciprocity_summary_into_canonical_truth(
    tmp_path,
) -> None:
    db_path = tmp_path / "runtime.db"
    runtime_state = RuntimeStateStore(db_path)
    memory_lattice = MemoryLattice(db_path=db_path, event_log_dir=tmp_path / "events")
    await runtime_state.init_db()
    await memory_lattice.init_db()

    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-reciprocity",
            operator_id="operator",
            status="active",
            current_task_id="task-reciprocity",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-reciprocity",
            session_id="sess-reciprocity",
            task_id="task-reciprocity",
            assigned_to="agent-reciprocity",
            assigned_by="operator",
            status="completed",
            metadata={"trace_id": "trace-reciprocity"},
        )
    )

    registry = EvaluationRegistry(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        workspace_root=tmp_path / "workspace" / "sessions",
        provenance_root=tmp_path / "workspace" / "sessions",
    )
    result = await registry.record_reciprocity_summary(
        {
            "service": "reciprocity_commons",
            "summary_type": "ledger_summary",
            "actors": 2,
            "activities": 1,
            "projects": 1,
            "obligations": 3,
            "active_obligations": 2,
            "challenged_claims": 1,
            "invariant_issues": 2,
            "chain_valid": False,
            "total_obligation_usd": 25000,
            "total_routed_usd": 5000,
            "issues": [
                {"code": "routing_missing_project"},
                {"code": "verified_ecology_missing_audit"},
            ],
        },
        run_id="run-reciprocity",
        created_by="codex",
    )

    artifact_path = (
        tmp_path / "workspace" / "sessions" / "sess-reciprocity" / "artifacts" / "evaluations"
    )
    provenance_log = (
        tmp_path / "workspace" / "sessions" / "sess-reciprocity" / "provenance" / "log.jsonl"
    )
    stream_rows = memory_lattice.event_log.read_envelopes(
        stream="reciprocity_evaluations",
        session_id="sess-reciprocity",
    )
    persisted_artifact = await runtime_state.get_artifact(result.artifact.artifact_id)

    assert persisted_artifact is not None
    assert persisted_artifact.artifact_kind == "reciprocity_ledger_summary"
    assert artifact_path.exists()
    assert result.manifest_path.exists()
    assert result.summary["source"] == "reciprocity_commons"
    assert {fact.fact_kind for fact in result.facts} == {
        "reciprocity_summary",
        "reciprocity_integrity_alert",
        "reciprocity_claim_watch",
    }
    assert any(
        "actors=2" in fact.text and "total_routed_usd=5000.00" in fact.text
        for fact in result.facts
    )
    assert any(
        fact.metadata.get("issue_codes") == [
            "routing_missing_project",
            "verified_ecology_missing_audit",
        ]
        for fact in result.facts
        if fact.fact_kind == "reciprocity_integrity_alert"
    )
    assert stream_rows[-1]["payload"]["action_name"] == "record_reciprocity_summary"
    assert provenance_log.exists()
    assert "reciprocity_summary_recorded" in provenance_log.read_text(encoding="utf-8")

    await memory_lattice.close()


@pytest.mark.asyncio
async def test_evaluation_registry_requires_canonical_binding_for_reciprocity_summary(
    tmp_path,
) -> None:
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
        await registry.record_reciprocity_summary(
            {"actors": 2, "obligations": 1, "chain_valid": True},
            created_by="codex",
        )

    await memory_lattice.close()


@pytest.mark.asyncio
async def test_evaluation_registry_records_ouroboros_observation_into_canonical_truth(
    tmp_path,
) -> None:
    db_path = tmp_path / "runtime.db"
    runtime_state = RuntimeStateStore(db_path)
    memory_lattice = MemoryLattice(db_path=db_path, event_log_dir=tmp_path / "events")
    await runtime_state.init_db()
    await memory_lattice.init_db()

    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-ouroboros",
            operator_id="operator",
            status="active",
            current_task_id="task-ouroboros",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-ouroboros",
            session_id="sess-ouroboros",
            task_id="task-ouroboros",
            assigned_to="agent-ouroboros",
            assigned_by="operator",
            status="completed",
            metadata={"trace_id": "trace-ouroboros"},
        )
    )

    registry = EvaluationRegistry(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        workspace_root=tmp_path / "workspace" / "sessions",
        provenance_root=tmp_path / "workspace" / "sessions",
    )
    result = await registry.record_ouroboros_observation(
        {
            "cycle_id": "cycle-ouro-1",
            "source": "dse_integration",
            "timestamp": "2026-03-11T00:00:00+00:00",
            "signature": {
                "entropy": 0.88,
                "complexity": 0.59,
                "self_reference_density": 0.03,
                "identity_stability": 0.71,
                "paradox_tolerance": 0.64,
                "swabhaav_ratio": 0.76,
                "word_count": 140,
                "recognition_type": "GENUINE",
            },
            "modifiers": {
                "quality": 0.83,
                "mimicry_penalty": 1.0,
                "recognition_bonus": 1.15,
                "witness_score": 0.76,
            },
            "is_mimicry": False,
            "is_genuine": True,
        },
        run_id="run-ouroboros",
        created_by="codex",
    )

    artifact_path = (
        tmp_path / "workspace" / "sessions" / "sess-ouroboros" / "artifacts" / "evaluations"
    )
    provenance_log = (
        tmp_path / "workspace" / "sessions" / "sess-ouroboros" / "provenance" / "log.jsonl"
    )
    stream_rows = memory_lattice.event_log.read_envelopes(
        stream="ouroboros_evaluations",
        session_id="sess-ouroboros",
    )
    persisted_artifact = await runtime_state.get_artifact(result.artifact.artifact_id)

    assert persisted_artifact is not None
    assert persisted_artifact.artifact_kind == "ouroboros_behavioral_observation"
    assert artifact_path.exists()
    assert result.manifest_path.exists()
    assert result.summary["recognition_type"] == "GENUINE"
    assert result.summary["is_genuine"] is True
    assert {fact.fact_kind for fact in result.facts} == {
        "ouroboros_behavioral_summary",
        "ouroboros_behavioral_alignment",
    }
    assert any(
        "cycle cycle-ouro-1" in fact.text and "swabhaav_ratio=0.760" in fact.text
        for fact in result.facts
        if fact.fact_kind == "ouroboros_behavioral_summary"
    )
    assert stream_rows[-1]["payload"]["action_name"] == "record_ouroboros_observation"
    assert provenance_log.exists()
    assert "ouroboros_observation_recorded" in provenance_log.read_text(encoding="utf-8")

    await memory_lattice.close()


@pytest.mark.asyncio
async def test_evaluation_registry_requires_canonical_binding_for_ouroboros_observation(
    tmp_path,
) -> None:
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
        await registry.record_ouroboros_observation(
            {
                "signature": {
                    "recognition_type": "GENUINE",
                    "swabhaav_ratio": 0.8,
                }
            },
            created_by="codex",
        )

    await memory_lattice.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_overrides", "message"),
    [
        (
            {
                "signature": {
                    "recognition_type": "GENUINE",
                    "swabhaav_ratio": 1.2,
                }
            },
            "swabhaav_ratio must be a finite number between 0 and 1",
        ),
        (
            {
                "is_mimicry": 2,
            },
            "is_mimicry must be a boolean",
        ),
        (
            {
                "is_mimicry": "true",
            },
            "is_mimicry must be a boolean",
        ),
        (
            {
                "is_genuine": 1,
            },
            "is_genuine must be a boolean",
        ),
    ],
)
async def test_evaluation_registry_rejects_invalid_ouroboros_metrics_before_persisting(
    tmp_path,
    payload_overrides,
    message,
) -> None:
    db_path = tmp_path / "runtime.db"
    runtime_state = RuntimeStateStore(db_path)
    memory_lattice = MemoryLattice(db_path=db_path, event_log_dir=tmp_path / "events")
    await runtime_state.init_db()
    await memory_lattice.init_db()

    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-invalid-ouroboros",
            operator_id="operator",
            status="active",
            current_task_id="task-invalid-ouroboros",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-invalid-ouroboros",
            session_id="sess-invalid-ouroboros",
            task_id="task-invalid-ouroboros",
            assigned_to="agent-ouroboros",
            assigned_by="operator",
            status="completed",
            metadata={"trace_id": "trace-invalid-ouroboros"},
        )
    )

    registry = EvaluationRegistry(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        workspace_root=tmp_path / "workspace" / "sessions",
        provenance_root=tmp_path / "workspace" / "sessions",
    )

    payload = {
        "cycle_id": "cycle-invalid",
        "signature": {
            "recognition_type": "GENUINE",
            "swabhaav_ratio": 0.8,
        },
        "modifiers": {
            "quality": 0.8,
            "mimicry_penalty": 1.0,
            "recognition_bonus": 1.15,
            "witness_score": 0.8,
        },
        "is_genuine": True,
    }
    payload.update(payload_overrides)

    with pytest.raises(ValueError, match=message):
        await registry.record_ouroboros_observation(
            payload,
            run_id="run-invalid-ouroboros",
            created_by="codex",
        )

    assert await runtime_state.list_artifacts(session_id="sess-invalid-ouroboros") == []
    assert memory_lattice.event_log.read_envelopes(
        stream="ouroboros_evaluations",
        session_id="sess-invalid-ouroboros",
    ) == []

    await memory_lattice.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_overrides", "message"),
    [
        ({"actors": -1}, "actors must be an integer >= 0"),
        ({"active_obligations": True}, "active_obligations must be an integer >= 0"),
        ({"total_routed_usd": "nan"}, "total_routed_usd must be a finite number >= 0"),
        ({"chain_valid": "maybe"}, "chain_valid must be a boolean"),
        ({"chain_valid": "true"}, "chain_valid must be a boolean"),
        ({"chain_valid": 1}, "chain_valid must be a boolean"),
    ],
)
async def test_evaluation_registry_rejects_invalid_reciprocity_metrics_before_persisting(
    tmp_path,
    payload_overrides,
    message,
) -> None:
    db_path = tmp_path / "runtime.db"
    runtime_state = RuntimeStateStore(db_path)
    memory_lattice = MemoryLattice(db_path=db_path, event_log_dir=tmp_path / "events")
    await runtime_state.init_db()
    await memory_lattice.init_db()

    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-invalid-reciprocity",
            operator_id="operator",
            status="active",
            current_task_id="task-invalid-reciprocity",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-invalid-reciprocity",
            session_id="sess-invalid-reciprocity",
            task_id="task-invalid-reciprocity",
            assigned_to="agent-reciprocity",
            assigned_by="operator",
            status="completed",
            metadata={"trace_id": "trace-invalid-reciprocity"},
        )
    )

    registry = EvaluationRegistry(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
        workspace_root=tmp_path / "workspace" / "sessions",
        provenance_root=tmp_path / "workspace" / "sessions",
    )
    summary_payload = {
        "service": "reciprocity_commons",
        "summary_type": "ledger_summary",
        "actors": 2,
        "obligations": 3,
        "chain_valid": True,
    }
    summary_payload.update(payload_overrides)

    with pytest.raises(ValueError, match=message):
        await registry.record_reciprocity_summary(
            summary_payload,
            run_id="run-invalid-reciprocity",
            created_by="codex",
        )

    assert await runtime_state.list_artifacts(session_id="sess-invalid-reciprocity") == []
    assert memory_lattice.event_log.read_envelopes(
        stream="reciprocity_evaluations",
        session_id="sess-invalid-reciprocity",
    ) == []

    await memory_lattice.close()
