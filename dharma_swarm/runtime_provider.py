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
GOOGLE_AI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_CLAUDE_MODEL = "claude-opus-4-6"
DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-opus-4-6"
DEFAULT_GROQ_MODEL = "qwen/qwen3-32b"
DEFAULT_SILICONFLOW_MODEL = "Qwen/Qwen3-Coder-480B-A35B-Instruct"
DEFAULT_NIM_MODEL = "meta/llama-3.3-70b-instruct"
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 300

# FREE FIRST — Groq/Cerebras/SiliconFlow fastest, then Ollama Cloud, NVIDIA NIM,
# OpenRouter Free before paid providers.
DEFAULT_RUNTIME_PROVIDERS: tuple[ProviderType, ...] = (
    ProviderType.GROQ,
    ProviderType.CEREBRAS,
    ProviderType.SILICONFLOW,
    ProviderType.OLLAMA,
    ProviderType.NVIDIA_NIM,
    ProviderType.OPENROUTER_FREE,
    ProviderType.OPENROUTER,
    ProviderType.OPENAI,
    ProviderType.ANTHROPIC,
    ProviderType.CLAUDE_CODE,
    ProviderType.CODEX,
    ProviderType.GOOGLE_AI,
)

# Hardcoded low-cost preference for autonomous/runtime call sites that would
# otherwise talk to OpenRouter directly. Keep local/NIM ahead of OpenRouter;
# Groq/Cerebras/SiliconFlow slotted after free tiers.
PREFERRED_LOW_COST_RUNTIME_PROVIDERS: tuple[ProviderType, ...] = (
    ProviderType.OLLAMA,
    ProviderType.NVIDIA_NIM,
    ProviderType.OPENROUTER_FREE,
    ProviderType.GROQ,
    ProviderType.CEREBRAS,
    ProviderType.SILICONFLOW,
    ProviderType.OPENROUTER,
)

PREFERRED_LOW_COST_WITH_ANTHROPIC_RUNTIME_PROVIDERS: tuple[ProviderType, ...] = (
    ProviderType.OLLAMA,
    ProviderType.NVIDIA_NIM,
    ProviderType.OPENROUTER_FREE,
    ProviderType.OPENROUTER,
    ProviderType.ANTHROPIC,
)


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
        token = api_key or _env_value(env_map, "ANTHROPIC_API_KEY")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            default_model=model or DEFAULT_CLAUDE_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.OPENAI:
        token = api_key or _env_value(env_map, "OPENAI_API_KEY")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=(base_url or OPENAI_BASE_URL).rstrip("/"),
            default_model=model or DEFAULT_OPENAI_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.OPENROUTER:
        token = api_key or _env_value(env_map, "OPENROUTER_API_KEY")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=(base_url or OPENROUTER_BASE_URL).rstrip("/"),
            default_model=model or DEFAULT_OPENROUTER_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.OPENROUTER_FREE:
        token = api_key or _env_value(env_map, "OPENROUTER_API_KEY")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=(base_url or OPENROUTER_BASE_URL).rstrip("/"),
            default_model=model,
            available=bool(token),
        )

    if provider == ProviderType.NVIDIA_NIM:
        token = api_key or _env_value(env_map, "NVIDIA_NIM_API_KEY")
        resolved_base = (
            base_url
            or _env_value(env_map, "NVIDIA_NIM_BASE_URL")
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
        token = api_key or _env_value(env_map, "OLLAMA_API_KEY")
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
        binary = shutil.which("claude") or str(next(
            (p for p in [
                Path.home() / ".npm-global" / "bin" / "claude",
                Path("/usr/local/bin/claude"),
            ] if p.exists()),
            None,
        ))
        return RuntimeProviderConfig(
            provider=provider,
            default_model=model or DEFAULT_CLAUDE_MODEL,
            working_dir=cwd,
            timeout_seconds=timeout,
            binary_path=binary,
            available=binary is not None,
            source="binary",
        )

    if provider == ProviderType.CODEX:
        binary = shutil.which("codex")
        return RuntimeProviderConfig(
            provider=provider,
            default_model=model or _env_value(env_map, "DGC_DIRECTOR_CODEX_MODEL") or "gpt-5.4",
            working_dir=cwd,
            timeout_seconds=timeout,
            binary_path=binary,
            available=binary is not None,
            source="binary",
        )

    if provider == ProviderType.GROQ:
        token = api_key or _env_value(env_map, "GROQ_API_KEY")
        resolved_base = (
            base_url
            or _env_value(env_map, "GROQ_BASE_URL")
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
        token = api_key or _env_value(env_map, "CEREBRAS_API_KEY")
        resolved_base = (
            base_url
            or _env_value(env_map, "CEREBRAS_BASE_URL")
            or CEREBRAS_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or "llama-3.3-70b",
            available=bool(token),
        )

    if provider == ProviderType.SILICONFLOW:
        token = api_key or _env_value(env_map, "SILICONFLOW_API_KEY")
        resolved_base = (
            base_url
            or _env_value(env_map, "SILICONFLOW_BASE_URL")
            or SILICONFLOW_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or DEFAULT_SILICONFLOW_MODEL,
            available=bool(token),
        )

    if provider == ProviderType.GOOGLE_AI:
        token = api_key or _env_value(env_map, "GOOGLE_AI_API_KEY")
        resolved_base = (
            base_url
            or _env_value(env_map, "GOOGLE_AI_BASE_URL")
            or GOOGLE_AI_BASE_URL
        ).rstrip("/")
        return RuntimeProviderConfig(
            provider=provider,
            api_key=token,
            base_url=resolved_base,
            default_model=model or "gemini-2.5-flash",
            available=bool(token),
        )

    raise ValueError(f"Unsupported runtime provider: {provider.value}")


def create_runtime_provider(config: RuntimeProviderConfig) -> Any:
    """Instantiate a provider from centralized runtime config."""

    from dharma_swarm.providers import (
        AnthropicProvider,
        CerebrasProvider,
        ClaudeCodeProvider,
        CodexProvider,
        GoogleAIProvider,
        GroqProvider,
        NVIDIANIMProvider,
        OllamaProvider,
        OpenAIProvider,
        OpenRouterFreeProvider,
        OpenRouterProvider,
        SiliconFlowProvider,
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
    if config.provider == ProviderType.GOOGLE_AI:
        kwargs = {}
        if config.api_key is not None:
            kwargs["api_key"] = config.api_key
        return GoogleAIProvider(**kwargs)
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
    "DEFAULT_NIM_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_OPENROUTER_MODEL",
    "DEFAULT_PROVIDER_TIMEOUT_SECONDS",
    "DEFAULT_RUNTIME_PROVIDERS",
    "DEFAULT_SILICONFLOW_MODEL",
    "GOOGLE_AI_BASE_URL",
    "GROQ_BASE_URL",
    "NVIDIA_NIM_BASE_URL",
    "OPENAI_BASE_URL",
    "OPENROUTER_BASE_URL",
    "PREFERRED_LOW_COST_RUNTIME_PROVIDERS",
    "PREFERRED_LOW_COST_WITH_ANTHROPIC_RUNTIME_PROVIDERS",
    "RuntimeProviderConfig",
    "SILICONFLOW_BASE_URL",
    "complete_via_preferred_runtime_providers",
    "create_default_provider_map",
    "create_runtime_provider",
    "preferred_runtime_provider_configs",
    "resolve_runtime_provider_config",
]
