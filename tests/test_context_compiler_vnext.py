from __future__ import annotations

import pytest

from dharma_swarm.context_compiler import ContextCompiler
from dharma_swarm.memory_lattice import MemoryLattice
from dharma_swarm.provider_policy import ProviderRouteRequest
from dharma_swarm.runtime_contract import RuntimeEnvelope, RuntimeEventType
from dharma_swarm.runtime_state import (
    ArtifactRecord,
    DelegationRun,
    RuntimeStateStore,
    SessionState,
    WorkspaceLease,
)


@pytest.mark.asyncio
async def test_context_compiler_builds_and_persists_budgeted_bundle(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    workspace_root = tmp_path / "workspace"
    workspace_root.mkdir()
    active_file = workspace_root / "runtime_state.py"
    active_file.write_text("class RuntimeStateStore:\n    pass\n")

    runtime_state = RuntimeStateStore(db_path)
    memory_lattice = MemoryLattice(db_path=db_path, event_log_dir=tmp_path / "events")
    await runtime_state.init_db()
    await memory_lattice.init_db()

    await runtime_state.upsert_session(
        SessionState(
            session_id="sess-ctx",
            operator_id="operator",
            status="active",
            current_task_id="task-ctx",
        )
    )
    await runtime_state.record_delegation_run(
        DelegationRun(
            run_id="run-ctx",
            session_id="sess-ctx",
            task_id="task-ctx",
            assigned_to="agent-ctx",
            assigned_by="operator",
            requested_output=["runtime_state.py", "tests"],
            status="in_progress",
        )
    )
    await runtime_state.record_workspace_lease(
        WorkspaceLease(
            lease_id="lease-ctx",
            zone_path=str(workspace_root),
            holder_run_id="run-ctx",
            mode="write",
        )
    )
    await runtime_state.record_artifact(
        ArtifactRecord(
            artifact_id="art-ctx",
            artifact_kind="patch",
            session_id="sess-ctx",
            task_id="task-ctx",
            run_id="run-ctx",
            payload_path=str(active_file),
            promotion_state="published",
        )
    )
    await memory_lattice.record_fact(
        "Canonical runtime state should be the structured source of truth.",
        fact_kind="architecture",
        truth_state="promoted",
        confidence=0.96,
        session_id="sess-ctx",
        task_id="task-ctx",
    )
    await memory_lattice.ingest_runtime_envelope(
        RuntimeEnvelope.create(
            event_type=RuntimeEventType.ACTION_EVENT,
            source="orchestrator.lifecycle",
            agent_id="agent-ctx",
            session_id="sess-ctx",
            trace_id="trace-ctx",
            payload={
                "action_name": "compile_context",
                "decision": "recorded",
                "confidence": 1.0,
            },
        )
    )

    compiler = ContextCompiler(
        runtime_state=runtime_state,
        memory_lattice=memory_lattice,
    )
    bundle = await compiler.compile_bundle(
        session_id="sess-ctx",
        task_id="task-ctx",
        run_id="run-ctx",
        operator_intent="Build the canonical runtime spine and context compiler.",
        task_description="Assemble a reproducible context bundle for the active sprint.",
        token_budget=240,
        policy_constraints=[
            "No hidden RAM truth for important state.",
            "Shared writes require explicit lease or promotion.",
        ],
        provider_request=ProviderRouteRequest(
            action_name="context_compile",
            risk_score=0.18,
            uncertainty=0.2,
            novelty=0.3,
            urgency=0.5,
            expected_impact=0.7,
            context={"requires_tooling": True},
        ),
        workspace_root=workspace_root,
        active_paths=[active_file],
    )
    saved = await runtime_state.list_context_bundles(
        session_id="sess-ctx",
        task_id="task-ctx",
        limit=5,
    )

    assert bundle.bundle_id
    assert "Operator Intent" in bundle.rendered_text
    assert "No hidden RAM truth" in bundle.rendered_text
    assert "runtime_state.py" in bundle.rendered_text
    assert len(bundle.rendered_text) <= 240 * 4
    assert saved[0].bundle_id == bundle.bundle_id

    await memory_lattice.close()
