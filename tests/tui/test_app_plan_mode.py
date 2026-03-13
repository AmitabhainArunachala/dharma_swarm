"""Tests for DGC app mode policy wiring."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

import dharma_swarm.tui.app as tui_app
from dharma_swarm.tui.app import DGCApp
from dharma_swarm.tui.engine.events import TextComplete


@pytest.fixture(autouse=True)
def _isolate_tui_policy_state(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setattr(tui_app, "MODEL_POLICY_PATH", tmp_path / "tui_model_policy.json")
    monkeypatch.setattr(tui_app, "MODEL_STATS_PATH", tmp_path / "tui_model_stats.json")


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
        self.lines: list[str] = []
        self.users: list[str] = []

    def write_system(self, msg: str) -> None:
        self.system.append(msg)

    def write_error(self, msg: str) -> None:
        self.errors.append(msg)

    def write(self, msg: str) -> None:
        self.lines.append(msg)

    def write_user(self, msg: str) -> None:
        self.users.append(msg)


class _DummyStatus:
    def __init__(self, running: bool) -> None:
        self.is_running = running


class _DummyMain:
    def __init__(self, running: bool) -> None:
        self.status_bar = _DummyStatus(running)
        self.stream_output = _DummyOutput()


class _DummyStore:
    def __init__(
        self,
        meta: dict[str, Any] | None,
        *,
        transcript: list[Any] | None = None,
    ) -> None:
        self._meta = meta
        self._transcript = list(transcript or [])
        self._tmpdir = Path(tempfile.mkdtemp(prefix="dgc-tui-store-"))
        self.root = self._tmpdir
        self.created: list[dict[str, Any]] = []
        self.appended: list[tuple[str, Any]] = []

    def latest_session(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._meta

    def load_meta(self, session_id: str) -> dict[str, Any]:
        if self._meta is None:
            raise FileNotFoundError(session_id)
        return dict(self._meta)

    def load_transcript(
        self,
        session_id: str,
        *,
        include_types: set[str] | None = None,
        limit: int | None = None,
    ) -> list[Any]:
        events = list(self._transcript)
        if include_types is not None:
            events = [
                event
                for event in events
                if str(getattr(event, "type", "")) in include_types
            ]
        if limit is not None and limit >= 0:
            return events[-limit:]
        return events

    def create_session(self, **kwargs: Any) -> str:
        session_id = str(kwargs["session_id"])
        session_dir = self.root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        meta = dict(self._meta or {})
        meta.update(kwargs)
        (session_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        self._meta = meta
        self.created.append(kwargs)
        return session_id

    def append_event(self, session_id: str, event: Any, *, strip_raw: bool = True) -> None:
        self.appended.append((session_id, event))
        self._transcript.append(event)


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


def test_get_state_context_includes_latent_gold(monkeypatch, tmp_path) -> None:
    import dharma_swarm.tui.app as tui_app

    monkeypatch.setattr(
        "dharma_swarm.context.read_memory_context",
        lambda **_: "  [retrieval:note] recent memory",
        raising=True,
    )
    monkeypatch.setattr(
        "dharma_swarm.context.read_latent_gold_overview",
        lambda **_: "  [idea:orphaned] proposal | latent branch",
        raising=True,
    )
    monkeypatch.setattr(tui_app, "HOME", tmp_path)
    monkeypatch.setattr(tui_app, "DHARMA_STATE", tmp_path / ".dharma")

    app = tui_app.DGCApp()
    out = app._get_state_context()

    assert "Recent memory:" in out
    assert "Latent gold:" in out
    assert "latent branch" in out


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


def test_send_to_claude_recovers_running_lock_from_completed_session_meta(monkeypatch) -> None:
    app = DGCApp()
    runner = _DummyRunner()
    runner.is_running = True
    app._provider_runner = runner  # type: ignore[assignment]
    app._session.session_id = "sid-meta-stale"
    app._session_store = _DummyStore({"status": "completed"})  # type: ignore[assignment]
    app._set_mode("N")

    main = _DummyMain(running=True)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "_get_state_context", lambda: "")

    app._send_to_claude("resume after stale completion")

    assert runner.mark_end_calls == 1
    assert len(runner.calls) == 1
    assert any(
        "Recovered stale provider lock from persisted session status=completed"
        in line
        for line in main.stream_output.system
    )


def test_report_provider_inactivity_recovers_from_completed_session_meta(monkeypatch) -> None:
    app = DGCApp()
    runner = _DummyRunner()
    runner.is_running = True
    app._provider_runner = runner  # type: ignore[assignment]
    app._session.session_id = "sid-meta-inactivity"
    app._session_store = _DummyStore({"status": "completed"})  # type: ignore[assignment]
    app._active_provider = "codex"
    app._active_model = "gpt-5.4"
    app._last_provider_event_ts = 0.0

    main = _DummyMain(running=True)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)

    app._report_provider_inactivity()

    assert runner.mark_end_calls == 1
    assert main.status_bar.is_running is False
    assert not any("No new events from" in line for line in main.stream_output.system)
    assert any(
        "Recovered stale provider lock from persisted session status=completed"
        in line
        for line in main.stream_output.system
    )


def test_report_provider_inactivity_explains_codex_offstream_gap(monkeypatch) -> None:
    app = DGCApp()
    runner = _DummyRunner()
    runner.is_running = True
    app._provider_runner = runner  # type: ignore[assignment]
    app._active_provider = "codex"
    app._active_model = "gpt-5.4"
    app._last_provider_event_ts = 0.0
    app._last_provider_event_label = "tool shell finished"

    main = _DummyMain(running=True)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "_recover_stale_provider_lock_from_session_meta", lambda: False)

    app._report_provider_inactivity()

    assert any(
        "reasoning off-stream after the last tool result" in line
        for line in main.stream_output.system
    )
    assert any("/cancel" in line for line in main.stream_output.system)


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
    monkeypatch.setenv("DGC_AUTO_RESUME", "1")

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


def test_restore_last_session_context_defaults_off(monkeypatch) -> None:
    app = DGCApp()
    meta = {
        "session_id": "dgc-20260308-000001-abcd",
        "provider_session_id": "prov-abc-123456789",
        "provider_id": "claude",
        "model_id": "claude-opus-4-6",
    }
    app._session_store = _DummyStore(meta)  # type: ignore[assignment]
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.delenv("DGC_AUTO_RESUME", raising=False)

    app._restore_last_session_context()

    assert app._provider_session_id is None
    assert not main.stream_output.system


def test_restore_last_session_history_replays_transcript_and_hydrates_chat_history(
    monkeypatch,
) -> None:
    app = DGCApp()
    transcript = [
        TextComplete(
            provider_id="codex",
            session_id="dgc-20260308-000001-abcd",
            content="hello",
            role="user",
        ),
        TextComplete(
            provider_id="codex",
            session_id="dgc-20260308-000001-abcd",
            content="hi there",
            role="assistant",
        ),
    ]
    meta = {
        "session_id": "dgc-20260308-000001-abcd",
        "provider_id": "codex",
        "model_id": "gpt-5.4",
    }
    app._session_store = _DummyStore(meta, transcript=transcript)  # type: ignore[assignment]
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)

    restored = app._restore_last_session_history()

    assert restored is True
    assert any("Session history" in line for line in main.stream_output.system)
    assert main.stream_output.users == ["hello"]
    assert "hi there" in main.stream_output.lines
    assert app._chat_history == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi there"},
    ]


def test_restore_last_session_context_skips_claude_resume_when_preferred_is_codex(
    monkeypatch,
) -> None:
    app = DGCApp()
    app._preferred_provider = "codex"
    app._preferred_model = "gpt-5.4"
    app._active_provider = "codex"
    app._active_model = "gpt-5.4"
    meta = {
        "session_id": "dgc-20260308-000001-abcd",
        "provider_session_id": "prov-abc-123456789",
        "provider_id": "claude",
        "model_id": "claude-opus-4-6",
    }
    app._session_store = _DummyStore(meta)  # type: ignore[assignment]
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.delenv("DGC_AUTO_RESUME", raising=False)

    app._restore_last_session_context()

    assert app._provider_session_id is None
    assert app._active_provider == "codex"
    assert app._active_model == "gpt-5.4"
    assert not main.stream_output.system


def test_send_to_claude_persists_local_user_turn(monkeypatch) -> None:
    app = DGCApp()
    runner = _DummyRunner()
    store = _DummyStore(None)
    app._provider_runner = runner  # type: ignore[assignment]
    app._session_store = store  # type: ignore[assignment]
    app._set_mode("N")

    monkeypatch.setattr(app, "_ensure_local_session_id", lambda: "sid-local-user")
    monkeypatch.setattr(app, "_get_state_context", lambda: "")

    app._send_to_claude("keep this turn")

    assert any(
        session_id == "sid-local-user"
        and isinstance(event, TextComplete)
        and event.role == "user"
        and event.content == "keep this turn"
        for session_id, event in store.appended
    )


def test_model_set_action_switches_provider_and_model(monkeypatch) -> None:
    app = DGCApp()
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "_save_model_policy", lambda: None)

    app._handle_action("model:set codex-5.4", "model set codex-5.4")

    assert app._active_provider == "codex"
    assert app._active_model == "gpt-5.4"
    assert any("Model switched" in line for line in main.stream_output.system)


def test_process_started_surfaces_codex_startup_hint(monkeypatch) -> None:
    app = DGCApp()
    main = _DummyMain(running=False)
    app._inflight_provider = "codex"
    app._inflight_model = "gpt-5.4"
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "set_timer", lambda *_args, **_kwargs: None)

    app.on_provider_runner_process_started(type("E", (), {})())

    assert main.status_bar.is_running is True
    assert any("Starting Codex session" in line for line in main.stream_output.system)


def test_report_slow_provider_start_writes_hint(monkeypatch) -> None:
    app = DGCApp()
    main = _DummyMain(running=False)
    app._provider_runner = type("Runner", (), {"is_running": True})()  # type: ignore[assignment]
    app._active_provider = "codex"
    app._active_model = "gpt-5.4"
    app._inflight_provider = "codex"
    app._inflight_model = "gpt-5.4"
    app._provider_event_seen = False
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)

    app._report_slow_provider_start()

    assert any("Still waiting for codex:gpt-5.4" in line for line in main.stream_output.system)


def test_model_set_resets_provider_session_even_same_provider(monkeypatch) -> None:
    app = DGCApp()
    app._provider_session_id = "prov-123"
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "_save_model_policy", lambda: None)

    app._handle_action("model:set opus-4.6", "model set opus-4.6")

    assert app._active_provider == "claude"
    assert app._active_model == "claude-opus-4-6"
    assert app._provider_session_id is None


def test_model_auto_action_toggles_fallback(monkeypatch) -> None:
    app = DGCApp()
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "_save_model_policy", lambda: None)

    app._handle_action("model:auto off", "model auto off")
    assert app._auto_model_fallback is False

    app._handle_action("model:auto on", "model auto on")
    assert app._auto_model_fallback is True


def test_model_set_action_accepts_index(monkeypatch) -> None:
    app = DGCApp()
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "_save_model_policy", lambda: None)

    app._handle_action("model:set 3", "model set 3")

    assert app._active_provider == "claude"
    assert app._active_model == "claude-opus-4-6"


def test_model_auto_strategy_sets_profile(monkeypatch) -> None:
    app = DGCApp()
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "_save_model_policy", lambda: None)
    app._auto_model_fallback = False

    app._handle_action("model:auto genius", "model auto genius")

    assert app._auto_model_fallback is True
    assert app._model_strategy == "genius"


def test_model_metrics_action_renders_output(monkeypatch) -> None:
    app = DGCApp()
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    app._model_stats = {
        "sonnet-4.5": {
            "successes": 3,
            "failures": 1,
            "consecutive_failures": 0,
            "ema_latency_ms": 420.0,
            "last_error": "",
        }
    }

    app._handle_action("model:metrics", "model metrics")

    assert any("Model metrics" in line for line in main.stream_output.lines)


def test_model_cooldown_clear_action(monkeypatch) -> None:
    app = DGCApp()
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    app._cooldown_until_by_alias = {"sonnet-4.5": 9999999999.0}

    app._handle_action("model:cooldown clear", "model cooldown clear")

    assert app._cooldown_until_by_alias == {}
    assert any("cooldowns cleared" in line.lower() for line in main.stream_output.system)


def test_inline_switch_short_circuits_send(monkeypatch) -> None:
    app = DGCApp()
    sent: list[str] = []
    monkeypatch.setattr(app, "_dispatch_prompt", lambda text, **kwargs: sent.append(text))

    handled = app._maybe_handle_inline_model_switch("please switch to opus 4.6")
    assert handled is True
    assert app._active_provider == "claude"
    assert app._active_model == "claude-opus-4-6"
    assert sent == []


def test_rate_limit_rejected_marks_pending_fallback(monkeypatch) -> None:
    from dharma_swarm.tui.engine.events import RateLimitEvent

    app = DGCApp()
    app._last_user_prompt = "finish the task"
    app._auto_model_fallback = True
    main = _DummyMain(running=False)
    monkeypatch.setattr(app, "_get_main_screen", lambda: main)

    event = type("E", (), {"event": RateLimitEvent(provider_id="claude", session_id="sid", status="rejected")})()
    app.on_provider_runner_agent_event(event)

    assert app._last_error_code == "rate_limit"
    assert app._pending_fallback is True


def test_auto_fallback_prefers_non_claude_provider_for_usage_exhaustion(monkeypatch) -> None:
    app = DGCApp()
    app._active_provider = "claude"
    app._active_model = "claude-opus-4-6"
    app._preferred_provider = "claude"
    app._preferred_model = "claude-opus-4-6"
    app._auto_model_fallback = True
    app._last_user_prompt = "keep going"
    app._last_error_code = "usage_exhausted"
    app._last_error_message = "You're out of extra usage · resets tomorrow"
    main = _DummyMain(running=False)
    dispatched: list[tuple[str, bool, bool]] = []
    policy_saves: list[bool] = []

    monkeypatch.setattr(app, "_get_main_screen", lambda: main)
    monkeypatch.setattr(app, "_save_model_policy", lambda: policy_saves.append(True))
    monkeypatch.setattr(app, "_provider_ready", lambda provider_id: True)
    monkeypatch.setattr(
        app,
        "_dispatch_prompt",
        lambda text, append_user=True, reset_fallback_queue=True: dispatched.append(
            (text, append_user, reset_fallback_queue)
        ),
    )

    moved = app._try_auto_fallback(main.stream_output, reason="usage exhaustion")

    assert moved is True
    assert app._active_provider == "codex"
    assert app._active_model == "gpt-5.4"
    assert app._preferred_provider == "codex"
    assert app._preferred_model == "gpt-5.4"
    assert policy_saves == [True]
    assert dispatched == [("keep going", False, False)]
    assert any("Preferred route updated to codex:gpt-5.4" in line for line in main.stream_output.system)
