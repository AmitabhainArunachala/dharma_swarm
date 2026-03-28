"""Tests for the Codex TUI adapter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from dharma_swarm.tui.engine.adapters.base import CompletionRequest, ProviderConfig
from dharma_swarm.tui.engine.adapters.codex import CodexAdapter
from dharma_swarm.tui.engine.events import (
    ErrorEvent,
    SessionEnd,
    SessionStart,
    TextComplete,
    ToolCallComplete,
    ToolResult,
    UsageReport,
)


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


class _FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._chunks = [f"{line}\n".encode("utf-8") for line in lines]

    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        if not self._chunks:
            return b""
        return self._chunks.pop(0)

    async def read(self, size: int = -1) -> bytes:
        await asyncio.sleep(0)
        if not self._chunks:
            return b""
        if size is None or size < 0:
            data = b"".join(self._chunks)
            self._chunks = []
            return data
        chunk = self._chunks[0]
        if len(chunk) <= size:
            return self._chunks.pop(0)
        data = chunk[:size]
        self._chunks[0] = chunk[size:]
        return data


class _FakeStderr:
    def __init__(self, text: str = "") -> None:
        self._text = text

    async def read(self) -> bytes:
        await asyncio.sleep(0)
        return self._text.encode("utf-8")


class _FakeStdin:
    def __init__(self) -> None:
        self.buffer = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.buffer.extend(data)

    async def drain(self) -> None:
        await asyncio.sleep(0)

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        await asyncio.sleep(0)


class _FakeProc:
    def __init__(self, lines: list[str], *, exit_code: int = 0, stderr: str = "") -> None:
        self.stdin = _FakeStdin()
        self.stdout = _FakeStdout(lines)
        self.stderr = _FakeStderr(stderr)
        self.returncode = None if exit_code == 0 else exit_code
        self._exit_code = exit_code

    async def wait(self) -> int:
        await asyncio.sleep(0)
        self.returncode = self._exit_code
        return self._exit_code

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9


def test_codex_build_command_uses_dangerous_bypass(tmp_path: Path) -> None:
    adapter = CodexAdapter(
        config=ProviderConfig(provider_id="codex", default_model="gpt-5.4"),
        workdir=tmp_path,
    )

    cmd = adapter._build_command(
        CompletionRequest(messages=[{"role": "user", "content": "hello"}]),
        output_path=tmp_path / "last.txt",
    )

    assert cmd[:2] == ["codex", "exec"]
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    assert "--json" in cmd
    assert "-m" in cmd
    assert "gpt-5.4" in cmd


@pytest.mark.asyncio
async def test_codex_success_reads_output_file(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = CodexAdapter(
        config=ProviderConfig(provider_id="codex", default_model="gpt-5.4")
    )
    captured: dict[str, _FakeProc] = {}

    async def _fake_spawn(cmd: list[str], env: dict[str, str]) -> _FakeProc:
        output_path = Path(cmd[cmd.index("-o") + 1])
        output_path.write_text("hello from codex\n", encoding="utf-8")
        proc = _FakeProc(
            [
                _j({"type": "thread.started", "thread_id": "thread-123"}),
                _j({"type": "turn.started"}),
            ],
            exit_code=0,
        )
        captured["proc"] = proc
        return proc

    monkeypatch.setattr(adapter, "_spawn_process", _fake_spawn)

    req = CompletionRequest(messages=[{"role": "user", "content": "hello"}])
    events = [e async for e in adapter.stream(req, session_id="sid-codex-1")]

    assert any(isinstance(e, SessionStart) for e in events)
    assert any(isinstance(e, TextComplete) and e.content == "hello from codex" for e in events)
    assert any(isinstance(e, SessionEnd) and e.success for e in events)
    assert captured["proc"].stdin.buffer.decode("utf-8") == "User: hello\n"
    assert captured["proc"].stdin.closed is True


@pytest.mark.asyncio
async def test_codex_failure_emits_error_and_session_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = CodexAdapter(
        config=ProviderConfig(provider_id="codex", default_model="gpt-5.4")
    )

    async def _fake_spawn(cmd: list[str], env: dict[str, str]) -> _FakeProc:
        return _FakeProc(
            [
                _j(
                    {
                        "type": "error",
                        "message": "You're out of extra usage · resets tomorrow",
                    }
                )
            ],
            exit_code=1,
            stderr="codex failed",
        )

    monkeypatch.setattr(adapter, "_spawn_process", _fake_spawn)

    req = CompletionRequest(messages=[{"role": "user", "content": "hello"}])
    events = [e async for e in adapter.stream(req, session_id="sid-codex-2")]

    err = next((e for e in events if isinstance(e, ErrorEvent)), None)
    assert isinstance(err, ErrorEvent)
    assert err.code == "usage_exhausted"
    assert any(
        isinstance(e, SessionEnd) and (not e.success) and e.error_code == "usage_exhausted"
        for e in events
    )


@pytest.mark.asyncio
async def test_codex_stream_handles_large_json_event_without_readline_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = CodexAdapter(
        config=ProviderConfig(provider_id="codex", default_model="gpt-5.4")
    )
    large_text = "x" * 120000

    async def _fake_spawn(cmd: list[str], env: dict[str, str]) -> _FakeProc:
        return _FakeProc(
            [
                _j({"type": "thread.started", "thread_id": "thread-giant"}),
                _j(
                    {
                        "type": "item.completed",
                        "item": {"type": "message", "content": large_text},
                    }
                ),
            ],
            exit_code=0,
        )

    monkeypatch.setattr(adapter, "_spawn_process", _fake_spawn)

    req = CompletionRequest(messages=[{"role": "user", "content": "hello"}])
    events = [e async for e in adapter.stream(req, session_id="sid-codex-giant")]

    assert any(isinstance(e, SessionStart) for e in events)
    giant = next((e for e in events if isinstance(e, TextComplete)), None)
    assert isinstance(giant, TextComplete)
    assert giant.content == large_text
    assert all(
        not (isinstance(e, ErrorEvent) and e.code == "stream_read_error")
        for e in events
    )
    assert any(isinstance(e, SessionEnd) and e.success for e in events)


@pytest.mark.asyncio
async def test_codex_stream_surfaces_progress_and_command_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = CodexAdapter(
        config=ProviderConfig(provider_id="codex", default_model="gpt-5.4")
    )

    async def _fake_spawn(cmd: list[str], env: dict[str, str]) -> _FakeProc:
        output_path = Path(cmd[cmd.index("-o") + 1])
        output_path.write_text("/Users/dhyana/dharma_swarm\n", encoding="utf-8")
        return _FakeProc(
            [
                _j({"type": "thread.started", "thread_id": "thread-tools"}),
                _j(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_0",
                            "type": "agent_message",
                            "text": "Running `pwd` to verify the current working directory.",
                        },
                    }
                ),
                _j(
                    {
                        "type": "item.started",
                        "item": {
                            "id": "item_1",
                            "type": "command_execution",
                            "command": "/bin/zsh -lc pwd",
                            "status": "in_progress",
                        },
                    }
                ),
                _j(
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "item_1",
                            "type": "command_execution",
                            "command": "/bin/zsh -lc pwd",
                            "aggregated_output": "/Users/dhyana/dharma_swarm\n",
                            "exit_code": 0,
                            "status": "completed",
                        },
                    }
                ),
                _j(
                    {
                        "type": "turn.completed",
                        "usage": {
                            "input_tokens": 16582,
                            "cached_input_tokens": 14080,
                            "output_tokens": 280,
                        },
                    }
                ),
            ],
            exit_code=0,
        )

    monkeypatch.setattr(adapter, "_spawn_process", _fake_spawn)

    req = CompletionRequest(messages=[{"role": "user", "content": "pwd"}])
    events = [e async for e in adapter.stream(req, session_id="sid-codex-tools")]

    start = next((e for e in events if isinstance(e, SessionStart)), None)
    assert isinstance(start, SessionStart)
    assert start.tools_available == ["shell"]

    progress = next(
        (
            e for e in events
            if isinstance(e, TextComplete)
            and e.role == "commentary"
            and "Running `pwd`" in e.content
        ),
        None,
    )
    assert isinstance(progress, TextComplete)

    tool_call = next((e for e in events if isinstance(e, ToolCallComplete)), None)
    assert isinstance(tool_call, ToolCallComplete)
    assert tool_call.tool_name == "shell"
    assert "pwd" in tool_call.arguments

    tool_result = next((e for e in events if isinstance(e, ToolResult)), None)
    assert isinstance(tool_result, ToolResult)
    assert tool_result.tool_name == "shell"
    assert tool_result.is_error is False
    assert tool_result.content == "/Users/dhyana/dharma_swarm"

    usage = next((e for e in events if isinstance(e, UsageReport)), None)
    assert isinstance(usage, UsageReport)
    assert usage.input_tokens == 16582
    assert usage.output_tokens == 280

    final_text = [
        e for e in events if isinstance(e, TextComplete) and e.role == "assistant"
    ]
    assert len(final_text) == 1
    assert final_text[0].content == "/Users/dhyana/dharma_swarm"
