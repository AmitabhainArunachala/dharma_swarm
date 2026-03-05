"""Tests for provider-agnostic canonical event schema (v1.1)."""

from __future__ import annotations

from dharma_swarm.tui.engine.events import (
    EVENT_TYPES,
    CanonicalEvent,
    ErrorEvent,
    RateLimitEvent,
    SCHEMA_VERSION,
    SessionEnd,
    SessionStart,
    TaskComplete,
    TaskProgress,
    TaskStarted,
    TextComplete,
    TextDelta,
    ThinkingComplete,
    ThinkingDelta,
    ToolArgumentsDelta,
    ToolCallComplete,
    ToolCallStart,
    ToolProgress,
    ToolResult,
    UsageReport,
)


def test_schema_version_is_1() -> None:
    assert SCHEMA_VERSION == 1


def test_event_timestamp_autopopulated() -> None:
    ev = CanonicalEvent(type="noop")
    assert ev.timestamp > 0
    assert ev.schema_version == 1


def test_all_event_types_instantiable() -> None:
    events = [
        SessionStart(),
        SessionEnd(),
        TextDelta(),
        TextComplete(),
        ThinkingDelta(),
        ThinkingComplete(),
        ToolCallStart(),
        ToolArgumentsDelta(),
        ToolCallComplete(),
        ToolResult(),
        ToolProgress(),
        TaskStarted(),
        TaskProgress(),
        TaskComplete(),
        UsageReport(),
        ErrorEvent(),
        RateLimitEvent(),
    ]
    assert all(ev.schema_version == 1 for ev in events)
    assert all(isinstance(ev.type, str) and ev.type for ev in events)


def test_event_registry_complete() -> None:
    expected = {
        "session_start",
        "session_end",
        "text_delta",
        "text_complete",
        "thinking_delta",
        "thinking_complete",
        "tool_call_start",
        "tool_args_delta",
        "tool_call_complete",
        "tool_result",
        "tool_progress",
        "task_started",
        "task_progress",
        "task_complete",
        "usage",
        "error",
        "rate_limit",
    }
    assert set(EVENT_TYPES) == expected
