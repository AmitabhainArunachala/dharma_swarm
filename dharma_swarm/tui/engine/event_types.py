"""Typed dataclasses for all Claude Code NDJSON stream events.

Pure stdlib — no Pydantic, no Textual. These map 1:1 to the event types
emitted by ``claude --output-format stream-json``.

Event taxonomy (Claude Code CLI v2.1.69):
    system + init        -> SystemInit
    assistant            -> AssistantMessage  (text / tool_use / thinking blocks)
    user (tool_result)   -> ToolResult
    stream_event         -> StreamDelta       (requires --include-partial-messages)
    result               -> ResultMessage
    tool_progress        -> ToolProgress
    system + task_started  -> TaskStarted
    system + task_progress -> TaskProgress
    rate_limit_event     -> RateLimitEvent
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class SystemInit:
    """Emitted once at session start (requires ``--verbose``)."""

    session_id: str
    model: str
    tools: list[str]
    cwd: str
    permission_mode: str
    claude_code_version: str
    mcp_servers: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class AssistantMessage:
    """A complete assistant turn containing one or more content blocks.

    Content blocks are heterogeneous dicts with at least a ``"type"`` key:
        - ``{"type": "text", "text": "..."}``
        - ``{"type": "tool_use", "id": "...", "name": "...", "input": {...}}``
        - ``{"type": "thinking", "thinking": "..."}``
    """

    uuid: str
    session_id: str
    parent_tool_use_id: str | None
    content_blocks: list[dict[str, Any]]
    usage: dict[str, Any] | None = None
    stop_reason: str | None = None


@dataclass(slots=True)
class ToolResult:
    """Result of a tool invocation, surfaced as a ``user`` message."""

    uuid: str
    session_id: str
    tool_use_id: str
    tool_name: str
    content: str
    is_error: bool = False
    structured_result: dict[str, Any] | None = None
    duration_ms: int | None = None


@dataclass(slots=True)
class StreamDelta:
    """Token-level delta (requires ``--include-partial-messages``).

    ``delta_type`` is one of:
        - ``"text_delta"``
        - ``"thinking_delta"``
        - ``"input_json_delta"``
    """

    delta_type: str
    content: str
    block_index: int
    parent_tool_use_id: str | None = None


@dataclass(slots=True)
class ResultMessage:
    """Final event emitted when the session completes or errors."""

    session_id: str
    subtype: str  # "success", "error_max_turns", "error_tool", etc.
    is_error: bool
    total_cost_usd: float
    duration_ms: int
    num_turns: int
    result_text: str | None = None
    errors: list[str] = field(default_factory=list)
    model_usage: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolProgress:
    """Periodic heartbeat while a tool is executing."""

    tool_use_id: str
    tool_name: str
    elapsed_seconds: float


@dataclass(slots=True)
class TaskStarted:
    """Emitted when an Agent-spawned sub-task begins."""

    task_id: str
    tool_use_id: str
    description: str


@dataclass(slots=True)
class TaskProgress:
    """Periodic progress update for an Agent sub-task."""

    task_id: str
    usage: dict[str, Any]
    last_tool_name: str | None = None


@dataclass(slots=True)
class RateLimitEvent:
    """Rate-limit status notification."""

    status: str
    resets_at: int | None = None
    utilization: float | None = None
