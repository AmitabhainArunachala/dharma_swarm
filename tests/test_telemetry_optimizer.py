from __future__ import annotations

from datetime import datetime, timezone

import pytest

from dharma_swarm.telemetry_optimizer import TelemetryOptimizer
from dharma_swarm.telemetry_plane import (
    EconomicEventRecord,
    InterventionOutcomeRecord,
    PolicyDecisionRecord,
    RoutingDecisionRecord,
    TelemetryPlaneStore,
)


@pytest.mark.asyncio
async def test_telemetry_optimizer_ranks_providers_and_lists_donors(tmp_path) -> None:
    store = TelemetryPlaneStore(tmp_path / "runtime.db")
    await store.init_db()

    await store.record_routing_decision(
        RoutingDecisionRecord(
            decision_id="route-anthropic-1",
            action_name="research",
            route_path="deliberative",
            selected_provider="anthropic",
            confidence=0.92,
            requires_human=False,
            task_id="task-1",
            run_id="run-1",
        )
    )
    await store.record_routing_decision(
        RoutingDecisionRecord(
            decision_id="route-anthropic-2",
            action_name="summarize",
            route_path="reflex",
            selected_provider="anthropic",
            confidence=0.88,
            requires_human=False,
            task_id="task-2",
            run_id="run-2",
        )
    )
    await store.record_routing_decision(
        RoutingDecisionRecord(
            decision_id="route-openai-1",
            action_name="deploy",
            route_path="escalate",
            selected_provider="openai",
            confidence=0.55,
            requires_human=True,
            task_id="task-3",
            run_id="run-3",
        )
    )
    await store.record_intervention_outcome(
        InterventionOutcomeRecord(
            intervention_id="intervention-openai-1",
            intervention_type="approve_checkpoint",
            outcome_status="helpful",
            task_id="task-3",
            run_id="run-3",
            operator_id="operator",
        )
    )
    await store.record_policy_decision(
        PolicyDecisionRecord(
            decision_id="policy-openai-1",
            policy_name="provider_policy",
            decision="blocked",
            task_id="task-3",
            run_id="run-3",
            reason="needs operator approval",
        )
    )
    await store.record_economic_event(
        EconomicEventRecord(
            event_id="econ-anthropic-cost",
            event_kind="cost",
            amount=1.25,
            currency="USD",
            counterparty="anthropic",
            task_id="task-1",
            run_id="run-1",
        )
    )
    await store.record_economic_event(
        EconomicEventRecord(
            event_id="econ-openai-cost",
            event_kind="cost",
            amount=4.75,
            currency="USD",
            counterparty="openai",
            task_id="task-3",
            run_id="run-3",
        )
    )
    await store.record_economic_event(
        EconomicEventRecord(
            event_id="econ-anthropic-revenue",
            event_kind="revenue",
            amount=6.0,
            currency="USD",
            counterparty="anthropic",
            task_id="task-2",
            run_id="run-2",
            created_at=datetime(2026, 3, 19, tzinfo=timezone.utc),
        )
    )

    optimizer = TelemetryOptimizer(store)
    recommendations = await optimizer.provider_recommendations(limit=10)
    donors = optimizer.donor_targets(priority=1)

    assert [item.provider for item in recommendations[:2]] == ["anthropic", "openai"]
    assert recommendations[0].recommended_role == "promote_to_default_lane"
    assert recommendations[0].net_usd == 4.75
    assert recommendations[1].recommended_actions[0] == "run_provider_eval_benchmark"
    assert recommendations[1].policy_block_rate == 1.0
    assert donors[0].priority == 1
    assert any(item.donor_id == "tensorzero" for item in donors)
