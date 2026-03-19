from __future__ import annotations

import pytest
from types import SimpleNamespace

from dharma_swarm.agent_runner import AgentRunner
from dharma_swarm.decision_router import RoutePath
from dharma_swarm.models import (
    AgentConfig,
    AgentRole,
    LLMRequest,
    LLMResponse,
    ProviderType,
    Task,
)
from dharma_swarm.provider_policy import ProviderRouteDecision


class _RoutedProvider:
    def __init__(self, *, content: str) -> None:
        self._content = content
        self.calls: list[tuple[object, LLMRequest, list[ProviderType] | None]] = []
        self.feedback: list[dict[str, object]] = []

    async def complete_for_task(
        self,
        route_request,
        request: LLMRequest,
        *,
        available_provider_types: list[ProviderType] | None = None,
    ) -> tuple[ProviderRouteDecision, LLMResponse]:
        self.calls.append((route_request, request, available_provider_types))
        selected_provider = (
            available_provider_types[0]
            if available_provider_types
            else ProviderType.ANTHROPIC
        )
        return (
            ProviderRouteDecision(
                path=RoutePath.DELIBERATIVE,
                selected_provider=selected_provider,
                selected_model_hint=request.model,
                fallback_providers=[],
                fallback_model_hints=[],
                confidence=0.82,
                requires_human=False,
                reasons=["test"],
            ),
            LLMResponse(
                content=self._content,
                model=request.model,
                usage={"total_tokens": 321},
            ),
        )

    def record_task_feedback(self, **kwargs) -> str:
        self.feedback.append(kwargs)
        return "sig-test"


@pytest.mark.asyncio
async def test_run_task_uses_routed_provider_and_records_feedback(fast_gate) -> None:
    provider = _RoutedProvider(content="Implemented fix in `module.py`.")
    runner = AgentRunner(
        AgentConfig(
            name="router-agent",
            role=AgentRole.CODER,
            provider=ProviderType.OPENAI,
            model="gpt-4.1",
        ),
        provider=provider,
    )
    await runner.start()

    result = await runner.run_task(
        Task(
            id="task-route-1",
            title="Implement module fix",
            description="Apply patch and update the failing test.",
        )
    )

    assert result.startswith("Implemented fix")
    route_request, _, allowlist = provider.calls[0]
    assert allowlist == [ProviderType.OPENAI]
    assert route_request.context["preferred_provider"] == "openai"
    assert route_request.context["preserve_requested_model"] is True
    feedback = provider.feedback[0]
    assert feedback["success"] is True
    assert feedback["model"] == "gpt-4.1"
    assert feedback["total_tokens"] == 321
    assert feedback["metadata"]["feedback_origin"] == "agent_runner"


@pytest.mark.asyncio
async def test_run_task_can_widen_provider_routing_from_task_metadata(fast_gate) -> None:
    provider = _RoutedProvider(content="Compared two options and outlined tradeoffs.")
    runner = AgentRunner(
        AgentConfig(
            name="research-router",
            role=AgentRole.RESEARCHER,
            provider=ProviderType.ANTHROPIC,
            model="claude-sonnet-4-20250514",
        ),
        provider=provider,
    )
    await runner.start()

    await runner.run_task(
        Task(
            id="task-route-2",
            title="Research architecture tradeoffs",
            description="Analyze and compare two designs before implementation.",
            metadata={
                "allow_provider_routing": True,
                "trace_id": "trc-route-2",
            },
        )
    )

    route_request, _, allowlist = provider.calls[0]
    assert allowlist is None
    assert route_request.requires_frontier_precision is True
    assert route_request.context["trace_id"] == "trc-route-2"
    assert route_request.context["preserve_requested_model"] is False


@pytest.mark.asyncio
async def test_run_task_records_failure_feedback_for_routed_provider(fast_gate) -> None:
    provider = _RoutedProvider(content="")
    runner = AgentRunner(
        AgentConfig(
            name="router-agent",
            role=AgentRole.CODER,
            provider=ProviderType.OPENAI,
            model="gpt-4.1",
        ),
        provider=provider,
    )
    await runner.start()

    with pytest.raises(RuntimeError):
        await runner.run_task(
            Task(
                id="task-route-3",
                title="Implement fix",
                description="Apply patch.",
            )
        )

    feedback = provider.feedback[0]
    assert feedback["success"] is False
    assert feedback["quality_score"] == 0.0
    assert "Provider returned empty response" in feedback["metadata"]["error"]


@pytest.mark.asyncio
async def test_run_task_uses_output_evaluation_for_router_feedback(fast_gate) -> None:
    class _FakeEvaluator:
        async def evaluate(self, *args, **kwargs):
            return SimpleNamespace(quality_score=0.93)

    provider = _RoutedProvider(content="Implemented fix in `module.py` with tests.")
    runner = AgentRunner(
        AgentConfig(
            name="router-agent",
            role=AgentRole.CODER,
            provider=ProviderType.OPENAI,
            model="gpt-4.1",
        ),
        provider=provider,
        output_evaluator=_FakeEvaluator(),
    )
    await runner.start()

    await runner.run_task(
        Task(
            id="task-route-4",
            title="Implement module fix",
            description="Apply patch and update the failing test.",
        )
    )

    feedback = provider.feedback[0]
    assert feedback["quality_score"] == pytest.approx(0.93)
