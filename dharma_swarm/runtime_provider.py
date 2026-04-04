"""Centralized runtime provider resolution and factory helpers.

Keeps environment/auth/model/base-url resolution in one place while leaving
ModelRouter policy and provider implementations unchanged.
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from dharma_swarm.api_keys import (
    ANTHROPIC_API_KEY_ENV,
    CEREBRAS_API_KEY_ENV,
    CEREBRAS_BASE_URL_ENV,
    CHUTES_API_KEY_ENV,
    CHUTES_BASE_URL_ENV,
    FIREWORKS_API_KEY_ENV,
    FIREWORKS_BASE_URL_ENV,
    GOOGLE_AI_API_KEY_ENV,
    GOOGLE_AI_BASE_URL_ENV,
    GROQ_API_KEY_ENV,
    GROQ_BASE_URL_ENV,
    MISTRAL_API_KEY_ENV,
    MISTRAL_BASE_URL_ENV,
    NVIDIA_NIM_API_KEY_ENV,
    NVIDIA_NIM_BASE_URL_ENV,
    OLLAMA_API_KEY_ENV,
    OPENAI_API_KEY_ENV,
    OPENROUTER_API_KEY_ENV,
    SAMBANOVA_API_KEY_ENV,
    SAMBANOVA_BASE_URL_ENV,
    SILICONFLOW_API_KEY_ENV,
    SILICONFLOW_BASE_URL_ENV,
    TOGETHER_API_KEY_ENV,
    TOGETHER_BASE_URL_ENV,
)
from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.ollama_config import (
    build_ollama_headers,
    ollama_transport_mode,
    resolve_ollama_base_url,
    resolve_ollama_model,
)

OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
TOGETHER_BASE_URL = "https://api.together.xyz/v1"
FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
GOOGLE_AI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
SAMBANOVA_BASE_URL = "https://api.sambanova.ai/v1"
MISTRAL_BASE_URL = "https://api.mistral.ai/v1"
CHUTES_BASE_URL = "https://api.chutes.ai/v1"
from dharma_swarm.model_hierarchy import (
    CANONICAL_SEED_ORDER,
    DEFAULT_MODELS,
)

# Default models — sourced from model_hierarchy.py (the single source of truth)
DEFAULT_CLAUDE_MODEL = DEFAULT_MODELS.get(ProviderType.ANTHROPIC, "claude-opus-4-6")
DEFAULT_OPENAI_MODEL = DEFAULT_MODELS.get(ProviderType.OPENAI, "gpt-5")
DEFAULT_OPENROUTER_MODEL = DEFAULT_MODELS.get(ProviderType.OPENROUTER, "xiaomi/mimo-v2-pro")
DEFAULT_GROQ_MODEL = DEFAULT_MODELS.get(ProviderType.GROQ, "qwen/qwen3-32b")
DEFAULT_CEREBRAS_MODEL = DEFAULT_MODELS.get(ProviderType.CEREBRAS, "qwen-3-235b-a22b-instruct-2507")
DEFAULT_SILICONFLOW_MODEL = DEFAULT_MODELS.get(ProviderType.SILICONFLOW, "Qwen/Qwen3-Coder-480B-A35B-Instruct")
DEFAULT_TOGETHER_MODEL = DEFAULT_MODELS.get(ProviderType.TOGETHER, "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8")
DEFAULT_FIREWORKS_MODEL = DEFAULT_MODELS.get(ProviderType.FIREWORKS, "accounts/fireworks/models/qwen3-coder-480b-a35b-instruct")
DEFAULT_NIM_MODEL = DEFAULT_MODELS.get(ProviderType.NVIDIA_NIM, "meta/llama-3.3-70b-instruct")
DEFAULT_SAMBANOVA_MODEL = DEFAULT_MODELS.get(ProviderType.SAMBANOVA, "Meta-Llama-3.3-70B-Instruct")
DEFAULT_MISTRAL_MODEL = DEFAULT_MODELS.get(ProviderType.MISTRAL, "mistral-small-latest")
DEFAULT_CHUTES_MODEL = DEFAULT_MODELS.get(ProviderType.CHUTES, "deepseek-ai/DeepSeek-R1")
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 300

# Provider ordering sourced from model_hierarchy.py — the single source of truth.
# Power-first: paid (strongest) → cheap → free (fallback).
DEFAULT_RUNTIME_PROVIDERS: tuple[ProviderType, ...] = CANONICAL_SEED_ORDER

# Power-first provider chain: strongest models first, degrade gracefully.
# Try paid/powerful → cheap/fast → free/fallback.
# Only falls back when the upstream provider fails (rate limit, key missing,
# circuit broken). EWMA learning will reorder after ~100 events.
PREFERRED_RUNTIME_PROVIDERS: tuple[ProviderType, ...] = (
    ProviderType.ANTHROPIC,       # PAID: Opus 4.6 (strongest reasoning)
    ProviderType.OPENAI,          # PAID: GPT-5
    ProviderType.OPENROUTER,      # PAID: xiaomi/mimo-v2-pro + full catalog
    ProviderType.CODEX,           # PAID: Codex CLI (tool access)
    ProviderType.CLAUDE_CODE,     # PAID: Claude Code CLI (tool access)
    ProviderType.GOOGLE_AI,       # CHEAP: Gemini 2.5 Flash (1M ctx)
    ProviderType.MISTRAL,         # CHEAP: mistral-small (fast)
    ProviderType.CHUTES,          # CHEAP: DeepSeek-R1
    ProviderType.OLLAMA,          # FREE: GLM-5 744B, DeepSeek-v3.2
    ProviderType.GROQ,            # FREE: Qwen3-32B (3000 tok/s)
    ProviderType.CEREBRAS,        # FREE: Qwen3 235B
    ProviderType.NVIDIA_NIM,      # FREE: Llama 3.3 70B
    ProviderType.SILICONFLOW,     # FREE: Qwen3-Coder 480B
    ProviderType.TOGETHER,        # FREE: Qwen3-Coder 480B
    ProviderType.FIREWORKS,       # FREE: Qwen3-Coder 480B
    ProviderType.SAMBANOVA,       # FREE: Llama 3.3 70B
    ProviderType.OPENROUTER_FREE, # FREE: auto-discovered
)

# Legacy alias — code that imported the old name still works
PREFERRED_LOW_COST_RUNTIME_PROVIDERS = PREFERRED_RUNTIME_PROVIDERS

PREFERRED_WITH_ANTHROPIC_RUNTIME_PROVIDERS: tuple[ProviderType, ...] = (
    ProviderType.ANTHROPIC,       # Opus 4.6 first
    ProviderType.OPENAI,          # GPT-5
    ProviderType.OPENROUTER,      # Full catalog
    ProviderType.GOOGLE_AI,       # Gemini
    ProviderType.MISTRAL,         # Fast
    ProviderType.OLLAMA,          # Free frontier
    ProviderType.GROQ,            # Free fast
    ProviderType.CEREBRAS,        # Free large
    ProviderType.OPENROUTER_FREE, # Free auto
    ProviderType.TOGETHER,
    ProviderType.FIREWORKS,
)

# Legacy alias
PREFERRED_LOW_COST_WITH_ANTHROPIC_RUNTIME_PROVIDERS = PREFERRED_WITH_ANTHROPIC_RUNTIME_PROVIDERS


@dataclass(frozen=True, slots=True)
class RuntimeProviderConfig:
    provider: ProviderType
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    transport_mode: str | None = None
    working_dir: str | None = None
    timeout_seconds: int | None = None
    binary_path: str | None = None
    available: bool = False
    source: str = "env"
    metadata: dict[str, Any] | None = None


def _env_value(env: Mapping[str, str], key: str) -> str | None:
    value = str(env.get(key, "")).strip()
    return value or None


def _resolve_cli_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found

    for candidate in (
        Path.home() / ".npm-global" / "bin" / name,
        Path("/opt/homebrew/bin") / name,
        Path("/usr/local/bin") / name,
    ):
        if candidate.exists():
            return str(candidate)
    return None


def resolve_runtime_provider_config(
    provider: ProviderType,
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    working_dir: str | None = None,
    timeout_seconds: int | None = None,
    env: Mapping[str, str] | None = None,
) -> RuntimeProviderConfig:
    """Resolve runtime config for a provider from args + environment."""

    env_map = env or os.environ
    timeout = int(timeout_seconds or DEFAULT_PROVIDER_TIMEOUT_SECONDS)
    cwd = str(Path(working_dir or os.getcwd()))

    if provider == ProviderType.ANTHROPIC:
        token = api_key or _env_value(env_map, ANTHROPIC_API_KEY_ENV)
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            default_model=model or DEFAULT_CLAUDE_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.OPENAI:
        token = api_key or _env_value(env_map, OPENAI_API_KEY_ENV)
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=(base_url or OPENAI_BASE_URL).rstrip("/"),
            default_model=model or DEFAULT_OPENAI_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.OPENROUTER:
        token = api_key or _env_value(env_map, OPENROUTER_API_KEY_ENV)
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=(base_url or OPENROUTER_BASE_URL).rstrip("/"),
            default_model=model or DEFAULT_OPENROUTER_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.OPENROUTER_FREE:
        token = api_key or _env_value(env_map, OPENROUTER_API_KEY_ENV)
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=(base_url or OPENROUTER_BASE_URL).rstrip("/"),
            default_model=model,
            available=bool(token),
        )

    if provider == ProviderType.NVIDIA_NIM:
        token = api_key or _env_value(env_map, NVIDIA_NIM_API_KEY_ENV)
        resolved_base = (
            base_url
            or _env_value(env_map, NVIDIA_NIM_BASE_URL_ENV)
            or NVIDIA_NIM_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or DEFAULT_NIM_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.OLLAMA:
        token = api_key or _env_value(env_map, OLLAMA_API_KEY_ENV)
        resolved_base = resolve_ollama_base_url(base_url=base_url, api_key=token)
        resolved_model = resolve_ollama_model(
            model,
            base_url=resolved_base,
            api_key=token,
        )
        transport_mode = ollama_transport_mode(
            base_url=resolved_base,
            api_key=token,
        )
        available = bool(resolved_base)
        metadata: dict[str, Any] = {}
        try:
            metadata["headers"] = build_ollama_headers(
                base_url=resolved_base,
                api_key=token,
            )
        except Exception:
            metadata["headers"] = {}
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=resolved_model,
            transport_mode=transport_mode,
            available=available,
            metadata=metadata,
        )

    if provider == ProviderType.CLAUDE_CODE:
        binary = _resolve_cli_binary("claude")
        return RuntimeProviderConfig(
            provider=provider,
            default_model=model or DEFAULT_CLAUDE_MODEL,
            working_dir=cwd,
            timeout_seconds=timeout,
            binary_path=binary,
            available=bool(binary),
            source="binary",
        )

    if provider == ProviderType.CODEX:
        binary = _resolve_cli_binary("codex")
        return RuntimeProviderConfig(
            provider=provider,
            default_model=model or _env_value(env_map, "DGC_DIRECTOR_CODEX_MODEL") or "gpt-5.4",
            working_dir=cwd,
            timeout_seconds=timeout,
            binary_path=binary,
            available=bool(binary),
            source="binary",
        )

    if provider == ProviderType.GROQ:
        token = api_key or _env_value(env_map, GROQ_API_KEY_ENV)
        resolved_base = (
            base_url
            or _env_value(env_map, GROQ_BASE_URL_ENV)
            or GROQ_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or DEFAULT_GROQ_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.CEREBRAS:
        token = api_key or _env_value(env_map, CEREBRAS_API_KEY_ENV)
        resolved_base = (
            base_url
            or _env_value(env_map, CEREBRAS_BASE_URL_ENV)
            or CEREBRAS_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or DEFAULT_CEREBRAS_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.SILICONFLOW:
        token = api_key or _env_value(env_map, SILICONFLOW_API_KEY_ENV)
        resolved_base = (
            base_url
            or _env_value(env_map, SILICONFLOW_BASE_URL_ENV)
            or SILICONFLOW_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or DEFAULT_SILICONFLOW_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.TOGETHER:
        token = api_key or _env_value(env_map, TOGETHER_API_KEY_ENV)
        resolved_base = (
            base_url
            or _env_value(env_map, TOGETHER_BASE_URL_ENV)
            or TOGETHER_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or DEFAULT_TOGETHER_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.FIREWORKS:
        token = api_key or _env_value(env_map, FIREWORKS_API_KEY_ENV)
        resolved_base = (
            base_url
            or _env_value(env_map, FIREWORKS_BASE_URL_ENV)
            or FIREWORKS_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or DEFAULT_FIREWORKS_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.GOOGLE_AI:
        token = api_key or _env_value(env_map, GOOGLE_AI_API_KEY_ENV)
        resolved_base = (
            base_url
            or _env_value(env_map, GOOGLE_AI_BASE_URL_ENV)
            or GOOGLE_AI_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or "gemini-2.5-flash",
            available=bool(token),
        )

    if provider == ProviderType.SAMBANOVA:
        token = api_key or _env_value(env_map, SAMBANOVA_API_KEY_ENV)
        resolved_base = (
            base_url
            or _env_value(env_map, SAMBANOVA_BASE_URL_ENV)
            or SAMBANOVA_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or DEFAULT_SAMBANOVA_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.MISTRAL:
        token = api_key or _env_value(env_map, MISTRAL_API_KEY_ENV)
        resolved_base = (
            base_url
            or _env_value(env_map, MISTRAL_BASE_URL_ENV)
            or MISTRAL_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or DEFAULT_MISTRAL_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.CHUTES:
        token = api_key or _env_value(env_map, CHUTES_API_KEY_ENV)
        resolved_base = (
            base_url
            or _env_value(env_map, CHUTES_BASE_URL_ENV)
            or CHUTES_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or DEFAULT_CHUTES_MODEL,
            available=bool(token),
        )

    raise ValueError(f"Unsupported runtime provider: {provider.value}")


def create_runtime_provider(config: RuntimeProviderConfig) -> Any:
    """Instantiate a provider from centralized runtime config."""

    from dharma_swarm.providers import (
        AnthropicProvider,
        CerebrasProvider,
        ChutesProvider,
        ClaudeCodeProvider,
        CodexProvider,
        FireworksProvider,
        GoogleAIProvider,
        GroqProvider,
        MistralProvider,
        NVIDIANIMProvider,
        OllamaProvider,
        OpenAIProvider,
        OpenRouterFreeProvider,
        OpenRouterProvider,
        SambaNovaProvider,
        SiliconFlowProvider,
        TogetherProvider,
    )

    if config.provider == ProviderType.ANTHROPIC:
        kwargs: dict[str, Any] = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return AnthropicProvider(**kwargs)
    if config.provider == ProviderType.OPENAI:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return OpenAIProvider(**kwargs)
    if config.provider == ProviderType.OPENROUTER:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return OpenRouterProvider(**kwargs)
    if config.provider == ProviderType.OPENROUTER_FREE:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        if config.default_model is not None:
            kwargs["model"] = config.default_model
        return OpenRouterFreeProvider(**kwargs)
    if config.provider == ProviderType.NVIDIA_NIM:
        kwargs = {"default_model": config.default_model or DEFAULT_NIM_MODEL}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        if config.base_url is not None:
            kwargs["base_url"] = config.base_url
        return NVIDIANIMProvider(**kwargs)
    if config.provider == ProviderType.OLLAMA:
        kwargs = {}
        if config.base_url is not None:
            kwargs["base_url"] = config.base_url
        if config.default_model is not None:
            kwargs["model"] = config.default_model
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return OllamaProvider(**kwargs)
    if config.provider == ProviderType.CLAUDE_CODE:
        kwargs = {"timeout": config.timeout_seconds or DEFAULT_PROVIDER_TIMEOUT_SECONDS}
        if config.working_dir is not None:
            kwargs["working_dir"] = config.working_dir
        return ClaudeCodeProvider(**kwargs)
    if config.provider == ProviderType.CODEX:
        kwargs = {"timeout": config.timeout_seconds or DEFAULT_PROVIDER_TIMEOUT_SECONDS}
        if config.working_dir is not None:
            kwargs["working_dir"] = config.working_dir
        return CodexProvider(**kwargs)
    if config.provider == ProviderType.GROQ:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return GroqProvider(**kwargs)
    if config.provider == ProviderType.CEREBRAS:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return CerebrasProvider(**kwargs)
    if config.provider == ProviderType.SILICONFLOW:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return SiliconFlowProvider(**kwargs)
    if config.provider == ProviderType.TOGETHER:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return TogetherProvider(**kwargs)
    if config.provider == ProviderType.FIREWORKS:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return FireworksProvider(**kwargs)
    if config.provider == ProviderType.GOOGLE_AI:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return GoogleAIProvider(**kwargs)
    if config.provider == ProviderType.SAMBANOVA:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return SambaNovaProvider(**kwargs)
    if config.provider == ProviderType.MISTRAL:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return MistralProvider(**kwargs)
    if config.provider == ProviderType.CHUTES:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return ChutesProvider(**kwargs)
    raise ValueError(f"Unsupported runtime provider: {config.provider.value}")


def create_default_provider_map(
    *,
    working_dir: str | None = None,
    timeout_seconds: int | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[ProviderType, Any]:
    """Instantiate the default provider map for ModelRouter."""

    providers: dict[ProviderType, Any] = {}
    for provider in DEFAULT_RUNTIME_PROVIDERS:
        cfg = resolve_runtime_provider_config(
            provider,
            working_dir=working_dir,
            timeout_seconds=timeout_seconds,
            env=env,
        )
        providers[provider] = create_runtime_provider(cfg)
    return providers


def preferred_runtime_provider_configs(
    *,
    model: str | None = None,
    provider_order: tuple[ProviderType, ...] | None = None,
    model_overrides: Mapping[ProviderType, str | None] | None = None,
    working_dir: str | None = None,
    timeout_seconds: int | None = None,
    env: Mapping[str, str] | None = None,
) -> list[RuntimeProviderConfig]:
    """Resolve the preferred cheap/runtime provider chain in fixed order.

    This is the canonical helper for direct-call sites that should prefer
    Ollama and NVIDIA NIM before any OpenRouter lane.
    """

    order = provider_order or PREFERRED_LOW_COST_RUNTIME_PROVIDERS
    overrides = model_overrides or {}
    configs: list[RuntimeProviderConfig] = []
    for provider in order:
        cfg = resolve_runtime_provider_config(
            provider,
            model=overrides.get(provider, model),
            working_dir=working_dir,
            timeout_seconds=timeout_seconds,
            env=env,
        )
        if cfg.available:
            configs.append(cfg)
    return configs


async def complete_via_preferred_runtime_providers(
    *,
    messages: list[dict[str, str]],
    system: str = "",
    openrouter_model: str | None = None,
    anthropic_model: str | None = None,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    provider_order: tuple[ProviderType, ...] | None = None,
    working_dir: str | None = None,
    timeout_seconds: float | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[LLMResponse, RuntimeProviderConfig]:
    """Complete an LLM request via the canonical cheap-first runtime stack."""

    overrides: dict[ProviderType, str | None] = {
        ProviderType.OPENROUTER_FREE: openrouter_model,
        ProviderType.OPENROUTER: openrouter_model,
    }
    if anthropic_model is not None:
        overrides[ProviderType.ANTHROPIC] = anthropic_model

    configs = preferred_runtime_provider_configs(
        provider_order=provider_order or PREFERRED_LOW_COST_RUNTIME_PROVIDERS,
        model_overrides=overrides,
        working_dir=working_dir,
        timeout_seconds=int(timeout_seconds) if timeout_seconds is not None else None,
        env=env,
    )
    if not configs:
        raise RuntimeError(
            "No preferred providers available; configure Ollama, NVIDIA NIM, OpenRouter, or Anthropic"
        )

    last_exc: Exception | None = None
    for config in configs:
        provider = create_runtime_provider(config)
        try:
            request = LLMRequest(
                model=config.default_model or anthropic_model or openrouter_model or DEFAULT_NIM_MODEL,
                messages=messages,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            if timeout_seconds is not None:
                response = await asyncio.wait_for(
                    provider.complete(request),
                    timeout=timeout_seconds,
                )
            else:
                response = await provider.complete(request)
            return response, config
        except Exception as exc:
            last_exc = exc
        finally:
            close = getattr(provider, "close", None)
            if callable(close):
                await close()

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("Preferred provider chain exhausted without an explicit error")


__all__ = [
    "CEREBRAS_BASE_URL",
    "DEFAULT_CLAUDE_MODEL",
    "DEFAULT_GROQ_MODEL",
    "DEFAULT_FIREWORKS_MODEL",
    "DEFAULT_NIM_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_OPENROUTER_MODEL",
    "DEFAULT_PROVIDER_TIMEOUT_SECONDS",
    "DEFAULT_RUNTIME_PROVIDERS",
    "DEFAULT_SILICONFLOW_MODEL",
    "DEFAULT_TOGETHER_MODEL",
    "FIREWORKS_BASE_URL",
    "GOOGLE_AI_BASE_URL",
    "GROQ_BASE_URL",
    "NVIDIA_NIM_BASE_URL",
    "OPENAI_BASE_URL",
    "OPENROUTER_BASE_URL",
    "PREFERRED_LOW_COST_RUNTIME_PROVIDERS",
    "PREFERRED_LOW_COST_WITH_ANTHROPIC_RUNTIME_PROVIDERS",
    "RuntimeProviderConfig",
    "SILICONFLOW_BASE_URL",
    "TOGETHER_BASE_URL",
    "complete_via_preferred_runtime_providers",
    "create_default_provider_map",
    "create_runtime_provider",
    "preferred_runtime_provider_configs",
    "resolve_runtime_provider_config",
]
