from __future__ import annotations

import pytest

from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.provider_policy import ProviderRouteRequest
from dharma_swarm.providers import ModelRouter


class _CapturingProvider:
    def __init__(self) -> None:
        self.models: list[str] = []

    async def complete(self, request: LLMRequest) -> LLMResponse:
        self.models.append(request.model)
        return LLMResponse(content="ok", model=request.model)

    async def stream(self, request: LLMRequest):
        yield "ok"


@pytest.mark.asyncio
async def test_model_router_preserves_requested_model_for_single_pinned_provider() -> None:
    provider = _CapturingProvider()
    router = ModelRouter({ProviderType.OPENAI: provider})

    decision, response = await router.complete_for_task(
        ProviderRouteRequest(
            action_name="summarize_logs",
            risk_score=0.05,
            uncertainty=0.05,
            novelty=0.05,
            urgency=0.2,
            expected_impact=0.1,
            context={"preserve_requested_model": True},
        ),
        LLMRequest(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": "Summarize these logs"}],
        ),
        available_provider_types=[ProviderType.OPENAI],
    )

    assert decision.selected_provider == ProviderType.OPENAI
    assert provider.models == ["gpt-4.1-mini"]
    assert response.model == "gpt-4.1-mini"
