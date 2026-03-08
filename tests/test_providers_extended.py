"""Tests for dharma_swarm.providers_extended -- Ollama, NVIDIA NIM, Moonshot providers."""

import pytest

from dharma_swarm.models import LLMRequest
from dharma_swarm.providers_extended import (
    MoonshotProvider,
    NVIDIANIMProvider,
    OllamaProvider,
)


# ---------------------------------------------------------------------------
# OllamaProvider
# ---------------------------------------------------------------------------


def test_ollama_defaults():
    p = OllamaProvider()
    assert p.base_url == "http://localhost:11434"
    assert p.default_model == "llama3.2"


def test_ollama_custom_model():
    p = OllamaProvider(model="mistral")
    assert p.default_model == "mistral"


def test_ollama_custom_url():
    p = OllamaProvider(base_url="http://custom:1234")
    assert p.base_url == "http://custom:1234"


def test_ollama_env_override(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://from-env:5555")
    p = OllamaProvider()
    assert p.base_url == "http://from-env:5555"


@pytest.mark.asyncio
async def test_ollama_stream_not_implemented():
    p = OllamaProvider()
    request = LLMRequest(
        model="llama3.2",
        messages=[{"role": "user", "content": "hi"}],
    )
    with pytest.raises(NotImplementedError, match="Ollama streaming"):
        async for _ in p.stream(request):
            pass


# ---------------------------------------------------------------------------
# NVIDIANIMProvider
# ---------------------------------------------------------------------------


def test_nvidia_nim_defaults():
    p = NVIDIANIMProvider(api_key="test-key")
    assert p.base_url == "https://integrate.api.nvidia.com/v1"
    assert p._api_key == "test-key"


def test_nvidia_nim_custom_url():
    p = NVIDIANIMProvider(api_key="k", base_url="https://custom.nvidia.com/v2")
    assert p.base_url == "https://custom.nvidia.com/v2"


def test_nvidia_nim_env_key(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "env-key-123")
    p = NVIDIANIMProvider()
    assert p._api_key == "env-key-123"


def test_nvidia_nim_env_url(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_BASE_URL", "https://env.nvidia.com")
    p = NVIDIANIMProvider(api_key="k")
    assert p.base_url == "https://env.nvidia.com"


@pytest.mark.asyncio
async def test_nvidia_nim_no_key_raises():
    p = NVIDIANIMProvider()
    # Ensure no env key
    p._api_key = None
    request = LLMRequest(
        model="meta/llama-3.3-70b-instruct",
        messages=[{"role": "user", "content": "hi"}],
    )
    with pytest.raises(RuntimeError, match="NVIDIA_NIM_API_KEY not set"):
        await p.complete(request)


@pytest.mark.asyncio
async def test_nvidia_nim_stream_not_implemented():
    p = NVIDIANIMProvider(api_key="k")
    request = LLMRequest(
        model="test",
        messages=[{"role": "user", "content": "hi"}],
    )
    with pytest.raises(NotImplementedError, match="NVIDIA NIM streaming"):
        async for _ in p.stream(request):
            pass


# ---------------------------------------------------------------------------
# MoonshotProvider
# ---------------------------------------------------------------------------


def test_moonshot_defaults():
    p = MoonshotProvider(api_key="moon-key")
    assert p.base_url == "https://api.moonshot.cn/v1"
    assert p._api_key == "moon-key"


def test_moonshot_custom_url():
    p = MoonshotProvider(api_key="k", base_url="https://custom.moonshot.io")
    assert p.base_url == "https://custom.moonshot.io"


def test_moonshot_env_key(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "moon-env-key")
    p = MoonshotProvider()
    assert p._api_key == "moon-env-key"


def test_moonshot_env_url(monkeypatch):
    monkeypatch.setenv("MOONSHOT_BASE_URL", "https://env.moonshot.cn")
    p = MoonshotProvider(api_key="k")
    assert p.base_url == "https://env.moonshot.cn"


@pytest.mark.asyncio
async def test_moonshot_no_key_raises():
    p = MoonshotProvider()
    p._api_key = None
    request = LLMRequest(
        model="moonshot-v1-8k",
        messages=[{"role": "user", "content": "hi"}],
    )
    with pytest.raises(RuntimeError, match="MOONSHOT_API_KEY not set"):
        await p.complete(request)


@pytest.mark.asyncio
async def test_moonshot_stream_not_implemented():
    p = MoonshotProvider(api_key="k")
    request = LLMRequest(
        model="test",
        messages=[{"role": "user", "content": "hi"}],
    )
    with pytest.raises(NotImplementedError, match="Moonshot streaming"):
        async for _ in p.stream(request):
            pass


# ---------------------------------------------------------------------------
# Explicit URL takes precedence over env
# ---------------------------------------------------------------------------


def test_explicit_url_overrides_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://env-url:1111")
    p = OllamaProvider(base_url="http://explicit:2222")
    assert p.base_url == "http://explicit:2222"


def test_explicit_key_overrides_env(monkeypatch):
    monkeypatch.setenv("NVIDIA_NIM_API_KEY", "env-key")
    p = NVIDIANIMProvider(api_key="explicit-key")
    assert p._api_key == "explicit-key"
