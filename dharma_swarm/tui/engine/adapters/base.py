"""Provider adapter base abstractions for the DGC TUI engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Flag, auto
from typing import Any, AsyncIterator

from ..events import CanonicalEventType


class Capability(Flag):
    """Provider capability flags used for runtime negotiation."""

    STREAMING = auto()
    TOOL_USE = auto()
    THINKING = auto()
    VISION = auto()
    JSON_SCHEMA = auto()
    PARALLEL_TOOLS = auto()
    RESUME = auto()
    COST_TRACKING = auto()
    CONTEXT_USAGE = auto()
    SYSTEM_PROMPT = auto()
    CANCEL = auto()


@dataclass(frozen=True, slots=True)
class ModelProfile:
    """Immutable capability and cost profile for one model."""

    provider_id: str
    model_id: str
    display_name: str
    capabilities: Capability = Capability(0)
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    cost_per_input_mtok: float | None = None
    cost_per_output_mtok: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def supports(self, cap: Capability) -> bool:
        return bool(self.capabilities & cap)


@dataclass(slots=True)
class ProviderConfig:
    """Runtime provider configuration."""

    provider_id: str
    api_key: str | None = None
    base_url: str | None = None
    default_model: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompletionRequest:
    """Provider-neutral request envelope for one streamed completion."""

    messages: list[dict[str, Any]]
    model: str | None = None
    system_prompt: str | None = None
    tools: list[dict[str, Any]] = field(default_factory=list)
    tool_choice: str | dict[str, Any] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    stop_sequences: list[str] = field(default_factory=list)
    enable_thinking: bool = False
    resume_session_id: str | None = None
    provider_options: dict[str, Any] = field(default_factory=dict)


class ProviderAdapter(ABC):
    """Abstract provider adapter interface used by the TUI engine."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Stable provider identifier (e.g. claude, openai, ollama)."""

    @abstractmethod
    async def list_models(self) -> list[ModelProfile]:
        """Return available model profiles."""

    @abstractmethod
    def get_profile(self, model_id: str | None = None) -> ModelProfile:
        """Resolve a profile for the requested or default model."""

    @abstractmethod
    async def stream(
        self,
        request: CompletionRequest,
        session_id: str,
    ) -> AsyncIterator[CanonicalEventType]:
        """Yield canonical events for one streaming request."""

    @abstractmethod
    async def cancel(self) -> None:
        """Cancel an active in-flight stream if supported."""

    @abstractmethod
    async def close(self) -> None:
        """Release provider resources and ensure no active process remains."""
