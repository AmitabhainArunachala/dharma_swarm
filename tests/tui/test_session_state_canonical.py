"""Canonical event coverage for SessionState."""

from __future__ import annotations

from dharma_swarm.tui.engine.events import (
    SessionEnd,
    SessionStart,
    TextComplete,
    ToolCallComplete,
    ToolResult,
    UsageReport,
)
from dharma_swarm.tui.engine.session_state import SessionState


def test_session_state_handles_canonical_start_and_text() -> None:
    state = SessionState()
    state.handle_event(
        SessionStart(
            provider_id="claude",
            session_id="dgc-123",
            model="claude-sonnet-4-5",
            tools_available=["Read", "Bash"],
        )
    )
    state.handle_event(
        TextComplete(
            provider_id="claude",
            session_id="dgc-123",
            content="Hello",
            role="assistant",
        )
    )

    assert state.session_id == "dgc-123"
    assert state.model == "claude-sonnet-4-5"
    assert state.tools == ["Read", "Bash"]
    assert state.is_running is True
    assert state.turn_count == 1


def test_session_state_resolves_canonical_tool_name() -> None:
    state = SessionState()
    state.handle_event(
        ToolCallComplete(
            provider_id="claude",
            session_id="dgc-123",
            tool_call_id="toolu_123",
            tool_name="Read",
            arguments='{"file_path":"a.py"}',
        )
    )
    result = ToolResult(
        provider_id="claude",
        session_id="dgc-123",
        tool_call_id="toolu_123",
        tool_name="",
        content="ok",
    )

    state.handle_event(result)

    assert result.tool_name == "Read"


def test_session_state_handles_usage_and_end() -> None:
    state = SessionState(is_running=True)
    state.handle_event(
        UsageReport(
            provider_id="claude",
            session_id="dgc-123",
            input_tokens=100,
            output_tokens=50,
            total_cost_usd=0.0123,
        )
    )
    state.handle_event(
        SessionEnd(
            provider_id="claude",
            session_id="dgc-123",
            success=True,
        )
    )

    assert state.total_cost_usd == 0.0123
    assert state.is_running is False
