"""Canonical provider-agnostic event schema for DGC TUI.

This module defines the normalized event envelope and payloads used by the
provider adapter layer. Events here are intentionally decoupled from any
single provider wire format (Claude NDJSON, OpenAI SSE, Ollama NDJSON, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import time
from typing import Any

SCHEMA_VERSION = 1


@dataclass(slots=True)
class CanonicalEvent:
    """Base envelope shared by all normalized events."""

    type: str
    schema_version: int = SCHEMA_VERSION
    timestamp: float = field(default_factory=time.time)
    provider_id: str = ""
    session_id: str = ""
    raw: dict[str, Any] | None = None


@dataclass(slots=True)
class SessionStart(CanonicalEvent):
    type: str = "session_start"
    model: str = ""
    provider_session_id: str | None = None
    capabilities: list[str] = field(default_factory=list)
    tools_available: list[str] = field(default_factory=list)
    system_info: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SessionEnd(CanonicalEvent):
    type: str = "session_end"
    success: bool = True
    error_code: str | None = None
    error_message: str | None = None


@dataclass(slots=True)
class TextDelta(CanonicalEvent):
    type: str = "text_delta"
    content: str = ""
    content_index: int = 0
    role: str = "assistant"


@dataclass(slots=True)
class TextComplete(CanonicalEvent):
    type: str = "text_complete"
    content: str = ""
    content_index: int = 0
    role: str = "assistant"


@dataclass(slots=True)
class ThinkingDelta(CanonicalEvent):
    type: str = "thinking_delta"
    content: str = ""


@dataclass(slots=True)
class ThinkingComplete(CanonicalEvent):
    type: str = "thinking_complete"
    content: str = ""
    is_redacted: bool = False


@dataclass(slots=True)
class ToolCallStart(CanonicalEvent):
    type: str = "tool_call_start"
    tool_call_id: str = ""
    tool_name: str = ""
    arguments_partial: str = ""


@dataclass(slots=True)
class ToolArgumentsDelta(CanonicalEvent):
    type: str = "tool_args_delta"
    tool_call_id: str = ""
    delta: str = ""


@dataclass(slots=True)
class ToolCallComplete(CanonicalEvent):
    type: str = "tool_call_complete"
    tool_call_id: str = ""
    tool_name: str = ""
    arguments: str = ""
    provider_options: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResult(CanonicalEvent):
    type: str = "tool_result"
    tool_call_id: str = ""
    tool_name: str = ""
    content: str = ""
    is_error: bool = False
    structured_result: dict[str, Any] | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class ToolProgress(CanonicalEvent):
    type: str = "tool_progress"
    tool_call_id: str = ""
    tool_name: str = ""
    elapsed_seconds: float = 0.0


@dataclass(slots=True)
class TaskStarted(CanonicalEvent):
    type: str = "task_started"
    task_id: str = ""
    description: str = ""
    parent_tool_call_id: str | None = None


@dataclass(slots=True)
class TaskProgress(CanonicalEvent):
    type: str = "task_progress"
    task_id: str = ""
    summary: str = ""


@dataclass(slots=True)
class TaskComplete(CanonicalEvent):
    type: str = "task_complete"
    task_id: str = ""
    success: bool = True
    summary: str = ""


@dataclass(slots=True)
class UsageReport(CanonicalEvent):
    type: str = "usage"
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    thinking_tokens: int = 0
    total_cost_usd: float | None = None
    model_breakdown: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ErrorEvent(CanonicalEvent):
    type: str = "error"
    code: str = ""
    message: str = ""
    retryable: bool = False
    retry_after_seconds: float | None = None


@dataclass(slots=True)
class RateLimitEvent(CanonicalEvent):
    type: str = "rate_limit"
    status: str = ""
    utilization: float | None = None
    resets_at: float | None = None


@dataclass(slots=True)
class PermissionDecisionEvent(CanonicalEvent):
    type: str = "permission_decision"
    action_id: str = ""
    tool_name: str = ""
    risk: str = ""
    decision: str = ""
    rationale: str = ""
    policy_source: str = ""
    requires_confirmation: bool = False
    command_prefix: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PermissionResolutionEvent(CanonicalEvent):
    type: str = "permission_resolution"
    action_id: str = ""
    resolution: str = ""
    resolved_at: str = ""
    actor: str = ""
    summary: str = ""
    note: str | None = None
    enforcement_state: str = "recorded_only"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PermissionOutcomeEvent(CanonicalEvent):
    type: str = "permission_outcome"
    action_id: str = ""
    outcome: str = ""
    outcome_at: str = ""
    source: str = ""
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


EVENT_TYPES: dict[str, type[CanonicalEvent]] = {
    "session_start": SessionStart,
    "session_end": SessionEnd,
    "text_delta": TextDelta,
    "text_complete": TextComplete,
    "thinking_delta": ThinkingDelta,
    "thinking_complete": ThinkingComplete,
    "tool_call_start": ToolCallStart,
    "tool_args_delta": ToolArgumentsDelta,
    "tool_call_complete": ToolCallComplete,
    "tool_result": ToolResult,
    "tool_progress": ToolProgress,
    "task_started": TaskStarted,
    "task_progress": TaskProgress,
    "task_complete": TaskComplete,
    "usage": UsageReport,
    "error": ErrorEvent,
    "rate_limit": RateLimitEvent,
    "permission_decision": PermissionDecisionEvent,
    "permission_resolution": PermissionResolutionEvent,
    "permission_outcome": PermissionOutcomeEvent,
}


CanonicalEventType = (
    SessionStart
    | SessionEnd
    | TextDelta
    | TextComplete
    | ThinkingDelta
    | ThinkingComplete
    | ToolCallStart
    | ToolArgumentsDelta
    | ToolCallComplete
    | ToolResult
    | ToolProgress
    | TaskStarted
    | TaskProgress
    | TaskComplete
    | UsageReport
    | ErrorEvent
    | RateLimitEvent
    | PermissionDecisionEvent
    | PermissionResolutionEvent
    | PermissionOutcomeEvent
)
