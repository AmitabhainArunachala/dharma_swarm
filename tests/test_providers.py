"""Tests for dharma_swarm.providers."""

import asyncio
import errno
from unittest.mock import AsyncMock, patch

import pytest

from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.providers import (
    AnthropicProvider,
    ClaudeCodeProvider,
    CodexProvider,
    ModelRouter,
    NVIDIANIMProvider,
    OpenAIProvider,
    OpenRouterFreeProvider,
    OpenRouterProvider,
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


def test_openai_provider_no_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
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


def test_openai_token_limit_kwargs_switches_for_gpt5_family():
    assert OpenAIProvider._token_limit_kwargs("gpt-5.4", 64) == {
        "max_completion_tokens": 64,
    }
    assert OpenAIProvider._token_limit_kwargs("o3-mini", 64) == {
        "max_completion_tokens": 64,
    }
    assert OpenAIProvider._token_limit_kwargs("gpt-4o", 64) == {
        "max_tokens": 64,
    }


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
    assert router.get_provider(ProviderType.NVIDIA_NIM) is not None
    assert router.get_provider(ProviderType.CLAUDE_CODE) is not None
    assert router.get_provider(ProviderType.CODEX) is not None
    assert router.get_provider(ProviderType.OPENROUTER_FREE) is not None


def test_nvidia_nim_provider_no_key():
    p = NVIDIANIMProvider(api_key=None)
    p._api_key = None
    with pytest.raises(RuntimeError, match="NVIDIA_NIM_API_KEY"):
        p._headers_or_raise()


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
@pytest.mark.parametrize(
    ("provider", "expected_label"),
    [
        (ClaudeCodeProvider(timeout=1), "claude-code"),
        (CodexProvider(timeout=1), "codex"),
    ],
)
async def test_subprocess_provider_timeout_escalates_to_kill_after_grace(
    provider,
    expected_label,
):
    spawned_proc = None

    async def fake_exec(*args, **kwargs):
        nonlocal spawned_proc
        spawned_proc = AsyncMock()
        spawned_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        spawned_proc.terminate = AsyncMock()
        spawned_proc.kill = AsyncMock()
        spawned_proc.wait = AsyncMock(side_effect=[asyncio.TimeoutError, None])
        return spawned_proc

    with patch("dharma_swarm.providers.asyncio.create_subprocess_exec", side_effect=fake_exec):
        result = await provider.complete(
            LLMRequest(model=expected_label, messages=[{"role": "user", "content": "test"}])
        )

    assert result.content == "TIMEOUT: exceeded limit"
    assert result.model == expected_label
    assert spawned_proc is not None
    spawned_proc.terminate.assert_awaited_once()
    spawned_proc.kill.assert_awaited_once()
    assert spawned_proc.wait.await_count == 2


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
async def test_claude_code_provider_truncates_at_50000():
    """Verify output is truncated to 50000 chars (not the old 5000)."""
    big_output = b"x" * 100_000

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

    assert len(result.content) == 50_000


@pytest.mark.asyncio
async def test_subprocess_output_not_truncated_at_5000():
    """Verify that 10000-char output is preserved (old bug was truncating at 5000)."""
    big_output = b"y" * 10_000

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

    assert len(result.content) > 5000
    assert len(result.content) == 10_000


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider", "missing_binary", "expected_label"),
    [
        (ClaudeCodeProvider(timeout=10), "claude", "claude-code"),
        (CodexProvider(timeout=10), "codex", "codex"),
    ],
)
async def test_subprocess_provider_missing_binary_returns_error_response(
    provider,
    missing_binary,
    expected_label,
):
    with patch(
        "dharma_swarm.providers.asyncio.create_subprocess_exec",
        side_effect=FileNotFoundError(
            errno.ENOENT,
            "No such file or directory",
            missing_binary,
        ),
    ):
        result = await provider.complete(
            LLMRequest(model=expected_label, messages=[{"role": "user", "content": "test"}])
        )

    assert result.model == expected_label
    assert result.content.startswith(f"ERROR: failed to launch {expected_label}:")
    assert missing_binary in result.content


# --- OpenRouterFreeProvider tests ---


def test_openrouter_free_provider_init():
    p = OpenRouterFreeProvider(api_key="test-key")
    assert p._api_key == "test-key"
    assert "free" in p._preferred_model


@pytest.mark.parametrize(
    ("provider", "expected_base_url"),
    [
        (OpenRouterProvider(api_key="test-key", base_url="https://router.proxy/v1/"), "https://router.proxy/v1"),
        (
            OpenRouterFreeProvider(
                api_key="test-key",
                model="deepseek/deepseek-r1:free",
                base_url="https://router.proxy/free/",
            ),
            "https://router.proxy/free",
        ),
    ],
)
def test_openrouter_clients_use_configured_base_url(provider, expected_base_url):
    with patch("openai.AsyncOpenAI") as mock_client:
        provider._client_or_raise()

    mock_client.assert_called_once_with(
        api_key="test-key",
        base_url=expected_base_url,
    )


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


# --- Memory Survival Directive Tests (IMPL-SAFETY) ---


def test_memory_survival_directive_in_subprocess_prompt():
    """Memory survival directive is injected into subprocess prompts."""
    from dharma_swarm.providers import MEMORY_SURVIVAL_DIRECTIVE
    provider = ClaudeCodeProvider(timeout=10)
    request = LLMRequest(
        model="claude-code",
        messages=[{"role": "user", "content": "Do a thing"}],
        system="You are a test agent.",
    )
    prompt = provider._build_prompt(request)
    assert "CONTEXT WILL BE DESTROYED" in prompt
    assert "externalize" in prompt.lower()


def test_memory_survival_directive_content():
    """Directive contains all required elements."""
    from dharma_swarm.providers import MEMORY_SURVIVAL_DIRECTIVE
    assert "MEMORY SURVIVAL" in MEMORY_SURVIVAL_DIRECTIVE
    assert "~/.dharma/shared/" in MEMORY_SURVIVAL_DIRECTIVE
    assert "~/.dharma/witness/" in MEMORY_SURVIVAL_DIRECTIVE
    assert "knowledge loss" in MEMORY_SURVIVAL_DIRECTIVE.lower()


@pytest.mark.asyncio
async def test_model_router_injects_survival_directive():
    """ModelRouter.complete injects survival directive into system prompt."""
    from dharma_swarm.providers import MEMORY_SURVIVAL_DIRECTIVE

    captured_request = None

    class CapturingProvider(AnthropicProvider):
        async def complete(self, request):
            nonlocal captured_request
            captured_request = request
            return LLMResponse(content="ok", model="mock")

    router = ModelRouter({ProviderType.ANTHROPIC: CapturingProvider(api_key="test")})
    request = LLMRequest(
        model="test",
        messages=[{"role": "user", "content": "hi"}],
        system="You are a coder.",
    )
    await router.complete(ProviderType.ANTHROPIC, request)
    assert captured_request is not None
    assert "CONTEXT WILL BE DESTROYED" in captured_request.system
