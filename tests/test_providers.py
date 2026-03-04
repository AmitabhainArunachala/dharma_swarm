"""Tests for dharma_swarm.providers."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.providers import (
    AnthropicProvider,
    ClaudeCodeProvider,
    CodexProvider,
    ModelRouter,
    OpenAIProvider,
    OpenRouterFreeProvider,
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
    assert router.get_provider(ProviderType.CLAUDE_CODE) is not None
    assert router.get_provider(ProviderType.CODEX) is not None
    assert router.get_provider(ProviderType.OPENROUTER_FREE) is not None


# --- ClaudeCodeProvider tests ---


def test_claude_code_provider_init():
    p = ClaudeCodeProvider(timeout=120, working_dir="/tmp/test")
    assert p._timeout == 120
    assert p._working_dir == "/tmp/test"


def test_claude_code_provider_default_dir():
    p = ClaudeCodeProvider()
    assert "dharma_swarm" in p._working_dir


@pytest.mark.asyncio
async def test_claude_code_provider_builds_prompt():
    """Verify prompt is assembled from system + user messages."""
    request = LLMRequest(
        model="claude-code",
        messages=[
            {"role": "user", "content": "Do the thing"},
            {"role": "assistant", "content": "OK"},
            {"role": "user", "content": "Now check results"},
        ],
        system="You are a test agent.",
    )

    captured_prompt = None

    async def fake_exec(*args, **kwargs):
        nonlocal captured_prompt
        # args: "claude", "-p", <prompt>, "--output-format", "text"
        captured_prompt = args[2]

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"done", b""))
        mock_proc.returncode = 0
        mock_proc.terminate = AsyncMock()
        return mock_proc

    provider = ClaudeCodeProvider(timeout=10)
    with patch("dharma_swarm.providers.asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await provider.complete(request)

    assert captured_prompt is not None
    assert "You are a test agent." in captured_prompt
    assert "Do the thing" in captured_prompt
    assert "Now check results" in captured_prompt
    # Assistant messages should NOT be included
    assert "OK" not in captured_prompt
    assert result.content == "done"
    assert result.model == "claude-code"


@pytest.mark.asyncio
async def test_claude_code_provider_timeout():
    """Verify timeout returns a TIMEOUT response instead of raising."""

    async def fake_exec(*args, **kwargs):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        mock_proc.terminate = AsyncMock()
        return mock_proc

    provider = ClaudeCodeProvider(timeout=1)
    with patch("dharma_swarm.providers.asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await provider.complete(
            LLMRequest(model="claude-code", messages=[{"role": "user", "content": "test"}])
        )

    assert "TIMEOUT" in result.content
    assert result.model == "claude-code"


@pytest.mark.asyncio
async def test_claude_code_provider_error():
    """Verify non-zero exit code with no stdout returns error content."""

    async def fake_exec(*args, **kwargs):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"something broke"))
        mock_proc.returncode = 1
        mock_proc.terminate = AsyncMock()
        return mock_proc

    provider = ClaudeCodeProvider(timeout=10)
    with patch("dharma_swarm.providers.asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await provider.complete(
            LLMRequest(model="claude-code", messages=[{"role": "user", "content": "test"}])
        )

    assert "ERROR (rc=1)" in result.content
    assert "something broke" in result.content


@pytest.mark.asyncio
async def test_claude_code_provider_truncates_output():
    """Verify output is truncated to 5000 chars."""
    big_output = b"x" * 10000

    async def fake_exec(*args, **kwargs):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(big_output, b""))
        mock_proc.returncode = 0
        mock_proc.terminate = AsyncMock()
        return mock_proc

    provider = ClaudeCodeProvider(timeout=10)
    with patch("dharma_swarm.providers.asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await provider.complete(
            LLMRequest(model="claude-code", messages=[{"role": "user", "content": "test"}])
        )

    assert len(result.content) == 5000


# --- CodexProvider tests ---


def test_codex_provider_init():
    p = CodexProvider(timeout=60, working_dir="/tmp/test")
    assert p._timeout == 60
    assert p._cli_command == "codex"
    assert p._cli_label == "codex"


def test_codex_provider_cli_args():
    p = CodexProvider()
    args = p._build_cli_args("test prompt")
    assert args[:2] == ["codex", "exec"]
    assert "test prompt" in args


@pytest.mark.asyncio
async def test_codex_provider_complete():
    """Verify Codex spawns subprocess and returns result."""

    async def fake_exec(*args, **kwargs):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"codex result", b""))
        mock_proc.returncode = 0
        mock_proc.terminate = AsyncMock()
        return mock_proc

    provider = CodexProvider(timeout=10)
    with patch("dharma_swarm.providers.asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await provider.complete(
            LLMRequest(model="codex", messages=[{"role": "user", "content": "test"}])
        )

    assert result.content == "codex result"
    assert result.model == "codex"


# --- OpenRouterFreeProvider tests ---


def test_openrouter_free_provider_init():
    p = OpenRouterFreeProvider(api_key="test-key")
    assert p._api_key == "test-key"
    assert "free" in p._preferred_model


def test_openrouter_free_no_key():
    p = OpenRouterFreeProvider(api_key=None)
    # Clear env to test
    with patch.dict("os.environ", {}, clear=True):
        p._api_key = None
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            p._client_or_raise()


def test_openrouter_free_models_list():
    assert len(OpenRouterFreeProvider.FREE_MODELS) >= 3
    for model in OpenRouterFreeProvider.FREE_MODELS:
        assert ":free" in model
