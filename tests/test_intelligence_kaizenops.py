from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from dharma_swarm.contracts.intelligence_kaizenops import (
    evaluation_registration_to_kaizenops_event,
    export_evaluation_registration_to_kaizenops,
)
from dharma_swarm.contracts.intelligence_stack import build_sovereign_evaluation_recorder
from dharma_swarm.integrations import KaizenOpsClient, KaizenOpsConfig
from dharma_swarm.runtime_state import DelegationRun, RuntimeStateStore, SessionState


async def _seed_runtime(db_path: Path) -> None:
    runtime_state = RuntimeStateStore(db_path)
    await runtime_state.init_db()
    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-bridge",
            operator_id="operator",
            status="active",
            current_task_id="task-bridge",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-bridge",
            session_id="sess-bridge",
            task_id="task-bridge",
            assigned_to="agent-bridge",
            assigned_by="operator",
            status="completed",
            metadata={"trace_id": "trace-bridge"},
        )
    )


@pytest.mark.asyncio
async def test_evaluation_registration_to_kaizenops_event_maps_receipt_shape(
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
        run_id="run-bridge",
        created_by="bridge-test",
    )

    event = evaluation_registration_to_kaizenops_event(result)

    assert event["agent_id"] == "bridge-test"
    assert event["session_id"] == "sess-bridge"
    assert event["trace_id"] == "run-bridge"
    assert event["task_id"] == "task-bridge"
    assert event["category"] == "evaluation"
    assert event["intent"] == "record_evaluation"
    assert event["metadata"]["metric"] == "integrity"
    assert event["metadata"]["artifact_id"] == result.artifact.artifact_id
    assert event["metadata"]["receipt_event_id"] == result.receipt["event_id"]
    assert event["deliverables"][0] == result.artifact.artifact_id
    assert event["raw_payload"]["summary"]["summary_type"] == "ledger_summary"


@pytest.mark.asyncio
async def test_export_evaluation_registration_to_kaizenops_posts_canonical_event(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "runtime.db"
    await _seed_runtime(db_path)

    recorder = build_sovereign_evaluation_recorder(db_path=db_path)
    result = await recorder.record_ouroboros_observation(
        {
            "cycle_id": "cycle-bridge",
            "source": "dse_integration",
            "signature": {"recognition_type": "GENUINE", "swabhaav_ratio": 0.8},
            "modifiers": {"quality": 0.85, "witness_score": 0.82},
            "is_mimicry": False,
            "is_genuine": True,
        },
        run_id="run-bridge",
        created_by="bridge-test",
    )

    def _handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/ingest/events"
        payload = json.loads(request.content.decode("utf-8"))
        assert payload["events"][0]["session_id"] == "sess-bridge"
        assert payload["events"][0]["metadata"]["metric"] == "behavioral_quality"
        assert payload["events"][0]["metadata"]["artifact_id"] == result.artifact.artifact_id
        return httpx.Response(200, json={"accepted": len(payload["events"])})

    client = KaizenOpsClient(
        config=KaizenOpsConfig(base_url="http://kaizen.local"),
        transport=httpx.MockTransport(_handler),
    )
    out = await export_evaluation_registration_to_kaizenops(result, client=client)
    assert out["accepted"] == 1
