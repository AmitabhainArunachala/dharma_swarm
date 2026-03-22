from __future__ import annotations

import pytest

from dharma_swarm.models import LLMResponse, ProviderType
from dharma_swarm.runtime_provider import (
    NVIDIA_NIM_BASE_URL,
    OPENROUTER_BASE_URL,
    RuntimeProviderConfig,
    complete_via_preferred_runtime_providers,
    create_default_provider_map,
    preferred_runtime_provider_configs,
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


def test_create_default_provider_map_includes_expected_runtime_providers() -> None:
    provider_map = create_default_provider_map(env={})

    assert ProviderType.ANTHROPIC in provider_map
    assert ProviderType.OPENROUTER in provider_map
    assert ProviderType.NVIDIA_NIM in provider_map
    assert ProviderType.OPENROUTER_FREE in provider_map
    assert ProviderType.OLLAMA in provider_map


def test_preferred_runtime_provider_configs_prioritizes_ollama_nim_before_openrouter(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-key")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nim-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

    configs = preferred_runtime_provider_configs(model="test-model")

    providers = [cfg.provider for cfg in configs]
    assert providers[:4] == [
        ProviderType.OLLAMA,
        ProviderType.NVIDIA_NIM,
        ProviderType.OPENROUTER_FREE,
        ProviderType.OPENROUTER,
    ]


def test_preferred_runtime_provider_configs_skips_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

    configs = preferred_runtime_provider_configs(model="test-model")

    providers = [cfg.provider for cfg in configs]
    assert providers == [
        ProviderType.OLLAMA,
        ProviderType.OPENROUTER_FREE,
        ProviderType.OPENROUTER,
    ]


@pytest.mark.asyncio
async def test_complete_via_preferred_runtime_providers_prefers_ollama_then_nim(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str]] = []

    class _FakeProvider:
        def __init__(self, label: str, *, fail: bool = False):
            self.label = label
            self.fail = fail

        async def complete(self, request):
            calls.append((self.label, request.model))
            if self.fail:
                raise RuntimeError(f"{self.label} failed")
            return LLMResponse(content=f"{self.label} ok", model=request.model)

        async def close(self):
            return None

    def _fake_preferred_configs(**kwargs):
        return [
            RuntimeProviderConfig(
                provider=ProviderType.OLLAMA,
                available=True,
                default_model="ollama-local",
            ),
            RuntimeProviderConfig(
                provider=ProviderType.NVIDIA_NIM,
                available=True,
                default_model="nim-local",
            ),
            RuntimeProviderConfig(
                provider=ProviderType.OPENROUTER,
                available=True,
                default_model="openrouter-fallback",
            ),
        ]

    def _fake_create_provider(config):
        return _FakeProvider(
            config.provider.value,
            fail=config.provider == ProviderType.OLLAMA,
        )

    monkeypatch.setattr(
        "dharma_swarm.runtime_provider.preferred_runtime_provider_configs",
        _fake_preferred_configs,
    )
    monkeypatch.setattr(
        "dharma_swarm.runtime_provider.create_runtime_provider",
        _fake_create_provider,
    )

    response, config = await complete_via_preferred_runtime_providers(
        messages=[{"role": "user", "content": "hello"}],
        openrouter_model="meta-llama/llama-3.3-70b-instruct:free",
    )

    assert response.content == "nvidia_nim ok"
    assert config.provider == ProviderType.NVIDIA_NIM
    assert calls == [
        ("ollama", "ollama-local"),
        ("nvidia_nim", "nim-local"),
    ]
