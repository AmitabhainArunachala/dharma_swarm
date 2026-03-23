"""Centralized runtime provider resolution and factory helpers.

Keeps environment/auth/model/base-url resolution in one place while leaving
ModelRouter policy and provider implementations unchanged.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from dharma_swarm.models import ProviderType
from dharma_swarm.ollama_config import (
    build_ollama_headers,
    ollama_transport_mode,
    resolve_ollama_base_url,
    resolve_ollama_model,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
NVIDIA_NIM_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_CLAUDE_MODEL = "claude-opus-4-6"
DEFAULT_OPENAI_MODEL = "gpt-5.4"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-opus-4-6"
DEFAULT_NIM_MODEL = "meta/llama-3.3-70b-instruct"
DEFAULT_PROVIDER_TIMEOUT_SECONDS = 300

# FREE FIRST — Ollama Cloud, NVIDIA NIM, OpenRouter Free before paid providers.
DEFAULT_RUNTIME_PROVIDERS: tuple[ProviderType, ...] = (
    ProviderType.OLLAMA,
    ProviderType.NVIDIA_NIM,
    ProviderType.OPENROUTER_FREE,
    ProviderType.OPENROUTER,
    ProviderType.OPENAI,
    ProviderType.ANTHROPIC,
    ProviderType.CLAUDE_CODE,
    ProviderType.CODEX,
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

    raise ValueError(f"Unsupported runtime provider: {provider.value}")


def create_runtime_provider(config: RuntimeProviderConfig) -> Any:
    """Instantiate a provider from centralized runtime config."""

    from dharma_swarm.providers import (
        AnthropicProvider,
        ClaudeCodeProvider,
        CodexProvider,
        NVIDIANIMProvider,
        OllamaProvider,
        OpenAIProvider,
        OpenRouterFreeProvider,
        OpenRouterProvider,
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


__all__ = [
    "DEFAULT_CLAUDE_MODEL",
    "DEFAULT_NIM_MODEL",
    "DEFAULT_OPENAI_MODEL",
    "DEFAULT_OPENROUTER_MODEL",
    "DEFAULT_PROVIDER_TIMEOUT_SECONDS",
    "DEFAULT_RUNTIME_PROVIDERS",
    "NVIDIA_NIM_BASE_URL",
    "OPENROUTER_BASE_URL",
    "RuntimeProviderConfig",
    "create_default_provider_map",
    "create_runtime_provider",
    "resolve_runtime_provider_config",
]
