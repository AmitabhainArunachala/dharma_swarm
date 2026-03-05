"""Tests for ClaudeAdapter canonical normalization (v1.1 layer)."""

from __future__ import annotations

import asyncio
import json

import pytest

from dharma_swarm.tui.engine.adapters.base import CompletionRequest, ProviderConfig
from dharma_swarm.tui.engine.adapters.claude import ClaudeAdapter
from dharma_swarm.tui.engine.events import (
    ErrorEvent,
    SessionEnd,
    SessionStart,
    TextComplete,
    TextDelta,
    ThinkingComplete,
    ThinkingDelta,
    ToolArgumentsDelta,
    ToolCallComplete,
    ToolProgress,
    ToolResult,
    UsageReport,
)


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


def _adapter() -> ClaudeAdapter:
    return ClaudeAdapter(config=ProviderConfig(provider_id="claude", default_model="claude-sonnet-4-5"))


@pytest.mark.asyncio
async def test_list_models_and_profile() -> None:
    a = _adapter()
    models = await a.list_models()
    assert len(models) >= 3
    assert any(m.model_id == "claude-sonnet-4-5" for m in models)
    p = a.get_profile("claude-sonnet-4-5")
    assert p.display_name
    assert p.supports(type(p.capabilities).STREAMING)


def test_normalize_simple_success_flow() -> None:
    a = _adapter()
    p = a.get_profile("claude-sonnet-4-5")
    sid = "dgc-test-1"

    lines = [
        _j(
            {
                "type": "system",
                "subtype": "init",
                "session_id": "provider-session-1",
                "model": "claude-sonnet-4-5",
                "tools": ["Read", "Bash"],
                "cwd": "/repo",
                "permissionMode": "default",
                "claude_code_version": "2.1.69",
            }
        ),
        _j(
            {
                "type": "assistant",
                "session_id": "provider-session-1",
                "uuid": "u1",
                "message": {"content": [{"type": "text", "text": "Hello"}]},
            }
        ),
        _j(
            {
                "type": "result",
                "session_id": "provider-session-1",
                "subtype": "success",
                "is_error": False,
                "total_cost_usd": 0.01,
                "duration_ms": 1200,
                "num_turns": 1,
                "model_usage": {"input_tokens": 10, "output_tokens": 20},
            }
        ),
    ]

    out = []
    for line in lines:
        out.extend(a._normalize_line(line, session_id=sid, profile=p))

    assert any(isinstance(e, SessionStart) for e in out)
    assert any(isinstance(e, TextComplete) and e.content == "Hello" for e in out)
    assert any(isinstance(e, UsageReport) and e.total_cost_usd == 0.01 for e in out)
    assert any(isinstance(e, SessionEnd) and e.success for e in out)


def test_normalize_tool_and_stream_deltas() -> None:
    a = _adapter()
    p = a.get_profile("claude-sonnet-4-5")
    sid = "dgc-test-2"

    assistant_tool = _j(
        {
            "type": "assistant",
            "session_id": "provider-session-2",
            "uuid": "u2",
            "message": {
                "content": [
                    {"type": "tool_use", "id": "toolu_123", "name": "Read", "input": {"file_path": "x.py"}}
                ]
            },
        }
    )
    tool_result = _j(
        {
            "type": "user",
            "session_id": "provider-session-2",
            "uuid": "u3",
            "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_123", "content": "ok"}]},
        }
    )
    text_delta = _j(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": "He"},
            },
        }
    )
    think_delta = _j(
        {
            "type": "stream_event",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "thinking_delta", "thinking": "analyzing"},
            },
        }
    )
    arg_delta = _j(
        {
            "type": "stream_event",
            "parent_tool_use_id": "toolu_123",
            "event": {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '{"a":1'},
            },
        }
    )
    progress = _j(
        {"type": "tool_progress", "tool_use_id": "toolu_123", "tool_name": "Read", "elapsed_time_seconds": 1.2}
    )

    out = []
    for line in [assistant_tool, tool_result, text_delta, think_delta, arg_delta, progress]:
        out.extend(a._normalize_line(line, session_id=sid, profile=p))

    assert any(isinstance(e, ToolCallComplete) and e.tool_call_id == "toolu_123" for e in out)
    assert any(isinstance(e, ToolResult) and e.tool_call_id == "toolu_123" for e in out)
    assert any(isinstance(e, TextDelta) and e.content == "He" for e in out)
    assert any(isinstance(e, ThinkingDelta) and "analyzing" in e.content for e in out)
    assert any(isinstance(e, ToolArgumentsDelta) and e.tool_call_id == "toolu_123" for e in out)
    assert any(isinstance(e, ToolProgress) and e.tool_call_id == "toolu_123" for e in out)


def test_normalize_thinking_and_error_flow() -> None:
    a = _adapter()
    p = a.get_profile("claude-sonnet-4-5")
    sid = "dgc-test-3"

    thinking = _j(
        {
            "type": "assistant",
            "session_id": "provider-session-3",
            "uuid": "u4",
            "message": {"content": [{"type": "thinking", "thinking": "deep thought"}]},
        }
    )
    err = _j(
        {
            "type": "result",
            "session_id": "provider-session-3",
            "subtype": "error_max_turns",
            "is_error": True,
            "total_cost_usd": 0.03,
            "duration_ms": 5000,
            "num_turns": 4,
            "errors": ["turn limit reached"],
        }
    )

    out = []
    for line in [thinking, err]:
        out.extend(a._normalize_line(line, session_id=sid, profile=p))

    assert any(isinstance(e, ThinkingComplete) and e.content == "deep thought" for e in out)
    assert any(isinstance(e, ErrorEvent) and e.code == "error_max_turns" for e in out)
    assert any(isinstance(e, SessionEnd) and (not e.success) for e in out)


class _FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [l.encode("utf-8") + b"\n" for l in lines]

    async def readline(self) -> bytes:
        if not self._lines:
            await asyncio.sleep(0)
            return b""
        return self._lines.pop(0)


class _FakeStderr:
    async def read(self) -> bytes:
        return b""


class _FakeProc:
    def __init__(self, lines: list[str], exit_code: int = 0) -> None:
        self.stdout = _FakeStdout(lines)
        self.stderr = _FakeStderr()
        self.returncode: int | None = None
        self._exit_code = exit_code

    async def wait(self) -> int:
        self.returncode = self._exit_code
        return self._exit_code

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9


@pytest.mark.asyncio
async def test_stream_uses_subprocess_and_yields_events(monkeypatch: pytest.MonkeyPatch) -> None:
    a = _adapter()
    lines = [
        _j(
            {
                "type": "system",
                "subtype": "init",
                "session_id": "provider-session-x",
                "model": "claude-sonnet-4-5",
                "tools": [],
                "cwd": "/repo",
                "permissionMode": "default",
                "claude_code_version": "2.1.69",
            }
        ),
        _j(
            {
                "type": "result",
                "session_id": "provider-session-x",
                "subtype": "success",
                "is_error": False,
                "total_cost_usd": 0.0,
                "duration_ms": 1,
                "num_turns": 1,
            }
        ),
    ]

    async def _fake_spawn(cmd: list[str], env: dict[str, str]) -> _FakeProc:
        assert "claude" in cmd[0]
        return _FakeProc(lines, exit_code=0)

    monkeypatch.setattr(a, "_spawn_process", _fake_spawn)

    req = CompletionRequest(messages=[{"role": "user", "content": "hello"}])
    events = [e async for e in a.stream(req, session_id="dgc-test-stream")]
    assert any(isinstance(e, SessionStart) for e in events)
    assert any(isinstance(e, SessionEnd) for e in events)


@pytest.mark.asyncio
async def test_cancel_without_active_process_is_safe() -> None:
    a = _adapter()
    await a.cancel()
