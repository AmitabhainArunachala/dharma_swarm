"""Tests for TUI slash command handling."""

from __future__ import annotations

from dharma_swarm.tui.commands.system_commands import SystemCommandHandler


def test_plan_status_defaults_off() -> None:
    handler = SystemCommandHandler()
    out, action = handler.handle("plan")
    assert "Plan mode:" in out
    assert "OFF" in out
    assert action is None


def test_plan_on_returns_mode_set_action() -> None:
    handler = SystemCommandHandler()
    out, action = handler.handle("plan on")
    assert "enabled" in out.lower()
    assert action == "mode:set:P"


def test_plan_off_returns_mode_set_action() -> None:
    handler = SystemCommandHandler()
    out, action = handler.handle("plan off")
    assert "disabled" in out.lower()
    assert action == "mode:set:N"


def test_plan_status_reflects_mode_sync_from_app() -> None:
    handler = SystemCommandHandler()
    handler.set_mode("P")
    out, action = handler.handle("plan status")
    assert "ON" in out
    assert action is None
