from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.contracts import EvaluationSink, LearningEngine, MemoryPlane, SkillStore
from dharma_swarm.contracts.common import EvaluationRecord
from dharma_swarm.engine.event_memory import EventMemoryStore
from dharma_swarm.contracts.intelligence_stack import (
    SovereignEvaluationRecorder,
    SovereignTaskFeedbackService,
    build_sovereign_evaluation_recorder,
    build_sovereign_intelligence_layer,
    build_sovereign_task_feedback_service,
)
from dharma_swarm.runtime_state import DelegationRun, RuntimeStateStore, SessionState


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "skills"
    directory.mkdir()
    (directory / "surgeon.skill.md").write_text(
        "---\n"
        "name: surgeon\n"
        "tags: [debug, patch]\n"
        "keywords: [fix, bug, repair]\n"
        "---\n"
        "# Surgeon\n\n"
        "Repairs bugs and stabilizes failing code paths.\n",
        encoding="utf-8",
    )
    return directory


async def _seed_runtime(db_path: Path) -> None:
    runtime_state = RuntimeStateStore(db_path)
    await runtime_state.init_db()
    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-stack",
            operator_id="operator",
            status="active",
            current_task_id="task-stack",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-stack",
            session_id="sess-stack",
            task_id="task-stack",
            assigned_to="agent-stack",
            assigned_by="operator",
            status="completed",
            metadata={"trace_id": "trace-stack"},
        )
    )


@pytest.mark.asyncio
async def test_build_sovereign_intelligence_layer_returns_protocol_backed_stack(
    tmp_path: Path,
    skill_dir: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    await _seed_runtime(db_path)

    layer = build_sovereign_intelligence_layer(
        db_path=db_path,
        skill_dirs=[skill_dir],
    )

    assert isinstance(layer.memory, MemoryPlane)
    assert isinstance(layer.learning, LearningEngine)
    assert isinstance(layer.skills, SkillStore)
    assert isinstance(layer.evaluations, EvaluationSink)


@pytest.mark.asyncio
async def test_task_feedback_service_uses_sovereign_interfaces_for_feedback_slice(
    tmp_path: Path,
    skill_dir: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    await _seed_runtime(db_path)
    service = build_sovereign_task_feedback_service(
        db_path=db_path,
        skill_dirs=[skill_dir],
    )

    assert isinstance(service, SovereignTaskFeedbackService)

    result = await service.ingest_task_feedback(
        evaluation=EvaluationRecord(
            evaluation_id="eval-stack-1",
            subject_kind="task",
            subject_id="task-stack",
            evaluator="reviewer",
            metric="routing_fit",
            score=0.94,
            run_id="run-stack",
            metadata={
                "preferred_roles": ["surgeon"],
                "recommended_model": "openai/gpt-5-mini",
            },
        ),
    )

    assert result.evaluation.session_id == "sess-stack"
    assert result.evaluation.task_id == "task-stack"
    assert result.extracted_candidates
    assert any(candidate.name == "surgeon" for candidate in result.extracted_candidates)
    assert result.saved_skills
    assert any(skill.name == "surgeon" for skill in result.saved_skills)
    assert any(hint.get("preferred_role") == "surgeon" for hint in result.routing_hints)
    assert any(hint.get("recommended_model") == "openai/gpt-5-mini" for hint in result.routing_hints)


@pytest.mark.asyncio
async def test_sovereign_evaluation_recorder_records_reciprocity_summary_through_contracts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    workspace_root = tmp_path / "workspace"
    provenance_root = tmp_path / "provenance"
    await _seed_runtime(db_path)

    recorder = build_sovereign_evaluation_recorder(
        db_path=db_path,
        workspace_root=workspace_root,
        provenance_root=provenance_root,
    )

    assert isinstance(recorder, SovereignEvaluationRecorder)

    result = await recorder.record_reciprocity_summary(
        {
            "service": "reciprocity_commons",
            "summary_type": "ledger_summary",
            "actors": 3,
            "activities": 2,
            "projects": 1,
            "obligations": 4,
            "active_obligations": 3,
            "challenged_claims": 1,
            "invariant_issues": 0,
            "chain_valid": True,
            "total_obligation_usd": 12000,
            "total_routed_usd": 4000,
            "issues": [],
        },
        run_id="run-stack",
        created_by="stack-test",
    )

    assert result.artifact.artifact_id
    assert result.manifest_path.exists()
    assert result.summary["summary_type"] == "ledger_summary"
    assert result.summary["receipt_event_id"] == result.receipt["event_id"]

    runtime_state = RuntimeStateStore(db_path)
    artifact = await runtime_state.get_artifact(result.artifact.artifact_id)
    assert artifact is not None

    layer = build_sovereign_intelligence_layer(db_path=db_path)
    evaluations = await layer.evaluations.list_evaluations(
        subject_kind="reciprocity_summary",
        subject_id="reciprocity_commons:ledger_summary",
    )
    assert evaluations
    assert evaluations[0].run_id == "run-stack"
    assert evaluations[0].session_id == "sess-stack"

    memories = await layer.memory.query_memory(
        session_id="sess-stack",
        task_id="task-stack",
        limit=20,
    )
    assert any(record.kind == "reciprocity_summary" for record in memories)

    event_store = EventMemoryStore(db_path)
    events = await event_store.replay_session("sess-stack")
    assert any(event["event_id"] == result.receipt["event_id"] for event in events)


@pytest.mark.asyncio
async def test_sovereign_evaluation_recorder_records_ouroboros_observation_through_contracts(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    await _seed_runtime(db_path)

    recorder = build_sovereign_evaluation_recorder(db_path=db_path)
    result = await recorder.record_ouroboros_observation(
        {
            "cycle_id": "cycle-stack",
            "source": "dse_integration",
            "signature": {
                "recognition_type": "GENUINE",
                "entropy": 0.91,
                "swabhaav_ratio": 0.82,
            },
            "modifiers": {
                "quality": 0.88,
                "mimicry_penalty": 1.0,
                "recognition_bonus": 1.15,
                "witness_score": 0.84,
            },
            "is_mimicry": False,
            "is_genuine": True,
        },
        session_id="sess-stack",
        task_id="task-stack",
        created_by="stack-test",
    )

    assert result.summary["cycle_id"] == "cycle-stack"
    assert result.summary["recognition_type"] == "GENUINE"
    assert result.summary["is_genuine"] is True

    layer = build_sovereign_intelligence_layer(db_path=db_path)
    evaluations = await layer.evaluations.list_evaluations(
        subject_kind="ouroboros_observation",
        subject_id="cycle-stack",
    )
    assert evaluations
    assert evaluations[0].metric == "behavioral_quality"

    memories = await layer.memory.query_memory(
        session_id="sess-stack",
        task_id="task-stack",
        limit=20,
    )
    assert any(record.kind == "ouroboros_behavioral_summary" for record in memories)
