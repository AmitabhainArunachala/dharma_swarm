"""Async LLM provider abstraction layer.

Wraps Anthropic and OpenAI async clients with a router for dispatching
by provider type. Missing API keys are tolerated at import; only raised on use.
"""

from __future__ import annotations

import asyncio
import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType


class LLMProvider(ABC):
    """Abstract base for all LLM providers."""

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request and return the full response."""

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream completion tokens as they arrive."""
        yield  # type: ignore[misc]  # required for async generator signature


class AnthropicProvider(LLMProvider):
    """Provider backed by the Anthropic Messages API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ImportError("pip install anthropic") from exc
        self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    @staticmethod
    def _strip_system(msgs: list[dict[str, str]]) -> list[dict[str, str]]:
        return [m for m in msgs if m.get("role") != "system"]

    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._client_or_raise()
        kwargs: dict[str, Any] = dict(
            model=request.model, max_tokens=request.max_tokens,
            temperature=request.temperature,
            messages=self._strip_system(request.messages),
        )
        if request.system:
            kwargs["system"] = request.system
        if request.tools:
            kwargs["tools"] = request.tools
        resp = await client.messages.create(**kwargs)
        content = "".join(b.text for b in resp.content if hasattr(b, "text"))
        tool_calls = [
            {"id": b.id, "name": b.name, "input": b.input}
            for b in resp.content if b.type == "tool_use"
        ]
        return LLMResponse(
            content=content, model=resp.model,
            usage={"input_tokens": resp.usage.input_tokens,
                   "output_tokens": resp.usage.output_tokens},
            tool_calls=tool_calls, stop_reason=resp.stop_reason,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        client = self._client_or_raise()
        kwargs: dict[str, Any] = dict(
            model=request.model, max_tokens=request.max_tokens,
            temperature=request.temperature,
            messages=self._strip_system(request.messages),
        )
        if request.system:
            kwargs["system"] = request.system
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text


class OpenAIProvider(LLMProvider):
    """Provider backed by the OpenAI Chat Completions API."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(api_key=self._api_key)
        return self._client

    @staticmethod
    def _build_messages(msgs: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(msgs)
        return out

    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._client_or_raise()
        messages = self._build_messages(request.messages, request.system)
        kwargs: dict[str, Any] = dict(
            model=request.model, messages=messages,
            max_tokens=request.max_tokens, temperature=request.temperature,
        )
        if request.tools:
            kwargs["tools"] = request.tools
        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        tool_calls: list[dict[str, Any]] = [
            {"id": tc.id, "name": tc.function.name,
             "arguments": tc.function.arguments}
            for tc in (msg.tool_calls or [])
        ]
        return LLMResponse(
            content=msg.content or "", model=resp.model,
            usage={"prompt_tokens": resp.usage.prompt_tokens,
                   "completion_tokens": resp.usage.completion_tokens,
                   "total_tokens": resp.usage.total_tokens} if resp.usage else {},
            tool_calls=tool_calls, stop_reason=choice.finish_reason,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        client = self._client_or_raise()
        resp = await client.chat.completions.create(
            model=request.model, stream=True,
            messages=self._build_messages(request.messages, request.system),
            max_tokens=request.max_tokens, temperature=request.temperature,
        )
        async for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content


class OpenRouterProvider(LLMProvider):
    """Provider backed by OpenRouter (OpenAI-compatible API with custom base_url)."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        return self._client

    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._client_or_raise()
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        kwargs: dict[str, Any] = dict(
            model=request.model, messages=messages,
            max_tokens=request.max_tokens, temperature=request.temperature,
        )
        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        return LLMResponse(
            content=msg.content or "", model=resp.model or request.model,
            usage={"prompt_tokens": resp.usage.prompt_tokens,
                   "completion_tokens": resp.usage.completion_tokens,
                   "total_tokens": resp.usage.total_tokens} if resp.usage else {},
            tool_calls=[], stop_reason=choice.finish_reason,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        client = self._client_or_raise()
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        resp = await client.chat.completions.create(
            model=request.model, stream=True, messages=messages,
            max_tokens=request.max_tokens, temperature=request.temperature,
        )
        async for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content


class _SubprocessProvider(LLMProvider):
    """Base for providers that spawn CLI agents as subprocesses.

    Subclasses only need to define ``_cli_command`` and optionally
    override ``_build_cli_args``.
    """

    _cli_command: str = "claude"
    _cli_label: str = "claude-code"

    def __init__(self, timeout: int = 300, working_dir: str | None = None) -> None:
        self._timeout = timeout
        self._working_dir = working_dir or str(Path.home() / "dharma_swarm")

    def _build_prompt(self, request: LLMRequest) -> str:
        parts: list[str] = []
        if request.system:
            parts.append(request.system)
        for msg in request.messages:
            if msg.get("role") == "user":
                parts.append(msg["content"])
        prompt = "\n\n".join(parts)
        prompt += "\n\n## Communication\n"
        prompt += "- Write findings to ~/.dharma/shared/ (APPEND)\n"
        prompt += "- Read other agents' notes in ~/.dharma/shared/ first\n"
        return prompt

    def _build_cli_args(self, prompt: str) -> list[str]:
        return [self._cli_command, "-p", prompt, "--output-format", "text"]

    def _build_env(self) -> dict[str, str]:
        env = {**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        env.pop("CLAUDECODE", None)  # Allow nesting
        return env

    async def complete(self, request: LLMRequest) -> LLMResponse:
        shared = Path.home() / ".dharma" / "shared"
        shared.mkdir(parents=True, exist_ok=True)

        prompt = self._build_prompt(request)
        args = self._build_cli_args(prompt)
        env = self._build_env()

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self._working_dir,
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            proc.terminate()
            return LLMResponse(content="TIMEOUT: exceeded limit", model=self._cli_label)

        content = stdout.decode()[:5000] if stdout else ""
        if proc.returncode != 0 and not content:
            content = (
                f"ERROR (rc={proc.returncode}): "
                f"{stderr.decode()[:500] if stderr else 'unknown'}"
            )

        return LLMResponse(content=content, model=self._cli_label)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        response = await self.complete(request)
        yield response.content


class ClaudeCodeProvider(_SubprocessProvider):
    """Spawns real Claude Code instances via ``claude -p``.

    Each complete() call spawns a subprocess with full tool access.
    This is the REAL agent — file access, bash, everything.
    """

    _cli_command = "claude"
    _cli_label = "claude-code"


class CodexProvider(_SubprocessProvider):
    """Spawns OpenAI Codex CLI instances via ``codex``.

    Uses ``codex exec`` for non-interactive operation.
    """

    _cli_command = "codex"
    _cli_label = "codex"

    def _build_cli_args(self, prompt: str) -> list[str]:
        return [self._cli_command, "exec", prompt]

    def _build_env(self) -> dict[str, str]:
        env = {**os.environ}
        return env


class OpenRouterFreeProvider(LLMProvider):
    """OpenRouter with free-tier models only.

    Pre-configured with a rotation of free models for cost-zero support tasks.
    Falls back through the list if a model is unavailable.
    """

    # Free models on OpenRouter (verified March 2026)
    FREE_MODELS = [
        "meta-llama/llama-3.3-70b-instruct:free",
        "nousresearch/hermes-3-llama-3.1-405b:free",
        "google/gemma-3-27b-it:free",
        "mistralai/mistral-small-3.1-24b-instruct:free",
        "google/gemma-3-12b-it:free",
    ]

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        self._preferred_model = model or self.FREE_MODELS[0]
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        return self._client

    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._client_or_raise()
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)

        # Use the free model, ignore request.model
        model = self._preferred_model

        kwargs: dict[str, Any] = dict(
            model=model, messages=messages,
            max_tokens=min(request.max_tokens, 4096),
            temperature=request.temperature,
        )

        try:
            resp = await client.chat.completions.create(**kwargs)
        except Exception as exc:
            # Try fallback models
            for fallback in self.FREE_MODELS:
                if fallback == model:
                    continue
                try:
                    kwargs["model"] = fallback
                    resp = await client.chat.completions.create(**kwargs)
                    model = fallback
                    break
                except Exception:
                    continue
            else:
                return LLMResponse(
                    content=f"ERROR: All free models failed: {exc}",
                    model=model,
                )

        choice = resp.choices[0]
        msg = choice.message
        return LLMResponse(
            content=msg.content or "", model=resp.model or model,
            usage={"prompt_tokens": resp.usage.prompt_tokens,
                   "completion_tokens": resp.usage.completion_tokens,
                   "total_tokens": resp.usage.total_tokens} if resp.usage else {},
            tool_calls=[], stop_reason=choice.finish_reason,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        client = self._client_or_raise()
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        resp = await client.chat.completions.create(
            model=self._preferred_model, stream=True, messages=messages,
            max_tokens=min(request.max_tokens, 4096),
            temperature=request.temperature,
        )
        async for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content


class ModelRouter:
    """Routes LLM requests to the appropriate provider."""

    def __init__(self, providers: dict[ProviderType, LLMProvider]) -> None:
        self._providers = providers

    def get_provider(self, provider_type: ProviderType) -> LLMProvider:
        """Look up a provider by type. Raises KeyError if not registered."""
        try:
            return self._providers[provider_type]
        except KeyError:
            available = ", ".join(p.value for p in self._providers)
            raise KeyError(
                f"No provider for {provider_type.value!r}. "
                f"Available: [{available}]"
            ) from None

    async def complete(
        self, provider_type: ProviderType, request: LLMRequest,
    ) -> LLMResponse:
        """Dispatch a completion request to the named provider."""
        return await self.get_provider(provider_type).complete(request)


def create_default_router() -> ModelRouter:
    """Build a ModelRouter with all available providers.

    Missing API keys are tolerated here -- providers only raise on use.
    """
    return ModelRouter({
        ProviderType.ANTHROPIC: AnthropicProvider(),
        ProviderType.OPENAI: OpenAIProvider(),
        ProviderType.OPENROUTER: OpenRouterProvider(),
        ProviderType.CLAUDE_CODE: ClaudeCodeProvider(),
        ProviderType.CODEX: CodexProvider(),
        ProviderType.OPENROUTER_FREE: OpenRouterFreeProvider(),
    })
