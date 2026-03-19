"""Canonical model pool for the DHARMA ecosystem.

This module is the single place to ask:
  - which providers are actually wired
  - which model IDs we actively use
  - which routes are currently available
  - which agent is configured to use which model

It replaces the earlier partial catalog with a broader union of:
  - direct runtime defaults
  - TUI/dashboard model catalogs
  - fleet and routing defaults
  - free-tier provider rotations
  - locally discovered OpenClaw model catalogs for mapped providers
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
import os
import re
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any

import httpx

from dharma_swarm.models import ProviderType
from dharma_swarm.ollama_config import build_ollama_headers, resolve_ollama_base_url
from dharma_swarm.models import LLMRequest
from dharma_swarm.runtime_provider import (
    create_runtime_provider,
    resolve_runtime_provider_config,
)

logger = logging.getLogger(__name__)


class ModelTier(str, Enum):
    FRONTIER = "frontier"
    STRONG = "strong"
    FAST = "fast"
    FREE = "free"
    LOCAL = "local"


@dataclass(frozen=True)
class ProviderDef:
    type: ProviderType
    display_name: str
    env_keys: tuple[str, ...] = ()
    keychain_services: tuple[str, ...] = ()
    base_url_env: str = ""
    default_base_url: str = ""
    needs_key: bool = True
    availability_kind: str = "api_key"  # api_key, ollama_http, claude_auth, binary
    command: str = ""


@dataclass(frozen=True)
class ModelDef:
    id: str
    provider: ProviderType
    display_name: str
    tier: ModelTier
    strengths: tuple[str, ...] = ()
    max_context: int = 128_000
    cost_per_mtok: float = 0.0
    notes: str = ""
    power_rank: int = 999
    alt_providers: tuple[ProviderType, ...] = ()
    aliases: tuple[str, ...] = ()
    source: str = "static"

    @property
    def routes(self) -> tuple[ProviderType, ...]:
        return (self.provider, *self.alt_providers)


PROVIDERS: dict[ProviderType, ProviderDef] = {
    ProviderType.ANTHROPIC: ProviderDef(
        type=ProviderType.ANTHROPIC,
        display_name="Anthropic API",
        env_keys=("ANTHROPIC_API_KEY",),
        default_base_url="https://api.anthropic.com",
    ),
    ProviderType.OPENAI: ProviderDef(
        type=ProviderType.OPENAI,
        display_name="OpenAI API",
        env_keys=("OPENAI_API_KEY",),
        keychain_services=("openai-api-key",),
        default_base_url="https://api.openai.com/v1",
    ),
    ProviderType.OPENROUTER: ProviderDef(
        type=ProviderType.OPENROUTER,
        display_name="OpenRouter",
        env_keys=("OPENROUTER_API_KEY",),
        keychain_services=("openrouter-api-key",),
        base_url_env="OPENROUTER_BASE_URL",
        default_base_url="https://openrouter.ai/api/v1",
    ),
    ProviderType.OPENROUTER_FREE: ProviderDef(
        type=ProviderType.OPENROUTER_FREE,
        display_name="OpenRouter Free",
        env_keys=("OPENROUTER_API_KEY",),
        keychain_services=("openrouter-api-key",),
        base_url_env="OPENROUTER_BASE_URL",
        default_base_url="https://openrouter.ai/api/v1",
    ),
    ProviderType.NVIDIA_NIM: ProviderDef(
        type=ProviderType.NVIDIA_NIM,
        display_name="NVIDIA NIM",
        env_keys=("NVIDIA_NIM_API_KEY", "NIM_API_KEY"),
        base_url_env="NVIDIA_NIM_BASE_URL",
        default_base_url="https://integrate.api.nvidia.com/v1",
    ),
    ProviderType.OLLAMA: ProviderDef(
        type=ProviderType.OLLAMA,
        display_name="Ollama",
        env_keys=("OLLAMA_API_KEY",),
        needs_key=False,
        availability_kind="ollama_http",
    ),
    ProviderType.CLAUDE_CODE: ProviderDef(
        type=ProviderType.CLAUDE_CODE,
        display_name="Claude Max / Claude Code",
        needs_key=False,
        availability_kind="claude_auth",
        command="claude",
    ),
    ProviderType.CODEX: ProviderDef(
        type=ProviderType.CODEX,
        display_name="Codex CLI",
        needs_key=False,
        availability_kind="binary",
        command="codex",
    ),
}


MODELS: dict[str, ModelDef] = {}
_ALIASES: dict[str, str] = {}
_availability_cache: dict[ProviderType, tuple[bool, float]] = {}
_CACHE_TTL = 60.0
_OPENCLAW_MODEL_CATALOG = (
    Path.home() / ".openclaw-chat" / "agents" / "main" / "agent" / "models.json"
)
_DHARMA_HOME = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))
_MODEL_PROFILE_PATH = _DHARMA_HOME / "model_pool_profiles.json"
_MODEL_VERIFY_PATH = _DHARMA_HOME / "model_pool_verify.json"
_OPENROUTER_AFFORD_RE = re.compile(r"can only afford (\d+)", re.I)

CURATED_TOP10_MODEL_IDS: tuple[str, ...] = (
    "claude-opus-4-6",
    "gpt-5.4",
    "claude-sonnet-4-6",
    "openai/gpt-5-codex",
    "google/gemini-2.5-pro",
    "z-ai/glm-5",
    "moonshotai/kimi-k2.5",
    "deepseek/deepseek-r1",
    "deepseek-ai/deepseek-v3.2",
    "qwen3-coder:480b-cloud",
)

_MODEL_LINKS: dict[str, dict[str, str]] = {
    "claude-opus-4-6": {
        "docs_url": "https://platform.claude.com/docs/en/about-claude/models/overview",
        "provider_url": "https://claude.ai",
    },
    "claude-sonnet-4-6": {
        "docs_url": "https://platform.claude.com/docs/en/about-claude/models/overview",
        "provider_url": "https://claude.ai",
    },
    "gpt-5.4": {
        "docs_url": "https://platform.openai.com/docs/guides/code-generation",
        "provider_url": "https://platform.openai.com/docs/models",
    },
    "openai/gpt-5-codex": {
        "docs_url": "https://platform.openai.com/docs/guides/code-generation",
        "provider_url": "https://openrouter.ai/models/openai/gpt-5-codex",
    },
    "google/gemini-2.5-pro": {
        "docs_url": "https://ai.google.dev/gemini-api/docs/models",
        "provider_url": "https://openrouter.ai/models/google/gemini-2.5-pro",
    },
    "z-ai/glm-5": {
        "docs_url": "https://docs.z.ai/api-reference/llm/chat-completion",
        "provider_url": "https://openrouter.ai/models/z-ai/glm-5",
    },
    "moonshotai/kimi-k2.5": {
        "docs_url": "https://platform.moonshot.ai/docs/api-reference/chat",
        "provider_url": "https://openrouter.ai/models/moonshotai/kimi-k2.5",
    },
    "deepseek/deepseek-r1": {
        "docs_url": "https://api-docs.deepseek.com/news/news250120",
        "provider_url": "https://openrouter.ai/models/deepseek/deepseek-r1",
    },
    "deepseek-ai/deepseek-v3.2": {
        "docs_url": "https://api-docs.deepseek.com/news/news251201",
        "provider_url": "https://build.nvidia.com/deepseek-ai/deepseek-v3_2",
    },
    "qwen3-coder:480b-cloud": {
        "docs_url": "https://qwenlm.github.io/blog/qwen3-coder/",
        "provider_url": "https://ollama.com",
    },
}


def _norm_model_key(value: str) -> str:
    return value.strip().lower()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _write_json_file(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _profile_overrides() -> dict[str, dict[str, Any]]:
    raw = _read_json_file(_MODEL_PROFILE_PATH)
    data = raw.get("profiles", {})
    return data if isinstance(data, dict) else {}


def _verification_snapshot() -> dict[str, dict[str, Any]]:
    raw = _read_json_file(_MODEL_VERIFY_PATH)
    data = raw.get("models", {})
    return data if isinstance(data, dict) else {}


def _extract_openrouter_affordable_max_tokens(error_text: str) -> int | None:
    match = _OPENROUTER_AFFORD_RE.search(error_text)
    if not match:
        return None
    try:
        affordable = int(match.group(1))
    except ValueError:
        return None
    return affordable if affordable > 0 else None


def _append_provider(
    providers: tuple[ProviderType, ...],
    provider: ProviderType,
) -> tuple[ProviderType, ...]:
    if provider in providers:
        return providers
    return (*providers, provider)


def _register_aliases(model_id: str, aliases: tuple[str, ...]) -> None:
    _ALIASES[_norm_model_key(model_id)] = model_id
    for alias in aliases:
        normalized = _norm_model_key(alias)
        if normalized:
            _ALIASES[normalized] = model_id


def _merge_model_route(
    *,
    model_id: str,
    provider: ProviderType,
    aliases: tuple[str, ...] = (),
) -> None:
    existing = MODELS.get(model_id)
    if existing is None:
        return
    if provider == existing.provider or provider in existing.alt_providers:
        _register_aliases(model_id, (*existing.aliases, *aliases))
        return
    MODELS[model_id] = replace(
        existing,
        alt_providers=_append_provider(existing.alt_providers, provider),
        aliases=tuple(dict.fromkeys((*existing.aliases, *aliases))),
    )
    _register_aliases(model_id, MODELS[model_id].aliases)


def _m(
    model_id: str,
    provider: ProviderType,
    name: str,
    tier: ModelTier,
    strengths: tuple[str, ...] = (),
    ctx: int = 128_000,
    cost: float = 0.0,
    notes: str = "",
    power_rank: int = 999,
    alt_providers: tuple[ProviderType, ...] = (),
    aliases: tuple[str, ...] = (),
    source: str = "static",
) -> None:
    if model_id in MODELS:
        _merge_model_route(model_id=model_id, provider=provider, aliases=aliases)
        return
    MODELS[model_id] = ModelDef(
        id=model_id,
        provider=provider,
        display_name=name,
        tier=tier,
        strengths=strengths,
        max_context=ctx,
        cost_per_mtok=cost,
        notes=notes,
        power_rank=power_rank,
        alt_providers=alt_providers,
        aliases=aliases,
        source=source,
    )
    _register_aliases(model_id, aliases)


def _register_static_models() -> None:
    # Claude Max / Claude Code lane.
    _m(
        "claude-opus-4-6",
        ProviderType.CLAUDE_CODE,
        "Claude Opus 4.6",
        ModelTier.FRONTIER,
        ("reasoning", "code", "architecture"),
        200_000,
        15.0,
        "Primary Claude Max route; also referenced by direct Anthropic runtime defaults.",
        power_rank=1,
        alt_providers=(ProviderType.ANTHROPIC,),
    )
    _m(
        "claude-sonnet-4-6",
        ProviderType.CLAUDE_CODE,
        "Claude Sonnet 4.6",
        ModelTier.FRONTIER,
        ("code", "reasoning", "speed"),
        200_000,
        3.0,
        "Primary Claude Max route; preferred balanced Claude lane.",
        power_rank=2,
        alt_providers=(ProviderType.ANTHROPIC,),
    )
    _m(
        "claude-sonnet-4-5",
        ProviderType.CLAUDE_CODE,
        "Claude Sonnet 4.5",
        ModelTier.FRONTIER,
        ("code", "reasoning", "speed"),
        200_000,
        3.0,
        "TUI default responsive Claude route.",
        power_rank=4,
        alt_providers=(ProviderType.ANTHROPIC,),
    )
    _m(
        "claude-haiku-4-5",
        ProviderType.CLAUDE_CODE,
        "Claude Haiku 4.5",
        ModelTier.FAST,
        ("speed", "cheap"),
        200_000,
        0.8,
        "Fast Claude lane for low-cost / responsive routing.",
        power_rank=10,
        alt_providers=(ProviderType.ANTHROPIC,),
    )
    _m(
        "claude-opus-4",
        ProviderType.CLAUDE_CODE,
        "Claude Opus 4",
        ModelTier.FRONTIER,
        ("reasoning", "code", "architecture"),
        200_000,
        15.0,
        "Older Claude CLI / TUI identifier kept for compatibility.",
        power_rank=6,
        alt_providers=(ProviderType.ANTHROPIC,),
    )

    # Anthropic direct dated IDs.
    _m(
        "claude-opus-4-20250514",
        ProviderType.ANTHROPIC,
        "Claude Opus 4 (2025-05-14)",
        ModelTier.FRONTIER,
        ("reasoning", "code", "architecture"),
        200_000,
        15.0,
        "Direct Anthropic dated model ID used by fleet auto-upgrade.",
        power_rank=3,
        aliases=("claude-opus-4-0",),
    )
    _m(
        "claude-sonnet-4-20250514",
        ProviderType.ANTHROPIC,
        "Claude Sonnet 4 (2025-05-14)",
        ModelTier.FRONTIER,
        ("code", "reasoning", "speed"),
        200_000,
        3.0,
        "Direct Anthropic dated model ID used by legacy runtime defaults.",
        power_rank=5,
        aliases=("claude-sonnet-4-0",),
    )
    _m(
        "claude-haiku-4-20250514",
        ProviderType.ANTHROPIC,
        "Claude Haiku 4 (2025-05-14)",
        ModelTier.FAST,
        ("speed", "cheap"),
        200_000,
        0.8,
        "Direct Anthropic dated Haiku lane.",
        power_rank=11,
    )
    _m(
        "claude-haiku-4-5-20251001",
        ProviderType.ANTHROPIC,
        "Claude Haiku 4.5 (2025-10-01)",
        ModelTier.FAST,
        ("speed", "cheap"),
        200_000,
        0.8,
        "Model-manager Anthropic Haiku 4.5 identifier.",
        power_rank=9,
    )

    # OpenAI / Codex lane.
    _m(
        "gpt-5.4",
        ProviderType.OPENAI,
        "GPT-5.4",
        ModelTier.FRONTIER,
        ("reasoning", "code", "architecture"),
        200_000,
        10.0,
        "Direct OpenAI Pro route; also used by local Codex CLI.",
        power_rank=7,
        alt_providers=(ProviderType.CODEX,),
        aliases=("codex-5.4", "codex 5.4"),
    )
    _m(
        "gpt-5",
        ProviderType.OPENAI,
        "GPT-5",
        ModelTier.FRONTIER,
        ("reasoning", "code"),
        200_000,
        10.0,
        "Router/provider-policy hint model.",
    )
    _m(
        "gpt-4.1",
        ProviderType.OPENAI,
        "GPT-4.1",
        ModelTier.STRONG,
        ("code", "reasoning"),
        128_000,
        5.0,
        "Router/provider-policy hint model.",
    )
    _m(
        "gpt-4o",
        ProviderType.OPENAI,
        "GPT-4o",
        ModelTier.STRONG,
        ("code", "reasoning", "vision"),
        128_000,
        2.5,
        "Direct OpenAI route used across chat, fleet, and provider policy.",
        power_rank=12,
    )
    _m(
        "gpt-4o-mini",
        ProviderType.OPENAI,
        "GPT-4o Mini",
        ModelTier.FAST,
        ("speed", "vision"),
        128_000,
        0.15,
        "OpenAI mini model discovered from local operator catalog.",
    )
    _m(
        "o1",
        ProviderType.OPENAI,
        "o1",
        ModelTier.FRONTIER,
        ("reasoning",),
        128_000,
        15.0,
        "Legacy reasoning model kept because model_manager still exposes it.",
    )
    _m(
        "o1-mini",
        ProviderType.OPENAI,
        "o1 Mini",
        ModelTier.STRONG,
        ("reasoning", "speed"),
        128_000,
        3.0,
        "Legacy model-manager reasoning lane.",
    )
    _m(
        "o3-mini",
        ProviderType.OPENAI,
        "o3 Mini",
        ModelTier.STRONG,
        ("reasoning", "speed"),
        200_000,
        1.1,
        "Local operator catalog reasoning model.",
    )

    # OpenRouter frontier / premium.
    _m(
        "openai/gpt-5-codex",
        ProviderType.OPENROUTER,
        "GPT-5 Codex (OpenRouter)",
        ModelTier.FRONTIER,
        ("code", "reasoning", "architecture"),
        200_000,
        10.0,
        "High-agency coding route via OpenRouter.",
        power_rank=8,
    )
    _m(
        "openai/gpt-4o",
        ProviderType.OPENROUTER,
        "GPT-4o (OpenRouter)",
        ModelTier.STRONG,
        ("code", "reasoning", "vision"),
        128_000,
        2.5,
        power_rank=13,
    )
    _m(
        "openai/gpt-4o-mini",
        ProviderType.OPENROUTER,
        "GPT-4o Mini (OpenRouter)",
        ModelTier.FAST,
        ("speed", "vision"),
        128_000,
        0.15,
    )
    _m(
        "anthropic/claude-opus-4",
        ProviderType.OPENROUTER,
        "Claude Opus 4 (OpenRouter)",
        ModelTier.FRONTIER,
        ("reasoning", "code", "architecture"),
        200_000,
        15.0,
        "OpenRouter Anthropic fallback lane.",
    )
    _m(
        "anthropic/claude-opus-4-6",
        ProviderType.OPENROUTER,
        "Claude Opus 4.6 (OpenRouter)",
        ModelTier.FRONTIER,
        ("reasoning", "code", "architecture"),
        200_000,
        15.0,
        "Runtime default for OpenRouter Anthropic lane.",
    )
    _m(
        "anthropic/claude-sonnet-4",
        ProviderType.OPENROUTER,
        "Claude Sonnet 4 (OpenRouter)",
        ModelTier.FRONTIER,
        ("code", "reasoning", "speed"),
        200_000,
        3.0,
    )
    _m(
        "anthropic/claude-sonnet-4-6",
        ProviderType.OPENROUTER,
        "Claude Sonnet 4.6 (OpenRouter)",
        ModelTier.FRONTIER,
        ("code", "reasoning", "speed"),
        200_000,
        3.0,
        "User-requested 4.6 Anthropic OpenRouter route.",
    )
    _m(
        "moonshotai/kimi-k2.5",
        ProviderType.OPENROUTER,
        "Kimi K2.5",
        ModelTier.STRONG,
        ("reasoning", "long_context", "synthesis"),
        262_144,
        0.45,
    )
    _m(
        "deepseek/deepseek-chat-v3-0324",
        ProviderType.OPENROUTER,
        "DeepSeek V3",
        ModelTier.STRONG,
        ("code", "reasoning"),
        128_000,
        0.26,
    )
    _m(
        "deepseek/deepseek-r1",
        ProviderType.OPENROUTER,
        "DeepSeek R1",
        ModelTier.STRONG,
        ("reasoning", "code"),
        64_000,
        0.55,
    )
    _m(
        "z-ai/glm-5",
        ProviderType.OPENROUTER,
        "GLM 5",
        ModelTier.STRONG,
        ("reasoning", "synthesis", "multilingual"),
        128_000,
        0.72,
        aliases=("zai-org/GLM-5",),
    )
    _m(
        "qwen/qwen3-235b-a22b",
        ProviderType.OPENROUTER,
        "Qwen 3 235B",
        ModelTier.STRONG,
        ("reasoning", "code"),
        128_000,
        0.50,
    )
    _m(
        "qwen/qwen-2.5-coder-32b-instruct",
        ProviderType.OPENROUTER,
        "Qwen 2.5 Coder 32B",
        ModelTier.STRONG,
        ("code",),
        32_768,
        0.20,
        aliases=("qwen/qwen2.5-coder-32b-instruct",),
    )
    _m(
        "qwen/qwen-2.5-72b-instruct",
        ProviderType.OPENROUTER,
        "Qwen 2.5 72B",
        ModelTier.STRONG,
        ("reasoning", "code"),
        128_000,
        0.0,
    )
    _m(
        "mistralai/mistral-large-2411",
        ProviderType.OPENROUTER,
        "Mistral Large",
        ModelTier.STRONG,
        ("code", "reasoning"),
        128_000,
        2.0,
    )
    _m(
        "mistralai/mistral-small-3.1-24b-instruct",
        ProviderType.OPENROUTER,
        "Mistral Small 3.1",
        ModelTier.STRONG,
        ("speed", "code"),
        32_768,
        0.0,
    )
    _m(
        "meta-llama/llama-3.3-70b-instruct",
        ProviderType.OPENROUTER,
        "Llama 3.3 70B",
        ModelTier.STRONG,
        ("code", "reasoning"),
        128_000,
        0.40,
    )
    _m(
        "google/gemini-2.5-pro",
        ProviderType.OPENROUTER,
        "Gemini 2.5 Pro",
        ModelTier.FRONTIER,
        ("reasoning", "long_context", "vision"),
        1_000_000,
        0.0,
        "TUI openrouter adapter exposes this explicitly.",
    )
    _m(
        "google/gemini-2.0-flash-001",
        ProviderType.OPENROUTER,
        "Gemini 2.0 Flash",
        ModelTier.STRONG,
        ("speed", "vision"),
        128_000,
        0.0,
    )
    _m(
        "x-ai/grok-3-mini-beta",
        ProviderType.OPENROUTER,
        "Grok 3 Mini",
        ModelTier.STRONG,
        ("reasoning", "speed"),
        128_000,
        0.0,
    )
    _m(
        "cohere/command-r-plus-08-2024",
        ProviderType.OPENROUTER,
        "Command R+",
        ModelTier.STRONG,
        ("long_context", "reasoning"),
        128_000,
        0.0,
    )
    _m(
        "amazon/nova-pro-v1",
        ProviderType.OPENROUTER,
        "Amazon Nova Pro",
        ModelTier.STRONG,
        ("reasoning", "multimodal"),
        300_000,
        0.0,
    )
    _m(
        "nvidia/llama-3.1-nemotron-70b-instruct",
        ProviderType.OPENROUTER,
        "Nemotron 70B",
        ModelTier.STRONG,
        ("reasoning", "code"),
        128_000,
        0.0,
    )

    # OpenRouter free / zero-cost lanes.
    _m(
        "meta-llama/llama-3.3-70b-instruct:free",
        ProviderType.OPENROUTER_FREE,
        "Llama 3.3 70B (free)",
        ModelTier.FREE,
        ("code", "reasoning"),
        128_000,
        0.0,
    )
    _m(
        "google/gemma-3-27b-it:free",
        ProviderType.OPENROUTER_FREE,
        "Gemma 3 27B (free)",
        ModelTier.FREE,
        ("speed",),
        8_192,
        0.0,
    )
    _m(
        "mistralai/mistral-small-3.1-24b-instruct:free",
        ProviderType.OPENROUTER_FREE,
        "Mistral Small 3.1 (free)",
        ModelTier.FREE,
        ("speed", "code"),
        32_768,
        0.0,
    )
    _m(
        "deepseek/deepseek-r1:free",
        ProviderType.OPENROUTER_FREE,
        "DeepSeek R1 (free)",
        ModelTier.FREE,
        ("reasoning", "code"),
        128_000,
        0.0,
    )
    _m(
        "qwen/qwen3-235b-a22b:free",
        ProviderType.OPENROUTER_FREE,
        "Qwen 3 235B (free)",
        ModelTier.FREE,
        ("reasoning", "code"),
        128_000,
        0.0,
    )
    _m(
        "google/gemini-2.5-flash-preview:free",
        ProviderType.OPENROUTER_FREE,
        "Gemini 2.5 Flash Preview (free)",
        ModelTier.FREE,
        ("speed", "vision"),
        128_000,
        0.0,
    )
    _m(
        "google/gemini-2.0-flash-exp:free",
        ProviderType.OPENROUTER_FREE,
        "Gemini 2.0 Flash Exp (free)",
        ModelTier.FREE,
        ("speed", "vision"),
        128_000,
        0.0,
    )
    _m(
        "microsoft/phi-4-reasoning:free",
        ProviderType.OPENROUTER_FREE,
        "Phi-4 Reasoning (free)",
        ModelTier.FREE,
        ("reasoning", "speed"),
        128_000,
        0.0,
    )
    _m(
        "microsoft/phi-4:free",
        ProviderType.OPENROUTER_FREE,
        "Phi-4 (free)",
        ModelTier.FREE,
        ("speed",),
        128_000,
        0.0,
    )
    _m(
        "qwen/qwen-2.5-72b-instruct:free",
        ProviderType.OPENROUTER_FREE,
        "Qwen 2.5 72B (free)",
        ModelTier.FREE,
        ("reasoning", "code"),
        128_000,
        0.0,
    )
    _m(
        "qwen/qwen3-coder:free",
        ProviderType.OPENROUTER_FREE,
        "Qwen 3 Coder (free)",
        ModelTier.FREE,
        ("code",),
        128_000,
        0.0,
    )
    _m(
        "qwen/qwen3-next-80b-a3b-instruct:free",
        ProviderType.OPENROUTER_FREE,
        "Qwen 3 Next 80B (free)",
        ModelTier.FREE,
        ("reasoning", "speed"),
        128_000,
        0.0,
    )
    _m(
        "z-ai/glm-4.5-air:free",
        ProviderType.OPENROUTER_FREE,
        "GLM 4.5 Air (free)",
        ModelTier.FREE,
        ("speed", "multilingual"),
        128_000,
        0.0,
    )
    _m(
        "nvidia/llama-3.1-nemotron-70b-instruct:free",
        ProviderType.OPENROUTER_FREE,
        "Nemotron 70B (free)",
        ModelTier.FREE,
        ("reasoning", "code"),
        128_000,
        0.0,
    )
    _m(
        "nvidia/nemotron-nano-9b-v2:free",
        ProviderType.OPENROUTER_FREE,
        "Nemotron Nano 9B (free)",
        ModelTier.FREE,
        ("speed",),
        128_000,
        0.0,
    )
    _m(
        "nousresearch/hermes-3-llama-3.1-405b:free",
        ProviderType.OPENROUTER_FREE,
        "Hermes 3 Llama 405B (free)",
        ModelTier.FREE,
        ("reasoning", "long_context"),
        128_000,
        0.0,
    )

    # NVIDIA NIM lanes.
    _m(
        "meta/llama-3.3-70b-instruct",
        ProviderType.NVIDIA_NIM,
        "Llama 3.3 70B (NIM)",
        ModelTier.FAST,
        ("code", "reasoning", "speed"),
        128_000,
        0.0,
    )
    _m(
        "nvidia/llama-3.1-nemotron-ultra-253b-v1",
        ProviderType.NVIDIA_NIM,
        "Nemotron Ultra 253B",
        ModelTier.STRONG,
        ("reasoning", "architecture", "synthesis"),
        128_000,
        0.0,
    )
    _m(
        "nvidia/nemotron-3-super-120b-a12b:free",
        ProviderType.NVIDIA_NIM,
        "Nemotron Super 120B",
        ModelTier.STRONG,
        ("validation", "systems_reasoning"),
        128_000,
        0.0,
    )
    _m(
        "moonshotai/kimi-k2-thinking",
        ProviderType.NVIDIA_NIM,
        "Kimi K2 Thinking",
        ModelTier.STRONG,
        ("reasoning", "long_context"),
        262_144,
        0.0,
    )
    _m(
        "deepseek-ai/deepseek-v3.2",
        ProviderType.NVIDIA_NIM,
        "DeepSeek V3.2",
        ModelTier.STRONG,
        ("code", "reasoning"),
        163_840,
        0.0,
    )
    _m(
        "deepseek-ai/deepseek-v3.1-terminus",
        ProviderType.NVIDIA_NIM,
        "DeepSeek V3.1 Terminus",
        ModelTier.STRONG,
        ("reasoning", "code"),
        163_840,
        0.0,
    )
    _m(
        "deepseek-ai/deepseek-r1",
        ProviderType.NVIDIA_NIM,
        "DeepSeek R1 (NIM)",
        ModelTier.STRONG,
        ("reasoning", "code"),
        262_144,
        0.0,
    )
    _m(
        "qwen/qwen3-next-80b-a3b-instruct",
        ProviderType.NVIDIA_NIM,
        "Qwen3 Next 80B",
        ModelTier.STRONG,
        ("reasoning", "speed"),
        262_144,
        0.0,
    )
    _m(
        "nvidia/llama-3_3-nemotron-super-49b-v1",
        ProviderType.NVIDIA_NIM,
        "Nemotron Super 49B",
        ModelTier.STRONG,
        ("reasoning", "speed"),
        262_144,
        0.0,
    )
    _m(
        "nvidia/nemotron-3-nano-30b-a3b",
        ProviderType.NVIDIA_NIM,
        "Nemotron 3 Nano 30B",
        ModelTier.FAST,
        ("speed", "reasoning"),
        262_144,
        0.0,
    )
    _m(
        "nvidia/nemotron-nano-12b-v2-vl",
        ProviderType.NVIDIA_NIM,
        "Nemotron Nano 12B VL",
        ModelTier.FAST,
        ("vision", "speed"),
        128_000,
        0.0,
    )
    _m(
        "z-ai/glm4_7",
        ProviderType.NVIDIA_NIM,
        "GLM 4.7",
        ModelTier.STRONG,
        ("reasoning", "multilingual"),
        262_144,
        0.0,
    )

    # Ollama cloud / local lanes.
    _m(
        "kimi-k2.5:cloud",
        ProviderType.OLLAMA,
        "Kimi K2.5 (Ollama Cloud)",
        ModelTier.FREE,
        ("reasoning", "long_context", "synthesis"),
        128_000,
        0.0,
    )
    _m(
        "glm-5:cloud",
        ProviderType.OLLAMA,
        "GLM 5 (Ollama Cloud)",
        ModelTier.FREE,
        ("reasoning", "synthesis", "multilingual"),
        128_000,
        0.0,
    )
    _m(
        "minimax-m2.5:cloud",
        ProviderType.OLLAMA,
        "MiniMax M2.5 (Ollama Cloud)",
        ModelTier.FREE,
        ("reasoning", "long_context"),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "nemotron-3-nano:30b-cloud",
        ProviderType.OLLAMA,
        "Nemotron 3 Nano 30B (Ollama Cloud)",
        ModelTier.FREE,
        ("speed", "reasoning"),
        1_000_000,
        0.0,
        source="openclaw",
    )
    _m(
        "glm-4.7:cloud",
        ProviderType.OLLAMA,
        "GLM 4.7 (Ollama Cloud)",
        ModelTier.FREE,
        ("reasoning", "multilingual"),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "glm-4.6:cloud",
        ProviderType.OLLAMA,
        "GLM 4.6 (Ollama Cloud)",
        ModelTier.FREE,
        ("reasoning", "multilingual"),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "deepseek-v3.2:cloud",
        ProviderType.OLLAMA,
        "DeepSeek V3.2 (Ollama Cloud)",
        ModelTier.FREE,
        ("code", "reasoning"),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "mistral-large-3:675b-cloud",
        ProviderType.OLLAMA,
        "Mistral Large 3 675B (Ollama Cloud)",
        ModelTier.FREE,
        ("reasoning", "code"),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "gpt-oss:120b-cloud",
        ProviderType.OLLAMA,
        "GPT-OSS 120B (Ollama Cloud)",
        ModelTier.FREE,
        ("code", "reasoning"),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "deepseek-v3.1:671b-cloud",
        ProviderType.OLLAMA,
        "DeepSeek V3.1 671B (Ollama Cloud)",
        ModelTier.FREE,
        ("code", "reasoning"),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "qwen3-coder:480b-cloud",
        ProviderType.OLLAMA,
        "Qwen3 Coder 480B (Ollama Cloud)",
        ModelTier.FREE,
        ("code",),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "llama3.3:70b",
        ProviderType.OLLAMA,
        "Llama 3.3 70B",
        ModelTier.LOCAL,
        ("code", "reasoning"),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "llama3.1:8b",
        ProviderType.OLLAMA,
        "Llama 3.1 8B",
        ModelTier.LOCAL,
        ("speed",),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "qwen2.5:7b",
        ProviderType.OLLAMA,
        "Qwen 2.5 7B",
        ModelTier.LOCAL,
        ("speed", "code"),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "yi:34b",
        ProviderType.OLLAMA,
        "Yi 34B",
        ModelTier.LOCAL,
        ("reasoning",),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "gemma3:27b",
        ProviderType.OLLAMA,
        "Gemma 3 27B",
        ModelTier.LOCAL,
        ("speed",),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "gemma3:4b",
        ProviderType.OLLAMA,
        "Gemma 3 4B",
        ModelTier.LOCAL,
        ("speed",),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "mistral:latest",
        ProviderType.OLLAMA,
        "Mistral Latest",
        ModelTier.LOCAL,
        ("speed",),
        128_000,
        0.0,
        source="openclaw",
    )
    _m(
        "qwen2.5-coder:14b",
        ProviderType.OLLAMA,
        "Qwen 2.5 Coder 14B",
        ModelTier.LOCAL,
        ("code", "speed"),
        32_768,
        0.0,
    )
    _m(
        "deepseek-coder-v2:16b",
        ProviderType.OLLAMA,
        "DeepSeek Coder V2 16B",
        ModelTier.LOCAL,
        ("code",),
        16_384,
        0.0,
    )
    _m(
        "llama3.2",
        ProviderType.OLLAMA,
        "Llama 3.2",
        ModelTier.LOCAL,
        ("speed",),
        128_000,
        0.0,
    )


def _guess_strengths(model_id: str, display_name: str, reasoning: bool) -> tuple[str, ...]:
    text = f"{model_id} {display_name}".lower()
    strengths: list[str] = []
    if reasoning or any(token in text for token in ("reason", "opus", "sonnet", "r1", "thinking")):
        strengths.append("reasoning")
    if any(token in text for token in ("coder", "codex", "gpt", "code")):
        strengths.append("code")
    if any(token in text for token in ("vision", "vl", "image", "4o", "gemini")):
        strengths.append("vision")
    if any(token in text for token in ("kimi", "glm", "long", "1m")):
        strengths.append("long_context")
    if any(token in text for token in ("mini", "nano", "flash", "haiku", "8b", "4b")):
        strengths.append("speed")
    return tuple(dict.fromkeys(strengths))


def _guess_tier(
    model_id: str,
    provider: ProviderType,
    *,
    cost_input: float,
    context_window: int,
    reasoning: bool,
) -> ModelTier:
    text = model_id.lower()
    if provider == ProviderType.OLLAMA:
        if text.endswith(":cloud") or "cloud" in text:
            return ModelTier.FREE
        return ModelTier.LOCAL
    if provider == ProviderType.OPENROUTER_FREE or text.endswith(":free"):
        return ModelTier.FREE
    if provider == ProviderType.NVIDIA_NIM:
        if "nano" in text:
            return ModelTier.FAST
        return ModelTier.STRONG
    if provider in {ProviderType.CLAUDE_CODE, ProviderType.CODEX}:
        return ModelTier.FRONTIER
    if any(token in text for token in ("opus", "gpt-5", "sonnet-4-6", "gemini-2.5-pro")):
        return ModelTier.FRONTIER
    if cost_input == 0.0 and provider != ProviderType.OPENAI:
        return ModelTier.FREE
    if context_window >= 200_000 or reasoning:
        return ModelTier.STRONG
    return ModelTier.STRONG


def _load_openclaw_catalog() -> None:
    if not _OPENCLAW_MODEL_CATALOG.exists():
        return
    try:
        data = json.loads(_OPENCLAW_MODEL_CATALOG.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("Failed to read OpenClaw model catalog: %s", exc)
        return

    provider_map = {
        "openai": ProviderType.OPENAI,
        "openrouter": ProviderType.OPENROUTER,
        "nvidia-nim": ProviderType.NVIDIA_NIM,
        "ollama": ProviderType.OLLAMA,
        "ollama-nemotron": ProviderType.OLLAMA,
    }

    for provider_label, provider_data in (data.get("providers") or {}).items():
        provider = provider_map.get(provider_label)
        if provider is None:
            continue
        for entry in provider_data.get("models") or []:
            model_id = str(entry.get("id") or "").strip()
            if not model_id:
                continue
            name = str(entry.get("name") or model_id)
            ctx_raw = entry.get("contextWindow") or 128_000
            try:
                context_window = int(ctx_raw)
            except (TypeError, ValueError):
                context_window = 128_000
            cost_input = 0.0
            cost = entry.get("cost") or {}
            try:
                cost_input = float(cost.get("input") or 0.0)
            except (TypeError, ValueError):
                cost_input = 0.0
            reasoning = bool(entry.get("reasoning"))
            if model_id in MODELS:
                _merge_model_route(model_id=model_id, provider=provider)
                continue
            _m(
                model_id,
                provider,
                name,
                _guess_tier(
                    model_id,
                    provider,
                    cost_input=cost_input,
                    context_window=context_window,
                    reasoning=reasoning,
                ),
                _guess_strengths(model_id, name, reasoning),
                context_window,
                cost_input,
                f"Discovered from local OpenClaw catalog provider '{provider_label}'.",
                source="openclaw",
            )


def _lookup_keychain_secret(service: str, *, account: str | None = None) -> str:
    if shutil.which("security") is None:
        return ""
    cmd = ["security", "find-generic-password", "-s", service, "-w"]
    if account:
        cmd[2:2] = ["-a", account]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _provider_has_key(defn: ProviderDef) -> bool:
    for env_key in defn.env_keys:
        if os.environ.get(env_key, "").strip():
            return True
    user = os.environ.get("USER", "").strip() or None
    for service in defn.keychain_services:
        if _lookup_keychain_secret(service, account=user):
            return True
        if user and _lookup_keychain_secret(service):
            return True
    return False


def _claude_logged_in() -> bool:
    if shutil.which("claude") is None:
        return False
    try:
        proc = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return bool(data.get("loggedIn"))


def provider_available(pt: ProviderType) -> bool:
    now = time.monotonic()
    cached = _availability_cache.get(pt)
    if cached and (now - cached[1]) < _CACHE_TTL:
        return cached[0]

    defn = PROVIDERS.get(pt)
    if defn is None:
        return False

    available = False
    if defn.availability_kind == "api_key":
        available = _provider_has_key(defn)
    elif defn.availability_kind == "binary":
        available = bool(defn.command and shutil.which(defn.command))
    elif defn.availability_kind == "claude_auth":
        available = _claude_logged_in()
    elif defn.availability_kind == "ollama_http":
        try:
            base = resolve_ollama_base_url()
            headers = build_ollama_headers(base_url=base)
            resp = httpx.get(
                f"{base.rstrip('/')}/api/tags",
                headers=headers,
                timeout=3.0,
            )
            available = resp.status_code == 200
        except Exception:
            available = False
    else:
        available = False

    _availability_cache[pt] = (available, now)
    return available


def reset_availability_cache() -> None:
    _availability_cache.clear()


def _resolve_model_id(model_id: str) -> str | None:
    if model_id in MODELS:
        return model_id
    return _ALIASES.get(_norm_model_key(model_id))


def _provider_matches(model: ModelDef, provider: ProviderType | None) -> bool:
    if provider is None:
        return True
    return provider in model.routes


def _route_names(model: ModelDef) -> list[str]:
    return [route.value for route in model.routes]


def _link_meta(model_id: str) -> dict[str, str]:
    return _MODEL_LINKS.get(model_id, {})


def model_profile(model_id: str) -> dict[str, Any]:
    resolved = _resolve_model_id(model_id)
    key = resolved or model_id
    model = MODELS.get(key)
    override = _profile_overrides().get(key, {})
    links = _link_meta(key)
    base_display = model.display_name if model is not None else key
    return {
        "model_id": key,
        "display_name": base_display,
        "custom_label": str(override.get("custom_label", "") or ""),
        "short_name": str(override.get("short_name", "") or ""),
        "ui_label": str(override.get("custom_label", "") or base_display),
        "docs_url": links.get("docs_url", ""),
        "provider_url": links.get("provider_url", ""),
        "updated_at": str(override.get("updated_at", "") or ""),
    }


def update_model_profile(
    model_id: str,
    *,
    custom_label: str | None = None,
    short_name: str | None = None,
) -> dict[str, Any]:
    resolved = _resolve_model_id(model_id)
    if resolved is None or resolved not in MODELS:
        raise KeyError(f"Unknown model: {model_id}")

    store = _read_json_file(_MODEL_PROFILE_PATH)
    profiles = store.setdefault("profiles", {})
    current = dict(profiles.get(resolved, {}))

    if custom_label is not None:
        label = custom_label.strip()
        if label:
            current["custom_label"] = label
        else:
            current.pop("custom_label", None)
    if short_name is not None:
        short = short_name.strip()
        if short:
            current["short_name"] = short
        else:
            current.pop("short_name", None)

    current["updated_at"] = _utc_now()
    profiles[resolved] = current
    _write_json_file(_MODEL_PROFILE_PATH, store)
    return model_profile(resolved)


def _available_routes(model: ModelDef) -> list[str]:
    return [route.value for route in model.routes if provider_available(route)]


def _rank_model(model: ModelDef) -> tuple[int, int, int, str]:
    tier_bias = {
        ModelTier.FRONTIER: 100,
        ModelTier.STRONG: 200,
        ModelTier.FAST: 300,
        ModelTier.FREE: 400,
        ModelTier.LOCAL: 500,
    }
    rank = model.power_rank if model.power_rank != 999 else tier_bias[model.tier]
    return (rank, -model.max_context, -len(model.strengths), model.display_name.lower())


def get_model(model_id: str) -> ModelDef | None:
    resolved = _resolve_model_id(model_id)
    if not resolved:
        return None
    return MODELS.get(resolved)


def is_available(model_id: str) -> bool:
    model = get_model(model_id)
    if model is None:
        return False
    return any(provider_available(route) for route in model.routes)


def list_models(
    tier: ModelTier | None = None,
    provider: ProviderType | None = None,
    available_only: bool = False,
) -> list[ModelDef]:
    result = sorted(MODELS.values(), key=_rank_model)
    if tier is not None:
        result = [model for model in result if model.tier == tier]
    if provider is not None:
        result = [model for model in result if _provider_matches(model, provider)]
    if available_only:
        result = [model for model in result if is_available(model.id)]
    return result


def _model_to_dict(model: ModelDef) -> dict[str, Any]:
    available_routes = _available_routes(model)
    profile = model_profile(model.id)
    return {
        "id": model.id,
        "display_name": model.display_name,
        "ui_label": profile["ui_label"],
        "custom_label": profile["custom_label"],
        "short_name": profile["short_name"],
        "provider": model.provider.value,
        "routes": _route_names(model),
        "available_routes": available_routes,
        "available": bool(available_routes),
        "tier": model.tier.value,
        "strengths": list(model.strengths),
        "max_context": model.max_context,
        "cost_per_mtok": model.cost_per_mtok,
        "notes": model.notes,
        "aliases": list(model.aliases),
        "source": model.source,
        "power_rank": model.power_rank if model.power_rank != 999 else None,
        "docs_url": profile["docs_url"],
        "provider_url": profile["provider_url"],
        "profile_updated_at": profile["updated_at"],
    }


def list_providers(available_only: bool = False) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for provider_type, provider_def in PROVIDERS.items():
        available = provider_available(provider_type)
        if available_only and not available:
            continue
        result.append(
            {
                "type": provider_type.value,
                "display_name": provider_def.display_name,
                "available": available,
                "needs_key": provider_def.needs_key,
                "env_keys": list(provider_def.env_keys),
                "default_base_url": provider_def.default_base_url,
                "availability_kind": provider_def.availability_kind,
                "model_count": sum(
                    1 for model in MODELS.values() if provider_type in model.routes
                ),
            }
        )
    return result


def get_agent_model(agent_name: str) -> ModelDef | None:
    ginko_dir = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko" / "agents"
    identity_path = ginko_dir / agent_name / "identity.json"
    if not identity_path.exists():
        return None
    try:
        data = json.loads(identity_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    model_id = str(data.get("model") or "").strip()
    if not model_id:
        return None
    model = get_model(model_id)
    if model is not None:
        return model
    return ModelDef(
        id=model_id,
        provider=ProviderType.OPENROUTER,
        display_name=model_id,
        tier=ModelTier.STRONG,
        notes="Unknown to model pool; preserved from Ginko identity.",
        source="ginko",
    )


def get_pool_models(
    *,
    provider: str | None = None,
    free_only: bool = False,
    search: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    provider_type: ProviderType | None = None
    if provider:
        try:
            provider_type = ProviderType(provider)
        except ValueError:
            provider_type = None

    models = list_models(provider=provider_type)
    if free_only:
        models = [m for m in models if m.tier in {ModelTier.FREE, ModelTier.LOCAL}]
    if search:
        needle = search.strip().lower()
        models = [
            m for m in models
            if needle in m.id.lower()
            or needle in m.display_name.lower()
            or any(needle in strength.lower() for strength in m.strengths)
            or any(needle in alias.lower() for alias in m.aliases)
            or needle in m.notes.lower()
        ]
    return [_model_to_dict(model) for model in models[:max(1, limit)]]


def _fallback_chain(model: ModelDef, *, limit: int = 4) -> list[str]:
    candidates = []
    for other in list_models():
        if other.id == model.id:
            continue
        if other.tier == model.tier:
            candidates.append(other.id)
        elif model.tier == ModelTier.FRONTIER and other.tier == ModelTier.STRONG:
            candidates.append(other.id)
        elif model.tier in {ModelTier.STRONG, ModelTier.FAST} and other.tier in {
            ModelTier.FREE,
            ModelTier.LOCAL,
        }:
            candidates.append(other.id)
        if len(candidates) >= limit:
            break
    return candidates[:limit]


def _curated_top10_models() -> list[ModelDef]:
    ordered: list[ModelDef] = []
    seen: set[str] = set()
    for model_id in CURATED_TOP10_MODEL_IDS:
        model = get_model(model_id)
        if model is None or model.id in seen:
            continue
        ordered.append(model)
        seen.add(model.id)
    for model in list_models():
        if model.id in seen:
            continue
        ordered.append(model)
        seen.add(model.id)
        if len(ordered) >= 10:
            break
    return ordered[:10]


def _preferred_live_route(model: ModelDef) -> ProviderType | None:
    for route in model.routes:
        if provider_available(route):
            return route
    return None


async def _verify_model_live(model: ModelDef) -> dict[str, Any]:
    route = _preferred_live_route(model)
    started = time.perf_counter()
    if route is None:
        return {
            "model_id": model.id,
            "display_name": model.display_name,
            "status": "unavailable",
            "route": "",
            "latency_ms": 0,
            "verified_at": _utc_now(),
            "response_preview": "",
            "error": "No available provider route",
        }

    provider = create_runtime_provider(
        resolve_runtime_provider_config(
            route,
            model=model.id,
            timeout_seconds=120,
        )
    )
    try:
        async def _complete(max_tokens: int):
            return await provider.complete(
                LLMRequest(
                    model=model.id,
                    messages=[{
                        "role": "user",
                        "content": "Return exactly the single token OK. Do not explain your reasoning.",
                    }],
                    max_tokens=max_tokens,
                    temperature=0.0,
                )
            )
        try:
            response = await _complete(256)
        except Exception as exc:
            affordable = None
            if route in {ProviderType.OPENROUTER, ProviderType.OPENROUTER_FREE}:
                affordable = _extract_openrouter_affordable_max_tokens(str(exc))
            if affordable and affordable < 256:
                response = await _complete(max(affordable, 24))
            else:
                raise
        content = (response.content or "").strip()
        return {
            "model_id": model.id,
            "display_name": model.display_name,
            "status": "ok" if "ok" in content.lower() else "unexpected",
            "route": route.value,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "verified_at": _utc_now(),
            "response_preview": content[:120],
            "error": "",
        }
    except Exception as exc:
        return {
            "model_id": model.id,
            "display_name": model.display_name,
            "status": "error",
            "route": route.value,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "verified_at": _utc_now(),
            "response_preview": "",
            "error": str(exc)[:300],
        }
    finally:
        try:
            await provider.close()
        except Exception:
            pass


def resolve_top10(*, live: bool = True) -> list[dict[str, Any]]:
    if live:
        reset_availability_cache()
    ranked = _curated_top10_models()
    result = []
    for idx, model in enumerate(ranked, start=1):
        row = _model_to_dict(model)
        row["rank"] = idx
        row["fallbacks"] = _fallback_chain(model)
        result.append(row)
    return result


def top10_status(*, live: bool = True) -> list[dict[str, Any]]:
    if live:
        reset_availability_cache()
    verification = _verification_snapshot()
    result: list[dict[str, Any]] = []
    for row in resolve_top10(live=False):
        check = verification.get(row["id"], {})
        status = dict(row)
        status["verification"] = {
            "status": str(check.get("status", "unverified")),
            "route": str(check.get("route", "") or ""),
            "latency_ms": int(check.get("latency_ms", 0) or 0),
            "verified_at": str(check.get("verified_at", "") or ""),
            "response_preview": str(check.get("response_preview", "") or ""),
            "error": str(check.get("error", "") or ""),
        }
        result.append(status)
    return result


async def verify_top10(*, live: bool = True) -> dict[str, Any]:
    if live:
        reset_availability_cache()
    results: list[dict[str, Any]] = []
    for model in _curated_top10_models():
        results.append(await _verify_model_live(model))
    payload = {
        "verified_at": _utc_now(),
        "models": {row["model_id"]: row for row in results},
    }
    _write_json_file(_MODEL_VERIFY_PATH, payload)
    return {
        "verified_at": payload["verified_at"],
        "ok_count": sum(1 for row in results if row["status"] == "ok"),
        "results": results,
    }


def get_pool(*, live: bool = True) -> dict[str, Any]:
    if live:
        reset_availability_cache()

    providers = list_providers()
    models = [_model_to_dict(model) for model in list_models()]

    agents: list[dict[str, Any]] = []
    ginko_dir = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma")) / "ginko" / "agents"
    if ginko_dir.exists():
        for child in sorted(ginko_dir.iterdir()):
            if not child.is_dir():
                continue
            identity_path = child / "identity.json"
            if not identity_path.exists():
                continue
            try:
                data = json.loads(identity_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            model_id = str(data.get("model") or "")
            resolved = get_model(model_id)
            agents.append(
                {
                    "name": data.get("name", child.name),
                    "role": data.get("role", ""),
                    "model": model_id,
                    "model_display_name": resolved.display_name if resolved else model_id,
                    "model_available": is_available(model_id),
                    "provider_routes": _route_names(resolved) if resolved else [],
                    "tasks_completed": data.get("tasks_completed", 0),
                    "total_calls": data.get("total_calls", 0),
                }
            )

    tier_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    available_count = 0
    for model in models:
        tier_counts[model["tier"]] = tier_counts.get(model["tier"], 0) + 1
        for route in model["routes"]:
            provider_counts[route] = provider_counts.get(route, 0) + 1
        if model["available"]:
            available_count += 1

    return {
        "providers": providers,
        "providers_up": sum(1 for provider in providers if provider["available"]),
        "providers_total": len(providers),
        "models": models,
        "models_total": len(models),
        "models_available": available_count,
        "models_by_tier": tier_counts,
        "models_by_provider": provider_counts,
        "top10": resolve_top10(live=False),
        "agents": agents,
        "agents_total": len(agents),
    }


def cost_per_token(model_id: str) -> float:
    model = get_model(model_id)
    if model and model.cost_per_mtok > 0:
        return model.cost_per_mtok / 1_000_000
    normalized = _norm_model_key(model_id)
    for known_id, model in MODELS.items():
        if normalized in known_id.lower() or known_id.lower() in normalized:
            if model.cost_per_mtok > 0:
                return model.cost_per_mtok / 1_000_000
    return 0.0


_register_static_models()
_load_openclaw_catalog()


__all__ = [
    "CURATED_TOP10_MODEL_IDS",
    "MODELS",
    "PROVIDERS",
    "ModelDef",
    "ModelTier",
    "ProviderDef",
    "cost_per_token",
    "get_agent_model",
    "get_model",
    "get_pool",
    "get_pool_models",
    "is_available",
    "list_models",
    "list_providers",
    "model_profile",
    "provider_available",
    "reset_availability_cache",
    "resolve_top10",
    "top10_status",
    "update_model_profile",
    "verify_top10",
]
