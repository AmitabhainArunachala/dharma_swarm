"""End-to-end Textual pilot tests for DGC TUI interactivity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from textual import events

import dharma_swarm.tui.app as tui_app
from dharma_swarm.tui.app import DGCApp
from dharma_swarm.tui.screens.btw import BTWScreen
from dharma_swarm.tui.engine.events import (
    SessionEnd,
    SessionStart,
    TextComplete,
    ToolCallComplete,
    ToolResult,
    UsageReport,
)
from dharma_swarm.tui.engine.session_store import SessionStore


@pytest.fixture(autouse=True)
def _isolate_tui_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(tui_app, "MODEL_POLICY_PATH", tmp_path / "tui_model_policy.json")
    monkeypatch.setattr(tui_app, "MODEL_STATS_PATH", tmp_path / "tui_model_stats.json")
    monkeypatch.setenv("DGC_TUI_RESTORE_HISTORY", "0")
    monkeypatch.setenv("DGC_AUTO_RESUME", "0")
    tui_app.MODEL_POLICY_PATH.write_text(
        json.dumps(
            {
                "auto_fallback": True,
                "strategy": "responsive",
                "preferred_provider": "codex",
                "preferred_model": "gpt-5.4",
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_tui_submit_dispatches_to_persisted_codex_route() -> None:
    app = DGCApp()
    app._restore_last_session_context = lambda **_: None
    app._run_status_on_startup = lambda: None

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        main = app._get_main_screen()
        assert main is not None
        assert getattr(app.screen.focused, "id", None) == "prompt-input"
        assert main.status_bar.model == "codex:gpt-5.4"

        calls: list[tuple[str, str | None, str]] = []
        runner = app._provider_runner
        assert runner is not None

        def fake_run_provider(request, *, session_id: str, provider_id: str = "claude") -> None:
            calls.append((provider_id, request.model, request.messages[-1]["content"]))

        runner.run_provider = fake_run_provider  # type: ignore[method-assign]

        await pilot.press("h", "e", "l", "l", "o", "enter")
        await pilot.pause()

        assert calls == [("codex", "gpt-5.4", "hello")]
        assert main.prompt_input.text == ""


@pytest.mark.asyncio
async def test_tui_renders_provider_events_after_submit() -> None:
    app = DGCApp()
    app._restore_last_session_context = lambda **_: None
    app._run_status_on_startup = lambda: None

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        main = app._get_main_screen()
        assert main is not None
        runner = app._provider_runner
        assert runner is not None

        def fake_run_provider(request, *, session_id: str, provider_id: str = "claude") -> None:
            app.post_message(runner.ProcessStarted())
            app.post_message(
                runner.AgentEvent(
                    SessionStart(
                        provider_id="codex",
                        session_id=session_id,
                        model="gpt-5.4",
                        capabilities=["cancel"],
                        tools_available=[],
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    TextComplete(
                        provider_id="codex",
                        session_id=session_id,
                        content="hello back",
                        role="assistant",
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    SessionEnd(
                        provider_id="codex",
                        session_id=session_id,
                        success=True,
                    )
                )
            )
            app.post_message(runner.ProcessExited(0, was_cancelled=False))

        runner.run_provider = fake_run_provider  # type: ignore[method-assign]

        await pilot.press("h", "i", "enter")
        await pilot.pause()
        await pilot.pause()

        assert main.stream_output.get_last_reply() == "hello back"
        assert main.status_bar.model == "codex:gpt-5.4"
        assert main.status_bar.turn_count == 1
        assert main.status_bar.is_running is False


@pytest.mark.asyncio
async def test_tui_replays_last_session_history_on_startup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = DGCApp()
    app._run_status_on_startup = lambda: None
    monkeypatch.setenv("DGC_TUI_RESTORE_HISTORY", "1")
    store = SessionStore(root=tmp_path)
    session_id = store.create_session(
        session_id="dgc-20260313-090000-abcd",
        provider_id="codex",
        model_id="gpt-5.4",
        cwd=str(tui_app.DHARMA_SWARM),
    )
    store.append_event(
        session_id,
        TextComplete(
            provider_id="codex",
            session_id=session_id,
            content="hello",
            role="user",
        ),
    )
    store.append_event(
        session_id,
        TextComplete(
            provider_id="codex",
            session_id=session_id,
            content="history reply",
            role="assistant",
        ),
    )
    app._session_store = store  # type: ignore[assignment]

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        main = app._get_main_screen()
        assert main is not None
        assert main.stream_output.get_last_reply() == "history reply"
        assert app._chat_history == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "history reply"},
        ]


@pytest.mark.asyncio
async def test_tui_pageup_scrolls_transcript_while_prompt_stays_focused() -> None:
    app = DGCApp()
    app._restore_last_session_context = lambda **_: None
    app._run_status_on_startup = lambda: None

    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        main = app._get_main_screen()
        assert main is not None
        output = main.stream_output

        for index in range(120):
            output.write_system(f"line {index}")
        await pilot.pause()

        bottom = output.scroll_y
        assert getattr(app.screen.focused, "id", None) == "prompt-input"

        await pilot.press("pageup")
        await pilot.pause()

        assert output.scroll_y < bottom
        assert output._scroll_locked is True
        assert getattr(app.screen.focused, "id", None) == "prompt-input"


@pytest.mark.asyncio
async def test_tui_mouse_scroll_over_prompt_routes_to_transcript() -> None:
    app = DGCApp()
    app._restore_last_session_context = lambda **_: None
    app._run_status_on_startup = lambda: None

    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        main = app._get_main_screen()
        assert main is not None
        output = main.stream_output

        for index in range(120):
            output.write_system(f"line {index}")
        await pilot.pause()

        bottom = output.scroll_y
        app.on_mouse_scroll_up(
            events.MouseScrollUp(
                main.prompt_input,
                x=1,
                y=1,
                delta_x=0,
                delta_y=-1,
                button=0,
                shift=False,
                meta=False,
                ctrl=False,
            )
        )
        await pilot.pause()

        assert output.scroll_y < bottom
        assert output._scroll_locked is True


@pytest.mark.asyncio
async def test_tui_codex_progress_notes_do_not_count_as_turns() -> None:
    app = DGCApp()
    app._restore_last_session_context = lambda **_: None
    app._run_status_on_startup = lambda: None

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        main = app._get_main_screen()
        assert main is not None
        runner = app._provider_runner
        assert runner is not None

        def fake_run_provider(request, *, session_id: str, provider_id: str = "claude") -> None:
            app.post_message(runner.ProcessStarted())
            app.post_message(
                runner.AgentEvent(
                    SessionStart(
                        provider_id="codex",
                        session_id=session_id,
                        model="gpt-5.4",
                        capabilities=["streaming", "tool_use", "cancel"],
                        tools_available=["shell"],
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    TextComplete(
                        provider_id="codex",
                        session_id=session_id,
                        content="Running `pwd` to verify the current working directory.",
                        role="commentary",
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    ToolCallComplete(
                        provider_id="codex",
                        session_id=session_id,
                        tool_call_id="tool-1",
                        tool_name="shell",
                        arguments='{"command":"/bin/zsh -lc pwd"}',
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    ToolResult(
                        provider_id="codex",
                        session_id=session_id,
                        tool_call_id="tool-1",
                        tool_name="shell",
                        content="/Users/dhyana/dharma_swarm",
                        is_error=False,
                        duration_ms=23,
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    TextComplete(
                        provider_id="codex",
                        session_id=session_id,
                        content="/Users/dhyana/dharma_swarm",
                        role="assistant",
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    SessionEnd(
                        provider_id="codex",
                        session_id=session_id,
                        success=True,
                    )
                )
            )
            app.post_message(runner.ProcessExited(0, was_cancelled=False))

        runner.run_provider = fake_run_provider  # type: ignore[method-assign]

        await pilot.press("p", "w", "d", "enter")
        await pilot.pause()
        await pilot.pause()

        assert main.stream_output.get_last_reply() == "/Users/dhyana/dharma_swarm"
        assert main.status_bar.turn_count == 1
        assert main.status_bar.tool_count == 1
        assert main.status_bar.last_tool == "shell"


@pytest.mark.asyncio
async def test_tui_status_bar_tracks_activity_tools_and_usage() -> None:
    app = DGCApp()
    app._restore_last_session_context = lambda **_: None
    app._run_status_on_startup = lambda: None

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        main = app._get_main_screen()
        assert main is not None
        runner = app._provider_runner
        assert runner is not None

        def fake_run_provider(request, *, session_id: str, provider_id: str = "claude") -> None:
            app.post_message(runner.ProcessStarted())
            app.post_message(
                runner.AgentEvent(
                    SessionStart(
                        provider_id="codex",
                        session_id=session_id,
                        model="gpt-5.4",
                        provider_session_id="codex-session-1234",
                        capabilities=["cancel"],
                        tools_available=["shell"],
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    ToolCallComplete(
                        provider_id="codex",
                        session_id=session_id,
                        tool_call_id="tool-1",
                        tool_name="shell",
                        arguments='{"cmd":"echo hi"}',
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    ToolResult(
                        provider_id="codex",
                        session_id=session_id,
                        tool_call_id="tool-1",
                        tool_name="shell",
                        content="hi",
                        is_error=False,
                        duration_ms=23,
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    UsageReport(
                        provider_id="codex",
                        session_id=session_id,
                        input_tokens=1234,
                        output_tokens=456,
                        total_cost_usd=0.0312,
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    TextComplete(
                        provider_id="codex",
                        session_id=session_id,
                        content="done",
                        role="assistant",
                    )
                )
            )
            app.post_message(
                runner.AgentEvent(
                    SessionEnd(
                        provider_id="codex",
                        session_id=session_id,
                        success=True,
                    )
                )
            )
            app.post_message(runner.ProcessExited(0, was_cancelled=False))

        runner.run_provider = fake_run_provider  # type: ignore[method-assign]

        await pilot.press("r", "u", "n", "enter")
        await pilot.pause()
        await pilot.pause()

        assert main.status_bar.session_name == "codex-se"
        assert main.status_bar.tool_count == 1
        assert main.status_bar.last_tool == "shell"
        assert main.status_bar.input_tokens == 1234
        assert main.status_bar.output_tokens == 456
        assert main.status_bar.cost_usd == pytest.approx(0.0312)
        assert main.status_bar.activity == "complete"


@pytest.mark.asyncio
async def test_tui_bare_darwin_runs_system_command_not_chat() -> None:
    app = DGCApp()
    app._restore_last_session_context = lambda **_: None
    app._run_status_on_startup = lambda: None

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        async_calls: list[tuple[str, str]] = []
        chat_calls: list[str] = []

        app._run_async_command = lambda cmd, arg: async_calls.append((cmd, arg))  # type: ignore[method-assign]
        app._send_to_claude = lambda text: chat_calls.append(text)  # type: ignore[method-assign]

        await pilot.press("d", "a", "r", "w", "i", "n", "enter")
        await pilot.pause()

        assert async_calls == [("darwin", "")]
        assert chat_calls == []


@pytest.mark.asyncio
async def test_tui_slash_btw_opens_parallel_overlay() -> None:
    app = DGCApp()
    app._restore_last_session_context = lambda **_: None
    app._run_status_on_startup = lambda: None

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("/", "b", "t", "w", "enter")
        await pilot.pause()
        await pilot.pause()

        assert isinstance(app.screen, BTWScreen)


@pytest.mark.asyncio
async def test_btw_merge_adds_context_to_main_chat_history() -> None:
    app = DGCApp()
    app._restore_last_session_context = lambda **_: None
    app._run_status_on_startup = lambda: None

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        app._open_btw_screen()
        await pilot.pause()

        btw = app.screen
        assert isinstance(btw, BTWScreen)
        btw._transcript = [
            {"role": "user", "content": "Look into the side issue."},
            {"role": "assistant", "content": "The side issue traces back to model routing."},
        ]

        btw._merge_into_main(extra_note="Only apply if it helps the active task.")
        await pilot.pause()

        assert app._chat_history
        assert "[BTW merge from parallel thread" in app._chat_history[-1]["content"]
        assert "model routing" in app._chat_history[-1]["content"]


@pytest.mark.asyncio
async def test_tui_darkwin_autocorrects_to_darwin_command() -> None:
    app = DGCApp()
    app._restore_last_session_context = lambda **_: None
    app._run_status_on_startup = lambda: None

    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        async_calls: list[tuple[str, str]] = []
        chat_calls: list[str] = []

        app._run_async_command = lambda cmd, arg: async_calls.append((cmd, arg))  # type: ignore[method-assign]
        app._send_to_claude = lambda text: chat_calls.append(text)  # type: ignore[method-assign]

        await pilot.press("d", "a", "r", "k", "w", "i", "n", "enter")
        await pilot.pause()

        assert async_calls == [("darwin", "")]
        assert chat_calls == []
