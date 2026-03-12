"""Tests for the TUI entrypoint wrapper."""

from __future__ import annotations

import dharma_swarm.tui as tui


def test_run_restores_terminal_on_keyboard_interrupt(monkeypatch) -> None:
    called: dict[str, int] = {"restore": 0}

    class _FakeApp:
        def run(self) -> None:
            raise KeyboardInterrupt

    monkeypatch.setattr(tui, "DGCApp", _FakeApp)
    monkeypatch.setattr(
        tui,
        "_restore_terminal_state",
        lambda: called.__setitem__("restore", called["restore"] + 1),
    )

    tui.run()

    assert called["restore"] == 1
