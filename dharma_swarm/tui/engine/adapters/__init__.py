"""Provider adapter registry exports for the DGC TUI engine."""

from .base import (
    Capability,
    CompletionRequest,
    ModelProfile,
    ProviderAdapter,
    ProviderConfig,
)
from .claude import ClaudeAdapter, CLAUDE_CAPABILITIES

__all__ = [
    "Capability",
    "CompletionRequest",
    "ModelProfile",
    "ProviderAdapter",
    "ProviderConfig",
    "ClaudeAdapter",
    "CLAUDE_CAPABILITIES",
]
