from __future__ import annotations

import json

import pytest

from dharma_swarm.decision_router import RoutePath
from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.provider_policy import ProviderRouteDecision, ProviderRouteRequest
from dharma_swarm.providers import ModelRouter


class _DummyProvider:
    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(content="ok", model=request.model)

    async def stream(self, request: LLMRequest):
        yield "ok"


def test_record_task_feedback_writes_route_retrospective(monkeypatch, tmp_path) -> None:
    retrospective_log = tmp_path / "route_retrospectives.jsonl"
    monkeypatch.setenv("DGC_ROUTER_RETROSPECTIVE_LOG", str(retrospective_log))

    router = ModelRouter({ProviderType.OPENAI: _DummyProvider()})
    task_signature = router.record_task_feedback(
        route_request=ProviderRouteRequest(
            action_name="jp_design_review",
            risk_score=0.10,
            uncertainty=0.10,
            novelty=0.10,
            urgency=0.3,
            expected_impact=0.2,
        ),
        request=LLMRequest(
            model="gpt-4.1",
            messages=[{"role": "user", "content": "日本語で設計を分析して比較してください"}],
        ),
        decision=ProviderRouteDecision(
            path=RoutePath.REFLEX,
            selected_provider=ProviderType.OPENAI,
            selected_model_hint="gpt-4.1",
            fallback_providers=[],
            fallback_model_hints=[],
            confidence=0.92,
            requires_human=False,
            reasons=["seed_feedback"],
        ),
        quality_score=0.18,
        success=False,
        total_tokens=640,
        latency_ms=910.0,
        metadata={"error": "empty_output"},
    )

    assert task_signature
    lines = retrospective_log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    artifact = json.loads(lines[0])
    assert artifact["severity"] == "critical"
    assert artifact["route_record"]["selected_provider"] == "openai"
    assert artifact["route_record"]["quality_score"] == pytest.approx(0.18)


def test_record_task_feedback_skips_retrospective_for_healthy_route(
    monkeypatch,
    tmp_path,
) -> None:
    retrospective_log = tmp_path / "route_retrospectives.jsonl"
    monkeypatch.setenv("DGC_ROUTER_RETROSPECTIVE_LOG", str(retrospective_log))

    router = ModelRouter({ProviderType.OPENAI: _DummyProvider()})
    router.record_task_feedback(
        route_request=ProviderRouteRequest(
            action_name="healthy_route",
            risk_score=0.05,
            uncertainty=0.05,
            novelty=0.05,
            urgency=0.2,
            expected_impact=0.1,
        ),
        request=LLMRequest(
            model="gpt-4.1",
            messages=[{"role": "user", "content": "Quick summary"}],
        ),
        decision=ProviderRouteDecision(
            path=RoutePath.DELIBERATIVE,
            selected_provider=ProviderType.OPENAI,
            selected_model_hint="gpt-4.1",
            fallback_providers=[],
            fallback_model_hints=[],
            confidence=0.92,
            requires_human=False,
            reasons=["seed_feedback"],
        ),
        quality_score=0.91,
        success=True,
        total_tokens=120,
        latency_ms=220.0,
    )

    assert retrospective_log.exists() is False
