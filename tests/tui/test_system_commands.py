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


def test_model_status_and_list_actions() -> None:
    handler = SystemCommandHandler()
    out, action = handler.handle("model status")
    assert out == ""
    assert action == "model:status"

    out, action = handler.handle("model list")
    assert out == ""
    assert action == "model:list"


def test_model_set_and_auto_actions() -> None:
    handler = SystemCommandHandler()

    out, action = handler.handle("model set opus-4.6")
    assert out == ""
    assert action == "model:set opus-4.6"

    out, action = handler.handle("model codex 5.4")
    assert out == ""
    assert action == "model:set codex 5.4"

    out, action = handler.handle("model auto on")
    assert out == ""
    assert action == "model:auto on"

    out, action = handler.handle("model auto genius")
    assert out == ""
    assert action == "model:auto genius"

    out, action = handler.handle("model strategy cost")
    assert out == ""
    assert action == "model:auto cost"

    out, action = handler.handle("model cost")
    assert out == ""
    assert action == "model:auto cost"

    out, action = handler.handle("model metrics")
    assert out == ""
    assert action == "model:metrics"

    out, action = handler.handle("model cooldown status")
    assert out == ""
    assert action == "model:cooldown status"

    out, action = handler.handle("model reset")
    assert out == ""
    assert action == "model:cooldown clear"

    out, action = handler.handle("model auto banana")
    assert "Usage" in out
    assert action is None


def test_darwin_command_routes_to_async_handler() -> None:
    handler = SystemCommandHandler()
    out, action = handler.handle("darwin")
    assert out == ""
    assert action == "async:darwin:"


def test_btw_command_opens_parallel_overlay() -> None:
    handler = SystemCommandHandler()
    out, action = handler.handle("btw investigate the side quest")
    assert out == ""
    assert action == "btw:open"


def test_unknown_command_suggests_darwin_for_darkwin() -> None:
    handler = SystemCommandHandler()
    out, action = handler.handle("darkwin")
    assert "/darwin" in out
    assert action is None


def test_resolve_bare_darkwin_autocorrects_to_darwin() -> None:
    handler = SystemCommandHandler()
    cmd, notice = handler.resolve_bare_command("darkwin")
    assert cmd == "darwin"
    assert notice is not None
    assert "/darwin" in notice


def test_evolve_status_routes_to_async_handler() -> None:
    handler = SystemCommandHandler()
    out, action = handler.handle("evolve status")
    assert out == ""
    assert action == "async:evolve:status"


def test_help_text_is_provider_neutral_and_transparent() -> None:
    handler = SystemCommandHandler()

    out, action = handler.handle("help")

    assert action is None
    assert "Internet access for the active route" in out
    assert "Cancel active provider run" in out
    assert "Ctrl+Y" in out
    assert "live tools, usage, and cost telemetry" in out
