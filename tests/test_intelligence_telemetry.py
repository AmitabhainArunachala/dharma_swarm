from __future__ import annotations

from pathlib import Path

import pytest

from dharma_swarm.contracts.intelligence_stack import (
    build_sovereign_evaluation_recorder,
    evaluation_registration_to_telemetry_records,
    export_evaluation_registration_to_telemetry,
)
from dharma_swarm.runtime_state import DelegationRun, RuntimeStateStore, SessionState
from dharma_swarm.telemetry_plane import TelemetryPlaneStore
from dharma_swarm.telemetry_views import TelemetryViews


async def _seed_runtime(db_path: Path) -> None:
    runtime_state = RuntimeStateStore(db_path)
    await runtime_state.init_db()
    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-telemetry",
            operator_id="operator",
            status="active",
            current_task_id="task-telemetry",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-telemetry",
            session_id="sess-telemetry",
            task_id="task-telemetry",
            assigned_to="agent-telemetry",
            assigned_by="operator",
            status="completed",
            metadata={"trace_id": "trace-telemetry"},
        )
    )


@pytest.mark.asyncio
async def test_evaluation_registration_to_telemetry_records_maps_workflow_and_outcome(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    await _seed_runtime(db_path)

    recorder = build_sovereign_evaluation_recorder(db_path=db_path)
    result = await recorder.record_reciprocity_summary(
        {
            "service": "reciprocity_commons",
            "summary_type": "ledger_summary",
            "actors": 2,
            "activities": 1,
            "projects": 1,
            "obligations": 3,
            "active_obligations": 2,
            "challenged_claims": 0,
            "invariant_issues": 0,
            "chain_valid": True,
            "total_obligation_usd": 1000,
            "total_routed_usd": 500,
            "issues": [],
        },
        run_id="run-telemetry",
        created_by="telemetry-test",
    )

    records = evaluation_registration_to_telemetry_records(result)

    assert records.workflow_score.workflow_id == "task:task-telemetry"
    assert records.workflow_score.score_name == "integrity"
    assert records.workflow_score.score_value == result.evaluation.score
    assert records.workflow_score.metadata["artifact_id"] == result.artifact.artifact_id
    assert records.external_outcome.outcome_kind == "evaluation:integrity"
    assert records.external_outcome.status == "measured"
    assert records.external_outcome.subject_id == "reciprocity_commons:ledger_summary"
    assert records.external_outcome.metadata["fact_ids"]


@pytest.mark.asyncio
async def test_export_evaluation_registration_to_telemetry_records_and_surfaces_in_views(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    await _seed_runtime(db_path)

    recorder = build_sovereign_evaluation_recorder(db_path=db_path)
    result = await recorder.record_ouroboros_observation(
        {
            "cycle_id": "cycle-telemetry",
            "source": "dse_integration",
            "signature": {
                "recognition_type": "GENUINE",
                "entropy": 0.9,
                "swabhaav_ratio": 0.81,
            },
            "modifiers": {
                "quality": 0.87,
                "mimicry_penalty": 1.0,
                "recognition_bonus": 1.15,
                "witness_score": 0.84,
            },
            "is_mimicry": False,
            "is_genuine": True,
        },
        run_id="run-telemetry",
        created_by="telemetry-test",
    )

    telemetry = TelemetryPlaneStore(db_path)
    exported = await export_evaluation_registration_to_telemetry(
        result,
        telemetry=telemetry,
    )

    scores = await telemetry.list_workflow_scores(
        workflow_id="task:task-telemetry",
        score_name="behavioral_quality",
        limit=10,
    )
    outcomes = await telemetry.list_external_outcomes(
        outcome_kind="evaluation:behavioral_quality",
        session_id="sess-telemetry",
        limit=10,
    )
    views = TelemetryViews(telemetry)
    overview = await views.overview()

    assert exported.workflow_score.score_id == f"score_{result.evaluation.evaluation_id}"
    assert exported.external_outcome.outcome_id == f"outcome_{result.evaluation.evaluation_id}"
    assert scores
    assert scores[0].run_id == "run-telemetry"
    assert outcomes
    assert outcomes[0].subject_id == "cycle-telemetry"
    assert overview.workflow_score_count == 1
    assert overview.external_outcome_count == 1
