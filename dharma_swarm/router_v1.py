"""Minimal-elegant routing intelligence (language + complexity + request enrichment).

This module keeps classification local and deterministic:
- No network calls
- Fast heuristics only
- Provider-agnostic routing signals
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
import re

from dharma_swarm.models import LLMRequest, ProviderType
from dharma_swarm.ollama_config import (
    OLLAMA_DEFAULT_CLOUD_MODEL,
    OLLAMA_DEFAULT_LOCAL_MODEL,
    ollama_prefers_cloud,
)
from dharma_swarm.provider_policy import ProviderRouteRequest
from dharma_swarm.tiny_router_shadow import infer_tiny_router_shadow_from_messages


_RE_CODE = re.compile(r"```|`[^`]+`|\b(def|class|import|api|sql|json)\b", re.IGNORECASE)
_RE_NUM_LIST = re.compile(r"(^|\n)\s*\d+\.\s+")
_RE_SIMPLE = re.compile(
    r"^\s*(hi|hello|hey|thanks|thank you|what is|define)\b", re.IGNORECASE
)

_REASONING_PHRASES = (
    "step by step",
    "think through",
    "reason",
    "analyze",
    "compare",
    "evaluate",
    "derive",
    "prove",
    "why",
    "ステップごと",
    "理由",
    "分析",
    "比較",
    "評価",
)

_HIRA_KATA = tuple(range(0x3040, 0x30FF + 1))
_CJK_UNIFIED = tuple(range(0x4E00, 0x9FFF + 1))

_JP_TECH_HINTS = (
    "最適化",
    "設計",
    "実装",
    "検証",
    "原因",
    "改善",
    "分析",
)


_FASTTEXT_MODEL: object | None = None
_FASTTEXT_DISABLED = False


def _is_hira_kata(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return _HIRA_KATA[0] <= code <= _HIRA_KATA[-1]


def _is_cjk_unified(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return _CJK_UNIFIED[0] <= code <= _CJK_UNIFIED[-1]


def _estimate_tokens(text: str) -> int:
    if not text.strip():
        return 0
    words = len(text.split())
    chars = len(text)
    # Cheap blended estimate: avoids undercounting CJK-heavy text.
    return max(int(words * 1.3), int(chars / 3.8), 1)


@dataclass(frozen=True, slots=True)
class RoutingSignals:
    language_code: str
    language_confidence: float
    cjk_ratio: float
    complexity_score: float
    complexity_tier: str
    token_estimate: int
    context_tier: str
    reasoning_markers: int
    has_code: bool
    has_multi_step: bool
    relation_to_previous: str | None
    relation_confidence: float | None
    actionability: str | None
    actionability_confidence: float | None
    retention: str | None
    retention_confidence: float | None
    ingress_urgency_label: str | None
    ingress_urgency_confidence: float | None
    tiny_router_overall_confidence: float | None
    tiny_router_source: str | None


def detect_language_profile(text: str) -> tuple[str, float, float]:
    """Return (language_code, confidence, cjk_ratio) using local heuristics."""
    if not text:
        return ("en", 0.5, 0.0)

    total = max(len(text), 1)
    cjk_count = sum(1 for ch in text if _is_cjk_unified(ch))
    hira_kata_count = sum(1 for ch in text if _is_hira_kata(ch))
    cjk_ratio = cjk_count / total
    hk_ratio = hira_kata_count / total

    # Optional FastText path for stronger multilingual detection.
    fasttext_pred = _predict_fasttext_language(text)
    if fasttext_pred is not None:
        code, confidence = fasttext_pred
        if code == "ja":
            return ("ja", max(confidence, 0.70), cjk_ratio + hk_ratio)
        if code == "cjk":
            return ("cjk", max(confidence, 0.65), cjk_ratio + hk_ratio)
        if code == "en" and (cjk_ratio + hk_ratio) > 0.03:
            return ("en_ja_mixed", min(confidence, 0.80), cjk_ratio + hk_ratio)
        if code == "en":
            return ("en", max(confidence, 0.75), cjk_ratio + hk_ratio)

    lowered = text.lower()
    has_jp_terms = any(term in text for term in _JP_TECH_HINTS)

    if hk_ratio > 0.02 or has_jp_terms:
        confidence = min(0.99, 0.70 + hk_ratio * 4.0)
        return ("ja", confidence, cjk_ratio + hk_ratio)

    if cjk_ratio > 0.12:
        # CJK-heavy but not clearly Japanese.
        return ("cjk", min(0.90, 0.60 + cjk_ratio), cjk_ratio)

    if cjk_ratio > 0.03 and re.search(r"[a-zA-Z]", lowered):
        return ("en_ja_mixed", 0.72, cjk_ratio)

    return ("en", 0.88, cjk_ratio)


def _fasttext_model_path() -> Path:
    configured = os.environ.get("DGC_FASTTEXT_MODEL_PATH", "").strip()
    if configured:
        return Path(configured)
    return Path.home() / ".dharma" / "models" / "lid.176.bin"


def _predict_fasttext_language(text: str) -> tuple[str, float] | None:
    """Optional FastText language prediction.

    Returns None when FastText is unavailable/unconfigured so heuristics continue.
    """
    global _FASTTEXT_MODEL, _FASTTEXT_DISABLED
    if _FASTTEXT_DISABLED:
        return None
    model_path = _fasttext_model_path()
    if not model_path.exists():
        _FASTTEXT_DISABLED = True
        return None
    if _FASTTEXT_MODEL is None:
        try:
            import fasttext  # type: ignore

            _FASTTEXT_MODEL = fasttext.load_model(str(model_path))
        except Exception:
            _FASTTEXT_DISABLED = True
            return None
    if _FASTTEXT_MODEL is None:
        return None
    try:
        labels, probs = _FASTTEXT_MODEL.predict(text.replace("\n", " "), k=1)  # type: ignore[attr-defined]
        if not labels or not probs:
            return None
        label = str(labels[0]).replace("__label__", "").lower()
        confidence = float(probs[0])
    except Exception:
        # fasttext-wheel + NumPy 2 can fail in _FastText.predict() due array-copy semantics.
        # Fall back to the underlying pybind method which returns raw tuples.
        try:
            raw = _FASTTEXT_MODEL.f.predict(  # type: ignore[attr-defined]
                text.replace("\n", " "),
                1,
                0.0,
                "",
            )
            if not raw:
                return None
            confidence, label_raw = raw[0]
            label = str(label_raw).replace("__label__", "").lower()
            confidence = float(confidence)
        except Exception:
            return None
    if label == "ja":
        return ("ja", confidence)
    if label in {"zh", "ko"}:
        return ("cjk", confidence)
    if label == "en":
        return ("en", confidence)
    return None


def classify_complexity(text: str) -> tuple[float, str, int, bool, bool]:
    """Score request complexity in [0,1] and map to tier."""
    lowered = text.lower()
    token_est = _estimate_tokens(text)
    score = 0.0

    if token_est > 400:
        score += 0.25
    elif token_est < 15:
        score -= 0.15

    has_code = bool(_RE_CODE.search(text))
    if has_code:
        score += 0.15

    reasoning_count = sum(1 for marker in _REASONING_PHRASES if marker in lowered)
    if reasoning_count > 0:
        score += 0.20 * min(reasoning_count, 2)

    has_multi_step = bool(_RE_NUM_LIST.search(text)) or (" then " in lowered)
    if has_multi_step:
        score += 0.15

    if lowered.count("?") >= 2:
        score += 0.10

    if _RE_SIMPLE.search(text):
        score -= 0.20

    score = max(0.0, min(1.0, score))
    if reasoning_count >= 2:
        tier = "REASONING"
        score = max(score, 0.61)
    elif score < 0.15:
        tier = "SIMPLE"
    elif score < 0.35:
        tier = "MEDIUM"
    elif score < 0.60:
        tier = "COMPLEX"
    else:
        tier = "REASONING"
    return (score, tier, reasoning_count, has_code, has_multi_step)


def classify_context_tier(token_estimate: int) -> str:
    if token_estimate > 160000:
        return "VERY_LONG"
    if token_estimate > 60000:
        return "LONG"
    if token_estimate > 8000:
        return "MEDIUM_LONG"
    return "SHORT"


def build_routing_signals(request: LLMRequest) -> RoutingSignals:
    chunks: list[str] = []
    if request.system:
        chunks.append(request.system)
    chunks.extend(
        msg.get("content", "")
        for msg in request.messages
        if msg.get("role") in {"user", "assistant"}
    )
    text = "\n".join(chunks)

    language_code, lang_confidence, cjk_ratio = detect_language_profile(text)
    score, tier, reasoning_markers, has_code, has_multi_step = classify_complexity(text)
    token_est = _estimate_tokens(text)
    context_tier = classify_context_tier(token_est)
    transition = infer_tiny_router_shadow_from_messages(request.messages)
    return RoutingSignals(
        language_code=language_code,
        language_confidence=lang_confidence,
        cjk_ratio=cjk_ratio,
        complexity_score=score,
        complexity_tier=tier,
        token_estimate=token_est,
        context_tier=context_tier,
        reasoning_markers=reasoning_markers,
        has_code=has_code,
        has_multi_step=has_multi_step,
        relation_to_previous=(
            transition.relation_to_previous.label if transition is not None else None
        ),
        relation_confidence=(
            transition.relation_to_previous.confidence if transition is not None else None
        ),
        actionability=transition.actionability.label if transition is not None else None,
        actionability_confidence=(
            transition.actionability.confidence if transition is not None else None
        ),
        retention=transition.retention.label if transition is not None else None,
        retention_confidence=(
            transition.retention.confidence if transition is not None else None
        ),
        ingress_urgency_label=transition.urgency.label if transition is not None else None,
        ingress_urgency_confidence=(
            transition.urgency.confidence if transition is not None else None
        ),
        tiny_router_overall_confidence=(
            transition.overall_confidence if transition is not None else None
        ),
        tiny_router_source=transition.source if transition is not None else None,
    )


def enrich_route_request(
    route_request: ProviderRouteRequest,
    request: LLMRequest,
) -> ProviderRouteRequest:
    """Inject local routing signals into ProviderRouteRequest context."""
    signals = build_routing_signals(request)
    ctx = dict(route_request.context)
    ctx.update(
        {
            "language_code": signals.language_code,
            "language_confidence": round(signals.language_confidence, 4),
            "cjk_ratio": round(signals.cjk_ratio, 4),
            "complexity_score": round(signals.complexity_score, 4),
            "complexity_tier": signals.complexity_tier,
            "token_estimate": signals.token_estimate,
            "context_tier": signals.context_tier,
            "reasoning_markers": signals.reasoning_markers,
            "has_code": signals.has_code,
            "has_multi_step": signals.has_multi_step,
            # Explicit policy hints consumed by provider_policy.
            "prefer_japanese_quality": signals.language_code in {"ja", "en_ja_mixed"},
            "relation_to_previous": signals.relation_to_previous,
            "actionability": signals.actionability,
            "retention": signals.retention,
            "ingress_urgency_label": signals.ingress_urgency_label,
            "tiny_router_source": signals.tiny_router_source,
            "tiny_router_overall_confidence": signals.tiny_router_overall_confidence,
            "tiny_router_shadow": bool(signals.tiny_router_source),
            "updates_existing_thread": signals.relation_to_previous in {
                "follow_up",
                "correction",
                "confirmation",
                "cancellation",
                "closure",
            },
        }
    )
    if signals.relation_confidence is not None:
        ctx["relation_confidence"] = round(signals.relation_confidence, 4)
    if signals.actionability_confidence is not None:
        ctx["actionability_confidence"] = round(signals.actionability_confidence, 4)
    if signals.retention_confidence is not None:
        ctx["retention_confidence"] = round(signals.retention_confidence, 4)
    if signals.ingress_urgency_confidence is not None:
        ctx["ingress_urgency_confidence"] = round(signals.ingress_urgency_confidence, 4)

    prefer_low_cost = route_request.preferred_low_cost
    requires_frontier = route_request.requires_frontier_precision
    estimated_tokens = max(route_request.estimated_tokens, signals.token_estimate)

    # Promote quality-first routing for Japanese and high-complexity tasks.
    if signals.language_code in {"ja", "en_ja_mixed", "cjk"}:
        prefer_low_cost = False
    if signals.complexity_tier in {"COMPLEX", "REASONING"}:
        prefer_low_cost = False
    if signals.complexity_tier == "REASONING":
        requires_frontier = True
    if signals.context_tier in {"LONG", "VERY_LONG"}:
        # Long-context workloads degrade sharply on smaller models.
        prefer_low_cost = False
        requires_frontier = True

    return replace(
        route_request,
        preferred_low_cost=prefer_low_cost,
        requires_frontier_precision=requires_frontier,
        estimated_tokens=estimated_tokens,
        context=ctx,
    )


def model_hint_for_provider(
    provider: ProviderType,
    *,
    default_hint: str | None,
    signals: RoutingSignals,
) -> str | None:
    """Return provider-specific model hint with language/complexity overrides."""
    nim_base_url = os.environ.get("NVIDIA_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1").rstrip("/")
    nim_self_hosted = nim_base_url != "https://integrate.api.nvidia.com/v1"
    ollama_cloud = ollama_prefers_cloud()
    effective_default_hint = default_hint

    if provider == ProviderType.OLLAMA:
        if ollama_cloud and default_hint in {None, "", OLLAMA_DEFAULT_LOCAL_MODEL}:
            effective_default_hint = OLLAMA_DEFAULT_CLOUD_MODEL
        elif not ollama_cloud and default_hint and default_hint.endswith(":cloud"):
            effective_default_hint = OLLAMA_DEFAULT_LOCAL_MODEL

    if signals.context_tier in {"LONG", "VERY_LONG"}:
        if provider == ProviderType.OPENAI:
            return "gpt-4.1"
        if provider == ProviderType.ANTHROPIC:
            return "claude-sonnet-4-6"
        if provider == ProviderType.OPENROUTER:
            return "moonshotai/kimi-k2.5"
        if provider == ProviderType.NVIDIA_NIM and nim_self_hosted:
            return "moonshotai/kimi-k2.5"
        if provider == ProviderType.OLLAMA and ollama_cloud:
            return "kimi-k2.5:cloud"
        if provider == ProviderType.GOOGLE_AI:
            return "gemini-2.5-flash"

    if signals.language_code in {"ja", "en_ja_mixed"}:
        if provider == ProviderType.OPENROUTER:
            return "moonshotai/kimi-k2.5"
        if provider == ProviderType.ANTHROPIC:
            return "claude-sonnet-4-6"
        if provider == ProviderType.NVIDIA_NIM and nim_self_hosted:
            return "moonshotai/kimi-k2.5"
        if provider == ProviderType.OLLAMA and ollama_cloud:
            return "kimi-k2.5:cloud"

    if signals.complexity_tier == "REASONING":
        if provider == ProviderType.ANTHROPIC:
            return "claude-opus-4-6"
        if provider == ProviderType.OPENAI:
            return "gpt-5"
        if provider == ProviderType.OPENROUTER:
            return "z-ai/glm-5"
        if provider == ProviderType.NVIDIA_NIM:
            if nim_self_hosted:
                return "zai-org/GLM-5"
            return "nvidia/llama-3.1-nemotron-ultra-253b-v1"
        if provider == ProviderType.OLLAMA and ollama_cloud:
            return "glm-5:cloud"
        if provider == ProviderType.GROQ:
            return "llama-3.3-70b-versatile"
        if provider == ProviderType.CEREBRAS:
            return "llama-3.3-70b"
        if provider == ProviderType.SILICONFLOW:
            return "Qwen/Qwen3-Coder-480B-A35B-Instruct"
        if provider == ProviderType.GOOGLE_AI:
            return "gemini-2.5-flash"

    return effective_default_hint
