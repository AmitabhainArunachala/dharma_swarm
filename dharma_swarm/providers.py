"""Async LLM provider abstraction layer.

Wraps Anthropic and OpenAI async clients with a router for dispatching
by provider type. Missing API keys are tolerated at import; only raised on use.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
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
    """Build a ModelRouter with Anthropic and OpenAI providers.

    Missing API keys are tolerated here -- providers only raise on use.
    """
    return ModelRouter({
        ProviderType.ANTHROPIC: AnthropicProvider(),
        ProviderType.OPENAI: OpenAIProvider(),
        ProviderType.OPENROUTER: OpenRouterProvider(),
    })
