"""Tests for the DGC TUI engine: stream parser, event types, and session state.

Covers all Claude Code CLI v2.1.69 NDJSON event types with realistic payloads.
"""

from __future__ import annotations

import pytest

from dharma_swarm.tui.engine.event_types import (
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
from dharma_swarm.tui.engine.session_state import SessionState
from dharma_swarm.tui.engine.stream_parser import parse_ndjson_line


# ---------------------------------------------------------------------------
# SystemInit
# ---------------------------------------------------------------------------


class TestSystemInit:
    def test_parse_system_init(self) -> None:
        line = (
            '{"type":"system","subtype":"init","session_id":"abc-123",'
            '"model":"claude-sonnet-4-5","tools":["Read","Write","Bash"],'
            '"cwd":"/home/user","permissionMode":"default",'
            '"claude_code_version":"2.1.69"}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, SystemInit)
        assert event.session_id == "abc-123"
        assert event.model == "claude-sonnet-4-5"
        assert event.tools == ["Read", "Write", "Bash"]
        assert event.cwd == "/home/user"
        assert event.permission_mode == "default"
        assert event.claude_code_version == "2.1.69"
        assert event.mcp_servers == []

    def test_parse_system_init_with_mcp_servers(self) -> None:
        line = (
            '{"type":"system","subtype":"init","session_id":"s1",'
            '"model":"claude-sonnet-4-5","tools":["Read"],"cwd":"/",'
            '"permissionMode":"default","claude_code_version":"2.1.69",'
            '"mcp_servers":[{"name":"memory","url":"http://localhost:3000"}]}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, SystemInit)
        assert len(event.mcp_servers) == 1
        assert event.mcp_servers[0]["name"] == "memory"


# ---------------------------------------------------------------------------
# AssistantMessage
# ---------------------------------------------------------------------------


class TestAssistantMessage:
    def test_parse_assistant_text(self) -> None:
        line = (
            '{"type":"assistant","uuid":"u1","session_id":"s1",'
            '"message":{"content":[{"type":"text","text":"Hello world"}],'
            '"usage":{"input_tokens":100,"output_tokens":50},'
            '"stop_reason":"end_turn"}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, AssistantMessage)
        assert event.uuid == "u1"
        assert event.session_id == "s1"
        assert event.parent_tool_use_id is None
        assert len(event.content_blocks) == 1
        assert event.content_blocks[0]["text"] == "Hello world"
        assert event.usage is not None
        assert event.usage["input_tokens"] == 100
        assert event.stop_reason == "end_turn"

    def test_parse_assistant_thinking(self) -> None:
        line = (
            '{"type":"assistant","uuid":"u2","session_id":"s1",'
            '"message":{"content":[{"type":"thinking","thinking":"Let me analyze..."},'
            '{"type":"text","text":"Here is my analysis"}]}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, AssistantMessage)
        assert len(event.content_blocks) == 2
        assert event.content_blocks[0]["type"] == "thinking"
        assert event.content_blocks[0]["thinking"] == "Let me analyze..."
        assert event.content_blocks[1]["type"] == "text"
        assert event.content_blocks[1]["text"] == "Here is my analysis"

    def test_parse_assistant_tool_use(self) -> None:
        line = (
            '{"type":"assistant","uuid":"u3","session_id":"s1",'
            '"message":{"content":[{"type":"tool_use","id":"toolu_01abc",'
            '"name":"Read","input":{"file_path":"/foo/bar.py"}}]}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, AssistantMessage)
        assert len(event.content_blocks) == 1
        assert event.content_blocks[0]["name"] == "Read"
        assert event.content_blocks[0]["id"] == "toolu_01abc"
        assert event.content_blocks[0]["input"]["file_path"] == "/foo/bar.py"

    def test_parse_assistant_with_parent_tool_use_id(self) -> None:
        line = (
            '{"type":"assistant","uuid":"u4","session_id":"s1",'
            '"parent_tool_use_id":"toolu_parent",'
            '"message":{"content":[{"type":"text","text":"sub-agent reply"}]}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, AssistantMessage)
        assert event.parent_tool_use_id == "toolu_parent"


# ---------------------------------------------------------------------------
# ToolResult (user message)
# ---------------------------------------------------------------------------


class TestToolResult:
    def test_parse_tool_result(self) -> None:
        line = (
            '{"type":"user","uuid":"u4","session_id":"s1",'
            '"message":{"content":[{"type":"tool_result",'
            '"tool_use_id":"toolu_01abc","content":"file contents here"}]}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, ToolResult)
        assert event.uuid == "u4"
        assert event.session_id == "s1"
        assert event.tool_use_id == "toolu_01abc"
        assert event.content == "file contents here"
        assert not event.is_error

    def test_parse_tool_result_error(self) -> None:
        line = (
            '{"type":"user","uuid":"u5","session_id":"s1",'
            '"message":{"content":[{"type":"tool_result",'
            '"tool_use_id":"toolu_02","content":"Permission denied",'
            '"is_error":true}]}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, ToolResult)
        assert event.is_error is True
        assert event.content == "Permission denied"

    def test_parse_tool_result_with_list_content(self) -> None:
        line = (
            '{"type":"user","uuid":"u6","session_id":"s1",'
            '"message":{"content":[{"type":"tool_result",'
            '"tool_use_id":"toolu_03",'
            '"content":[{"type":"text","text":"line 1"},{"type":"text","text":"line 2"}]}]}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, ToolResult)
        assert event.content == "line 1\nline 2"

    def test_parse_user_no_tool_result(self) -> None:
        """A user message with no tool_result blocks returns None."""
        line = (
            '{"type":"user","uuid":"u7","session_id":"s1",'
            '"message":{"content":[{"type":"text","text":"human input"}]}}'
        )
        event = parse_ndjson_line(line)
        assert event is None


# ---------------------------------------------------------------------------
# StreamDelta
# ---------------------------------------------------------------------------


class TestStreamDelta:
    def test_parse_stream_delta_text(self) -> None:
        line = (
            '{"type":"stream_event","event":{"type":"content_block_delta",'
            '"index":0,"delta":{"type":"text_delta","text":"Hello"}}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, StreamDelta)
        assert event.delta_type == "text_delta"
        assert event.content == "Hello"
        assert event.block_index == 0

    def test_parse_stream_delta_thinking(self) -> None:
        line = (
            '{"type":"stream_event","event":{"type":"content_block_delta",'
            '"index":0,"delta":{"type":"thinking_delta","thinking":"analyzing..."}}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, StreamDelta)
        assert event.delta_type == "thinking_delta"
        assert event.content == "analyzing..."

    def test_parse_stream_delta_input_json(self) -> None:
        line = (
            '{"type":"stream_event","event":{"type":"content_block_delta",'
            '"index":1,"delta":{"type":"input_json_delta",'
            '"partial_json":"{\\"file_path\\":\\"/foo"}}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, StreamDelta)
        assert event.delta_type == "input_json_delta"
        assert "/foo" in event.content

    def test_parse_stream_event_non_delta(self) -> None:
        """Non-content_block_delta stream events return None."""
        line = '{"type":"stream_event","event":{"type":"message_start"}}'
        event = parse_ndjson_line(line)
        assert event is None


# ---------------------------------------------------------------------------
# ResultMessage
# ---------------------------------------------------------------------------


class TestResultMessage:
    def test_parse_result_success(self) -> None:
        line = (
            '{"type":"result","subtype":"success","session_id":"s1",'
            '"is_error":false,"total_cost_usd":0.03,"duration_ms":5000,'
            '"num_turns":3,"result":"Final answer"}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, ResultMessage)
        assert event.session_id == "s1"
        assert event.subtype == "success"
        assert not event.is_error
        assert event.total_cost_usd == 0.03
        assert event.duration_ms == 5000
        assert event.num_turns == 3
        assert event.result_text == "Final answer"
        assert event.errors == []

    def test_parse_result_error(self) -> None:
        line = (
            '{"type":"result","subtype":"error_max_turns","session_id":"s1",'
            '"is_error":true,"total_cost_usd":0.1,"duration_ms":30000,'
            '"num_turns":10}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, ResultMessage)
        assert event.is_error
        assert event.subtype == "error_max_turns"
        assert event.num_turns == 10
        assert event.result_text is None

    def test_parse_result_with_errors_list(self) -> None:
        line = (
            '{"type":"result","subtype":"error_tool","session_id":"s1",'
            '"is_error":true,"total_cost_usd":0.01,"duration_ms":1000,'
            '"num_turns":1,"errors":["Tool crashed","Retry failed"]}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, ResultMessage)
        assert len(event.errors) == 2


# ---------------------------------------------------------------------------
# ToolProgress
# ---------------------------------------------------------------------------


class TestToolProgress:
    def test_parse_tool_progress(self) -> None:
        line = (
            '{"type":"tool_progress","tool_use_id":"toolu_01abc",'
            '"tool_name":"Bash","elapsed_time_seconds":3.5}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, ToolProgress)
        assert event.tool_use_id == "toolu_01abc"
        assert event.tool_name == "Bash"
        assert event.elapsed_seconds == 3.5


# ---------------------------------------------------------------------------
# TaskStarted / TaskProgress
# ---------------------------------------------------------------------------


class TestTaskEvents:
    def test_parse_task_started(self) -> None:
        line = (
            '{"type":"system","subtype":"task_started","task_id":"t1",'
            '"tool_use_id":"toolu_01abc","description":"Research codebase"}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, TaskStarted)
        assert event.task_id == "t1"
        assert event.tool_use_id == "toolu_01abc"
        assert event.description == "Research codebase"

    def test_parse_task_progress(self) -> None:
        line = (
            '{"type":"system","subtype":"task_progress","task_id":"t1",'
            '"usage":{"input_tokens":500,"output_tokens":200},'
            '"last_tool_name":"Grep"}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, TaskProgress)
        assert event.task_id == "t1"
        assert event.usage["input_tokens"] == 500
        assert event.last_tool_name == "Grep"


# ---------------------------------------------------------------------------
# RateLimitEvent
# ---------------------------------------------------------------------------


class TestRateLimitEvent:
    def test_parse_rate_limit(self) -> None:
        line = (
            '{"type":"rate_limit_event","rate_limit_info":'
            '{"status":"allowed_warning","resetsAt":1709654400,'
            '"utilization":0.85}}'
        )
        event = parse_ndjson_line(line)
        assert isinstance(event, RateLimitEvent)
        assert event.status == "allowed_warning"
        assert event.resets_at == 1709654400
        assert event.utilization == 0.85

    def test_parse_rate_limit_minimal(self) -> None:
        line = '{"type":"rate_limit_event","rate_limit_info":{"status":"ok"}}'
        event = parse_ndjson_line(line)
        assert isinstance(event, RateLimitEvent)
        assert event.status == "ok"
        assert event.resets_at is None
        assert event.utilization is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_parse_invalid_json(self) -> None:
        assert parse_ndjson_line("not json") is None

    def test_parse_empty_string(self) -> None:
        assert parse_ndjson_line("") is None

    def test_parse_whitespace_only(self) -> None:
        assert parse_ndjson_line("   \n  ") is None

    def test_parse_unknown_type(self) -> None:
        assert parse_ndjson_line('{"type":"unknown_thing"}') is None

    def test_parse_missing_type(self) -> None:
        assert parse_ndjson_line('{"foo":"bar"}') is None

    def test_parse_unknown_system_subtype(self) -> None:
        assert parse_ndjson_line('{"type":"system","subtype":"unknown"}') is None


# ---------------------------------------------------------------------------
# SessionState
# ---------------------------------------------------------------------------


class TestSessionState:
    def test_session_state_tracks_init(self) -> None:
        state = SessionState()
        init = SystemInit(
            session_id="s1",
            model="claude-sonnet-4-5",
            tools=["Read", "Bash"],
            cwd="/home",
            permission_mode="default",
            claude_code_version="2.1.69",
        )
        state.handle_event(init)
        assert state.session_id == "s1"
        assert state.model == "claude-sonnet-4-5"
        assert state.tools == ["Read", "Bash"]
        assert state.is_running is True

    def test_session_state_tracks_assistant_turn(self) -> None:
        state = SessionState()
        msg = AssistantMessage(
            uuid="u1",
            session_id="s1",
            parent_tool_use_id=None,
            content_blocks=[
                {"type": "tool_use", "id": "toolu_01", "name": "Read", "input": {}}
            ],
        )
        state.handle_event(msg)
        assert state.turn_count == 1
        assert state.last_tool_use_map.get("toolu_01") == "Read"

    def test_session_state_tracks_result(self) -> None:
        state = SessionState()

        # Start session
        init = SystemInit(
            session_id="s1",
            model="claude-sonnet-4-5",
            tools=["Read", "Bash"],
            cwd="/home",
            permission_mode="default",
            claude_code_version="2.1.69",
        )
        state.handle_event(init)
        assert state.is_running is True

        # End session
        result = ResultMessage(
            session_id="s1",
            subtype="success",
            is_error=False,
            total_cost_usd=0.05,
            duration_ms=3000,
            num_turns=2,
        )
        state.handle_event(result)
        assert state.total_cost_usd == 0.05
        assert state.is_running is False

    def test_session_state_full_lifecycle(self) -> None:
        """End-to-end: init -> assistant (tool_use) -> tool_result -> result."""
        state = SessionState()

        # 1. Init
        init = SystemInit(
            session_id="s1",
            model="claude-sonnet-4-5",
            tools=["Read", "Bash"],
            cwd="/home",
            permission_mode="default",
            claude_code_version="2.1.69",
        )
        state.handle_event(init)

        # 2. Assistant with tool_use
        msg = AssistantMessage(
            uuid="u1",
            session_id="s1",
            parent_tool_use_id=None,
            content_blocks=[
                {"type": "tool_use", "id": "toolu_01", "name": "Read", "input": {}}
            ],
        )
        state.handle_event(msg)
        assert state.turn_count == 1
        assert state.last_tool_use_map["toolu_01"] == "Read"

        # 3. Tool result
        tr = ToolResult(
            uuid="u2",
            session_id="s1",
            tool_use_id="toolu_01",
            tool_name="",  # Intentionally empty to test resolution
            content="file contents",
        )
        state.handle_event(tr)
        assert tr.tool_name == "Read"  # Resolved from map

        # 4. Result
        result = ResultMessage(
            session_id="s1",
            subtype="success",
            is_error=False,
            total_cost_usd=0.05,
            duration_ms=3000,
            num_turns=2,
        )
        state.handle_event(result)
        assert state.total_cost_usd == 0.05
        assert not state.is_running

    def test_session_state_ignores_unknown_events(self) -> None:
        """Events not handled by SessionState are silently ignored."""
        state = SessionState()
        state.handle_event(ToolProgress(tool_use_id="x", tool_name="Bash", elapsed_seconds=1.0))
        assert state.turn_count == 0

    def test_session_state_multiple_tool_uses(self) -> None:
        """Track multiple tool_use blocks in a single assistant message."""
        state = SessionState()
        msg = AssistantMessage(
            uuid="u1",
            session_id="s1",
            parent_tool_use_id=None,
            content_blocks=[
                {"type": "tool_use", "id": "toolu_01", "name": "Read", "input": {}},
                {"type": "text", "text": "reading file..."},
                {"type": "tool_use", "id": "toolu_02", "name": "Bash", "input": {}},
            ],
        )
        state.handle_event(msg)
        assert state.turn_count == 1
        assert state.last_tool_use_map["toolu_01"] == "Read"
        assert state.last_tool_use_map["toolu_02"] == "Bash"
