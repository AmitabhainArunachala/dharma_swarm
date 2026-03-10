from __future__ import annotations

import pytest

from dharma_swarm.decision_router import CollaborationMode, RoutePath
from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.provider_policy import ProviderPolicyRouter, ProviderRouteRequest
from dharma_swarm.providers import ModelRouter
from dharma_swarm.resilience import RetryPolicy
from dharma_swarm.swarm_router import SwarmRole


def test_provider_policy_prefers_low_cost_provider_for_reflex_path() -> None:
    router = ProviderPolicyRouter()
    decision = router.route(
        ProviderRouteRequest(
            action_name="summarize_logs",
            risk_score=0.08,
            uncertainty=0.10,
            novelty=0.12,
            urgency=0.5,
            expected_impact=0.2,
            estimated_latency_ms=200,
            estimated_tokens=300,
            preferred_low_cost=True,
        ),
        available_providers=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.ANTHROPIC,
            ProviderType.CODEX,
        ],
    )

    assert decision.path == RoutePath.REFLEX
    assert decision.selected_provider == ProviderType.OPENROUTER_FREE
    assert ProviderType.CODEX in decision.fallback_providers


def test_provider_policy_escalates_for_frontier_precision() -> None:
    router = ProviderPolicyRouter()
    decision = router.route(
        ProviderRouteRequest(
            action_name="security_hotfix",
            risk_score=0.30,
            uncertainty=0.25,
            novelty=0.20,
            urgency=0.95,
            expected_impact=0.92,
            requires_frontier_precision=True,
            privileged_action=True,
            requires_human_consent=True,
        ),
        available_providers=[
            ProviderType.OPENAI,
            ProviderType.ANTHROPIC,
            ProviderType.OPENROUTER,
        ],
    )

    assert decision.path == RoutePath.ESCALATE
    assert decision.selected_provider == ProviderType.ANTHROPIC
    assert "frontier_precision_requested" in decision.reasons


def test_provider_policy_prefers_tooling_lanes_when_requested() -> None:
    router = ProviderPolicyRouter()
    decision = router.route(
        ProviderRouteRequest(
            action_name="apply_patch",
            risk_score=0.35,
            uncertainty=0.30,
            novelty=0.25,
            urgency=0.6,
            expected_impact=0.4,
            context={"requires_tooling": True},
        ),
        available_providers=[
            ProviderType.CLAUDE_CODE,
            ProviderType.CODEX,
            ProviderType.OPENROUTER,
        ],
    )

    assert decision.selected_provider == ProviderType.CODEX
    assert decision.selected_model_hint == "codex"


def test_provider_policy_prefers_japanese_quality_lanes() -> None:
    router = ProviderPolicyRouter()
    decision = router.route(
        ProviderRouteRequest(
            action_name="jp_analysis",
            risk_score=0.08,
            uncertainty=0.12,
            novelty=0.10,
            urgency=0.4,
            expected_impact=0.2,
            preferred_low_cost=False,
            context={
                "prefer_japanese_quality": True,
                "complexity_tier": "MEDIUM",
            },
        ),
        available_providers=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.OPENROUTER,
            ProviderType.ANTHROPIC,
        ],
    )
    assert decision.selected_provider == ProviderType.OPENROUTER


def test_provider_policy_swarm_plan_keeps_simple_task_single_agent() -> None:
    router = ProviderPolicyRouter()
    plan = router.plan_swarm(
        ProviderRouteRequest(
            action_name="summarize_logs",
            risk_score=0.08,
            uncertainty=0.10,
            novelty=0.12,
            urgency=0.2,
            expected_impact=0.2,
            context={"complexity_score": 0.10},
        ),
        available_providers=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.ANTHROPIC,
        ],
    )

    assert plan.collaboration.mode == CollaborationMode.SINGLE_AGENT
    assert plan.roles == (SwarmRole.PLANNER,)
    assert len(plan.role_routes) == 1
    assert plan.role_routes[0].route.selected_provider == ProviderType.OPENROUTER_FREE


def test_provider_policy_swarm_plan_fans_out_reasoning_task() -> None:
    router = ProviderPolicyRouter()
    plan = router.plan_swarm(
        ProviderRouteRequest(
            action_name="design_research",
            risk_score=0.30,
            uncertainty=0.48,
            novelty=0.52,
            urgency=0.55,
            expected_impact=0.60,
            context={
                "complexity_score": 0.72,
                "reasoning_markers": 2,
                "has_multi_step": True,
                "broad_domain": True,
                "requires_verification": True,
                "task_brief": "Compare design options and surface tradeoffs.",
            },
        ),
        available_providers=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.OPENROUTER,
            ProviderType.ANTHROPIC,
            ProviderType.CODEX,
        ],
    )

    assert plan.collaboration.mode == CollaborationMode.MULTI_AGENT
    assert plan.roles == (
        SwarmRole.PLANNER,
        SwarmRole.RESEARCHER,
        SwarmRole.CRITIC,
    )
    assert plan.blackboard.task_brief == "Compare design options and surface tradeoffs."
    assert all(route.request.context["collaboration_mode"] == "multi_agent" for route in plan.role_routes)


def test_provider_policy_swarm_role_allocation_is_deterministic() -> None:
    router = ProviderPolicyRouter()
    request = ProviderRouteRequest(
        action_name="implement_patch",
        risk_score=0.32,
        uncertainty=0.40,
        novelty=0.28,
        urgency=0.40,
        expected_impact=0.50,
        context={
            "complexity_score": 0.64,
            "has_code": True,
            "has_multi_step": True,
            "requires_verification": True,
        },
    )

    first = router.plan_swarm(
        request,
        available_providers=[
            ProviderType.CODEX,
            ProviderType.CLAUDE_CODE,
            ProviderType.ANTHROPIC,
        ],
    )
    second = router.plan_swarm(
        request,
        available_providers=[
            ProviderType.CODEX,
            ProviderType.CLAUDE_CODE,
            ProviderType.ANTHROPIC,
        ],
    )

    assert first.roles == second.roles == (
        SwarmRole.PLANNER,
        SwarmRole.CODER,
        SwarmRole.CRITIC,
    )
    assert first.role_routes[1].route.selected_provider == ProviderType.CODEX
    assert second.role_routes[1].route.selected_provider == ProviderType.CODEX


def test_provider_policy_swarm_plan_exposes_execution_contract() -> None:
    router = ProviderPolicyRouter()
    plan = router.plan_swarm(
        ProviderRouteRequest(
            action_name="implement_patch",
            risk_score=0.32,
            uncertainty=0.40,
            novelty=0.28,
            urgency=0.40,
            expected_impact=0.50,
            context={
                "complexity_score": 0.64,
                "has_code": True,
                "has_multi_step": True,
                "requires_verification": True,
            },
        ),
        available_providers=[
            ProviderType.CODEX,
            ProviderType.CLAUDE_CODE,
            ProviderType.ANTHROPIC,
        ],
    )

    route_by_role = {route.role: route for route in plan.role_routes}
    assert plan.execution_contract.contract_id == "swarm_execution_plan_v1"
    assert plan.execution_contract.required_context_keys == (
        "collaboration_mode",
        "assigned_role",
        "required_roles",
        "blackboard_contract",
    )
    assert route_by_role[SwarmRole.PLANNER].dependency_roles == ()
    assert route_by_role[SwarmRole.CODER].dependency_roles == (SwarmRole.PLANNER,)
    assert route_by_role[SwarmRole.CRITIC].dependency_roles == (
        SwarmRole.PLANNER,
        SwarmRole.CODER,
    )


class _DummyProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content=self.content, model="dummy")

    async def stream(self, request: LLMRequest):
        yield self.content


class _FailingProvider:
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("transient upstream failure")

    async def stream(self, request: LLMRequest):
        yield ""


class _CountingFailingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        raise RuntimeError("always fails")

    async def stream(self, request: LLMRequest):
        yield ""


@pytest.mark.asyncio
async def test_model_router_complete_for_task_uses_policy_selection() -> None:
    router = ModelRouter(
        {
            ProviderType.OPENROUTER_FREE: _DummyProvider("cheap"),
            ProviderType.ANTHROPIC: _DummyProvider("frontier"),
        }
    )

    decision, response = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="triage_notes",
            risk_score=0.10,
            uncertainty=0.12,
            novelty=0.10,
            urgency=0.3,
            expected_impact=0.2,
        ),
        LLMRequest(
            model="ignored",
            messages=[{"role": "user", "content": "summarize these notes"}],
        ),
        available_provider_types=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.ANTHROPIC,
        ],
    )

    assert decision.selected_provider == ProviderType.OPENROUTER_FREE
    assert response.content == "cheap"


@pytest.mark.asyncio
async def test_model_router_complete_for_task_falls_back_cross_provider() -> None:
    router = ModelRouter(
        {
            ProviderType.OPENROUTER_FREE: _FailingProvider(),
            ProviderType.ANTHROPIC: _DummyProvider("frontier"),
        },
        retry_policy=RetryPolicy(
            max_attempts=1,
            base_delay_seconds=0.0,
            jitter_seconds=0.0,
            max_delay_seconds=0.0,
        ),
    )
    decision, response = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="triage_notes",
            risk_score=0.10,
            uncertainty=0.12,
            novelty=0.10,
            urgency=0.3,
            expected_impact=0.2,
        ),
        LLMRequest(
            model="ignored",
            messages=[{"role": "user", "content": "summarize these notes"}],
        ),
        available_provider_types=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.ANTHROPIC,
        ],
    )
    assert decision.selected_provider == ProviderType.ANTHROPIC
    assert "fallback_provider_selected" in decision.reasons
    assert response.content == "frontier"


@pytest.mark.asyncio
async def test_model_router_complete_for_task_uses_language_enrichment() -> None:
    router = ModelRouter(
        {
            ProviderType.OPENROUTER_FREE: _DummyProvider("cheap"),
            ProviderType.OPENROUTER: _DummyProvider("jp-quality"),
            ProviderType.ANTHROPIC: _DummyProvider("frontier"),
        }
    )
    decision, response = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="jp_request",
            risk_score=0.08,
            uncertainty=0.10,
            novelty=0.10,
            urgency=0.4,
            expected_impact=0.2,
            preferred_low_cost=True,
        ),
        LLMRequest(
            model="ignored",
            messages=[{"role": "user", "content": "日本語で設計を分析してください"}],
        ),
        available_provider_types=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.OPENROUTER,
            ProviderType.ANTHROPIC,
        ],
    )
    assert decision.selected_provider != ProviderType.OPENROUTER_FREE
    assert response.content in {"jp-quality", "frontier"}


@pytest.mark.asyncio
async def test_model_router_session_affinity_keeps_provider_sticky() -> None:
    router = ModelRouter(
        {
            ProviderType.OPENROUTER_FREE: _DummyProvider("cheap"),
            ProviderType.OPENROUTER: _DummyProvider("sticky-jp"),
            ProviderType.ANTHROPIC: _DummyProvider("frontier"),
        },
        sticky_min_tokens=1,
        sticky_session_seconds=300.0,
    )

    first_decision, _ = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="jp_request",
            risk_score=0.08,
            uncertainty=0.10,
            novelty=0.10,
            urgency=0.4,
            expected_impact=0.2,
            preferred_low_cost=True,
            estimated_tokens=20_000,
            context={"session_id": "sess-stick"},
        ),
        LLMRequest(
            model="ignored",
            messages=[{"role": "user", "content": "日本語で設計を分析してください"}],
        ),
        available_provider_types=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.OPENROUTER,
            ProviderType.ANTHROPIC,
        ],
    )
    assert first_decision.selected_provider in {ProviderType.OPENROUTER, ProviderType.ANTHROPIC}

    second_decision, second_response = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="followup",
            risk_score=0.05,
            uncertainty=0.05,
            novelty=0.05,
            urgency=0.2,
            expected_impact=0.1,
            preferred_low_cost=True,
            estimated_tokens=20_000,
            context={"session_id": "sess-stick"},
        ),
        LLMRequest(
            model="ignored",
            messages=[{"role": "user", "content": "quick summary please"}],
        ),
        available_provider_types=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.OPENROUTER,
            ProviderType.ANTHROPIC,
        ],
    )
    assert "session_affinity_applied" in second_decision.reasons
    assert second_decision.selected_provider == first_decision.selected_provider
    assert second_response.content in {"sticky-jp", "frontier"}


@pytest.mark.asyncio
async def test_model_router_canary_routes_to_canary_provider() -> None:
    router = ModelRouter(
        {
            ProviderType.OPENROUTER_FREE: _DummyProvider("cheap"),
            ProviderType.ANTHROPIC: _DummyProvider("canary"),
        },
        canary_percent=100.0,
        canary_provider=ProviderType.ANTHROPIC,
        canary_model_hint="claude-sonnet-4-6",
    )
    decision, response = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="canary_test",
            risk_score=0.05,
            uncertainty=0.05,
            novelty=0.05,
            urgency=0.2,
            expected_impact=0.1,
            preferred_low_cost=True,
        ),
        LLMRequest(
            model="ignored",
            messages=[{"role": "user", "content": "quick summary"}],
        ),
        available_provider_types=[ProviderType.OPENROUTER_FREE, ProviderType.ANTHROPIC],
    )
    assert decision.selected_provider == ProviderType.ANTHROPIC
    assert "canary_applied" in decision.reasons
    assert response.content == "canary"


@pytest.mark.asyncio
async def test_model_router_learning_reorders_after_failures() -> None:
    failing = _CountingFailingProvider()
    router = ModelRouter(
        {
            ProviderType.OPENROUTER_FREE: failing,
            ProviderType.ANTHROPIC: _DummyProvider("frontier"),
        },
        retry_policy=RetryPolicy(
            max_attempts=1,
            base_delay_seconds=0.0,
            jitter_seconds=0.0,
            max_delay_seconds=0.0,
        ),
        learning_enabled=True,
        learning_alpha=1.0,
    )

    first_decision, first_response = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="learn1",
            risk_score=0.1,
            uncertainty=0.1,
            novelty=0.1,
            urgency=0.2,
            expected_impact=0.1,
        ),
        LLMRequest(model="ignored", messages=[{"role": "user", "content": "summarize"}]),
        available_provider_types=[ProviderType.OPENROUTER_FREE, ProviderType.ANTHROPIC],
    )
    assert first_decision.selected_provider == ProviderType.ANTHROPIC
    assert first_response.content == "frontier"
    assert failing.calls == 1

    second_decision, second_response = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="learn2",
            risk_score=0.1,
            uncertainty=0.1,
            novelty=0.1,
            urgency=0.2,
            expected_impact=0.1,
        ),
        LLMRequest(model="ignored", messages=[{"role": "user", "content": "summarize again"}]),
        available_provider_types=[ProviderType.OPENROUTER_FREE, ProviderType.ANTHROPIC],
    )
    assert second_decision.selected_provider == ProviderType.ANTHROPIC
    assert second_response.content == "frontier"
    # Learning promoted the successful lane ahead of the failing one.
    assert failing.calls == 1
    rewards = router.reward_snapshot()
    assert any(key.startswith("anthropic:") for key in rewards)
