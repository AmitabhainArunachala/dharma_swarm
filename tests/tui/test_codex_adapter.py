"""Tests for the Codex TUI adapter."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from dharma_swarm.tui.engine.adapters.base import CompletionRequest, ProviderConfig
from dharma_swarm.tui.engine.adapters.codex import CodexAdapter
from dharma_swarm.tui.engine.events import ErrorEvent, SessionEnd, SessionStart, TextComplete


def _j(obj: dict) -> str:
    return json.dumps(obj, separators=(",", ":"))


class _FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [f"{line}\n".encode("utf-8") for line in lines]

    async def readline(self) -> bytes:
        await asyncio.sleep(0)
        if not self._lines:
            return b""
        return self._lines.pop(0)


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
