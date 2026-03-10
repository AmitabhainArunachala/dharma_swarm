from __future__ import annotations

from pathlib import Path

import dharma_swarm.router_v1 as router_v1
from dharma_swarm.models import LLMRequest, ProviderType
from dharma_swarm.provider_policy import ProviderRouteRequest
from dharma_swarm.router_v1 import (
    build_routing_signals,
    classify_context_tier,
    detect_language_profile,
    enrich_route_request,
    model_hint_for_provider,
)


def test_detect_language_profile_japanese() -> None:
    code, confidence, cjk_ratio = detect_language_profile("実装を最適化して検証してください")
    assert code == "ja"
    assert confidence >= 0.70
    assert cjk_ratio > 0.0


def test_build_routing_signals_reasoning_tier() -> None:
    request = LLMRequest(
        model="x",
        messages=[
            {
                "role": "user",
                "content": "Think through this step by step and analyze why the design fails.",
            }
        ],
    )
    signals = build_routing_signals(request)
    assert signals.complexity_tier == "REASONING"
    assert signals.reasoning_markers >= 2


def test_enrich_route_request_promotes_quality_for_japanese() -> None:
    route = ProviderRouteRequest(
        action_name="jp_reasoning",
        risk_score=0.2,
        uncertainty=0.2,
        novelty=0.2,
        urgency=0.5,
        expected_impact=0.4,
        preferred_low_cost=True,
        requires_frontier_precision=False,
    )
    request = LLMRequest(
        model="x",
        messages=[
            {
                "role": "user",
                "content": "この設計を分析して、ステップごとに理由を説明してください",
            }
        ],
    )
    out = enrich_route_request(route, request)
    assert out.preferred_low_cost is False
    assert out.requires_frontier_precision is True
    assert out.context["prefer_japanese_quality"] is True
    assert out.context["complexity_tier"] == "REASONING"


def test_model_hint_for_provider_prefers_qwen_for_japanese() -> None:
    request = LLMRequest(
        model="x",
        messages=[{"role": "user", "content": "日本語で実装の改善を説明して"}],
    )
    signals = build_routing_signals(request)
    hint = model_hint_for_provider(
        ProviderType.OPENROUTER,
        default_hint="openai/gpt-5-codex",
        signals=signals,
    )
    assert hint == "qwen/qwen3-32b"


def test_classify_context_tier_thresholds() -> None:
    assert classify_context_tier(100) == "SHORT"
    assert classify_context_tier(9000) == "MEDIUM_LONG"
    assert classify_context_tier(70000) == "LONG"
    assert classify_context_tier(170000) == "VERY_LONG"


def test_detect_language_profile_fasttext_override(monkeypatch) -> None:
    monkeypatch.setattr(router_v1, "_predict_fasttext_language", lambda text: ("ja", 0.95))
    code, confidence, _ = detect_language_profile("hello mixed テスト")
    assert code == "ja"
    assert confidence >= 0.90


def test_predict_fasttext_language_pybind_fallback(monkeypatch) -> None:
    class _FakeInner:
        @staticmethod
        def predict(text, k, threshold, delimiter):
            return [(0.93, "__label__ja")]

    class _FakeModel:
        f = _FakeInner()

        @staticmethod
        def predict(text, k=1):
            raise ValueError("numpy2 copy error")

    monkeypatch.setattr(router_v1, "_FASTTEXT_DISABLED", False)
    monkeypatch.setattr(router_v1, "_FASTTEXT_MODEL", _FakeModel())
    monkeypatch.setattr(router_v1, "_fasttext_model_path", lambda: Path("/tmp"))
    pred = router_v1._predict_fasttext_language("テスト")
    assert pred == ("ja", 0.93)
