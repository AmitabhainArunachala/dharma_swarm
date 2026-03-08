"""Tests for DGC app mode policy wiring."""

from __future__ import annotations

from typing import Any

from dharma_swarm.tui.app import DGCApp


class _DummyRunner:
    def __init__(self) -> None:
        self.is_running = False
        self.cancel_calls = 0
        self.mark_end_calls = 0
        self.calls: list[tuple[Any, str, str]] = []

    def run_provider(self, request: Any, *, session_id: str, provider_id: str) -> None:
        self.calls.append((request, session_id, provider_id))

    def cancel(self) -> None:
        self.cancel_calls += 1

    def mark_session_end(self) -> None:
        self.mark_end_calls += 1
        self.is_running = False


class _DummyOutput:
    def __init__(self) -> None:
        self.system: list[str] = []
        self.errors: list[str] = []

    def write_system(self, msg: str) -> None:
        self.system.append(msg)

    def write_error(self, msg: str) -> None:
        self.errors.append(msg)


class _DummyStatus:
    def __init__(self, running: bool) -> None:
        self.is_running = running


class _DummyMain:
    def __init__(self, running: bool) -> None:
        self.status_bar = _DummyStatus(running)
        self.stream_output = _DummyOutput()


class _DummyStore:
    def __init__(self, meta: dict[str, Any] | None) -> None:
        self._meta = meta

    def latest_session(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._meta


def test_send_to_claude_plan_mode_uses_strict_prompt_and_default_permissions(
    monkeypatch,
) -> None:
    app = DGCApp()
    runner = _DummyRunner()
    app._provider_runner = runner  # type: ignore[assignment]
    app._set_mode("P")

    monkeypatch.setattr(app, "_ensure_local_session_id", lambda: "sid-plan")
    monkeypatch.setattr(app, "_get_state_context", lambda: "cached context")

    app._send_to_claude("design a plan")

    assert len(runner.calls) == 1
    req, sid, provider = runner.calls[0]
    assert sid == "sid-plan"
    assert provider == "claude"
    assert req.provider_options["permission_mode"] == "default"
    assert req.system_prompt is not None
    assert "PLAN MODE CONTRACT" in req.system_prompt
    assert "DGC mission-control context snapshot" in req.system_prompt


def test_send_to_claude_normal_mode_keeps_bypass_permissions(monkeypatch) -> None:
    app = DGCApp()
    runner = _DummyRunner()
    app._provider_runner = runner  # type: ignore[assignment]
    app._set_mode("N")

    monkeypatch.setattr(app, "_ensure_local_session_id", lambda: "sid-normal")
    monkeypatch.setattr(app, "_get_state_context", lambda: "")

    app._send_to_claude("hello")

    assert len(runner.calls) == 1
    req, sid, _ = runner.calls[0]
    assert sid == "sid-normal"
    assert req.provider_options["permission_mode"] == "bypassPermissions"
    assert req.system_prompt is None


def test_mode_cycle_synchronizes_command_handler() -> None:
    app = DGCApp()
    assert app._commands.mode == "N"
    app.action_cycle_mode()
    assert app._commands.mode == "A"
    app.action_cycle_mode()
    assert app._commands.mode == "P"


def test_send_to_claude_recovers_stale_lock_after_session_end(monkeypatch) -> None:
    app = DGCApp()
    runner = _DummyRunner()
    runner.is_running = True
    app._provider_runner = runner  # type: ignore[assignment]
    app._set_mode("N")

    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "_ensure_local_session_id", lambda: "sid-stale")
    monkeypatch.setattr(app, "_get_state_context", lambda: "")

    app._send_to_claude("resume please")

    assert runner.cancel_calls == 1
    assert runner.mark_end_calls == 1
    assert len(runner.calls) == 1
    assert any("Recovered stale provider lock" in line for line in main.stream_output.system)


def test_send_to_claude_blocks_when_actively_running(monkeypatch) -> None:
    app = DGCApp()
    runner = _DummyRunner()
    runner.is_running = True
    app._provider_runner = runner  # type: ignore[assignment]
    app._set_mode("N")

    main = _DummyMain(running=True)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "_ensure_local_session_id", lambda: "sid-block")
    monkeypatch.setattr(app, "_get_state_context", lambda: "")

    app._send_to_claude("still running?")

    assert runner.cancel_calls == 0
    assert runner.mark_end_calls == 0
    assert len(runner.calls) == 0
    assert any("already running" in line for line in main.stream_output.errors)


def test_restore_last_session_context_populates_resume_state(monkeypatch) -> None:
    app = DGCApp()
    meta = {
        "session_id": "dgc-20260308-000001-abcd",
        "provider_session_id": "prov-abc-123456789",
        "total_turns": 9,
        "total_cost_usd": 1.23,
    }
    app._session_store = _DummyStore(meta)  # type: ignore[assignment]
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.delenv("DGC_AUTO_RESUME", raising=False)

    app._restore_last_session_context()

    assert app._session.session_id == "dgc-20260308-000001-abcd"
    assert app._provider_session_id == "prov-abc-123456789"
    assert main.status_bar.session_name == "prov-abc"
    assert main.status_bar.turn_count == 9
    assert main.status_bar.cost_usd == 1.23
    assert any("Restored prior Claude context" in line for line in main.stream_output.system)


def test_restore_last_session_context_respects_disable_flag(monkeypatch) -> None:
    app = DGCApp()
    meta = {
        "session_id": "dgc-20260308-000001-abcd",
        "provider_session_id": "prov-abc-123456789",
    }
    app._session_store = _DummyStore(meta)  # type: ignore[assignment]
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setenv("DGC_AUTO_RESUME", "0")

    app._restore_last_session_context()

    assert app._session.session_id is None
    assert app._provider_session_id is None
    assert not main.stream_output.system
