"""Parse a single NDJSON line from Claude Code CLI into a typed event.

This module is the critical bridge between raw CLI output and the typed
event system. It handles every event type emitted by
``claude --output-format stream-json`` (v2.1.69).

Usage::

    from dharma_swarm.tui.engine.stream_parser import parse_ndjson_line

    event = parse_ndjson_line(line)
    if isinstance(event, AssistantMessage):
        for block in event.content_blocks:
            ...
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .event_types import (
    AssistantMessage,
    RateLimitEvent,
    ResultMessage,
    StreamDelta,
    SystemInit,
    TaskProgress,
    TaskStarted,
    ToolProgress,
    ToolResult,
)

logger = logging.getLogger(__name__)

# Union of all event types this parser can produce.
Event = (
    SystemInit
    | AssistantMessage
    | ToolResult
    | StreamDelta
    | ResultMessage
    | ToolProgress
    | TaskStarted
    | TaskProgress
    | RateLimitEvent
)


def parse_ndjson_line(line: str) -> Event | None:
    """Parse a single NDJSON line into a typed event dataclass.

    Args:
        line: A single line of NDJSON output from ``claude --output-format stream-json``.

    Returns:
        A typed event dataclass, or ``None`` if the line is unparseable or
        represents an unknown event type.
    """
    line = line.strip()
    if not line:
        return None

    try:
        data: dict[str, Any] = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        logger.debug("Failed to parse NDJSON line: %s", line[:200])
        return None

    event_type = data.get("type")
    if event_type is None:
        return None

    if event_type == "system":
        return _parse_system(data)
    if event_type == "assistant":
        return _parse_assistant(data)
    if event_type == "user":
        return _parse_user(data)
    if event_type == "stream_event":
        return _parse_stream_event(data)
    if event_type == "result":
        return _parse_result(data)
    if event_type == "tool_progress":
        return _parse_tool_progress(data)
    if event_type == "rate_limit_event":
        return _parse_rate_limit(data)

    logger.debug("Unknown event type: %s", event_type)
    return None


# ---------------------------------------------------------------------------
# Internal dispatchers
# ---------------------------------------------------------------------------


def _parse_system(data: dict[str, Any]) -> SystemInit | TaskStarted | TaskProgress | None:
    """Dispatch system events by subtype."""
    subtype = data.get("subtype")

    if subtype == "init":
        return SystemInit(
            session_id=data.get("session_id", ""),
            model=data.get("model", ""),
            tools=data.get("tools", []),
            cwd=data.get("cwd", ""),
            permission_mode=data.get("permissionMode", data.get("permission_mode", "")),
            claude_code_version=data.get("claude_code_version", ""),
            mcp_servers=data.get("mcp_servers", []),
        )

    if subtype == "task_started":
        return TaskStarted(
            task_id=data.get("task_id", ""),
            tool_use_id=data.get("tool_use_id", ""),
            description=data.get("description", ""),
        )

    if subtype == "task_progress":
        return TaskProgress(
            task_id=data.get("task_id", ""),
            usage=data.get("usage", {}),
            last_tool_name=data.get("last_tool_name"),
        )

    logger.debug("Unknown system subtype: %s", subtype)
    return None


def _parse_assistant(data: dict[str, Any]) -> AssistantMessage | None:
    """Parse an assistant message with its content blocks."""
    message = data.get("message", {})
    content_blocks = message.get("content", [])
    usage = message.get("usage")
    stop_reason = message.get("stop_reason")

    return AssistantMessage(
        uuid=data.get("uuid", ""),
        session_id=data.get("session_id", ""),
        parent_tool_use_id=data.get("parent_tool_use_id"),
        content_blocks=content_blocks,
        usage=usage,
        stop_reason=stop_reason,
    )


def _parse_user(data: dict[str, Any]) -> ToolResult | None:
    """Parse a user message containing tool results.

    Claude Code emits tool results as ``user`` messages with a ``content``
    array. Each element has ``type: "tool_result"``. We extract the first one.
    """
    message = data.get("message", {})
    content_list = message.get("content", [])

    for item in content_list:
        if item.get("type") == "tool_result":
            # Content can be a string or a list of content blocks
            raw_content = item.get("content", "")
            if isinstance(raw_content, list):
                # Concatenate text blocks
                raw_content = "\n".join(
                    block.get("text", "") for block in raw_content if isinstance(block, dict)
                )

            return ToolResult(
                uuid=data.get("uuid", ""),
                session_id=data.get("session_id", ""),
                tool_use_id=item.get("tool_use_id", ""),
                tool_name=item.get("tool_name", ""),
                content=str(raw_content),
                is_error=item.get("is_error", False),
                structured_result=item.get("structured_result"),
                duration_ms=item.get("duration_ms"),
            )

    return None


def _parse_stream_event(data: dict[str, Any]) -> StreamDelta | None:
    """Parse a streaming delta event (text_delta, thinking_delta, input_json_delta)."""
    event = data.get("event", {})
    if event.get("type") != "content_block_delta":
        return None

    delta = event.get("delta", {})
    delta_type = delta.get("type", "")

    # Extract content from the appropriate field based on delta type
    if delta_type == "text_delta":
        content = delta.get("text", "")
    elif delta_type == "thinking_delta":
        content = delta.get("thinking", "")
    elif delta_type == "input_json_delta":
        content = delta.get("partial_json", "")
    else:
        logger.debug("Unknown stream delta type: %s", delta_type)
        return None

    return StreamDelta(
        delta_type=delta_type,
        content=content,
        block_index=event.get("index", 0),
        parent_tool_use_id=data.get("parent_tool_use_id"),
    )


def _parse_result(data: dict[str, Any]) -> ResultMessage:
    """Parse a result event (session completion)."""
    return ResultMessage(
        session_id=data.get("session_id", ""),
        subtype=data.get("subtype", ""),
        is_error=data.get("is_error", False),
        total_cost_usd=data.get("total_cost_usd", 0.0),
        duration_ms=data.get("duration_ms", 0),
        num_turns=data.get("num_turns", 0),
        result_text=data.get("result"),
        errors=data.get("errors", []),
        model_usage=data.get("model_usage", {}),
    )


def _parse_tool_progress(data: dict[str, Any]) -> ToolProgress:
    """Parse a tool progress heartbeat."""
    return ToolProgress(
        tool_use_id=data.get("tool_use_id", ""),
        tool_name=data.get("tool_name", ""),
        elapsed_seconds=data.get("elapsed_time_seconds", 0.0),
    )


def _parse_rate_limit(data: dict[str, Any]) -> RateLimitEvent:
    """Parse a rate limit notification."""
    info = data.get("rate_limit_info", {})
    return RateLimitEvent(
        status=info.get("status", data.get("status", "")),
        resets_at=info.get("resetsAt", info.get("resets_at")),
        utilization=info.get("utilization"),
    )
