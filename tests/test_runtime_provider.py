from __future__ import annotations

import os

from dharma_swarm.models import ProviderType
from dharma_swarm.providers import OpenRouterFreeProvider, OpenRouterProvider
from dharma_swarm.runtime_provider import (
    DEFAULT_CLAUDE_MODEL,
    DEFAULT_NIM_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    NVIDIA_NIM_BASE_URL,
    OPENROUTER_BASE_URL,
    create_default_provider_map,
    create_runtime_provider,
    RuntimeProviderConfig,
    resolve_runtime_provider_config,
)


def test_resolve_runtime_provider_config_for_nim_uses_env_base_and_model(monkeypatch) -> None:
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nim-key")
    monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "https://nim.local/v1")

    cfg = resolve_runtime_provider_config(
        ProviderType.NVIDIA_NIM,
        model="moonshotai/kimi-k2.5",
    )

    assert cfg.api_key == "nim-key"
    assert cfg.base_url == "https://nim.local/v1"
    assert cfg.default_model == "moonshotai/kimi-k2.5"
    assert cfg.available is True


def test_resolve_runtime_provider_config_for_ollama_prefers_cloud_with_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-key")

    cfg = resolve_runtime_provider_config(ProviderType.OLLAMA)

    assert cfg.base_url == "https://ollama.com"
    assert cfg.transport_mode == "cloud_api"
    assert cfg.default_model == "kimi-k2.5:cloud"


def test_resolve_runtime_provider_config_for_openrouter_uses_canonical_base(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

    cfg = resolve_runtime_provider_config(ProviderType.OPENROUTER)

    assert cfg.api_key == "or-key"
    assert cfg.base_url == OPENROUTER_BASE_URL
    assert cfg.available is True


def test_resolve_runtime_provider_config_ignores_whitespace_api_key_override(monkeypatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")

    cfg = resolve_runtime_provider_config(
        ProviderType.ANTHROPIC,
        api_key="   ",
    )

    assert cfg.api_key == "env-key"
    assert cfg.available is True


def test_resolve_runtime_provider_config_ignores_whitespace_model_and_base_url_overrides(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

    cfg = resolve_runtime_provider_config(
        ProviderType.OPENROUTER,
        model="   ",
        base_url="   ",
    )

    assert cfg.base_url == OPENROUTER_BASE_URL
    assert cfg.default_model == DEFAULT_OPENROUTER_MODEL
    assert cfg.api_key == "or-key"


def test_resolve_runtime_provider_config_ignores_whitespace_working_dir_and_model(
    monkeypatch,
) -> None:
    expected_cwd = os.getcwd()

    cfg = resolve_runtime_provider_config(
        ProviderType.CLAUDE_CODE,
        model="   ",
        working_dir="   ",
    )

    assert cfg.working_dir == expected_cwd
    assert cfg.default_model == DEFAULT_CLAUDE_MODEL


def test_resolve_runtime_provider_config_for_nim_ignores_whitespace_explicit_overrides(
    monkeypatch,
) -> None:
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nim-key")
    monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "https://nim.local/v1/")

    cfg = resolve_runtime_provider_config(
        ProviderType.NVIDIA_NIM,
        api_key="   ",
        model="   ",
        base_url="   ",
    )

    assert cfg.api_key == "nim-key"
    assert cfg.base_url == "https://nim.local/v1"
    assert cfg.default_model == DEFAULT_NIM_MODEL
    assert cfg.available is True


def test_create_default_provider_map_includes_expected_runtime_providers() -> None:
    provider_map = create_default_provider_map(env={})

    assert ProviderType.ANTHROPIC in provider_map
    assert ProviderType.OPENROUTER in provider_map
    assert ProviderType.NVIDIA_NIM in provider_map
    assert ProviderType.OPENROUTER_FREE in provider_map
    assert ProviderType.OLLAMA in provider_map


def test_create_runtime_provider_passes_openrouter_base_url() -> None:
    provider = create_runtime_provider(
        RuntimeProviderConfig(
            provider=ProviderType.OPENROUTER,
            api_key="or-key",
            base_url="https://router.proxy/v1/",
        )
    )

    assert isinstance(provider, OpenRouterProvider)
    assert provider._api_key == "or-key"
    assert provider._base_url == "https://router.proxy/v1"


def test_create_runtime_provider_passes_openrouter_free_base_url_and_model() -> None:
    provider = create_runtime_provider(
        RuntimeProviderConfig(
            provider=ProviderType.OPENROUTER_FREE,
            api_key="or-key",
            base_url="https://router.proxy/free/",
            default_model="deepseek/deepseek-r1:free",
        )
    )

    assert isinstance(provider, OpenRouterFreeProvider)
    assert provider._api_key == "or-key"
    assert provider._base_url == "https://router.proxy/free"
    assert provider._preferred_model == "deepseek/deepseek-r1:free"
