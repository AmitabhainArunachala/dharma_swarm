from __future__ import annotations

import pytest

from dharma_swarm.model_hierarchy import DEFAULT_MODELS
from dharma_swarm.models import LLMResponse, ProviderType
from dharma_swarm.runtime_provider import (
    DEFAULT_GROQ_MODEL,
    DEFAULT_SILICONFLOW_MODEL,
    DEFAULT_FIREWORKS_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    DEFAULT_TOGETHER_MODEL,
    FIREWORKS_BASE_URL,
    GROQ_BASE_URL,
    NVIDIA_NIM_BASE_URL,
    OPENROUTER_BASE_URL,
    SILICONFLOW_BASE_URL,
    TOGETHER_BASE_URL,
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
    assert cfg.default_model == DEFAULT_MODELS[ProviderType.OLLAMA]


def test_resolve_runtime_provider_config_for_openrouter_uses_canonical_base(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")

    cfg = resolve_runtime_provider_config(ProviderType.OPENROUTER)

    assert cfg.api_key == "or-key"
    assert cfg.base_url == OPENROUTER_BASE_URL
    assert cfg.available is True


def test_resolve_runtime_provider_config_for_codex_uses_npm_global_fallback(
    monkeypatch,
    tmp_path,
) -> None:
    codex_path = tmp_path / ".npm-global" / "bin" / "codex"
    codex_path.parent.mkdir(parents=True)
    codex_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    monkeypatch.setattr("dharma_swarm.runtime_provider.shutil.which", lambda _name: None)
    monkeypatch.setattr("dharma_swarm.runtime_provider.Path.home", lambda: tmp_path)

    cfg = resolve_runtime_provider_config(ProviderType.CODEX)

    assert cfg.binary_path == str(codex_path)
    assert cfg.available is True


def test_runtime_provider_openrouter_default_model_matches_canonical_hierarchy() -> None:
    assert DEFAULT_OPENROUTER_MODEL == DEFAULT_MODELS[ProviderType.OPENROUTER]


def test_resolve_runtime_provider_config_for_groq_uses_env_base_and_model(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("GROQ_BASE_URL", "https://groq.internal/openai/v1")

    cfg = resolve_runtime_provider_config(
        ProviderType.GROQ,
        model="qwen/qwen3-32b",
    )

    assert cfg.api_key == "groq-key"
    assert cfg.base_url == "https://groq.internal/openai/v1"
    assert cfg.default_model == "qwen/qwen3-32b"
    assert cfg.available is True


def test_resolve_runtime_provider_config_for_groq_uses_default_model(monkeypatch) -> None:
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")

    cfg = resolve_runtime_provider_config(ProviderType.GROQ)

    assert cfg.default_model == DEFAULT_GROQ_MODEL


def test_resolve_runtime_provider_config_for_cerebras_uses_canonical_default_model(
    monkeypatch,
) -> None:
    monkeypatch.setenv("CEREBRAS_API_KEY", "cerebras-key")

    cfg = resolve_runtime_provider_config(ProviderType.CEREBRAS)

    assert cfg.default_model == DEFAULT_MODELS[ProviderType.CEREBRAS]


def test_resolve_runtime_provider_config_for_siliconflow_uses_canonical_base(monkeypatch) -> None:
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sf-key")

    cfg = resolve_runtime_provider_config(
        ProviderType.SILICONFLOW,
        model="Qwen/Qwen3-Coder-30B-A3B-Instruct",
    )

    assert cfg.api_key == "sf-key"
    assert cfg.base_url == SILICONFLOW_BASE_URL
    assert cfg.default_model == "Qwen/Qwen3-Coder-30B-A3B-Instruct"
    assert cfg.available is True


def test_resolve_runtime_provider_config_for_siliconflow_uses_default_model(monkeypatch) -> None:
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sf-key")

    cfg = resolve_runtime_provider_config(ProviderType.SILICONFLOW)

    assert cfg.default_model == DEFAULT_SILICONFLOW_MODEL


def test_resolve_runtime_provider_config_for_together_uses_env_base_and_model(monkeypatch) -> None:
    monkeypatch.setenv("TOGETHER_API_KEY", "together-key")
    monkeypatch.setenv("TOGETHER_BASE_URL", "https://together.internal/v1")

    cfg = resolve_runtime_provider_config(
        ProviderType.TOGETHER,
        model="Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8",
    )

    assert cfg.api_key == "together-key"
    assert cfg.base_url == "https://together.internal/v1"
    assert cfg.default_model == "Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8"
    assert cfg.available is True


def test_resolve_runtime_provider_config_for_together_uses_default_model(monkeypatch) -> None:
    monkeypatch.setenv("TOGETHER_API_KEY", "together-key")

    cfg = resolve_runtime_provider_config(ProviderType.TOGETHER)

    assert cfg.base_url == TOGETHER_BASE_URL
    assert cfg.default_model == DEFAULT_TOGETHER_MODEL


def test_resolve_runtime_provider_config_for_fireworks_uses_env_base_and_model(monkeypatch) -> None:
    monkeypatch.setenv("FIREWORKS_API_KEY", "fireworks-key")
    monkeypatch.setenv("FIREWORKS_BASE_URL", "https://fireworks.internal/inference/v1")

    cfg = resolve_runtime_provider_config(
        ProviderType.FIREWORKS,
        model="accounts/fireworks/models/qwen3-coder-480b-a35b-instruct",
    )

    assert cfg.api_key == "fireworks-key"
    assert cfg.base_url == "https://fireworks.internal/inference/v1"
    assert cfg.default_model == "accounts/fireworks/models/qwen3-coder-480b-a35b-instruct"
    assert cfg.available is True


def test_resolve_runtime_provider_config_for_fireworks_uses_default_model(monkeypatch) -> None:
    monkeypatch.setenv("FIREWORKS_API_KEY", "fireworks-key")

    cfg = resolve_runtime_provider_config(ProviderType.FIREWORKS)

    assert cfg.base_url == FIREWORKS_BASE_URL
    assert cfg.default_model == DEFAULT_FIREWORKS_MODEL


def test_create_default_provider_map_includes_expected_runtime_providers() -> None:
    provider_map = create_default_provider_map(env={})

    assert ProviderType.ANTHROPIC in provider_map
    assert ProviderType.OPENROUTER in provider_map
    assert ProviderType.GROQ in provider_map
    assert ProviderType.SILICONFLOW in provider_map
    assert ProviderType.TOGETHER in provider_map
    assert ProviderType.FIREWORKS in provider_map
    assert ProviderType.NVIDIA_NIM in provider_map
    assert ProviderType.OPENROUTER_FREE in provider_map
    assert ProviderType.OLLAMA in provider_map


def test_preferred_runtime_provider_configs_prioritizes_ollama_nim_before_openrouter(
    monkeypatch,
) -> None:
    monkeypatch.setenv("OLLAMA_API_KEY", "ollama-key")
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "nim-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("GROQ_API_KEY", "groq-key")
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sf-key")
    monkeypatch.setenv("TOGETHER_API_KEY", "together-key")
    monkeypatch.setenv("FIREWORKS_API_KEY", "fireworks-key")

    configs = preferred_runtime_provider_configs(model="test-model")

    providers = [cfg.provider for cfg in configs]
    assert providers.index(ProviderType.GROQ) < providers.index(ProviderType.OPENROUTER)
    assert providers.index(ProviderType.SILICONFLOW) < providers.index(ProviderType.OPENROUTER)
    assert providers.index(ProviderType.TOGETHER) < providers.index(ProviderType.OPENROUTER)
    assert providers.index(ProviderType.FIREWORKS) < providers.index(ProviderType.OPENROUTER)
    assert ProviderType.OPENROUTER_FREE in providers
    assert ProviderType.NVIDIA_NIM in providers
    assert ProviderType.OLLAMA in providers


def test_preferred_runtime_provider_configs_skips_unavailable(monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    monkeypatch.delenv("NVIDIA_NIM_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("CEREBRAS_API_KEY", raising=False)
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    monkeypatch.delenv("TOGETHER_API_KEY", raising=False)
    monkeypatch.delenv("FIREWORKS_API_KEY", raising=False)
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
