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


def test_enrich_route_request_includes_tiny_router_shadow_metadata() -> None:
    route = ProviderRouteRequest(
        action_name="calendar_update",
        risk_score=0.1,
        uncertainty=0.1,
        novelty=0.1,
        urgency=0.2,
        expected_impact=0.2,
    )
    request = LLMRequest(
        model="x",
        messages=[
            {"role": "user", "content": "Set a reminder for Friday"},
            {"role": "assistant", "content": "Done."},
            {"role": "user", "content": "Actually next Monday"},
        ],
    )

    out = enrich_route_request(route, request)

    assert out.context["relation_to_previous"] == "correction"
    assert out.context["actionability"] == "act"
    assert out.context["retention"] == "useful"
    assert out.context["ingress_urgency_label"] in {"medium", "high"}
    assert out.context["tiny_router_source"] in {
        "heuristic-shadow",
        "hf-tgupj-tiny-router-shadow",
    }


def test_model_hint_for_provider_prefers_kimi_for_japanese() -> None:
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
    assert hint == "moonshotai/kimi-k2.5"


def test_model_hint_for_provider_prefers_glm_and_nemotron_for_reasoning() -> None:
    request = LLMRequest(
        model="x",
        messages=[{"role": "user", "content": "Analyze the failure chain step by step and reason carefully."}],
    )
    signals = build_routing_signals(request)

    openrouter_hint = model_hint_for_provider(
        ProviderType.OPENROUTER,
        default_hint="openai/gpt-5-codex",
        signals=signals,
    )
    nim_hint = model_hint_for_provider(
        ProviderType.NVIDIA_NIM,
        default_hint="meta/llama-3.3-70b-instruct",
        signals=signals,
    )

    assert openrouter_hint == "z-ai/glm-5"
    assert nim_hint == "nvidia/llama-3.1-nemotron-ultra-253b-v1"


def test_model_hint_for_provider_prefers_self_hosted_nim_frontier(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "http://nim.local:8000/v1")
    request = LLMRequest(
        model="x",
        messages=[{"role": "user", "content": "日本語で長い設計の分析をしてください。理由も説明して。"}],
    )
    signals = build_routing_signals(request)

    jp_hint = model_hint_for_provider(
        ProviderType.NVIDIA_NIM,
        default_hint="meta/llama-3.3-70b-instruct",
        signals=signals,
    )
    assert jp_hint == "moonshotai/kimi-k2.5"

    reasoning_request = LLMRequest(
        model="x",
        messages=[{"role": "user", "content": "Analyze the system carefully and reason step by step."}],
    )
    reasoning_signals = build_routing_signals(reasoning_request)
    reasoning_hint = model_hint_for_provider(
        ProviderType.NVIDIA_NIM,
        default_hint="meta/llama-3.3-70b-instruct",
        signals=reasoning_signals,
    )
    assert reasoning_hint == "zai-org/GLM-5"


def test_model_hint_for_provider_prefers_ollama_cloud_frontier(monkeypatch) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-cloud-key")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    jp_request = LLMRequest(
        model="x",
        messages=[{"role": "user", "content": "日本語で設計の全体像を説明して"}],
    )
    jp_signals = build_routing_signals(jp_request)
    jp_hint = model_hint_for_provider(
        ProviderType.OLLAMA,
        default_hint="llama3.2",
        signals=jp_signals,
    )
    assert jp_hint == "kimi-k2.5:cloud"

    reasoning_request = LLMRequest(
        model="x",
        messages=[{"role": "user", "content": "Analyze the architecture carefully and reason step by step."}],
    )
    reasoning_signals = build_routing_signals(reasoning_request)
    reasoning_hint = model_hint_for_provider(
        ProviderType.OLLAMA,
        default_hint="llama3.2",
        signals=reasoning_signals,
    )
    assert reasoning_hint == "glm-5:cloud"


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
