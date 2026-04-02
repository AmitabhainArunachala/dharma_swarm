from __future__ import annotations

from dharma_swarm.operator_core import (
    CanonicalEntity,
    CanonicalEventEnvelope,
    CanonicalPermissionDecision,
    CanonicalRelation,
    CanonicalRoutingDecision,
    CanonicalRuntimeSnapshot,
    CanonicalSession,
    CanonicalWorkflowState,
    EntityBadge,
    EntityRef,
    EventAudience,
    EventSource,
    EventTransport,
    PermissionDecisionKind,
    PermissionRisk,
    RuntimeHealth,
    WorkflowExecutionMode,
)


def test_operator_core_contracts_hold_shell_neutral_shapes() -> None:
    entity = CanonicalEntity(
        kind="agent",
        id="qwen35-surgeon",
        title="Qwen Surgeon",
        subtitle="bounded coding lane",
        source_route="tui.agents",
        status=RuntimeHealth.OK,
        badges=[EntityBadge(label="live", tone=RuntimeHealth.OK)],
        raw={"provider": "openrouter"},
    )
    relation = CanonicalRelation(
        kind="assigned_to",
        from_ref=EntityRef(kind="task", id="task-1"),
        to_ref=EntityRef(kind="agent", id=entity.id),
        label="owns",
        evidence=["/api/commands/tasks"],
    )
    session = CanonicalSession(
        session_id="sess-1",
        provider_id="codex",
        model_id="gpt-5.4",
        cwd="/Users/dhyana/dharma_swarm",
        created_at="2026-04-02T00:00:00Z",
        updated_at="2026-04-02T00:10:00Z",
        status="running",
        branch_label="main",
        worktree_path="/Users/dhyana/dharma_swarm",
    )
    permission = CanonicalPermissionDecision(
        action_id="act-1",
        tool_name="Bash",
        risk=PermissionRisk.SHELL_OR_NETWORK,
        decision=PermissionDecisionKind.REQUIRE_APPROVAL,
        rationale="shell mutations must remain operator-gated",
        policy_source="workspace-policy",
        requires_confirmation=True,
        command_prefix="git status",
    )
    routing = CanonicalRoutingDecision(
        route_id="deep_code_work",
        provider_id="codex",
        model_id="gpt-5.4",
        strategy="responsive",
        reason="coding task with bounded mutability",
        fallback_chain=["claude:claude-sonnet-4-6", "openrouter:qwen2.5-coder"],
    )
    runtime = CanonicalRuntimeSnapshot(
        snapshot_id="snap-1",
        created_at="2026-04-02T00:00:00Z",
        repo_root="/Users/dhyana/dharma_swarm",
        runtime_db="/Users/dhyana/.dharma/state/runtime.db",
        health=RuntimeHealth.DEGRADED,
        bridge_status="connected",
        active_session_count=12,
        active_run_count=2,
        artifact_count=7,
        context_bundle_count=3,
        anomaly_count=1,
        verification_status="1 failing, 3/4 passing",
        warnings=["session rail delayed"],
    )
    workflow = CanonicalWorkflowState(
        workflow_id="wf-1",
        title="terminal convergence",
        execution_mode=WorkflowExecutionMode.SERIAL_WRITE,
        status="running",
        active_lane_ids=["lane-a", "lane-b"],
        blocked_by=["approval:workspace-write"],
        writable_scopes=["terminal/", "dharma_swarm/operator_core/"],
    )
    event = CanonicalEventEnvelope(
        event_id="evt-1",
        event_type="tool.result",
        source=EventSource.PROVIDER,
        audience=EventAudience.ALL,
        transport=EventTransport.STDIO,
        session_id=session.session_id,
        created_at="2026-04-02T00:00:05Z",
        payload={"tool_name": "Read", "ok": True},
        entity_refs=[EntityRef(kind="agent", id=entity.id)],
    )

    assert entity.badges[0].label == "live"
    assert relation.to_ref.id == entity.id
    assert session.worktree_path == "/Users/dhyana/dharma_swarm"
    assert permission.decision is PermissionDecisionKind.REQUIRE_APPROVAL
    assert routing.fallback_chain[0] == "claude:claude-sonnet-4-6"
    assert runtime.health is RuntimeHealth.DEGRADED
    assert workflow.execution_mode is WorkflowExecutionMode.SERIAL_WRITE
    assert event.entity_refs[0].kind == "agent"
