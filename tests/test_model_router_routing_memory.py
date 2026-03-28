from __future__ import annotations

from dharma_swarm.decision_router import RoutePath
from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.provider_policy import ProviderRouteDecision, ProviderRouteRequest
from dharma_swarm.providers import ModelRouter
from dharma_swarm.routing_memory import RoutingMemoryStore, build_task_signature


class _DummyProvider:
    def __init__(self, content: str) -> None:
        self.content = content

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=self.content,
            model=request.model,
            usage={"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
        )

    async def stream(self, request: LLMRequest):
        yield self.content


async def test_model_router_uses_persistent_routing_memory_to_reorder(tmp_path) -> None:
    store = RoutingMemoryStore(tmp_path / "routing.sqlite3")
    route_request = ProviderRouteRequest(
        action_name="triage_notes",
        risk_score=0.08,
        uncertainty=0.10,
        novelty=0.10,
        urgency=0.3,
        expected_impact=0.2,
        preferred_low_cost=True,
    )
    request = LLMRequest(
        model="ignored",
        messages=[{"role": "user", "content": "summarize these notes"}],
    )
    task_signature = build_task_signature(
        action_name=route_request.action_name,
        context={
            "language_code": "en",
            "complexity_tier": "SIMPLE",
            "context_tier": "SHORT",
            "requires_tooling": False,
        },
    )

    # Record outcomes using the DEFAULT_MODELS hints that will be looked up
    from dharma_swarm.model_hierarchy import DEFAULT_MODELS

    anthropic_model = DEFAULT_MODELS.get(ProviderType.ANTHROPIC, "claude-opus-4-6")
    orfree_model = DEFAULT_MODELS.get(ProviderType.OPENROUTER_FREE, "meta-llama/llama-3.3-70b-instruct:free")

    for _ in range(4):
        store.record_outcome(
            provider=ProviderType.ANTHROPIC,
            model=anthropic_model,
            task_signature=task_signature,
            action_name=route_request.action_name,
            route_path="reflex",
            success=True,
            latency_ms=800.0,
            total_tokens=500,
        )
    for _ in range(3):
        store.record_outcome(
            provider=ProviderType.OPENROUTER_FREE,
            model=orfree_model,
            task_signature=task_signature,
            action_name=route_request.action_name,
            route_path="reflex",
            success=False,
            latency_ms=1000.0,
            total_tokens=0,
            error="provider_error",
        )

    router = ModelRouter(
        {
            ProviderType.OPENROUTER_FREE: _DummyProvider("cheap"),
            ProviderType.ANTHROPIC: _DummyProvider("frontier"),
        },
        routing_memory=store,
    )

    decision, response = await router.complete_for_task(
        route_request,
        request,
        available_provider_types=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.ANTHROPIC,
        ],
    )

    assert decision.selected_provider == ProviderType.ANTHROPIC
    assert "routing_memory_applied" in decision.reasons
    assert response.content == "frontier"


async def test_model_router_posthoc_feedback_reorders_future_routes(tmp_path) -> None:
    store = RoutingMemoryStore(tmp_path / "routing.sqlite3")
    route_request = ProviderRouteRequest(
        action_name="triage_notes",
        risk_score=0.08,
        uncertainty=0.10,
        novelty=0.10,
        urgency=0.3,
        expected_impact=0.2,
        preferred_low_cost=True,
    )
    request = LLMRequest(
        model="ignored",
        messages=[{"role": "user", "content": "summarize these notes"}],
    )
    router = ModelRouter(
        {
            ProviderType.OPENROUTER_FREE: _DummyProvider("cheap"),
            ProviderType.ANTHROPIC: _DummyProvider("frontier"),
        },
        routing_memory=store,
    )

    router.record_task_feedback(
        route_request=route_request,
        request=request,
        decision=ProviderRouteDecision(
            path=RoutePath.REFLEX,
            selected_provider=ProviderType.OPENROUTER_FREE,
            selected_model_hint="meta-llama/llama-3.3-70b-instruct:free",
            fallback_providers=[ProviderType.ANTHROPIC],
            fallback_model_hints=["claude-opus-4-6"],
            confidence=0.8,
            requires_human=False,
            reasons=["seed_feedback"],
        ),
        quality_score=0.15,
        success=False,
        total_tokens=200,
        latency_ms=500.0,
    )
    router.record_task_feedback(
        route_request=route_request,
        request=request,
        decision=ProviderRouteDecision(
            path=RoutePath.DELIBERATIVE,
            selected_provider=ProviderType.ANTHROPIC,
            selected_model_hint="claude-opus-4-6",
            fallback_providers=[ProviderType.OPENROUTER_FREE],
            fallback_model_hints=["meta-llama/llama-3.3-70b-instruct:free"],
            confidence=0.8,
            requires_human=False,
            reasons=["seed_feedback"],
        ),
        quality_score=0.95,
        success=True,
        total_tokens=800,
        latency_ms=900.0,
    )

    decision, response = await router.complete_for_task(
        route_request,
        request,
        available_provider_types=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.ANTHROPIC,
        ],
    )

    assert decision.selected_provider == ProviderType.ANTHROPIC
    assert "routing_memory_applied" in decision.reasons
    assert response.content == "frontier"
