"""Tests for dharma_swarm.providers."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from dharma_swarm.model_hierarchy import default_model
from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.providers import (
    AnthropicProvider,
    ClaudeCodeProvider,
    CodexProvider,
    FireworksProvider,
    GroqProvider,
    ModelRouter,
    NVIDIANIMProvider,
    OpenAIProvider,
    OpenRouterFreeProvider,
    SiliconFlowProvider,
    TogetherProvider,
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
    assert router.get_provider(ProviderType.GROQ) is not None
    assert router.get_provider(ProviderType.SILICONFLOW) is not None
    assert router.get_provider(ProviderType.TOGETHER) is not None
    assert router.get_provider(ProviderType.FIREWORKS) is not None
    assert router.get_provider(ProviderType.NVIDIA_NIM) is not None
    assert router.get_provider(ProviderType.CLAUDE_CODE) is not None
    assert router.get_provider(ProviderType.CODEX) is not None
    assert router.get_provider(ProviderType.OPENROUTER_FREE) is not None


def test_groq_provider_init():
    p = GroqProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_siliconflow_provider_init():
    p = SiliconFlowProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_together_provider_init():
    p = TogetherProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_fireworks_provider_init():
    p = FireworksProvider(api_key="test-key")
    assert p._api_key == "test-key"


def test_nvidia_nim_provider_no_key():
    p = NVIDIANIMProvider(api_key=None)
    p._api_key = None
    with pytest.raises(RuntimeError, match="NVIDIA_NIM_API_KEY"):
        p._headers_or_raise()


def test_nvidia_nim_provider_uses_canonical_default_model():
    p = NVIDIANIMProvider(api_key="test-key")
    assert p._default_model == default_model(ProviderType.NVIDIA_NIM)


def test_nvidia_nim_provider_resolves_default_via_canonical_helper(monkeypatch):
    monkeypatch.setattr(
        "dharma_swarm.providers.canonical_default_model",
        lambda provider: "nim-from-helper",
    )
    p = NVIDIANIMProvider(api_key="test-key")
    assert p._default_model == "nim-from-helper"


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
    # The resolved command may be an absolute path (e.g. /usr/local/bin/codex)
    assert args[0].endswith("codex")
    assert args[1] == "exec"
    assert "--dangerously-bypass-approvals-and-sandbox" in args
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
    # Without explicit model, _preferred_model is None (resolved at call time)
    assert p._preferred_model is None
    # With explicit model, it's stored
    p2 = OpenRouterFreeProvider(api_key="test-key", model="meta-llama/llama-3.3-70b-instruct:free")
    assert p2._preferred_model == "meta-llama/llama-3.3-70b-instruct:free"


def test_openrouter_free_no_key():
    p = OpenRouterFreeProvider(api_key=None)
    # Clear env to test
    with patch.dict("os.environ", {}, clear=True):
        p._api_key = None
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            p._client_or_raise()


def test_openrouter_free_auto_discovery():
    """OpenRouterFreeProvider should auto-discover free models at runtime."""
    import asyncio

    async def _discover():
        return await OpenRouterFreeProvider.get_free_models()

    models = asyncio.run(_discover())
    assert len(models) >= 3, f"Expected >=3 free models, got {len(models)}"
    for model in models:
        assert model.endswith(":free"), f"Non-free model: {model}"


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
