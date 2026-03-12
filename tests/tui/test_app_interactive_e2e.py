"""End-to-end Textual pilot tests for DGC TUI interactivity."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import dharma_swarm.tui.app as tui_app
from dharma_swarm.tui.app import DGCApp
from dharma_swarm.tui.engine.events import SessionEnd, SessionStart, TextComplete


@pytest.fixture(autouse=True)
def _isolate_tui_state(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(tui_app, "MODEL_POLICY_PATH", tmp_path / "tui_model_policy.json")
    monkeypatch.setattr(tui_app, "MODEL_STATS_PATH", tmp_path / "tui_model_stats.json")
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
    app._restore_last_session_context = lambda: None
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
    app._restore_last_session_context = lambda: None
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
