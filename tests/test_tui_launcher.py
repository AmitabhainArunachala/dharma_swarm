"""Tests for dharma_swarm.tui_launcher — TUI launch with fallback chain."""

from __future__ import annotations

import sys

import pytest


# ---------------------------------------------------------------------------
# launch_tui fallback behaviour
# ---------------------------------------------------------------------------


def test_launch_tui_new_tui_success(monkeypatch):
    """When the new TUI's run() works, launch_tui should call it and return."""
    called = {}

    def fake_run():
        called["new"] = True

    # Patch the import so `from dharma_swarm.tui import run` yields fake_run
    import types

    fake_tui = types.ModuleType("dharma_swarm.tui")
    fake_tui.run = fake_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dharma_swarm.tui", fake_tui)

    # Must reload tui_launcher so the import resolves to our fake
    from dharma_swarm import tui_launcher
    import importlib

    importlib.reload(tui_launcher)

    tui_launcher.launch_tui()
    assert called.get("new") is True


def test_launch_tui_falls_back_to_legacy(monkeypatch):
    """When the new TUI raises, launch_tui should try tui_legacy.DGCApp."""
    called = {}

    # Make the new TUI fail
    import types

    bad_tui = types.ModuleType("dharma_swarm.tui")

    def bad_run():
        raise RuntimeError("new TUI broken")

    bad_tui.run = bad_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dharma_swarm.tui", bad_tui)

    # Provide a mock tui_legacy with DGCApp
    class FakeDGCApp:
        def run(self):
            called["legacy"] = True

    fake_legacy = types.ModuleType("dharma_swarm.tui_legacy")
    fake_legacy.DGCApp = FakeDGCApp  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dharma_swarm.tui_legacy", fake_legacy)

    from dharma_swarm import tui_launcher
    import importlib

    importlib.reload(tui_launcher)

    tui_launcher.launch_tui()
    assert called.get("legacy") is True


def test_launch_tui_exits_when_all_fail(monkeypatch):
    """When both new and legacy TUI fail, launch_tui should sys.exit(1)."""
    import types

    # New TUI fails
    bad_tui = types.ModuleType("dharma_swarm.tui")

    def bad_run():
        raise RuntimeError("new TUI broken")

    bad_tui.run = bad_run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "dharma_swarm.tui", bad_tui)

    # Also patch the parent package attribute so that
    # `from dharma_swarm import tui as _old_tui` returns bad_tui too
    # (Python checks the package attribute, not just sys.modules)
    import dharma_swarm
    monkeypatch.setattr(dharma_swarm, "tui", bad_tui, raising=False)

    # Legacy fails with ImportError (module not found)
    monkeypatch.setitem(sys.modules, "dharma_swarm.tui_legacy", None)

    from dharma_swarm import tui_launcher
    import importlib

    importlib.reload(tui_launcher)

    with pytest.raises(SystemExit) as exc_info:
        tui_launcher.launch_tui()
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# Module-level import sanity
# ---------------------------------------------------------------------------


def test_tui_launcher_importable():
    """tui_launcher module should be importable without side effects."""
    from dharma_swarm import tui_launcher

    assert hasattr(tui_launcher, "launch_tui")
    assert callable(tui_launcher.launch_tui)
