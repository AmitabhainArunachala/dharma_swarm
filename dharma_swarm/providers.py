"""Async LLM provider abstraction layer.

Wraps Anthropic and OpenAI async clients with a router for dispatching
by provider type. Missing API keys are tolerated at import; only raised on use.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
import random
import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx

from dharma_swarm.models import LLMRequest, LLMResponse, ProviderType
from dharma_swarm.jikoku_instrumentation import jikoku_traced_provider  # type: ignore
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

    @jikoku_traced_provider
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


class NVIDIANIMProvider(LLMProvider):
    """Provider backed by NVIDIA NIM's OpenAI-compatible endpoint."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        default_model: str = "meta/llama-3.3-70b-instruct",
    ) -> None:
        self._api_key = api_key or os.environ.get("NVIDIA_NIM_API_KEY")
        self._base_url = (
            base_url
            or os.environ.get("NVIDIA_NIM_BASE_URL")
            or "https://integrate.api.nvidia.com/v1"
        ).rstrip("/")
        self._default_model = default_model

    @staticmethod
    def _build_messages(request: LLMRequest) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.extend(request.messages)
        return messages

    def _headers_or_raise(self) -> dict[str, str]:
        if not self._api_key:
            raise RuntimeError("NVIDIA_NIM_API_KEY not set")
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

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

        async with httpx.AsyncClient(timeout=120.0) as client:
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
        # Memory survival instinct — injected into EVERY subprocess agent
        prompt += MEMORY_SURVIVAL_DIRECTIVE
        return prompt

    def _build_cli_args(self, prompt: str) -> list[str]:
        return [self._cli_command, "-p", prompt, "--output-format", "text", "--model", "opus"]

    def _build_env(self) -> dict[str, str]:
        env = {**os.environ, "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"}
        env.pop("CLAUDECODE", None)  # Allow nesting
        return env

    @jikoku_traced_provider
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

    @jikoku_traced_provider
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


class OllamaProvider(LLMProvider):
    """Provider for local Ollama inference via REST API."""

    DEFAULT_BASE_URL = "http://localhost:11434"
    DEFAULT_MODEL = "llama3.2"

    def __init__(
        self,
        base_url: str | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._base_url = (
            base_url
            or os.environ.get("OLLAMA_BASE_URL")
            or self.DEFAULT_BASE_URL
        ).rstrip("/")
        self._model = model

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

    @jikoku_traced_provider
    async def complete(self, request: LLMRequest) -> LLMResponse:
        model = request.model or self._model
        messages = self._build_messages(request)
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self._base_url}/api/chat", json=payload)
            if resp.status_code in {404, 405}:
                # Back-compat for older Ollama instances.
                generate_payload = {
                    "model": model,
                    "prompt": self._build_prompt_from_messages(messages),
                    "stream": False,
                    "options": payload["options"],
                }
                resp = await client.post(
                    f"{self._base_url}/api/generate",
                    json=generate_payload,
                )
            if resp.status_code != 200:
                raise RuntimeError(
                    f"Ollama error {resp.status_code}: {resp.text[:300]}"
                )
            data = resp.json()

        if "message" in data:
            content = ((data.get("message") or {}).get("content") or "").strip()
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
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=payload,
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
                    continue
                breaker.record_success()
                total_tokens = int(
                    response.usage.get("total_tokens")
                    or (
                        response.usage.get("prompt_tokens", 0)
                        + response.usage.get("completion_tokens", 0)
                    )
                    or 0
                )
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
    return ModelRouter({
        ProviderType.ANTHROPIC: AnthropicProvider(),
        ProviderType.OPENAI: OpenAIProvider(),
        ProviderType.OPENROUTER: OpenRouterProvider(),
        ProviderType.NVIDIA_NIM: NVIDIANIMProvider(),
        ProviderType.CLAUDE_CODE: ClaudeCodeProvider(),
        ProviderType.CODEX: CodexProvider(),
        ProviderType.OPENROUTER_FREE: OpenRouterFreeProvider(),
        ProviderType.OLLAMA: OllamaProvider(),
    })
