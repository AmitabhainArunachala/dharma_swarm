from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers import telemetry as telemetry_router
from dharma_swarm.telemetry_plane import (
    AgentIdentityRecord,
    EconomicEventRecord,
    ExternalOutcomeRecord,
    InterventionOutcomeRecord,
    PolicyDecisionRecord,
    RoutingDecisionRecord,
    TeamRosterRecord,
    TelemetryPlaneStore,
)


def _telemetry_client() -> TestClient:
    app = FastAPI()
    app.include_router(telemetry_router.router)
    return TestClient(app)


def test_telemetry_teams_route_registered_once() -> None:
    client = _telemetry_client()
    team_routes = [
        route
        for route in client.app.routes
        if getattr(route, "path", None) == "/api/telemetry/teams"
        and "GET" in getattr(route, "methods", set())
    ]

    assert len(team_routes) == 1


@pytest.fixture
async def telemetry_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    store = TelemetryPlaneStore(tmp_path / "runtime.db")
    await store.init_db()

    await store.upsert_agent_identity(
        AgentIdentityRecord(agent_id="agent-1", codename="vajra", status="active")
    )
    await store.record_team_roster(
        TeamRosterRecord(
            roster_id="roster-1",
            team_id="dharma-core",
            agent_id="agent-1",
            role="surgeon",
        )
    )
    await store.record_routing_decision(
        RoutingDecisionRecord(
            decision_id="route-1",
            action_name="research",
            route_path="deliberative",
            selected_provider="anthropic",
            confidence=0.81,
            task_id="task-1",
            reasons=["default_to_deliberative"],
        )
    )
    await store.record_policy_decision(
        PolicyDecisionRecord(
            decision_id="policy-1",
            policy_name="provider_policy",
            decision="approved",
            task_id="task-1",
            reason="budget acceptable",
        )
    )
    await store.record_intervention_outcome(
        InterventionOutcomeRecord(
            intervention_id="intervention-1",
            intervention_type="approve_checkpoint",
            outcome_status="helpful",
            operator_id="operator",
            task_id="task-1",
        )
    )
    await store.record_economic_event(
        EconomicEventRecord(
            event_id="economic-1",
            event_kind="cost",
            amount=2.5,
            currency="USD",
            session_id="sess-1",
        )
    )
    await store.record_external_outcome(
        ExternalOutcomeRecord(
            outcome_id="outcome-1",
            outcome_kind="user_satisfaction",
            value=4.0,
            unit="stars",
            session_id="sess-1",
            subject_id="customer-42",
        )
    )

    telemetry_router._telemetry_store = None
    telemetry_router._telemetry_views = None
    telemetry_router._runtime_projector = None
    telemetry_router._projection_lock = None
    telemetry_router._last_projection_at = 0.0
    monkeypatch.setattr(telemetry_router, "_get_telemetry_store", lambda: store)

    def _views():
        from dharma_swarm.telemetry_views import TelemetryViews

        return TelemetryViews(store)

    monkeypatch.setattr(telemetry_router, "_get_telemetry_views", _views)
    telemetry_router._telemetry_optimizer = None
    return store


@pytest.mark.asyncio
async def test_telemetry_overview_and_summary_endpoints(telemetry_env) -> None:
    client = _telemetry_client()

    overview = client.get("/api/telemetry/overview")
    routing = client.get("/api/telemetry/routing")
    economics = client.get("/api/telemetry/economics")

    assert overview.status_code == 200
    assert overview.json()["data"]["agent_count"] == 1
    assert routing.status_code == 200
    assert routing.json()["data"]["provider_counts"]["anthropic"] == 1
    assert economics.status_code == 200
    assert economics.json()["data"]["total_cost_usd"] == 2.5


@pytest.mark.asyncio
async def test_telemetry_record_endpoints_return_filtered_data(telemetry_env) -> None:
    client = _telemetry_client()

    agents = client.get("/api/telemetry/agents?status=active")
    teams = client.get("/api/telemetry/teams?team_id=dharma-core")
    routes = client.get("/api/telemetry/routes?task_id=task-1")
    policies = client.get("/api/telemetry/policies?task_id=task-1")
    interventions = client.get("/api/telemetry/interventions?task_id=task-1")
    economic = client.get("/api/telemetry/events/economic?session_id=sess-1")
    outcomes = client.get("/api/telemetry/outcomes?session_id=sess-1")

    assert agents.status_code == 200
    assert agents.json()["data"][0]["codename"] == "vajra"
    assert teams.status_code == 200
    assert teams.json()["data"][0]["role"] == "surgeon"
    assert routes.json()["data"][0]["selected_provider"] == "anthropic"
    assert policies.json()["data"][0]["policy_name"] == "provider_policy"
    assert interventions.json()["data"][0]["operator_id"] == "operator"
    assert economic.json()["data"][0]["amount"] == 2.5
    assert outcomes.json()["data"][0]["subject_id"] == "customer-42"


@pytest.mark.asyncio
async def test_telemetry_optimization_endpoints_return_recommendations(telemetry_env) -> None:
    await telemetry_env.record_routing_decision(
        RoutingDecisionRecord(
            decision_id="route-2",
            action_name="deploy",
            route_path="escalate",
            selected_provider="openai",
            confidence=0.41,
            requires_human=True,
            task_id="task-2",
            run_id="run-2",
        )
    )
    await telemetry_env.record_intervention_outcome(
        InterventionOutcomeRecord(
            intervention_id="intervention-2",
            intervention_type="operator_approval",
            outcome_status="helpful",
            operator_id="operator",
            task_id="task-2",
            run_id="run-2",
        )
    )
    await telemetry_env.record_policy_decision(
        PolicyDecisionRecord(
            decision_id="policy-2",
            policy_name="provider_policy",
            decision="blocked",
            task_id="task-2",
            run_id="run-2",
            reason="high risk",
        )
    )
    await telemetry_env.record_economic_event(
        EconomicEventRecord(
            event_id="economic-2",
            event_kind="cost",
            amount=4.0,
            currency="USD",
            counterparty="openai",
            task_id="task-2",
            run_id="run-2",
        )
    )
    await telemetry_env.record_economic_event(
        EconomicEventRecord(
            event_id="economic-3",
            event_kind="revenue",
            amount=5.0,
            currency="USD",
            counterparty="anthropic",
            task_id="task-1",
        )
    )

    client = _telemetry_client()

    providers = client.get("/api/telemetry/optimization/providers")
    donors = client.get("/api/telemetry/optimization/donors?priority=1")

    assert providers.status_code == 200
    assert providers.json()["data"][0]["provider"] == "anthropic"
    assert providers.json()["data"][1]["provider"] == "openai"
    assert donors.status_code == 200
    assert any(item["donor_id"] == "tensorzero" for item in donors.json()["data"])


@pytest.mark.asyncio
async def test_telemetry_project_endpoint_returns_projection_status(telemetry_env) -> None:
    client = _telemetry_client()

    projected = client.post("/api/telemetry/project")

    assert projected.status_code == 200
    assert projected.json()["data"]["status"] in {"projected", "fresh"}
