"""Base contract for provider adapters used by the DGC engine."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator

from dharma_swarm.engine.events import CanonicalEvent


class Capability(str, Enum):
    """Normalized provider feature flags."""

    STREAMING = "streaming"
    TOOLS = "tools"
    THINKING = "thinking"
    SESSION_RESUME = "session_resume"
    MULTI_LINE_INPUT = "multi_line_input"


@dataclass(slots=True)
class ModelProfile:
    """Describes a model exposed by a provider."""

    model_id: str
    capabilities: set[Capability] = field(default_factory=set)
    context_window: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderConfig:
    """Provider configuration used by concrete adapters."""

    name: str
    model: str
    kwargs: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CompletionRequest:
    """Canonical completion request for adapters."""

    prompt: str
    session_id: str = ""
    system: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    metadata: dict[str, Any] = field(default_factory=dict)


class ProviderAdapter(ABC):
    """Abstract interface every provider adapter must satisfy."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def available_models(self) -> list[ModelProfile]: ...

    def supports(self, capability: Capability) -> bool:
        return any(capability in model.capabilities for model in self.available_models())

    @abstractmethod
    async def stream(self, request: CompletionRequest) -> AsyncIterator[CanonicalEvent]: ...

