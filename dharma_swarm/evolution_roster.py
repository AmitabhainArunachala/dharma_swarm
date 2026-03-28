"""Evolution Model Roster — multi-provider, multi-tier model selection.

Instead of always using a single OpenRouter model, the Darwin Engine now
draws from a diverse roster of models across providers.  Selection is
strategy-aware:

* **exploit** — frontier models for polishing winning solutions
* **explore** — diverse mid-tier models for creative proposals
* **restart** — cheap/fast models to rapidly escape local optima
* **backtrack** — strong models for careful analysis of regressions

The roster degrades gracefully: if a provider is unavailable (no API key,
Ollama not running, etc.) those slots are simply skipped.
"""

from __future__ import annotations

import logging
import os
import random
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

from dharma_swarm.api_keys import PROVIDER_API_KEY_ENV_KEYS
from dharma_swarm.models import ProviderType
from dharma_swarm.ollama_config import (
    build_ollama_headers,
    ollama_transport_mode,
    resolve_ollama_base_url,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model slot
# ---------------------------------------------------------------------------


class ModelTier(str, Enum):
    """Cost / capability tier for a model slot."""

    FRONTIER = "frontier"  # Opus, GPT-4o, o3 — expensive, best quality
    STRONG = "strong"      # DeepSeek V3, Qwen 72B, Llama 70B — good balance
    FAST = "fast"          # Groq-hosted, NIM-hosted — speed optimised
    FREE = "free"          # OpenRouter free tier — zero cost
    LOCAL = "local"        # Ollama — zero cost, variable speed


@dataclass(frozen=True)
class ModelSlot:
    """A single model available for evolution proposals."""

    provider: ProviderType
    model_id: str
    display_name: str
    tier: ModelTier
    strengths: tuple[str, ...] = ()  # e.g. ("code", "reasoning", "speed")
    max_context: int = 128_000
    notes: str = ""


# ---------------------------------------------------------------------------
# The Roster
# ---------------------------------------------------------------------------

EVOLUTION_ROSTER: tuple[ModelSlot, ...] = (
    # ── Frontier tier ──────────────────────────────────────────────────
    # Direct providers (used when ANTHROPIC_API_KEY / OPENAI_API_KEY are set)
    ModelSlot(
        ProviderType.ANTHROPIC,
        "claude-opus-4-20250514",
        "Claude Opus 4 (direct)",
        ModelTier.FRONTIER,
        ("reasoning", "code", "architecture"),
        200_000,
        "Best for structural / architectural proposals",
    ),
    ModelSlot(
        ProviderType.ANTHROPIC,
        "claude-sonnet-4-20250514",
        "Claude Sonnet 4 (direct)",
        ModelTier.FRONTIER,
        ("code", "reasoning", "speed"),
        200_000,
        "Fast frontier — great code quality at lower cost than Opus",
    ),
    ModelSlot(
        ProviderType.OPENAI,
        "gpt-4o",
        "GPT-4o (direct)",
        ModelTier.FRONTIER,
        ("code", "reasoning"),
        128_000,
    ),
    # Same frontier models via OpenRouter (when direct keys aren't set)
    ModelSlot(
        ProviderType.OPENROUTER,
        "anthropic/claude-opus-4",
        "Claude Opus 4",
        ModelTier.FRONTIER,
        ("reasoning", "code", "architecture"),
        200_000,
        "Opus via OpenRouter — main powerhouse model",
    ),
    ModelSlot(
        ProviderType.OPENROUTER,
        "anthropic/claude-sonnet-4",
        "Claude Sonnet 4",
        ModelTier.FRONTIER,
        ("code", "reasoning", "speed"),
        200_000,
        "Fast frontier via OpenRouter",
    ),
    ModelSlot(
        ProviderType.OPENROUTER,
        "openai/gpt-4o",
        "GPT-4o",
        ModelTier.FRONTIER,
        ("code", "reasoning"),
        128_000,
    ),
    ModelSlot(
        ProviderType.OPENROUTER,
        "openai/gpt-5-codex",
        "GPT-5 Codex",
        ModelTier.FRONTIER,
        ("code", "reasoning", "architecture"),
        200_000,
        "High-agency coding and technical synthesis via OpenRouter",
    ),
    # ── Strong tier (via OpenRouter) ───────────────────────────────────
    ModelSlot(
        ProviderType.OPENROUTER,
        "moonshotai/kimi-k2.5",
        "Kimi K2.5",
        ModelTier.STRONG,
        ("reasoning", "long_context", "synthesis"),
        128_000,
        "Strong semantic synthesis and long-context reasoning",
    ),
    ModelSlot(
        ProviderType.OPENROUTER,
        "z-ai/glm-5",
        "GLM 5",
        ModelTier.STRONG,
        ("reasoning", "synthesis", "multilingual"),
        128_000,
        "Reasoning-heavy research model with good multilingual depth",
    ),
    ModelSlot(
        ProviderType.OPENROUTER,
        "deepseek/deepseek-chat-v3-0324",
        "DeepSeek V3",
        ModelTier.STRONG,
        ("code", "reasoning", "chinese"),
        128_000,
        "Cutting-edge open model — rivals frontier at 10x lower cost",
    ),
    ModelSlot(
        ProviderType.OPENROUTER,
        "qwen/qwen-2.5-coder-32b-instruct",
        "Qwen 2.5 Coder 32B",
        ModelTier.STRONG,
        ("code",),
        32_768,
        "Specialist code model from Alibaba — not 70B, punches above weight",
    ),
    ModelSlot(
        ProviderType.OPENROUTER,
        "qwen/qwen3-235b-a22b",
        "Qwen 3 235B (MoE)",
        ModelTier.STRONG,
        ("reasoning", "code", "chinese"),
        128_000,
        "Massive MoE — deep reasoning with efficient inference",
    ),
    ModelSlot(
        ProviderType.OPENROUTER,
        "mistralai/mistral-large-2411",
        "Mistral Large",
        ModelTier.STRONG,
        ("code", "reasoning"),
        128_000,
    ),
    ModelSlot(
        ProviderType.OPENROUTER,
        "meta-llama/llama-3.3-70b-instruct",
        "Llama 3.3 70B",
        ModelTier.STRONG,
        ("code", "reasoning"),
        128_000,
        "Workhorse open model — current default",
    ),
    # ── Fast tier (dedicated inference) ────────────────────────────────
    ModelSlot(
        ProviderType.NVIDIA_NIM,
        "meta/llama-3.3-70b-instruct",
        "Llama 3.3 70B (NIM)",
        ModelTier.FAST,
        ("code", "speed"),
        128_000,
        "NVIDIA-optimised inference — same model, faster",
    ),
    ModelSlot(
        ProviderType.NVIDIA_NIM,
        "nvidia/llama-3.1-nemotron-ultra-253b-v1",
        "Nemotron Ultra 253B (NIM)",
        ModelTier.STRONG,
        ("reasoning", "synthesis", "architecture"),
        128_000,
        "Large NIM-hosted reasoning lane for high-stakes synthesis",
    ),
    ModelSlot(
        ProviderType.OPENROUTER,
        "deepseek/deepseek-r1",
        "DeepSeek R1",
        ModelTier.STRONG,
        ("reasoning", "code"),
        64_000,
        "Deep reasoning model — excellent for complex refactors",
    ),
    ModelSlot(
        ProviderType.OLLAMA,
        "kimi-k2.5:cloud",
        "Kimi K2.5 (Ollama Cloud)",
        ModelTier.STRONG,
        ("reasoning", "long_context", "synthesis"),
        128_000,
        "Cloud-hosted long-context semantic lane via Ollama",
    ),
    ModelSlot(
        ProviderType.OLLAMA,
        "glm-5:cloud",
        "GLM 5 (Ollama Cloud)",
        ModelTier.STRONG,
        ("reasoning", "synthesis", "multilingual"),
        128_000,
        "Cloud-hosted reasoning lane via Ollama",
    ),
    # ── Free tier (OpenRouter free) ────────────────────────────────────
    ModelSlot(
        ProviderType.OPENROUTER_FREE,
        "meta-llama/llama-3.3-70b-instruct:free",
        "Llama 3.3 70B (free)",
        ModelTier.FREE,
        ("code",),
        128_000,
        "Zero cost — good for restart/exploration spam",
    ),
    ModelSlot(
        ProviderType.OPENROUTER_FREE,
        "google/gemma-3-27b-it:free",
        "Gemma 3 27B (free)",
        ModelTier.FREE,
        ("speed",),
        8_192,
    ),
    ModelSlot(
        ProviderType.OPENROUTER_FREE,
        "mistralai/mistral-small-3.1-24b-instruct:free",
        "Mistral Small 3.1 (free)",
        ModelTier.FREE,
        ("code", "speed"),
        32_768,
    ),
    # ── Local tier (Ollama) ────────────────────────────────────────────
    ModelSlot(
        ProviderType.OLLAMA,
        "qwen2.5-coder:14b",
        "Qwen 2.5 Coder 14B (local)",
        ModelTier.LOCAL,
        ("code", "speed"),
        32_768,
        "Local — zero cost, no network latency",
    ),
    ModelSlot(
        ProviderType.OLLAMA,
        "deepseek-coder-v2:16b",
        "DeepSeek Coder V2 16B (local)",
        ModelTier.LOCAL,
        ("code",),
        16_384,
    ),
    ModelSlot(
        ProviderType.OLLAMA,
        "llama3.2",
        "Llama 3.2 (local)",
        ModelTier.LOCAL,
        ("speed",),
        128_000,
    ),
)


# ---------------------------------------------------------------------------
# Provider availability checking
# ---------------------------------------------------------------------------

_ENV_KEYS_FOR_PROVIDER: dict[ProviderType, str] = {
    provider: PROVIDER_API_KEY_ENV_KEYS[provider.value]
    for provider in (
        ProviderType.ANTHROPIC,
        ProviderType.OPENAI,
        ProviderType.OPENROUTER,
        ProviderType.OPENROUTER_FREE,
        ProviderType.NVIDIA_NIM,
        ProviderType.GROQ,
        ProviderType.SILICONFLOW,
        ProviderType.TOGETHER,
        ProviderType.FIREWORKS,
    )
}


def _provider_has_key(provider: ProviderType) -> bool:
    """Check if the env var for a provider is set (non-empty)."""
    env_key = _ENV_KEYS_FOR_PROVIDER.get(provider)
    if env_key is None:
        # Ollama, Claude Code, Codex don't need API keys
        return True
    return bool(os.environ.get(env_key, "").strip())


def _ollama_reachable() -> bool:
    """Quick synchronous check if Ollama is responding."""
    base = resolve_ollama_base_url()
    headers = build_ollama_headers(base_url=base)
    try:
        resp = httpx.get(f"{base.rstrip('/')}/api/tags", headers=headers, timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


_ollama_status: bool | None = None  # cached per process


def _is_ollama_available() -> bool:
    global _ollama_status
    if _ollama_status is None:
        _ollama_status = _ollama_reachable()
        if _ollama_status:
            if ollama_transport_mode() == "cloud_api":
                logger.info("Ollama Cloud detected — cloud models available")
            else:
                logger.info("Ollama detected — local models available")
        else:
            logger.debug("Ollama not reachable — skipping local models")
    return _ollama_status


def reset_ollama_cache() -> None:
    """Force re-check of Ollama availability (e.g. after user starts it)."""
    global _ollama_status
    _ollama_status = None


# ---------------------------------------------------------------------------
# Available roster (filtered by what's actually reachable)
# ---------------------------------------------------------------------------


# Direct providers that should suppress OpenRouter duplicates of the same model.
_DIRECT_PROVIDERS = {ProviderType.ANTHROPIC, ProviderType.OPENAI}


def get_available_roster(
    roster: tuple[ModelSlot, ...] | None = None,
) -> list[ModelSlot]:
    """Filter the roster to models whose provider is currently available.

    When the same model is available both directly (e.g. Anthropic) and
    via OpenRouter, prefer the direct route and skip the OpenRouter
    duplicate.  Models at different tiers (free vs paid) or on different
    infra (NIM vs OpenRouter) are NOT deduped.
    """
    roster = roster or EVOLUTION_ROSTER
    available: list[ModelSlot] = []
    # Track model IDs we've already added via a direct provider
    direct_model_ids: set[str] = set()
    ollama_checked = False
    ollama_ok = False

    for slot in roster:
        if slot.provider == ProviderType.OLLAMA:
            if not ollama_checked:
                ollama_ok = _is_ollama_available()
                ollama_checked = True
            if not ollama_ok:
                continue
        elif not _provider_has_key(slot.provider):
            continue

        # Dedup: skip OpenRouter slots that mirror a direct provider model
        if slot.provider in (ProviderType.OPENROUTER, ProviderType.OPENROUTER_FREE):
            # e.g. "anthropic/claude-opus-4" → "claude-opus-4"
            base_id = slot.model_id.split("/")[-1].removesuffix(":free")
            if base_id in direct_model_ids:
                continue
        elif slot.provider in _DIRECT_PROVIDERS:
            # Normalize: strip date suffix (e.g. -20250514) for cross-provider dedup
            normalized = re.sub(r"-\d{8}$", "", slot.model_id)
            direct_model_ids.add(normalized)

        available.append(slot)

    return available


# ---------------------------------------------------------------------------
# Strategy-aware model selection
# ---------------------------------------------------------------------------


# How many models to select per strategy
_STRATEGY_PROFILES: dict[str, dict[str, Any]] = {
    "exploit": {
        # Polish winners — use the best models
        "tier_weights": {
            ModelTier.FRONTIER: 0.50,
            ModelTier.STRONG: 0.35,
            ModelTier.FAST: 0.10,
            ModelTier.FREE: 0.03,
            ModelTier.LOCAL: 0.02,
        },
        "strength_bonus": "reasoning",
    },
    "explore": {
        # Maximise diversity — spread across tiers and models
        "tier_weights": {
            ModelTier.FRONTIER: 0.15,
            ModelTier.STRONG: 0.35,
            ModelTier.FAST: 0.15,
            ModelTier.FREE: 0.20,
            ModelTier.LOCAL: 0.15,
        },
        "strength_bonus": "code",
    },
    "restart": {
        # Escape local optima — cheap and fast, many attempts
        "tier_weights": {
            ModelTier.FRONTIER: 0.05,
            ModelTier.STRONG: 0.15,
            ModelTier.FAST: 0.25,
            ModelTier.FREE: 0.40,
            ModelTier.LOCAL: 0.15,
        },
        "strength_bonus": "speed",
    },
    "backtrack": {
        # Careful analysis — strong reasoning models
        "tier_weights": {
            ModelTier.FRONTIER: 0.40,
            ModelTier.STRONG: 0.40,
            ModelTier.FAST: 0.10,
            ModelTier.FREE: 0.05,
            ModelTier.LOCAL: 0.05,
        },
        "strength_bonus": "reasoning",
    },
}


def select_models_for_cycle(
    n: int,
    strategy: str = "explore",
    roster: tuple[ModelSlot, ...] | None = None,
    *,
    ensure_diversity: bool = True,
) -> list[ModelSlot]:
    """Select *n* models for an evolution cycle, weighted by strategy.

    Args:
        n: Number of model slots to return (one per source file).
        strategy: The current adaptive strategy from DarwinEngine.
        roster: Override the default roster (for testing).
        ensure_diversity: If True, avoid picking the same model twice
            (when possible).

    Returns:
        A list of *n* ModelSlots, possibly with duplicates if the
        available roster is smaller than *n*.
    """
    available = get_available_roster(roster)
    if not available:
        logger.warning("No models available in roster — falling back to OpenRouter default")
        return [
            ModelSlot(
                ProviderType.OPENROUTER,
                "meta-llama/llama-3.3-70b-instruct",
                "Llama 3.3 70B (fallback)",
                ModelTier.STRONG,
                ("code",),
            )
        ] * n

    profile = _STRATEGY_PROFILES.get(strategy, _STRATEGY_PROFILES["explore"])
    tier_weights: dict[ModelTier, float] = profile["tier_weights"]
    strength_bonus: str = profile["strength_bonus"]

    # Build weighted probability for each available slot
    weights: list[float] = []
    for slot in available:
        w = tier_weights.get(slot.tier, 0.1)
        if strength_bonus in slot.strengths:
            w *= 1.5
        weights.append(w)

    # Normalize
    total = sum(weights)
    if total <= 0:
        weights = [1.0] * len(available)
        total = float(len(available))
    probs = [w / total for w in weights]

    selected: list[ModelSlot] = []
    used_indices: set[int] = set()

    for _ in range(n):
        if ensure_diversity and len(used_indices) < len(available):
            # Zero out already-used slots for this draw
            adj_probs = [
                p if i not in used_indices else 0.0
                for i, p in enumerate(probs)
            ]
            adj_total = sum(adj_probs)
            if adj_total > 0:
                adj_probs = [p / adj_total for p in adj_probs]
            else:
                # All used up — allow repeats
                adj_probs = probs
        else:
            adj_probs = probs

        idx = random.choices(range(len(available)), weights=adj_probs, k=1)[0]
        selected.append(available[idx])
        used_indices.add(idx)

    return selected


def roster_summary(roster: tuple[ModelSlot, ...] | None = None) -> str:
    """Human-readable summary of available models."""
    available = get_available_roster(roster)
    if not available:
        return "No models available"

    lines = ["Available evolution models:"]
    by_tier: dict[ModelTier, list[ModelSlot]] = {}
    for slot in available:
        by_tier.setdefault(slot.tier, []).append(slot)

    for tier in ModelTier:
        slots = by_tier.get(tier, [])
        if not slots:
            continue
        lines.append(f"\n  {tier.value.upper()} ({len(slots)}):")
        for s in slots:
            strengths = ", ".join(s.strengths) if s.strengths else "general"
            lines.append(f"    {s.display_name:<35s} [{strengths}]")

    return "\n".join(lines)
