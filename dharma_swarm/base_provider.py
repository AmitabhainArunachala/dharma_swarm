"""Provider algebra — shared structure enabling mutual catalysis.

Kauffman's autocatalytic sets: shared structure enables mutual catalysis
between providers.  BaseProvider extracts the copy-pasted patterns from
8 providers into a single composable abstraction.

Key normalizations:
    - Tool calls: Anthropic ``input`` / OpenAI ``arguments`` → ``parameters``
    - Messages: system prompt handling (strip vs prepend)
    - Client lifecycle: lazy init with import guard
    - Response: uniform LLMResponse construction
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from dharma_swarm.models import LLMRequest, LLMResponse


# ---------------------------------------------------------------------------
# Provider capabilities declaration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProviderCapabilities:
    """Declares what a provider supports — requisite variety at the type level.

    Ashby: the type system's variety must match runtime variety.
    """

    supports_streaming: bool = True
    supports_tools: bool = False
    supports_thinking: bool = False
    supports_system_prompt: bool = True
    max_context_tokens: int = 128_000
    provider_family: str = "unknown"
    requires_api_key: bool = True
    can_close: bool = False


# ---------------------------------------------------------------------------
# Base provider
# ---------------------------------------------------------------------------

class BaseProvider(ABC):
    """Abstract base for all LLM providers.

    Subclasses implement ``_create_client``, ``_raw_complete``, and
    optionally ``_raw_stream``.  Shared plumbing lives here.
    """

    capabilities: ProviderCapabilities = ProviderCapabilities()

    # -- Abstract interface -------------------------------------------------

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Send a completion request and return the full response."""

    @abstractmethod
    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Stream completion tokens as they arrive."""
        yield  # type: ignore[misc]

    # -- Lazy client --------------------------------------------------------

    def _ensure_client(
        self,
        *,
        client_attr: str = "_client",
        api_key: str | None,
        key_env_var: str,
        import_path: str,
        import_class: str,
        client_kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Lazy-init pattern replacing 8 copies of ``_client_or_raise``.

        Returns the cached client or creates one.  Raises RuntimeError if
        the API key is missing, ImportError if the SDK isn't installed.
        """
        existing = getattr(self, client_attr, None)
        if existing is not None:
            return existing

        if not api_key:
            raise RuntimeError(f"{key_env_var} not set")

        import importlib
        try:
            module = importlib.import_module(import_path)
            cls = getattr(module, import_class)
        except ImportError as exc:
            raise ImportError(f"pip install {import_path.split('.')[0]}") from exc

        kwargs = {"api_key": api_key, **(client_kwargs or {})}
        client = cls(**kwargs)
        setattr(self, client_attr, client)
        return client

    # -- Message normalization ----------------------------------------------

    @staticmethod
    def normalize_messages_openai(
        messages: list[dict[str, str]],
        system: str,
    ) -> list[dict[str, str]]:
        """OpenAI/OpenRouter convention: system as first message."""
        out: list[dict[str, str]] = []
        if system:
            out.append({"role": "system", "content": system})
        out.extend(messages)
        return out

    @staticmethod
    def strip_system_messages(
        messages: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        """Anthropic convention: system goes in kwargs, not messages."""
        return [m for m in messages if m.get("role") != "system"]

    # -- Tool call normalization --------------------------------------------

    @staticmethod
    def normalize_tool_calls(raw_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Canonical tool call format: ``{"id", "name", "parameters"}``.

        Anthropic uses ``input``, OpenAI uses ``arguments`` (as JSON string
        or dict).  This normalizes both to ``parameters`` (always dict).
        """
        normalized: list[dict[str, Any]] = []
        for tc in raw_calls:
            # Direct tool call (Anthropic style: id, name, input at top level)
            if "name" in tc and ("input" in tc or "arguments" in tc):
                raw_params = tc.get("input") or tc.get("arguments") or {}
                if isinstance(raw_params, str):
                    import json
                    try:
                        raw_params = json.loads(raw_params)
                    except (json.JSONDecodeError, TypeError):
                        raw_params = {"raw": raw_params}
                normalized.append({
                    "id": tc.get("id", ""),
                    "name": tc["name"],
                    "parameters": raw_params,
                })
            # OpenAI style: function nested under tc.function
            elif "function" in tc:
                fn = tc["function"]
                raw_params = fn.get("arguments") or {}
                if isinstance(raw_params, str):
                    import json
                    try:
                        raw_params = json.loads(raw_params)
                    except (json.JSONDecodeError, TypeError):
                        raw_params = {"raw": raw_params}
                normalized.append({
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "parameters": raw_params,
                })
            else:
                # Pass through unknown formats
                normalized.append(tc)
        return normalized

    # -- Response construction ----------------------------------------------

    @staticmethod
    def build_response(
        *,
        content: str,
        model: str,
        usage: dict[str, int] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        stop_reason: str | None = None,
        normalize_tools: bool = True,
    ) -> LLMResponse:
        """Unified response builder — single path for all providers."""
        calls = tool_calls or []
        if normalize_tools and calls:
            calls = BaseProvider.normalize_tool_calls(calls)
        return LLMResponse(
            content=content,
            model=model,
            usage=usage or {},
            tool_calls=calls,
            stop_reason=stop_reason,
        )

    # -- Closeable protocol -------------------------------------------------

    async def close(self) -> None:
        """Close any persistent connections.  Override if needed."""
