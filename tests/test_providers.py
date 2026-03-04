"""Tests for dharma_swarm.providers."""

import pytest

from dharma_swarm.models import LLMRequest, ProviderType
from dharma_swarm.providers import (
    AnthropicProvider,
    ModelRouter,
    OpenAIProvider,
    create_default_router,
)


def test_anthropic_provider_init():
    p = AnthropicProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_anthropic_provider_no_key():
    p = AnthropicProvider(api_key=None)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        p._client_or_raise()


def test_openai_provider_init():
    p = OpenAIProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_openai_provider_no_key():
    p = OpenAIProvider(api_key=None)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        p._client_or_raise()


def test_strip_system():
    msgs = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
    ]
    result = AnthropicProvider._strip_system(msgs)
    assert len(result) == 1
    assert result[0]["role"] == "user"


def test_build_messages():
    msgs = [{"role": "user", "content": "hi"}]
    result = OpenAIProvider._build_messages(msgs, system="be helpful")
    assert len(result) == 2
    assert result[0]["role"] == "system"


def test_model_router_missing():
    router = ModelRouter({})
    with pytest.raises(KeyError, match="No provider"):
        router.get_provider(ProviderType.ANTHROPIC)


def test_model_router_lookup():
    p = AnthropicProvider(api_key="test")
    router = ModelRouter({ProviderType.ANTHROPIC: p})
    assert router.get_provider(ProviderType.ANTHROPIC) is p


def test_create_default_router():
    router = create_default_router()
    assert router.get_provider(ProviderType.ANTHROPIC) is not None
    assert router.get_provider(ProviderType.OPENAI) is not None
