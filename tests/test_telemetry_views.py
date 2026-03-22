from __future__ import annotations

import pytest

from dharma_swarm.telemetry_plane import (
    AgentIdentityRecord,
    EconomicEventRecord,
    RoutingDecisionRecord,
    TeamRosterRecord,
    TelemetryPlaneStore,
)
from dharma_swarm.telemetry_views import TelemetryViews


@pytest.mark.asyncio
async def test_telemetry_views_summarize_overview_and_routing(tmp_path) -> None:
    store = TelemetryPlaneStore(tmp_path / "runtime.db")
    await store.init_db()
    await store.upsert_agent_identity(
        AgentIdentityRecord(agent_id="agent-1", codename="vajra", status="active")
    )
    await store.upsert_agent_identity(
        AgentIdentityRecord(agent_id="agent-2", codename="lila", status="idle")
    )
    await store.record_team_roster(
        TeamRosterRecord(
            roster_id="roster-1",
            team_id="alpha",
            agent_id="agent-1",
            role="lead",
        )
    )
    await store.record_routing_decision(
        RoutingDecisionRecord(
            decision_id="route-1",
            action_name="research",
            route_path="deliberative",
            selected_provider="anthropic",
            confidence=0.8,
            requires_human=False,
        )
    )
    await store.record_routing_decision(
        RoutingDecisionRecord(
            decision_id="route-2",
            action_name="deploy",
            route_path="escalate",
            selected_provider="openai",
            confidence=0.4,
            requires_human=True,
        )
    )
    await store.record_economic_event(
        EconomicEventRecord(
            event_id="economic-1",
            event_kind="cost",
            amount=2.0,
            currency="USD",
        )
    )
    await store.record_economic_event(
        EconomicEventRecord(
            event_id="economic-2",
            event_kind="revenue",
            amount=5.5,
            currency="USD",
        )
    )

    views = TelemetryViews(store)
    overview = await views.overview()
    routing = await views.routing_summary()
    economic = await views.economic_summary()

    assert overview.agent_count == 2
    assert overview.active_agents == 1
    assert overview.team_count == 1
    assert overview.routing_decision_count == 2
    assert overview.total_cost_usd == 2.0
    assert overview.total_revenue_usd == 5.5
    assert routing.total_decisions == 2
    assert routing.human_required_count == 1
    assert routing.path_counts["deliberative"] == 1
    assert routing.provider_counts["openai"] == 1
    assert economic.net_usd == 3.5
    assert economic.currency_breakdown["USD"] == 7.5
