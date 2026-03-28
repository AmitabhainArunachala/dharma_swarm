"""Async LLM provider abstraction layer.

Wraps Anthropic and OpenAI async clients with a router for dispatching
by provider type. Missing API keys are tolerated at import; only raised on use.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import inspect
import json
import os
import random
import shutil
import time
from abc import abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

from dharma_swarm.api_keys import (
    ANTHROPIC_API_KEY_ENV,
    CEREBRAS_API_KEY_ENV,
    CHUTES_API_KEY_ENV,
    FIREWORKS_API_KEY_ENV,
    GOOGLE_AI_API_KEY_ENV,
    GROQ_API_KEY_ENV,
    MISTRAL_API_KEY_ENV,
    NVIDIA_NIM_API_KEY_ENV,
    OLLAMA_API_KEY_ENV,
    OPENAI_API_KEY_ENV,
    OPENROUTER_API_KEY_ENV,
    SAMBANOVA_API_KEY_ENV,
    SILICONFLOW_API_KEY_ENV,
    TOGETHER_API_KEY_ENV,
)
from dharma_swarm.base_provider import BaseProvider, ProviderCapabilities
from dharma_swarm.codex_cli import dgc_codex_exec_prefix
from dharma_swarm.cost_tracker import _estimate_cost
from dharma_swarm.model_hierarchy import default_model as canonical_default_model
from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.jikoku_instrumentation import jikoku_traced_provider  # type: ignore
from dharma_swarm.ollama_config import (
    OLLAMA_DEFAULT_CLOUD_MODEL,
    OLLAMA_DEFAULT_LOCAL_MODEL,
    OLLAMA_LOCAL_BASE_URL,
    build_ollama_headers,
    get_ollama_cloud_frontier_chain,
    ollama_transport_mode,
    resolve_ollama_base_url,
    resolve_ollama_model,
)
from dharma_swarm.provider_policy import (
    ProviderPolicyRouter,
    ProviderRouteDecision,
    ProviderRouteRequest,
)
from dharma_swarm.router_retrospective import (
    RouteOutcomeRecord,
    build_route_retrospective,
)
from dharma_swarm.resilience import (
    CircuitBreakerRegistry,
    RetryPolicy,
    run_with_retry,
)
from dharma_swarm.router_v1 import (
    build_routing_signals,
    enrich_route_request,
    model_hint_for_provider,
)
from dharma_swarm.routing_memory import RoutingMemoryStore, build_task_signature
from dharma_swarm.telemetry_plane import (
    EconomicEventRecord,
    ExternalOutcomeRecord,
    PolicyDecisionRecord,
    RoutingDecisionRecord,
    TelemetryPlaneStore,
)


class LLMProvider(BaseProvider):
    """Abstract base for all LLM providers.

    Inherits shared plumbing from BaseProvider (normalize_tool_calls,
    normalize_messages_openai, strip_system_messages, build_response,
    _ensure_client).  Concrete providers override complete() and stream().
    """

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request and return the full response."""

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream completion tokens as they arrive."""
        yield  # type: ignore[misc]  # required for async generator signature


def _coerce_openrouter_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        chunks: list[str] = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    chunks.append(text)
                continue
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    chunks.append(text.strip())
                continue
            text = getattr(item, "text", None) or getattr(item, "content", None)
            if isinstance(text, str) and text.strip():
                chunks.append(text.strip())
        return "\n".join(chunks).strip()
    if isinstance(value, dict):
        text = value.get("text") or value.get("content")
        if isinstance(text, str):
            return text.strip()
    text = getattr(value, "text", None) or getattr(value, "content", None)
    if isinstance(text, str):
        return text.strip()
    return ""


def _extract_openai_compatible_message_text(message: Any) -> str:
    if isinstance(message, dict):
        content = _coerce_openrouter_text(message.get("content"))
        if content:
            return content
        reasoning = _coerce_openrouter_text(message.get("reasoning"))
        if reasoning:
            return reasoning
        return _coerce_openrouter_text(message.get("reasoning_details"))

    content = _coerce_openrouter_text(getattr(message, "content", None))
    if content:
        return content
    reasoning = _coerce_openrouter_text(getattr(message, "reasoning", None))
    if reasoning:
        return reasoning
    return _coerce_openrouter_text(getattr(message, "reasoning_details", None))


def _extract_openrouter_message_text(message: Any) -> str:
    return _extract_openai_compatible_message_text(message)


def _openai_completion_kwargs(model: str | None, max_tokens: int) -> dict[str, int]:
    normalized = (model or "").strip().lower()
    if normalized.startswith("gpt-5"):
        return {"max_completion_tokens": max(max_tokens, 256)}
    return {"max_tokens": max_tokens}


def _openai_temperature_kwargs(model: str | None, temperature: float) -> dict[str, float]:
    normalized = (model or "").strip().lower()
    if normalized.startswith("gpt-5"):
        return {}
    return {"temperature": temperature}


def _ollama_cloud_wire_model(model: str) -> str:
    stripped = (model or "").strip()
    if stripped.lower().endswith(":cloud"):
        return stripped[:-6]
    return stripped


def _ollama_cloud_completion_limit(model: str, max_tokens: int) -> int:
    normalized = _ollama_cloud_wire_model(model).lower()
    if normalized.startswith("glm-5"):
        return max(max_tokens, 384)
    if normalized.startswith("kimi-k2.5") or normalized.startswith("minimax-m2.7"):
        return max(max_tokens, 256)
    return max_tokens


def _ollama_cloud_model_candidates(model: str) -> tuple[str, ...]:
    requested = _ollama_cloud_wire_model(model)
    frontier_chain = tuple(
        _ollama_cloud_wire_model(candidate)
        for candidate in get_ollama_cloud_frontier_chain()
    )
    if requested in frontier_chain:
        ordered = [requested]
        ordered.extend(candidate for candidate in frontier_chain if candidate != requested)
        return tuple(ordered)
    return (requested,)


def _openrouter_free_fallback_models() -> list[str]:
    primary = canonical_default_model(ProviderType.OPENROUTER_FREE)
    roster = [
        primary,
        "google/gemma-3-27b-it:free",
        "mistralai/mistral-small-3.1-24b-instruct:free",
    ]
    seen: set[str] = set()
    unique: list[str] = []
    for model in roster:
        if not model or model in seen:
            continue
        seen.add(model)
        unique.append(model)
    return unique


class AnthropicProvider(LLMProvider):
    """Provider backed by the Anthropic Messages API."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        supports_thinking=True, supports_system_prompt=True,
        max_context_tokens=200_000, provider_family="anthropic",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(ANTHROPIC_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{ANTHROPIC_API_KEY_ENV} not set")
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:
            raise ImportError("pip install anthropic") from exc
        self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    @staticmethod
    def _strip_system(msgs: list[dict[str, str]]) -> list[dict[str, str]]:
        return [m for m in msgs if m.get("role") != "system"]

    @jikoku_traced_provider
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

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        max_context_tokens=128_000, provider_family="openai",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(OPENAI_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{OPENAI_API_KEY_ENV} not set")
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

    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._client_or_raise()
        messages = self._build_messages(request.messages, request.system)
        kwargs: dict[str, Any] = dict(
            model=request.model, messages=messages,
        )
        kwargs.update(_openai_completion_kwargs(request.model, request.max_tokens))
        kwargs.update(_openai_temperature_kwargs(request.model, request.temperature))
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
            content=_extract_openai_compatible_message_text(msg), model=resp.model,
            usage={"prompt_tokens": resp.usage.prompt_tokens,
                   "completion_tokens": resp.usage.completion_tokens,
                   "total_tokens": resp.usage.total_tokens} if resp.usage else {},
            tool_calls=tool_calls, stop_reason=choice.finish_reason,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        client = self._client_or_raise()
        kwargs: dict[str, Any] = {
            "model": request.model,
            "stream": True,
            "messages": self._build_messages(request.messages, request.system),
        }
        kwargs.update(_openai_completion_kwargs(request.model, request.max_tokens))
        kwargs.update(_openai_temperature_kwargs(request.model, request.temperature))
        resp = await client.chat.completions.create(**kwargs)
        async for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content


class OpenRouterProvider(LLMProvider):
    """Provider backed by OpenRouter (OpenAI-compatible API with custom base_url)."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        max_context_tokens=128_000, provider_family="openrouter",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(OPENROUTER_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{OPENROUTER_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        return self._client

    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._client_or_raise()
        messages: list[dict[str, Any]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        kwargs: dict[str, Any] = dict(
            model=request.model, messages=messages,
        )
        kwargs.update(_openai_completion_kwargs(request.model, request.max_tokens))
        kwargs.update(_openai_temperature_kwargs(request.model, request.temperature))
        if request.tools:
            kwargs["tools"] = request.tools
        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        tool_calls: list[dict[str, Any]] = [
            {
                "id": tc.id,
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            }
            for tc in (msg.tool_calls or [])
        ]
        return BaseProvider.build_response(
            content=_extract_openrouter_message_text(msg),
            model=resp.model or request.model,
            usage={"prompt_tokens": resp.usage.prompt_tokens,
                   "completion_tokens": resp.usage.completion_tokens,
                   "total_tokens": resp.usage.total_tokens} if resp.usage else {},
            tool_calls=tool_calls,
            stop_reason=choice.finish_reason,
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


class NVIDIANIMProvider(LLMProvider):
    """Provider backed by NVIDIA NIM's OpenAI-compatible endpoint."""

    capabilities = ProviderCapabilities(
        supports_streaming=False, supports_tools=True,
        max_context_tokens=128_000, provider_family="nvidia",
        can_close=True,
    )

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get(NVIDIA_NIM_API_KEY_ENV)
        self._base_url = (
            base_url
            or os.environ.get("NVIDIA_NIM_BASE_URL")
            or "https://integrate.api.nvidia.com/v1"
        ).rstrip("/")
        self._default_model = default_model or canonical_default_model(ProviderType.NVIDIA_NIM)
        self._client: httpx.AsyncClient | None = None

    @staticmethod
    def _build_messages(request: LLMRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        return messages

    def _headers_or_raise(self) -> dict[str, str]:
        if not self._api_key:
            raise RuntimeError(f"{NVIDIA_NIM_API_KEY_ENV} not set")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _get_client(self) -> httpx.AsyncClient:
        """Return a persistent httpx client, creating one if needed."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def close(self) -> None:
        """Close the persistent HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        payload = {
            "model": request.model or self._default_model,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.tools:
            payload["tools"] = request.tools

        client = self._get_client()
        resp = await client.post(
            f"{self._base_url}/chat/completions",
            json=payload,
            headers=self._headers_or_raise(),
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"NVIDIA NIM error {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()

        choices = data.get("choices") or []
        message = (choices[0].get("message") if choices else {}) or {}
        usage_raw = data.get("usage") or {}
        usage: dict[str, int] = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if key in usage_raw:
                try:
                    usage[key] = int(usage_raw[key])
                except (TypeError, ValueError):
                    continue

        tool_calls: list[dict[str, Any]] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            tool_calls.append(
                {
                    "id": tc.get("id"),
                    "name": fn.get("name"),
                    "arguments": fn.get("arguments"),
                }
            )

        finish_reason = choices[0].get("finish_reason") if choices else None
        return LLMResponse(
            content=message.get("content") or "",
            model=str(data.get("model") or payload["model"]),
            usage=usage,
            tool_calls=tool_calls,
            stop_reason=finish_reason,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        # For now keep stream semantics stable with a single final chunk.
        response = await self.complete(request)
        yield response.content


MEMORY_SURVIVAL_DIRECTIVE = (
    "\n\n## CRITICAL: MEMORY SURVIVAL\n"
    "YOUR CONTEXT WILL BE DESTROYED after this task completes. "
    "You will have NO memory of this conversation.\n"
    "Before your task ends, you MUST externalize:\n"
    "- Discoveries and patterns -> write to ~/.dharma/shared/<your_role>_notes.md (APPEND)\n"
    "- Important findings -> write to ~/.dharma/witness/ with timestamp\n"
    "- Lessons learned -> include in task result\n"
    "Read ~/.dharma/shared/ FIRST to see what other agents already found.\n"
    "Failure to externalize = permanent knowledge loss.\n"
)


class _SubprocessProvider(LLMProvider):
    """Base for providers that spawn CLI agents as subprocesses.

    Subclasses only need to define ``_cli_command`` and optionally
    override ``_build_cli_args``.
    """

    capabilities = ProviderCapabilities(
        supports_streaming=False, supports_tools=False,
        supports_system_prompt=True, max_context_tokens=200_000,
        provider_family="subprocess", requires_api_key=False,
    )

    _cli_command: str = "claude"
    _cli_label: str = "claude-code"

    @staticmethod
    def _resolve_binary(name: str) -> str:
        """Resolve a CLI binary to an absolute path.

        Shell aliases and user PATH entries are invisible to subprocesses
        spawned by the daemon, so we check well-known locations.
        """
        found = shutil.which(name)
        if found:
            return found
        fallbacks = [
            Path.home() / ".npm-global" / "bin" / name,
            Path("/opt/homebrew/bin") / name,
            Path("/usr/local/bin") / name,
        ]
        for p in fallbacks:
            if p.exists():
                return str(p)
        return name  # last resort — hope PATH has it

    def __init__(self, timeout: int = 300, working_dir: str | None = None) -> None:
        self._timeout = timeout
        self._working_dir = working_dir or str(Path.home() / "dharma_swarm")
        # Resolve once at init so subprocess calls always use an absolute path
        self._resolved_command = self._resolve_binary(self._cli_command)

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
        # Memory survival instinct — injected into EVERY subprocess agent
        prompt += MEMORY_SURVIVAL_DIRECTIVE
        return prompt

    def _build_cli_args(self, prompt: str, model: str | None = None) -> list[str]:
        resolved = model or "sonnet"
        return [self._resolved_command, "-p", prompt, "--output-format", "text", "--model", resolved]

    def _build_env(self) -> dict[str, str]:
        env = {**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        env.pop("CLAUDECODE", None)  # Allow nesting
        return env

    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        shared = Path.home() / ".dharma" / "shared"
        shared.mkdir(parents=True, exist_ok=True)

        prompt = self._build_prompt(request)
        args = self._build_cli_args(prompt, model=request.model)
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
            terminate_result = proc.terminate()
            if inspect.isawaitable(terminate_result):
                await terminate_result
            await proc.wait()
            return LLMResponse(content="TIMEOUT: exceeded limit", model=self._cli_label)

        content = stdout.decode()[:50_000] if stdout else ""
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

    def _build_cli_args(self, prompt: str, model: str | None = None) -> list[str]:
        args = dgc_codex_exec_prefix(cli_path=self._resolved_command)
        if model:
            args.extend(["-m", model])
        args.append(prompt)
        return args

    def _build_env(self) -> dict[str, str]:
        env = {**os.environ}
        return env


class OpenRouterFreeProvider(LLMProvider):
    """OpenRouter with free-tier models — auto-discovered at runtime.

    Queries the OpenRouter /api/v1/models endpoint to find currently available
    free models, ranked by context length.  Falls through the live roster on
    failure instead of a stale hardcoded list.
    """

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=False,
        max_context_tokens=32_000, provider_family="openrouter_free",
    )

    # Class-level cache: populated once per process by _discover_free_models().
    _discovered_models: list[str] = []
    _discovery_lock: asyncio.Lock | None = None
    _discovery_done: bool = False

    # Minimum context length to consider a model useful for council work.
    _MIN_CTX = 32_000

    # Preferred families — sorted to the top of the discovered list when present.
    _PREFERRED_PREFIXES = [
        "nvidia/nemotron",
        "qwen/",
        "meta-llama/",
        "mistralai/",
        "google/gemma",
        "openai/gpt-oss",
        "nousresearch/",
    ]

    @classmethod
    async def _discover_free_models(cls) -> list[str]:
        """Hit OpenRouter /api/v1/models and return IDs with $0 pricing, sorted by quality."""
        if cls._discovery_lock is None:
            cls._discovery_lock = asyncio.Lock()
        async with cls._discovery_lock:
            if cls._discovered_models:
                return cls._discovered_models
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get("https://openrouter.ai/api/v1/models")
                    resp.raise_for_status()
                    data = resp.json()

                free: list[tuple[str, int, int]] = []
                for m in data.get("data", []):
                    mid = m.get("id", "")
                    pricing = m.get("pricing", {})
                    prompt_cost = float(pricing.get("prompt", "1") or "1")
                    completion_cost = float(pricing.get("completion", "1") or "1")
                    if prompt_cost == 0 and completion_cost == 0:
                        ctx = int(m.get("context_length", 0))
                        if ctx >= cls._MIN_CTX and mid.endswith(":free"):
                            # Score preferred families higher
                            pref = 0
                            for i, prefix in enumerate(cls._PREFERRED_PREFIXES):
                                if mid.startswith(prefix):
                                    pref = len(cls._PREFERRED_PREFIXES) - i
                                    break
                            free.append((mid, ctx, pref))

                # Sort: preferred families first, then by context length descending
                free.sort(key=lambda x: (-x[2], -x[1]))
                cls._discovered_models = [mid for mid, _, _ in free]
                cls._discovery_done = True
            except Exception:
                # If discovery fails, use a minimal known-good fallback
                cls._discovered_models = _openrouter_free_fallback_models()
            return cls._discovered_models

    # Kept for backwards compatibility — but now populated from live data.
    FREE_MODELS: list[str] = []

    @classmethod
    async def get_free_models(cls) -> list[str]:
        """Return the live free model roster (auto-discovers on first call)."""
        if not cls._discovered_models:
            await cls._discover_free_models()
        return list(cls._discovered_models)

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(OPENROUTER_API_KEY_ENV)
        self._preferred_model = model  # May be None — resolved at call time
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{OPENROUTER_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        return self._client

    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._client_or_raise()
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)

        # Auto-discover if needed
        roster = await self.get_free_models()
        if not roster:
            return LLMResponse(
                content="ERROR: No free models discovered on OpenRouter",
                model="none",
            )

        # Resolve preferred model — validate it's in the live roster
        model = self._preferred_model
        if model and model not in roster:
            # Requested model isn't available — fall through to roster
            model = None
        if not model:
            model = roster[0]

        kwargs: dict[str, Any] = dict(
            model=model, messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )

        # Try preferred, then fall through the entire live roster
        tried: set[str] = set()
        last_exc: Exception | None = None
        for candidate in [model] + roster:
            if candidate in tried:
                continue
            tried.add(candidate)
            kwargs["model"] = candidate
            try:
                resp = await client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                msg = choice.message
                return LLMResponse(
                    content=_extract_openrouter_message_text(msg),
                    model=resp.model or candidate,
                    usage={"prompt_tokens": resp.usage.prompt_tokens,
                           "completion_tokens": resp.usage.completion_tokens,
                           "total_tokens": resp.usage.total_tokens} if resp.usage else {},
                    tool_calls=[], stop_reason=choice.finish_reason,
                )
            except Exception as exc:
                last_exc = exc
                continue

        return LLMResponse(
            content=f"ERROR: All {len(tried)} free models failed. Last error: {last_exc}",
            model=model,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        client = self._client_or_raise()
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        roster = await self.get_free_models()
        model = self._preferred_model
        fallback_model = canonical_default_model(ProviderType.OPENROUTER_FREE)
        if model and model not in roster:
            model = roster[0] if roster else fallback_model
        elif not model:
            model = roster[0] if roster else fallback_model
        resp = await client.chat.completions.create(
            model=model, stream=True, messages=messages,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
        )
        async for chunk in resp:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content


class OllamaProvider(LLMProvider):
    """Provider for Ollama local or cloud inference via the native REST API."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=False,
        max_context_tokens=32_000, provider_family="ollama",
        requires_api_key=False, can_close=True,
    )

    DEFAULT_BASE_URL = OLLAMA_LOCAL_BASE_URL
    DEFAULT_MODEL = OLLAMA_DEFAULT_LOCAL_MODEL
    DEFAULT_CLOUD_MODEL = OLLAMA_DEFAULT_CLOUD_MODEL

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get(OLLAMA_API_KEY_ENV)
        self._base_url = resolve_ollama_base_url(base_url=base_url, api_key=self._api_key)
        self._model = resolve_ollama_model(model, base_url=self._base_url, api_key=self._api_key)
        self._transport_mode = ollama_transport_mode(base_url=self._base_url, api_key=self._api_key)
        self._client: httpx.AsyncClient | None = None

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def default_model(self) -> str:
        return self._model

    @property
    def transport_mode(self) -> str:
        return self._transport_mode

    def _get_client(self) -> httpx.AsyncClient:
        """Return a persistent httpx client, creating one if needed."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=120.0)
        return self._client

    async def close(self) -> None:
        """Close the persistent HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def _build_messages(request: LLMRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        return messages

    @staticmethod
    def _build_prompt_from_messages(messages: list[dict[str, str]]) -> str:
        out: list[str] = []
        for msg in messages:
            role = msg.get("role", "user").capitalize()
            content = msg.get("content", "")
            out.append(f"{role}: {content}")
        return "\n\n".join(out)

    def _headers_or_raise(self) -> dict[str, str]:
        return build_ollama_headers(base_url=self._base_url, api_key=self._api_key)

    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self._model
        messages = self._build_messages(request)

        # Cloud models use the OpenAI-compatible /v1/chat/completions endpoint
        # because the native /api/chat mishandles thinking models (e.g.
        # kimi-k2.5:cloud returns empty content with output in "thinking").
        if self._transport_mode == "cloud_api":
            return await self._complete_openai_compat(model, messages, request)

        return await self._complete_native(model, messages, request)

    async def _complete_openai_compat(
        self, model: str, messages: list[dict[str, str]], request: LLMRequest,
    ) -> LLMResponse:
        """Cloud path: OpenAI-compatible /v1/chat/completions endpoint."""
        client = self._get_client()
        headers = self._headers_or_raise()
        headers["Content-Type"] = "application/json"
        attempts = _ollama_cloud_model_candidates(model)
        last_error: str | None = None

        for candidate in attempts:
            payload = {
                "model": candidate,
                "messages": messages,
                "max_tokens": _ollama_cloud_completion_limit(candidate, request.max_tokens),
                "temperature": request.temperature,
                "stream": False,
            }
            try:
                resp = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers,
                )
            except Exception as exc:
                last_error = str(exc)
                continue
            if resp.status_code != 200:
                last_error = f"{resp.status_code}: {resp.text[:300]}"
                continue
            data = resp.json()
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            content = _extract_openai_compatible_message_text(msg)
            usage_data = data.get("usage") or {}
            return LLMResponse(
                content=content,
                model=data.get("model") or candidate,
                usage={
                    "prompt_tokens": int(usage_data.get("prompt_tokens") or 0),
                    "completion_tokens": int(usage_data.get("completion_tokens") or 0),
                    "total_tokens": int(usage_data.get("total_tokens") or 0),
                },
                tool_calls=[],
                stop_reason=str(choice.get("finish_reason") or "stop"),
            )

        raise RuntimeError(
            f"Ollama cloud error after {len(attempts)} attempts: {last_error or 'unknown error'}"
        )

    async def _complete_native(
        self, model: str, messages: list[dict[str, str]], request: LLMRequest,
    ) -> LLMResponse:
        """Local path: native Ollama /api/chat endpoint."""
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        client = self._get_client()
        request_kwargs: dict[str, Any] = {"json": payload}
        headers = self._headers_or_raise()
        if headers:
            request_kwargs["headers"] = headers
        resp = await client.post(f"{self._base_url}/api/chat", **request_kwargs)
        if resp.status_code in {404, 405}:
            # Back-compat for older Ollama instances.
            generate_payload = {
                "model": model,
                "prompt": self._build_prompt_from_messages(messages),
                "stream": False,
                "options": payload["options"],
            }
            generate_kwargs: dict[str, Any] = {"json": generate_payload}
            if headers:
                generate_kwargs["headers"] = headers
            resp = await client.post(f"{self._base_url}/api/generate", **generate_kwargs)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Ollama error {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()

        if "message" in data:
            msg_data = data.get("message") or {}
            content = (msg_data.get("content") or "").strip()
            # Thinking models put output in "thinking" with empty "content".
            if not content:
                content = (msg_data.get("thinking") or "").strip()
        else:
            content = str(data.get("response") or "").strip()
        usage = {
            "prompt_tokens": int(data.get("prompt_eval_count") or 0),
            "completion_tokens": int(data.get("eval_count") or 0),
            "total_tokens": int(data.get("prompt_eval_count") or 0)
            + int(data.get("eval_count") or 0),
        }
        return LLMResponse(
            content=content,
            model=model,
            usage=usage,
            tool_calls=[],
            stop_reason=str(data.get("done_reason") or "stop"),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        model = request.model or self._model
        payload = {
            "model": model,
            "messages": self._build_messages(request),
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        client = self._get_client()
        stream_kwargs: dict[str, Any] = {"json": payload}
        headers = self._headers_or_raise()
        if headers:
            stream_kwargs["headers"] = headers
        async with client.stream(
            "POST",
            f"{self._base_url}/api/chat",
            **stream_kwargs,
        ) as resp:
                if resp.status_code != 200:
                    raise RuntimeError(
                        f"Ollama stream error {resp.status_code}: {await resp.aread()}"
                    )
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    message = chunk.get("message") or {}
                    content = message.get("content")
                    if content:
                        yield str(content)


class GroqProvider(LLMProvider):
    """Groq -- fastest inference (800-2600 t/s). GPT-OSS 120B, Kimi K2, Llama 4 Scout."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        max_context_tokens=131_072, provider_family="groq",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(GROQ_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{GROQ_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.groq.com/openai/v1",
        )
        return self._client

    @staticmethod
    def _build_messages(msgs: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(msgs)
        return out

    @jikoku_traced_provider
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
            content=_extract_openai_compatible_message_text(msg), model=resp.model,
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


class CerebrasProvider(LLMProvider):
    """Cerebras -- 2600 t/s inference. Qwen3 235B, GPT-OSS 120B, Llama 70B."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        max_context_tokens=131_072, provider_family="cerebras",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(CEREBRAS_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{CEREBRAS_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.cerebras.ai/v1",
        )
        return self._client

    @staticmethod
    def _build_messages(msgs: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(msgs)
        return out

    @jikoku_traced_provider
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
            content=_extract_openai_compatible_message_text(msg), model=resp.model,
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


class SiliconFlowProvider(LLMProvider):
    """Silicon Flow -- Chinese frontier models: GLM-5, MiniMax, Qwen 3.5 Coder, Kimi K2.5."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        max_context_tokens=262_144, provider_family="siliconflow",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(SILICONFLOW_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{SILICONFLOW_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.siliconflow.cn/v1",
        )
        return self._client

    @staticmethod
    def _build_messages(msgs: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(msgs)
        return out

    @jikoku_traced_provider
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


class TogetherProvider(LLMProvider):
    """Together AI -- frontier open-model lane with OpenAI-compatible tools."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        max_context_tokens=262_144, provider_family="together",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(TOGETHER_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{TOGETHER_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.together.xyz/v1",
        )
        return self._client

    @staticmethod
    def _build_messages(msgs: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(msgs)
        return out

    @jikoku_traced_provider
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


class FireworksProvider(LLMProvider):
    """Fireworks AI -- fast open-model inference with OpenAI-compatible tools."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        max_context_tokens=262_144, provider_family="fireworks",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(FIREWORKS_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{FIREWORKS_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.fireworks.ai/inference/v1",
        )
        return self._client

    @staticmethod
    def _build_messages(msgs: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(msgs)
        return out

    @jikoku_traced_provider
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


class GoogleAIProvider(LLMProvider):
    """Google AI Studio -- Gemini 2.5 Flash with 1M context. Backup provider."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        max_context_tokens=1_000_000, provider_family="google_ai",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(GOOGLE_AI_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{GOOGLE_AI_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        )
        return self._client

    @staticmethod
    def _build_messages(msgs: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(msgs)
        return out

    @jikoku_traced_provider
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


class SambaNovaProvider(LLMProvider):
    """SambaNova -- 100-200 tok/s on 405B via RDU hardware. Free tier persists forever."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        max_context_tokens=128_000, provider_family="sambanova",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(SAMBANOVA_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{SAMBANOVA_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.sambanova.ai/v1",
        )
        return self._client

    @staticmethod
    def _build_messages(msgs: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(msgs)
        return out

    @jikoku_traced_provider
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


class MistralProvider(LLMProvider):
    """Mistral AI -- 1B free tokens/month. Mistral Large, Codestral, Small."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=True,
        max_context_tokens=128_000, provider_family="mistral",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(MISTRAL_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{MISTRAL_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.mistral.ai/v1",
        )
        return self._client

    @staticmethod
    def _build_messages(msgs: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(msgs)
        return out

    @jikoku_traced_provider
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


class ChutesProvider(LLMProvider):
    """Chutes AI -- community-powered free inference. DeepSeek R1, Llama, Qwen."""

    capabilities = ProviderCapabilities(
        supports_streaming=True, supports_tools=False,
        max_context_tokens=64_000, provider_family="chutes",
    )

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.environ.get(CHUTES_API_KEY_ENV)
        self._client: Any = None

    def _client_or_raise(self) -> Any:
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RuntimeError(f"{CHUTES_API_KEY_ENV} not set")
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url="https://api.chutes.ai/v1",
        )
        return self._client

    @staticmethod
    def _build_messages(msgs: list[dict[str, str]], system: str) -> list[dict[str, str]]:
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(msgs)
        return out

    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        client = self._client_or_raise()
        messages = self._build_messages(request.messages, request.system)
        kwargs: dict[str, Any] = dict(
            model=request.model, messages=messages,
            max_tokens=request.max_tokens, temperature=request.temperature,
        )
        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        return LLMResponse(
            content=msg.content or "", model=resp.model,
            usage={"prompt_tokens": resp.usage.prompt_tokens,
                   "completion_tokens": resp.usage.completion_tokens,
                   "total_tokens": resp.usage.total_tokens} if resp.usage else {},
            tool_calls=[], stop_reason=choice.finish_reason,
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


class ModelRouter:
    """Routes LLM requests to the appropriate provider."""

    def __init__(
        self,
        providers: dict[ProviderType, LLMProvider],
        *,
        policy_router: ProviderPolicyRouter | None = None,
        retry_policy: RetryPolicy | None = None,
        breaker_registry: CircuitBreakerRegistry | None = None,
        routing_audit_path: Path | None = None,
        routing_memory: RoutingMemoryStore | None = None,
        routing_memory_path: Path | None = None,
        sticky_session_seconds: float = 300.0,
        sticky_min_tokens: int = 10_000,
        canary_percent: float | None = None,
        canary_provider: ProviderType | None = None,
        canary_model_hint: str | None = None,
        learning_enabled: bool | None = None,
        learning_alpha: float = 0.15,
        telemetry: TelemetryPlaneStore | None = None,
        telemetry_enabled: bool | None = None,
        telemetry_db_path: Path | None = None,
    ) -> None:
        self._providers = providers
        self._policy_router = policy_router or ProviderPolicyRouter()
        self._retry_policy = retry_policy or RetryPolicy()
        self._breaker_registry = breaker_registry or CircuitBreakerRegistry()
        sticky_seconds_env = os.environ.get("DGC_ROUTER_STICKY_SECONDS")
        sticky_min_tokens_env = os.environ.get("DGC_ROUTER_STICKY_MIN_TOKENS")
        effective_sticky_seconds = (
            float(sticky_seconds_env)
            if sticky_seconds_env not in (None, "")
            else sticky_session_seconds
        )
        effective_sticky_min_tokens = (
            int(sticky_min_tokens_env)
            if sticky_min_tokens_env not in (None, "")
            else sticky_min_tokens
        )
        self._sticky_session_seconds = max(0.0, effective_sticky_seconds)
        self._sticky_min_tokens = max(0, effective_sticky_min_tokens)
        self._session_affinity: dict[str, dict[str, Any]] = {}
        self._provider_rewards: dict[str, float] = {}
        self._provider_reward_counts: dict[str, int] = {}

        canary_percent_env = os.environ.get("DGC_ROUTER_CANARY_PERCENT")
        self._canary_percent = max(
            0.0,
            min(
                100.0,
                float(canary_percent_env)
                if canary_percent_env not in (None, "")
                else float(canary_percent or 0.0),
            ),
        )
        canary_provider_env = os.environ.get("DGC_ROUTER_CANARY_PROVIDER", "").strip()
        parsed_provider = self._parse_provider_type(canary_provider_env)
        self._canary_provider = canary_provider or parsed_provider
        if self._canary_provider not in self._providers:
            self._canary_provider = None
        self._canary_model_hint = (
            canary_model_hint
            or os.environ.get("DGC_ROUTER_CANARY_MODEL", "").strip()
            or None
        )

        learning_enabled_env = os.environ.get("DGC_ROUTER_LEARNING_ENABLED")
        if learning_enabled is None:
            self._learning_enabled = (
                str(learning_enabled_env).strip().lower() in {"1", "true", "yes", "on"}
            )
        else:
            self._learning_enabled = bool(learning_enabled)
        learning_alpha_env = os.environ.get("DGC_ROUTER_LEARNING_ALPHA")
        effective_learning_alpha = (
            float(learning_alpha_env)
            if learning_alpha_env not in (None, "")
            else learning_alpha
        )
        self._learning_alpha = max(0.01, min(1.0, float(effective_learning_alpha)))
        self._routing_memory = routing_memory
        routing_memory_disabled = os.environ.get(
            "DGC_ROUTER_MEMORY_DISABLE", "0"
        ).strip().lower() in {"1", "true", "yes", "on"}
        env_memory_path = os.environ.get("DGC_ROUTER_MEMORY_DB", "").strip()
        routing_memory_requested = (
            routing_memory_path is not None or bool(env_memory_path)
        )
        if (
            self._routing_memory is None
            and routing_memory_requested
            and not routing_memory_disabled
        ):
            configured_memory_path = routing_memory_path
            if configured_memory_path is None and env_memory_path:
                configured_memory_path = Path(env_memory_path)
            self._routing_memory = RoutingMemoryStore(configured_memory_path)
        default_audit = (
            Path.home() / ".dharma" / "logs" / "router" / "routing_decisions.jsonl"
        )
        self._routing_audit_path = routing_audit_path or Path(
            os.environ.get("DGC_ROUTER_AUDIT_LOG", str(default_audit))
        )
        self._routing_audit_enabled = os.environ.get(
            "DGC_ROUTER_AUDIT_DISABLE", "0"
        ) not in {"1", "true", "yes"}
        default_retrospective = (
            Path.home() / ".dharma" / "logs" / "router" / "route_retrospectives.jsonl"
        )
        self._routing_retrospective_path = Path(
            os.environ.get(
                "DGC_ROUTER_RETROSPECTIVE_LOG",
                str(default_retrospective),
            )
        )
        self._routing_retrospective_enabled = os.environ.get(
            "DGC_ROUTER_RETROSPECTIVE_DISABLE", "0"
        ) not in {"1", "true", "yes"}
        telemetry_enabled_env = os.environ.get("DGC_ROUTER_TELEMETRY_ENABLE", "").strip()
        env_telemetry_db = os.environ.get("DGC_ROUTER_TELEMETRY_DB", "").strip()
        telemetry_requested = telemetry_db_path is not None or bool(env_telemetry_db)
        if telemetry is not None:
            self._telemetry = telemetry
            self._telemetry_enabled = (
                bool(telemetry_enabled) if telemetry_enabled is not None else True
            )
        else:
            if telemetry_enabled is None:
                self._telemetry_enabled = (
                    telemetry_enabled_env.lower() in {"1", "true", "yes", "on"}
                    or telemetry_requested
                )
            else:
                self._telemetry_enabled = bool(telemetry_enabled)
            if self._telemetry_enabled:
                configured_telemetry_path = telemetry_db_path
                if configured_telemetry_path is None and env_telemetry_db:
                    configured_telemetry_path = Path(env_telemetry_db)
                self._telemetry = (
                    TelemetryPlaneStore(configured_telemetry_path)
                    if configured_telemetry_path is not None
                    else TelemetryPlaneStore()
                )
            else:
                self._telemetry = None

    @staticmethod
    def _parse_provider_type(raw: str) -> ProviderType | None:
        if not raw:
            return None
        normalized = raw.strip().lower()
        for provider in ProviderType:
            if provider.value == normalized:
                return provider
        return None

    @staticmethod
    def _inject_survival_directive(request: LLMRequest) -> LLMRequest:
        if request.system and MEMORY_SURVIVAL_DIRECTIVE not in request.system:
            return LLMRequest(
                model=request.model,
                messages=request.messages,
                system=request.system + MEMORY_SURVIVAL_DIRECTIVE,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                tools=request.tools,
            )
        return request

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
        """Dispatch a completion request to the named provider.

        Injects memory survival directive into the system prompt so every
        agent knows to externalize findings before context destruction.
        """
        return await self.get_provider(provider_type).complete(
            self._inject_survival_directive(request)
        )

    def route_request(
        self,
        route_request: ProviderRouteRequest,
        *,
        available_provider_types: list[ProviderType] | None = None,
    ) -> ProviderRouteDecision:
        available = [
            provider
            for provider in (available_provider_types or list(self._providers.keys()))
            if provider in self._providers
        ]
        return self._policy_router.route(
            route_request,
            available_providers=available,
        )

    @staticmethod
    def _request_with_model_hint(request: LLMRequest, model_hint: str | None) -> LLMRequest:
        if not model_hint or model_hint == request.model:
            return request
        return request.model_copy(update={"model": model_hint})

    @staticmethod
    def _response_indicates_failure(response: LLMResponse) -> str | None:
        body = response.content.strip().lower()
        if body.startswith("timeout:"):
            return "provider_timeout"
        if body.startswith("error:") or body.startswith("error (rc="):
            return "provider_error"
        return None

    def _provider_chain(
        self,
        decision: ProviderRouteDecision,
        *,
        available_provider_types: list[ProviderType] | None = None,
    ) -> list[ProviderType]:
        available = set(available_provider_types or self._providers.keys())
        chain: list[ProviderType] = []
        for provider in [decision.selected_provider, *decision.fallback_providers]:
            if provider in available and provider in self._providers and provider not in chain:
                chain.append(provider)
        return chain

    @staticmethod
    def _session_id_from_context(route_request: ProviderRouteRequest) -> str | None:
        raw = route_request.context.get("session_id")
        if raw is None:
            return None
        text = str(raw).strip()
        return text or None

    @staticmethod
    def _telemetry_scope(route_request: ProviderRouteRequest) -> dict[str, str]:
        context = route_request.context

        def _coerce(key: str) -> str:
            raw = context.get(key)
            if raw is None:
                return ""
            return str(raw).strip()

        return {
            "session_id": _coerce("session_id"),
            "task_id": _coerce("task_id"),
            "run_id": _coerce("run_id"),
        }

    @staticmethod
    def _telemetry_id(prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:16]}"

    @staticmethod
    def _token_usage(response: LLMResponse) -> tuple[int, int, int]:
        usage = dict(response.usage or {})
        prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
        completion_tokens = int(
            usage.get("completion_tokens") or usage.get("output_tokens") or 0
        )
        total_tokens = int(usage.get("total_tokens") or (prompt_tokens + completion_tokens) or 0)
        if total_tokens > 0 and prompt_tokens == 0 and completion_tokens == 0:
            prompt_tokens = total_tokens
        return (prompt_tokens, completion_tokens, total_tokens)

    async def _record_policy_telemetry(
        self,
        *,
        route_request: ProviderRouteRequest,
        decision: ProviderRouteDecision,
        planned_provider: ProviderType,
        planned_model: str,
        chain: list[ProviderType],
        task_signature: str,
    ) -> None:
        if self._telemetry is None:
            return
        scope = self._telemetry_scope(route_request)
        record = PolicyDecisionRecord(
            decision_id=self._telemetry_id("policy"),
            policy_name="provider_policy",
            decision="review" if decision.requires_human else "approved",
            status_before="preflight",
            status_after=decision.path.value,
            confidence=decision.confidence,
            reason="; ".join(decision.reasons),
            session_id=scope["session_id"],
            task_id=scope["task_id"],
            run_id=scope["run_id"],
            evidence=[{"reason": reason} for reason in decision.reasons[:12]],
            metadata={
                "task_signature": task_signature,
                "planned_provider": planned_provider.value,
                "planned_model": planned_model,
                "candidate_chain": [provider.value for provider in chain],
            },
        )
        try:
            await self._telemetry.record_policy_decision(record)
        except Exception:
            return

    async def _record_provider_attempt_outcome(
        self,
        *,
        route_request: ProviderRouteRequest,
        provider: ProviderType,
        model: str,
        route_path: str,
        task_signature: str,
        success: bool,
        latency_ms: float,
        total_tokens: int,
        error: str | None = None,
    ) -> None:
        if self._telemetry is None:
            return
        scope = self._telemetry_scope(route_request)
        record = ExternalOutcomeRecord(
            outcome_id=self._telemetry_id("outcome"),
            outcome_kind="provider_attempt",
            value=1.0 if success else 0.0,
            unit="success_ratio",
            confidence=1.0,
            status="succeeded" if success else "failed",
            subject_id=provider.value,
            summary=f"{route_request.action_name} via {provider.value}",
            session_id=scope["session_id"],
            task_id=scope["task_id"],
            run_id=scope["run_id"],
            metadata={
                "provider": provider.value,
                "model": model,
                "route_path": route_path,
                "task_signature": task_signature,
                "latency_ms": round(float(latency_ms), 3),
                "total_tokens": int(total_tokens),
                "error": error or "",
            },
        )
        try:
            await self._telemetry.record_external_outcome(record)
        except Exception:
            return

    async def _record_route_execution_telemetry(
        self,
        *,
        route_request: ProviderRouteRequest,
        decision: ProviderRouteDecision,
        selected_provider: ProviderType,
        selected_model: str,
        chain: list[ProviderType],
        task_signature: str,
        result: str,
        latency_ms: float,
        total_tokens: int,
        prompt_tokens: int,
        completion_tokens: int,
        failure_trace: list[dict[str, Any]],
        initial_provider: ProviderType,
        initial_model: str,
        response_model: str | None = None,
    ) -> None:
        if self._telemetry is None:
            return
        scope = self._telemetry_scope(route_request)
        estimated_cost_usd = _estimate_cost(selected_model, prompt_tokens, completion_tokens)
        routing_record = RoutingDecisionRecord(
            decision_id=self._telemetry_id("route"),
            action_name=route_request.action_name,
            route_path=decision.path.value,
            selected_provider=selected_provider.value,
            selected_model_hint=selected_model,
            confidence=decision.confidence,
            requires_human=decision.requires_human,
            session_id=scope["session_id"],
            task_id=scope["task_id"],
            run_id=scope["run_id"],
            reasons=list(decision.reasons),
            metadata={
                "result": result,
                "task_signature": task_signature,
                "candidate_chain": [provider.value for provider in chain],
                "initial_selected_provider": initial_provider.value,
                "initial_selected_model": initial_model,
                "fallback_selected": selected_provider != initial_provider,
                "latency_ms": round(float(latency_ms), 3),
                "prompt_tokens": int(prompt_tokens),
                "completion_tokens": int(completion_tokens),
                "total_tokens": int(total_tokens),
                "estimated_cost_usd": estimated_cost_usd,
                "response_model": response_model or "",
                "failure_trace": list(failure_trace),
            },
        )
        completion_outcome = ExternalOutcomeRecord(
            outcome_id=self._telemetry_id("outcome"),
            outcome_kind="provider_completion",
            value=1.0 if result == "success" else 0.0,
            unit="success_ratio",
            confidence=decision.confidence,
            status="observed" if result == "success" else "failed",
            subject_id=selected_provider.value,
            summary=f"{route_request.action_name} via {selected_provider.value} {result}",
            session_id=scope["session_id"],
            task_id=scope["task_id"],
            run_id=scope["run_id"],
            metadata={
                "provider": selected_provider.value,
                "model": selected_model,
                "route_path": decision.path.value,
                "task_signature": task_signature,
                "latency_ms": round(float(latency_ms), 3),
                "total_tokens": int(total_tokens),
                "estimated_cost_usd": estimated_cost_usd,
                "response_model": response_model or "",
            },
        )
        try:
            await self._telemetry.record_routing_decision(routing_record)
            await self._telemetry.record_external_outcome(completion_outcome)
            if total_tokens > 0 or estimated_cost_usd > 0.0:
                await self._telemetry.record_economic_event(
                    EconomicEventRecord(
                        event_id=self._telemetry_id("economic"),
                        event_kind="cost",
                        amount=estimated_cost_usd,
                        currency="USD",
                        counterparty=selected_provider.value,
                        summary=f"{route_request.action_name} via {selected_provider.value}",
                        session_id=scope["session_id"],
                        task_id=scope["task_id"],
                        run_id=scope["run_id"],
                        metadata={
                            "provider": selected_provider.value,
                            "model": selected_model,
                            "task_signature": task_signature,
                            "prompt_tokens": int(prompt_tokens),
                            "completion_tokens": int(completion_tokens),
                            "total_tokens": int(total_tokens),
                            "latency_ms": round(float(latency_ms), 3),
                        },
                    )
                )
        except Exception:
            return

    def _apply_session_affinity(
        self,
        chain: list[ProviderType],
        *,
        route_request: ProviderRouteRequest,
        model_hints: dict[ProviderType, str | None],
    ) -> tuple[list[ProviderType], bool]:
        session_id = self._session_id_from_context(route_request)
        if not session_id or self._sticky_session_seconds <= 0:
            return (chain, False)
        sticky = self._session_affinity.get(session_id)
        if not sticky:
            return (chain, False)
        age = time.monotonic() - float(sticky.get("updated_at", 0.0))
        if age > self._sticky_session_seconds:
            self._session_affinity.pop(session_id, None)
            return (chain, False)
        if int(route_request.estimated_tokens) < self._sticky_min_tokens:
            return (chain, False)
        preferred_provider = sticky.get("provider")
        if not isinstance(preferred_provider, ProviderType):
            return (chain, False)
        if preferred_provider not in chain:
            return (chain, False)
        if chain and chain[0] == preferred_provider:
            return (chain, False)
        reordered = [preferred_provider] + [item for item in chain if item != preferred_provider]
        sticky_model = sticky.get("model")
        if isinstance(sticky_model, str) and sticky_model:
            model_hints[preferred_provider] = sticky_model
        return (reordered, True)

    def _record_session_affinity(
        self,
        route_request: ProviderRouteRequest,
        *,
        provider: ProviderType,
        model: str,
        token_estimate: int,
    ) -> None:
        session_id = self._session_id_from_context(route_request)
        if not session_id:
            return
        self._session_affinity[session_id] = {
            "provider": provider,
            "model": model,
            "token_estimate": int(token_estimate),
            "updated_at": time.monotonic(),
        }

    def _apply_canary(
        self,
        chain: list[ProviderType],
        *,
        model_hints: dict[ProviderType, str | None],
    ) -> tuple[list[ProviderType], bool]:
        if (
            self._canary_percent <= 0
            or self._canary_provider is None
            or self._canary_provider not in self._providers
        ):
            return (chain, False)
        if random.random() * 100.0 >= self._canary_percent:
            return (chain, False)
        canary_provider = self._canary_provider
        reordered = [canary_provider] + [item for item in chain if item != canary_provider]
        if self._canary_model_hint:
            model_hints[canary_provider] = self._canary_model_hint
        return (reordered, True)

    @staticmethod
    def _reward_key(provider: ProviderType, model: str) -> str:
        return f"{provider.value}:{model}"

    def _reward_for(self, provider: ProviderType, model: str) -> float:
        return self._provider_rewards.get(self._reward_key(provider, model), 0.0)

    def _apply_reward_ranking(
        self,
        chain: list[ProviderType],
        *,
        model_hints: dict[ProviderType, str | None],
    ) -> list[ProviderType]:
        if not self._learning_enabled or len(chain) <= 1:
            return chain
        scored: list[tuple[float, int, ProviderType]] = []
        for idx, provider in enumerate(chain):
            model = model_hints.get(provider) or ""
            reward = self._reward_for(provider, model)
            scored.append((reward, -idx, provider))
        scored.sort(reverse=True)
        return [provider for _, _, provider in scored]

    def _apply_routing_memory_ranking(
        self,
        chain: list[ProviderType],
        *,
        task_signature: str,
        model_hints: dict[ProviderType, str | None],
    ) -> tuple[list[ProviderType], bool, dict[str, float]]:
        if self._routing_memory is None or len(chain) <= 1:
            return (chain, False, {})
        ranked, scores = self._routing_memory.rank_candidates(
            task_signature,
            chain,
            model_hints=model_hints,
        )
        snapshot = {
            provider.value: lane.blended_score for provider, lane in scores.items()
        }
        return (ranked, ranked != chain, snapshot)

    def _update_reward(self, provider: ProviderType, model: str, reward: float) -> None:
        if not self._learning_enabled:
            return
        key = self._reward_key(provider, model)
        prev = self._provider_rewards.get(key)
        if prev is None:
            self._provider_rewards[key] = reward
        else:
            alpha = self._learning_alpha
            self._provider_rewards[key] = (1.0 - alpha) * prev + alpha * reward
        self._provider_reward_counts[key] = self._provider_reward_counts.get(key, 0) + 1

    def _append_routing_audit(self, record: dict[str, Any]) -> None:
        if not self._routing_audit_enabled:
            return
        try:
            self._routing_audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self._routing_audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        except Exception:
            # Auditing must never break inference traffic.
            return

    def _append_route_retrospective(self, artifact: Any) -> None:
        if not self._routing_retrospective_enabled:
            return
        try:
            self._routing_retrospective_path.parent.mkdir(parents=True, exist_ok=True)
            with self._routing_retrospective_path.open("a", encoding="utf-8") as handle:
                handle.write(artifact.model_dump_json() + "\n")
        except Exception:
            return

    def reward_snapshot(self) -> dict[str, float]:
        return dict(self._provider_rewards)

    def routing_memory_snapshot(self, *, task_signature: str | None = None) -> list[Any]:
        if self._routing_memory is None:
            return []
        return self._routing_memory.snapshot(task_signature=task_signature)

    def routing_memory_summary(self, *, limit: int = 8) -> list[Any]:
        if self._routing_memory is None:
            return []
        return self._routing_memory.top_routes(limit=limit)

    def task_signature_for(
        self,
        route_request: ProviderRouteRequest,
        request: LLMRequest,
    ) -> str:
        enriched_request = enrich_route_request(route_request, request)
        return build_task_signature(
            action_name=enriched_request.action_name,
            context=enriched_request.context,
        )

    def _record_routing_memory_outcome(
        self,
        *,
        provider: ProviderType,
        model: str,
        task_signature: str,
        action_name: str,
        route_path: str,
        success: bool,
        latency_ms: float,
        total_tokens: int,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self._routing_memory is None:
            return
        try:
            self._routing_memory.record_outcome(
                provider=provider,
                model=model,
                task_signature=task_signature,
                action_name=action_name,
                route_path=route_path,
                success=success,
                latency_ms=latency_ms,
                total_tokens=total_tokens,
                quality_score=1.0 if success else 0.0,
                error=error,
                metadata=metadata,
            )
        except Exception:
            # Routing memory must not break hot-path inference.
            return

    def record_task_feedback(
        self,
        *,
        route_request: ProviderRouteRequest,
        request: LLMRequest,
        decision: ProviderRouteDecision,
        quality_score: float,
        total_tokens: int = 0,
        latency_ms: float = 0.0,
        success: bool | None = None,
        model: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        enriched_request = enrich_route_request(route_request, request)
        task_signature = build_task_signature(
            action_name=enriched_request.action_name,
            context=enriched_request.context,
        )
        selected_model = model or decision.selected_model_hint or request.model
        quality = max(0.0, min(1.0, float(quality_score)))
        success_flag = bool(success) if success is not None else quality >= 0.6
        self._record_routing_memory_outcome(
            provider=decision.selected_provider,
            model=selected_model,
            task_signature=task_signature,
            action_name=enriched_request.action_name,
            route_path=decision.path.value,
            success=success_flag,
            latency_ms=latency_ms,
            total_tokens=total_tokens,
            error=None if success_flag else "quality_feedback_failure",
            metadata={
                **(metadata or {}),
                "feedback_source": "posthoc",
                "quality_score": quality,
            },
        )
        reward = max(-1.0, min(1.0, (quality - 0.5) * 2.0))
        self._update_reward(decision.selected_provider, selected_model, reward)
        self._append_routing_audit(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "action": enriched_request.action_name,
                "path": decision.path.value,
                "provider_selected": decision.selected_provider.value,
                "model_selected": selected_model,
                "task_signature": task_signature,
                "quality_score": quality,
                "success": success_flag,
                "latency_ms": round(float(latency_ms), 3),
                "total_tokens": int(total_tokens),
                "result": "feedback",
            }
        )
        try:
            retrospective = build_route_retrospective(
                RouteOutcomeRecord(
                    action_name=enriched_request.action_name,
                    route_path=decision.path.value,
                    selected_provider=decision.selected_provider.value,
                    selected_model=selected_model,
                    confidence=decision.confidence,
                    quality_score=quality,
                    result="success" if success_flag else "failed",
                    task_signature=task_signature,
                    latency_ms=latency_ms,
                    total_tokens=total_tokens,
                    reasons=list(decision.reasons),
                    signals={
                        key: enriched_request.context.get(key)
                        for key in (
                            "language_code",
                            "complexity_tier",
                            "complexity_score",
                            "context_tier",
                            "token_estimate",
                        )
                        if key in enriched_request.context
                    },
                    failures=[
                        {"error": str(metadata.get("error"))[:240]}
                        for metadata in [metadata or {}]
                        if metadata.get("error")
                    ],
                )
            )
            if retrospective is not None:
                self._append_route_retrospective(retrospective)
        except Exception:
            # Retrospectives are advisory and must never affect routing.
            pass
        return task_signature

    async def complete_for_task(
        self,
        route_request: ProviderRouteRequest,
        request: LLMRequest,
        *,
        available_provider_types: list[ProviderType] | None = None,
    ) -> tuple[ProviderRouteDecision, LLMResponse]:
        signals = build_routing_signals(request)
        enriched_request = enrich_route_request(route_request, request)
        decision = self.route_request(
            enriched_request,
            available_provider_types=available_provider_types,
        )
        chain = self._provider_chain(
            decision,
            available_provider_types=available_provider_types,
        )
        if not chain:
            raise RuntimeError("No available providers after routing filter")
        task_signature = build_task_signature(
            action_name=enriched_request.action_name,
            context=enriched_request.context,
        )
        preserve_requested_model = bool(
            enriched_request.context.get("preserve_requested_model")
        )
        pinned_provider = (
            available_provider_types[0]
            if preserve_requested_model
            and available_provider_types
            and len(available_provider_types) == 1
            else None
        )

        model_hints: dict[ProviderType, str | None] = {}
        if pinned_provider == decision.selected_provider:
            model_hints[decision.selected_provider] = request.model
        else:
            model_hints[decision.selected_provider] = model_hint_for_provider(
                decision.selected_provider,
                default_hint=decision.selected_model_hint,
                signals=signals,
            )
        for idx, provider in enumerate(decision.fallback_providers):
            default_hint = (
                decision.fallback_model_hints[idx]
                if idx < len(decision.fallback_model_hints)
                else None
            )
            if pinned_provider == provider:
                model_hints[provider] = request.model
            else:
                model_hints[provider] = model_hint_for_provider(
                    provider,
                    default_hint=default_hint,
                    signals=signals,
                )

        chain, affinity_applied = self._apply_session_affinity(
            chain,
            route_request=enriched_request,
            model_hints=model_hints,
        )
        memory_applied = False
        routing_memory_scores: dict[str, float] = {}
        if not affinity_applied:
            chain, memory_applied, routing_memory_scores = self._apply_routing_memory_ranking(
                chain,
                task_signature=task_signature,
                model_hints=model_hints,
            )
            chain = self._apply_reward_ranking(
                chain,
                model_hints=model_hints,
            )
        chain, canary_applied = self._apply_canary(
            chain,
            model_hints=model_hints,
        )
        if affinity_applied:
            decision = replace(
                decision,
                reasons=[*decision.reasons, "session_affinity_applied"],
            )
        if memory_applied:
            decision = replace(
                decision,
                reasons=[*decision.reasons, "routing_memory_applied"],
            )
        if canary_applied:
            decision = replace(
                decision,
                reasons=[*decision.reasons, "canary_applied"],
            )

        started_at = datetime.now(timezone.utc)
        failure_trace: list[dict[str, Any]] = []
        selected_provider = decision.selected_provider
        selected_model = model_hints.get(selected_provider) or request.model
        planned_provider = chain[0]
        planned_model = model_hints.get(planned_provider) or request.model
        await self._record_policy_telemetry(
            route_request=enriched_request,
            decision=decision,
            planned_provider=planned_provider,
            planned_model=planned_model,
            chain=chain,
            task_signature=task_signature,
        )

        for provider_type in chain:
            request_for_provider = self._request_with_model_hint(
                request,
                model_hints.get(provider_type),
            )
            reward_model = request_for_provider.model
            lane_key = f"{provider_type.value}:{request_for_provider.model}"
            breaker = self._breaker_registry.get(lane_key)
            if not breaker.allow_request():
                self._update_reward(provider_type, reward_model, -0.35)
                self._record_routing_memory_outcome(
                    provider=provider_type,
                    model=reward_model,
                    task_signature=task_signature,
                    action_name=enriched_request.action_name,
                    route_path=decision.path.value,
                    success=False,
                    latency_ms=0.0,
                    total_tokens=0,
                    error="circuit_open",
                    metadata={"reason": "breaker_open"},
                )
                failure_trace.append(
                    {
                        "provider": provider_type.value,
                        "model": request_for_provider.model,
                        "error": "circuit_open",
                        "state": breaker.state.value,
                    }
                )
                await self._record_provider_attempt_outcome(
                    route_request=enriched_request,
                    provider=provider_type,
                    model=reward_model,
                    route_path=decision.path.value,
                    task_signature=task_signature,
                    success=False,
                    latency_ms=0.0,
                    total_tokens=0,
                    error="circuit_open",
                )
                continue

            def _on_retry_error(exc: Exception, attempt: int) -> None:
                breaker.record_failure()
                self._update_reward(provider_type, reward_model, -0.25)
                failure_trace.append(
                    {
                        "provider": provider_type.value,
                        "model": request_for_provider.model,
                        "attempt": attempt,
                        "error": str(exc)[:300],
                        "state": breaker.state.value,
                    }
                )

            try:
                attempt_started = time.monotonic()
                response = await run_with_retry(
                    lambda: self.complete(provider_type, request_for_provider),
                    policy=self._retry_policy,
                    on_error=_on_retry_error,
                )
                latency_ms = (time.monotonic() - attempt_started) * 1000.0
                response_error = self._response_indicates_failure(response)
                if response_error:
                    breaker.record_failure()
                    self._update_reward(provider_type, reward_model, -0.50)
                    self._record_routing_memory_outcome(
                        provider=provider_type,
                        model=reward_model,
                        task_signature=task_signature,
                        action_name=enriched_request.action_name,
                        route_path=decision.path.value,
                        success=False,
                        latency_ms=latency_ms,
                        total_tokens=0,
                        error=response_error,
                    )
                    failure_trace.append(
                        {
                            "provider": provider_type.value,
                            "model": request_for_provider.model,
                            "error": response_error,
                            "state": breaker.state.value,
                        }
                    )
                    await self._record_provider_attempt_outcome(
                        route_request=enriched_request,
                        provider=provider_type,
                        model=reward_model,
                        route_path=decision.path.value,
                        task_signature=task_signature,
                        success=False,
                        latency_ms=latency_ms,
                        total_tokens=0,
                        error=response_error,
                    )
                    continue
                breaker.record_success()
                prompt_tokens, completion_tokens, total_tokens = self._token_usage(response)
                self._record_routing_memory_outcome(
                    provider=provider_type,
                    model=reward_model,
                    task_signature=task_signature,
                    action_name=enriched_request.action_name,
                    route_path=decision.path.value,
                    success=True,
                    latency_ms=latency_ms,
                    total_tokens=total_tokens,
                    metadata={
                        "language_code": signals.language_code,
                        "complexity_tier": signals.complexity_tier,
                    },
                )
                reward = max(0.0, 1.0 - min(total_tokens, 200_000) / 200_000)
                self._update_reward(provider_type, reward_model, reward)
                await self._record_provider_attempt_outcome(
                    route_request=enriched_request,
                    provider=provider_type,
                    model=reward_model,
                    route_path=decision.path.value,
                    task_signature=task_signature,
                    success=True,
                    latency_ms=latency_ms,
                    total_tokens=total_tokens,
                )
                selected_provider = provider_type
                selected_model = request_for_provider.model
                self._record_session_affinity(
                    enriched_request,
                    provider=selected_provider,
                    model=selected_model,
                    token_estimate=signals.token_estimate,
                )
                routed_decision = decision
                if selected_provider != decision.selected_provider:
                    routed_decision = replace(
                        decision,
                        selected_provider=selected_provider,
                        selected_model_hint=selected_model,
                        fallback_providers=[
                            item for item in chain if item != selected_provider
                        ],
                        fallback_model_hints=[
                            model_hints.get(item, "") or ""
                            for item in chain
                            if item != selected_provider
                        ],
                        reasons=[*decision.reasons, "fallback_provider_selected"],
                    )
                self._append_routing_audit(
                    {
                        "timestamp": started_at.isoformat(),
                        "action": enriched_request.action_name,
                        "path": decision.path.value,
                        "provider_selected": routed_decision.selected_provider.value,
                        "model_selected": selected_model,
                        "chain": [item.value for item in chain],
                        "reward_scores": {
                            item.value: self._reward_for(
                                item, model_hints.get(item) or ""
                            )
                            for item in chain
                        },
                        "routing_memory_scores": routing_memory_scores,
                        "task_signature": task_signature,
                        "reasons": routed_decision.reasons,
                        "signals": {
                            "language_code": signals.language_code,
                            "complexity_tier": signals.complexity_tier,
                            "complexity_score": signals.complexity_score,
                            "token_estimate": signals.token_estimate,
                        },
                        "failures": failure_trace,
                        "result": "success",
                    }
                )
                await self._record_route_execution_telemetry(
                    route_request=enriched_request,
                    decision=routed_decision,
                    selected_provider=selected_provider,
                    selected_model=selected_model,
                    chain=chain,
                    task_signature=task_signature,
                    result="success",
                    latency_ms=latency_ms,
                    total_tokens=total_tokens,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    failure_trace=failure_trace,
                    initial_provider=planned_provider,
                    initial_model=planned_model,
                    response_model=response.model,
                )
                # Enrich response with provider info for trajectory capture
                if not response.provider:
                    response.provider = selected_provider.value
                return (routed_decision, response)
            except Exception as exc:
                latency_ms = (
                    (time.monotonic() - attempt_started) * 1000.0
                    if "attempt_started" in locals()
                    else 0.0
                )
                self._update_reward(provider_type, reward_model, -1.0)
                self._record_routing_memory_outcome(
                    provider=provider_type,
                    model=reward_model,
                    task_signature=task_signature,
                    action_name=enriched_request.action_name,
                    route_path=decision.path.value,
                    success=False,
                    latency_ms=latency_ms,
                    total_tokens=0,
                    error=str(exc)[:120],
                )
                failure_trace.append(
                    {
                        "provider": provider_type.value,
                        "model": request_for_provider.model,
                        "error": str(exc)[:300],
                        "state": breaker.state.value,
                    }
                )
                await self._record_provider_attempt_outcome(
                    route_request=enriched_request,
                    provider=provider_type,
                    model=reward_model,
                    route_path=decision.path.value,
                    task_signature=task_signature,
                    success=False,
                    latency_ms=latency_ms,
                    total_tokens=0,
                    error=str(exc)[:120],
                )

        self._append_routing_audit(
            {
                "timestamp": started_at.isoformat(),
                "action": enriched_request.action_name,
                "path": decision.path.value,
                "provider_selected": decision.selected_provider.value,
                "model_selected": selected_model,
                "chain": [item.value for item in chain],
                "reward_scores": {
                    item.value: self._reward_for(item, model_hints.get(item) or "")
                    for item in chain
                },
                "routing_memory_scores": routing_memory_scores,
                "task_signature": task_signature,
                "reasons": decision.reasons,
                "signals": {
                    "language_code": signals.language_code,
                    "complexity_tier": signals.complexity_tier,
                    "complexity_score": signals.complexity_score,
                    "token_estimate": signals.token_estimate,
                },
                "failures": failure_trace,
                "result": "failed",
            }
        )
        await self._record_route_execution_telemetry(
            route_request=enriched_request,
            decision=decision,
            selected_provider=planned_provider,
            selected_model=planned_model,
            chain=chain,
            task_signature=task_signature,
            result="failed",
            latency_ms=0.0,
            total_tokens=0,
            prompt_tokens=0,
            completion_tokens=0,
            failure_trace=failure_trace,
            initial_provider=planned_provider,
            initial_model=planned_model,
        )
        trace_preview = "; ".join(
            f"{item.get('provider')}:{item.get('error')}" for item in failure_trace[-6:]
        )
        raise RuntimeError(
            f"All providers failed in chain {[item.value for item in chain]} :: {trace_preview}"
        )


def create_default_router() -> ModelRouter:
    """Build a ModelRouter with all available providers.

    Missing API keys are tolerated here -- providers only raise on use.
    """
    from dharma_swarm.runtime_provider import create_default_provider_map

    return ModelRouter(create_default_provider_map())
