"""Compatibility launcher for the Dharma Textual TUI."""

from __future__ import annotations

import sys


def launch_tui() -> None:
    """Launch the current TUI, falling back to the legacy app if needed."""
    try:
        from dharma_swarm.tui import run

        run()
        return
    except Exception as new_exc:
        print(f"New TUI failed: {new_exc}", file=sys.stderr)

    try:
        from dharma_swarm.tui_legacy import DGCApp

        DGCApp().run()
        return
    except Exception as legacy_exc:
        print(f"Legacy TUI failed: {legacy_exc}", file=sys.stderr)
        raise SystemExit(1) from legacy_exc


__all__ = ["launch_tui"]
