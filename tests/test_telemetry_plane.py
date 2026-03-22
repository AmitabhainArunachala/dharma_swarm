from __future__ import annotations

import sqlite3

import pytest

from dharma_swarm.telemetry_plane import (
    AgentIdentityRecord,
    AgentReputationRecord,
    EconomicEventRecord,
    ExternalOutcomeRecord,
    InterventionOutcomeRecord,
    PolicyDecisionRecord,
    RoutingDecisionRecord,
    TeamRosterRecord,
    TelemetryPlaneStore,
    WorkflowScoreRecord,
)


@pytest.mark.asyncio
async def test_telemetry_plane_initializes_core_tables(tmp_path) -> None:
    db_path = tmp_path / "runtime.db"
    store = TelemetryPlaneStore(db_path)
    await store.init_db()

    with sqlite3.connect(db_path) as db:
        tables = {
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        journal_mode = str(db.execute("PRAGMA journal_mode").fetchone()[0]).lower()

    assert journal_mode == "wal"
    assert {
        "agent_identity",
        "agent_reward_ledger",
        "agent_reputation",
        "team_roster",
        "workflow_scores",
        "routing_decisions",
        "policy_decisions",
        "intervention_outcomes",
        "economic_events",
        "external_outcomes",
    } <= tables


@pytest.mark.asyncio
async def test_telemetry_plane_upserts_identity_and_reputation(tmp_path) -> None:
    store = TelemetryPlaneStore(tmp_path / "runtime.db")
    await store.init_db()

    identity = await store.upsert_agent_identity(
        AgentIdentityRecord(
            agent_id="agent-1",
            codename="vajra",
            department="research",
            squad_id="alpha",
            specialization="routing",
            level=3,
            xp=42.5,
            status="active",
            metadata={"source": "test"},
        )
    )
    reputation = await store.upsert_agent_reputation(
        AgentReputationRecord(
            agent_id="agent-1",
            reputation=0.87,
            trust_band="high",
            last_reason="consistent routing quality",
            evidence=[{"kind": "eval", "score": 0.87}],
        )
    )

    identities = await store.list_agent_identities(status="active", limit=10)
    loaded_reputation = await store.get_agent_reputation("agent-1")

    assert identity.codename == "vajra"
    assert identity.department == "research"
    assert reputation.trust_band == "high"
    assert loaded_reputation is not None
    assert loaded_reputation.evidence[0]["kind"] == "eval"
    assert identities[0].agent_id == "agent-1"


@pytest.mark.asyncio
async def test_telemetry_plane_records_company_state_events(tmp_path) -> None:
    store = TelemetryPlaneStore(tmp_path / "runtime.db")
    await store.init_db()

    await store.record_team_roster(
        TeamRosterRecord(
            roster_id="roster-1",
            team_id="squad-alpha",
            agent_id="agent-1",
            role="router",
            metadata={"department": "research"},
        )
    )
    await store.record_workflow_score(
        WorkflowScoreRecord(
            score_id="score-1",
            workflow_id="wf-1",
            score_name="quality",
            score_value=0.91,
            task_id="task-1",
            evidence=[{"kind": "judge", "score": 0.91}],
        )
    )
    await store.record_routing_decision(
        RoutingDecisionRecord(
            decision_id="route-1",
            action_name="draft_research_plan",
            route_path="deliberative",
            selected_provider="anthropic",
            selected_model_hint="claude-sonnet-4-6",
            confidence=0.82,
            requires_human=False,
            task_id="task-1",
            reasons=["default_to_deliberative"],
        )
    )
    await store.record_policy_decision(
        PolicyDecisionRecord(
            decision_id="policy-1",
            policy_name="provider_policy",
            decision="approved",
            status_before="draft",
            status_after="active",
            confidence=0.78,
            reason="routing budget acceptable",
            task_id="task-1",
            evidence=[{"kind": "budget", "ok": True}],
        )
    )
    await store.record_intervention_outcome(
        InterventionOutcomeRecord(
            intervention_id="intervention-1",
            intervention_type="approve_checkpoint",
            outcome_status="helpful",
            impact_score=0.7,
            summary="operator approval cleared a blocked run",
            operator_id="operator",
            task_id="task-1",
        )
    )
    await store.record_economic_event(
        EconomicEventRecord(
            event_id="economic-1",
            event_kind="cost",
            amount=1.23,
            currency="USD",
            summary="model spend",
            session_id="sess-1",
        )
    )
    await store.record_external_outcome(
        ExternalOutcomeRecord(
            outcome_id="outcome-1",
            outcome_kind="user_satisfaction",
            value=4.5,
            unit="stars",
            confidence=0.8,
            status="measured",
            summary="positive feedback",
            session_id="sess-1",
            subject_id="customer-42",
        )
    )

    roster = await store.list_team_roster(team_id="squad-alpha", limit=10)
    scores = await store.list_workflow_scores(workflow_id="wf-1", limit=10)
    routes = await store.list_routing_decisions(task_id="task-1", limit=10)
    policies = await store.list_policy_decisions(task_id="task-1", limit=10)
    interventions = await store.list_intervention_outcomes(task_id="task-1", limit=10)
    economics = await store.list_economic_events(session_id="sess-1", limit=10)
    outcomes = await store.list_external_outcomes(session_id="sess-1", limit=10)

    assert roster[0].role == "router"
    assert scores[0].score_value == 0.91
    assert routes[0].selected_provider == "anthropic"
    assert policies[0].decision == "approved"
    assert interventions[0].operator_id == "operator"
    assert economics[0].amount == 1.23
    assert outcomes[0].subject_id == "customer-42"
