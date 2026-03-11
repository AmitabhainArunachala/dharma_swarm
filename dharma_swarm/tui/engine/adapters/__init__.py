"""Provider adapter registry exports for the DGC TUI engine."""

from .base import (
    Capability,
    CompletionRequest,
    ModelProfile,
    ProviderAdapter,
    ProviderConfig,
)
from .claude import ClaudeAdapter, CLAUDE_CAPABILITIES
from .openrouter import OpenRouterAdapter, OPENROUTER_CAPABILITIES

__all__ = [
    "Capability",
    "CompletionRequest",
    "ModelProfile",
    "ProviderAdapter",
    "ProviderConfig",
    "ClaudeAdapter",
    "CLAUDE_CAPABILITIES",
    "OpenRouterAdapter",
    "OPENROUTER_CAPABILITIES",
]
