from __future__ import annotations

import pytest

from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.provider_policy import ProviderRouteRequest
from dharma_swarm.providers import ModelRouter
from dharma_swarm.telemetry_plane import TelemetryPlaneStore


class _DummyProvider:
    def __init__(
        self,
        content: str,
        *,
        prompt_tokens: int = 120,
        completion_tokens: int = 40,
    ) -> None:
        self.content = content
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens

    async def complete(self, request: LLMRequest) -> LLMResponse:
        total_tokens = self.prompt_tokens + self.completion_tokens
        return LLMResponse(
            content=self.content,
            model=request.model,
            usage={
                "prompt_tokens": self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens": total_tokens,
            },
        )

    async def stream(self, request: LLMRequest):
        yield self.content


class _FailingProvider:
    async def complete(self, request: LLMRequest) -> LLMResponse:
        raise RuntimeError("synthetic upstream failure")

    async def stream(self, request: LLMRequest):
        yield ""


@pytest.mark.asyncio
async def test_model_router_success_writes_telemetry_records(tmp_path) -> None:
    telemetry = TelemetryPlaneStore(tmp_path / "runtime.db")
    router = ModelRouter(
        {ProviderType.OPENAI: _DummyProvider("ok")},
        telemetry=telemetry,
    )

    decision, response = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="summarize_notes",
            risk_score=0.12,
            uncertainty=0.14,
            novelty=0.12,
            urgency=0.4,
            expected_impact=0.2,
            estimated_latency_ms=200,
            estimated_tokens=300,
            context={
                "session_id": "sess-telemetry",
                "task_id": "task-success",
                "run_id": "run-success",
            },
        ),
        LLMRequest(
            model="gpt-4o",
            messages=[{"role": "user", "content": "Summarize these notes"}],
        ),
        available_provider_types=[ProviderType.OPENAI],
    )

    routes = await telemetry.list_routing_decisions(task_id="task-success", limit=10)
    policies = await telemetry.list_policy_decisions(
        task_id="task-success",
        policy_name="provider_policy",
        limit=10,
    )
    economic = await telemetry.list_economic_events(
        event_kind="cost",
        session_id="sess-telemetry",
        limit=10,
    )
    outcomes = await telemetry.list_external_outcomes(
        session_id="sess-telemetry",
        limit=20,
    )

    assert decision.selected_provider == ProviderType.OPENAI
    assert response.content == "ok"
    assert len(routes) == 1
    assert routes[0].selected_provider == "openai"
    assert routes[0].metadata["result"] == "success"
    assert len(policies) == 1
    assert policies[0].decision == "approved"
    assert len(economic) == 1
    assert economic[0].counterparty == "openai"
    assert economic[0].amount > 0.0
    assert any(
        item.outcome_kind == "provider_attempt"
        and item.subject_id == "openai"
        and item.status == "succeeded"
        for item in outcomes
    )
    assert any(
        item.outcome_kind == "provider_completion"
        and item.subject_id == "openai"
        and item.status == "observed"
        and item.value == 1.0
        for item in outcomes
    )


@pytest.mark.asyncio
async def test_model_router_fallback_success_marks_fallback_in_telemetry(tmp_path) -> None:
    telemetry = TelemetryPlaneStore(tmp_path / "runtime.db")
    router = ModelRouter(
        {
            ProviderType.OPENROUTER_FREE: _FailingProvider(),
            ProviderType.ANTHROPIC: _DummyProvider("frontier"),
        },
        telemetry=telemetry,
    )

    decision, response = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="triage_notes",
            risk_score=0.10,
            uncertainty=0.12,
            novelty=0.10,
            urgency=0.3,
            expected_impact=0.2,
            estimated_latency_ms=200,
            estimated_tokens=300,
            preferred_low_cost=True,
            context={
                "session_id": "sess-fallback",
                "task_id": "task-fallback",
                "run_id": "run-fallback",
            },
        ),
        LLMRequest(
            model="ignored",
            messages=[{"role": "user", "content": "Summarize these notes"}],
        ),
        available_provider_types=[
            ProviderType.OPENROUTER_FREE,
            ProviderType.ANTHROPIC,
        ],
    )

    routes = await telemetry.list_routing_decisions(task_id="task-fallback", limit=10)
    outcomes = await telemetry.list_external_outcomes(
        session_id="sess-fallback",
        limit=20,
    )

    assert decision.selected_provider == ProviderType.ANTHROPIC
    assert response.content == "frontier"
    assert len(routes) == 1
    assert routes[0].selected_provider == "anthropic"
    assert routes[0].metadata["fallback_selected"] is True
    assert routes[0].metadata["initial_selected_provider"] == "openrouter_free"
    assert any(
        item.outcome_kind == "provider_attempt"
        and item.subject_id == "openrouter_free"
        and item.status == "failed"
        for item in outcomes
    )
    assert any(
        item.outcome_kind == "provider_attempt"
        and item.subject_id == "anthropic"
        and item.status == "succeeded"
        for item in outcomes
    )


@pytest.mark.asyncio
async def test_model_router_total_failure_writes_failed_completion_telemetry(tmp_path) -> None:
    telemetry = TelemetryPlaneStore(tmp_path / "runtime.db")
    router = ModelRouter(
        {ProviderType.OPENAI: _FailingProvider()},
        telemetry=telemetry,
    )

    with pytest.raises(RuntimeError, match="All providers failed"):
        await router.complete_for_task(
            ProviderRouteRequest(
                action_name="deploy_hotfix",
                risk_score=0.12,
                uncertainty=0.14,
                novelty=0.15,
                urgency=0.6,
                expected_impact=0.4,
                context={
                    "session_id": "sess-failure",
                    "task_id": "task-failure",
                    "run_id": "run-failure",
                },
            ),
            LLMRequest(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Deploy the hotfix"}],
            ),
            available_provider_types=[ProviderType.OPENAI],
        )

    routes = await telemetry.list_routing_decisions(task_id="task-failure", limit=10)
    outcomes = await telemetry.list_external_outcomes(
        session_id="sess-failure",
        limit=20,
    )
    economic = await telemetry.list_economic_events(
        event_kind="cost",
        session_id="sess-failure",
        limit=10,
    )

    assert len(routes) == 1
    assert routes[0].selected_provider == "openai"
    assert routes[0].metadata["result"] == "failed"
    assert economic == []
    assert any(
        item.outcome_kind == "provider_completion"
        and item.subject_id == "openai"
        and item.status == "failed"
        and item.value == 0.0
        for item in outcomes
    )
