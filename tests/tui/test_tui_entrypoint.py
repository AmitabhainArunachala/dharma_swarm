"""Tests for the TUI entrypoint wrapper."""

from __future__ import annotations

import dharma_swarm.tui as tui


def test_run_restores_terminal_on_keyboard_interrupt(monkeypatch) -> None:
    called: dict[str, int] = {"restore": 0}
    captured: dict[str, object] = {}

    class _FakeApp:
        def run(self, *args, **kwargs) -> None:
            captured.update(kwargs)
            raise KeyboardInterrupt

    monkeypatch.setattr(tui, "DGCApp", _FakeApp)
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.delenv("DGC_TUI_ALT_SCREEN", raising=False)
    monkeypatch.delenv("DGC_TUI_INLINE", raising=False)
    monkeypatch.setattr(
        tui,
        "_restore_terminal_state",
        lambda: called.__setitem__("restore", called["restore"] + 1),
    )

    tui.run()

    assert called["restore"] == 2
    assert captured["mouse"] is True
    assert captured["inline"] is True
    assert captured["inline_no_clear"] is True


def test_run_restores_terminal_before_launch(monkeypatch) -> None:
    called: dict[str, int] = {"restore": 0}
    captured: dict[str, object] = {}

    class _FakeApp:
        def run(self, *args, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(tui, "DGCApp", _FakeApp)
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.delenv("DGC_TUI_ALT_SCREEN", raising=False)
    monkeypatch.delenv("DGC_TUI_INLINE", raising=False)
    monkeypatch.setattr(
        tui,
        "_restore_terminal_state",
        lambda: called.__setitem__("restore", called["restore"] + 1),
    )

    tui.run()

    assert called["restore"] == 1
    assert captured["mouse"] is True
    assert captured["inline"] is True
    assert captured["inline_no_clear"] is True


def test_run_can_force_alt_screen(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeApp:
        def run(self, *args, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(tui, "DGCApp", _FakeApp)
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.setenv("DGC_TUI_ALT_SCREEN", "1")

    tui.run()

    assert captured["mouse"] is True
    assert captured["inline"] is False
    assert captured["inline_no_clear"] is False


def test_run_defaults_to_alt_screen_in_apple_terminal(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeApp:
        def run(self, *args, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(tui, "DGCApp", _FakeApp)
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    monkeypatch.delenv("DGC_TUI_ALT_SCREEN", raising=False)
    monkeypatch.delenv("DGC_TUI_INLINE", raising=False)

    tui.run()

    assert captured["inline"] is False
    assert captured["inline_no_clear"] is False


def test_run_inline_override_wins_in_apple_terminal(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeApp:
        def run(self, *args, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(tui, "DGCApp", _FakeApp)
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    monkeypatch.setenv("DGC_TUI_INLINE", "1")

    tui.run()

    assert captured["inline"] is True
    assert captured["inline_no_clear"] is True


def test_run_can_disable_mouse(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeApp:
        def run(self, *args, **kwargs) -> None:
            captured.update(kwargs)

    monkeypatch.setattr(tui, "DGCApp", _FakeApp)
    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")
    monkeypatch.setenv("DGC_TUI_NO_MOUSE", "1")

    tui.run()

    assert captured["mouse"] is False
