"""DGC Terminal Interface -- Textual-based TUI for Dharmic Godel Claw.

Public API:
    DGCApp: The main Textual application
    run():  Entry point to launch the TUI
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys

from .app import DGCApp

_TERMINAL_RESTORE_SEQ = (
    "\x1b[?1000l"  # mouse tracking off
    "\x1b[?1002l"
    "\x1b[?1003l"
    "\x1b[?1004l"  # focus reporting off
    "\x1b[?1005l"
    "\x1b[?1006l"
    "\x1b[?1015l"
    "\x1b[?2004l"  # bracketed paste off
    "\x1b[?25h"    # show cursor
    "\x1b[0m"      # reset attributes
)


def _restore_terminal_state() -> None:
    """Best-effort terminal cleanup after interrupted Textual startup."""
    with contextlib.suppress(Exception):
        sys.stdout.write(_TERMINAL_RESTORE_SEQ)
        sys.stdout.flush()
    with contextlib.suppress(Exception):
        if sys.stdin.isatty():
            subprocess.run(
                ["stty", "sane"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def _env_truthy(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_alt_screen_for_terminal() -> bool:
    """Choose a pragmatic default mode for the current terminal."""
    term_program = (os.getenv("TERM_PROGRAM") or "").strip()
    if term_program == "Apple_Terminal":
        # Apple Terminal still collapses Textual inline apps to a thin band
        # in practice, so prefer the stable full-screen mode there.
        return True
    return False


def _mouse_enabled() -> bool:
    """Enable mouse capture unless explicitly disabled."""
    return not _env_truthy("DGC_TUI_NO_MOUSE", False)


def run() -> None:
    """Launch the DGC TUI.

    Default to Textual inline mode so terminal scrollback behaves more like
    Codex / Claude Code. Apple Terminal is forced back to the stable full-screen
    mode by default because its inline rendering still collapses to a thin band.
    Set ``DGC_TUI_INLINE=1`` to force inline mode, or ``DGC_TUI_ALT_SCREEN=1``
    to force the legacy full alternate-screen mode.
    """
    _restore_terminal_state()
    app = DGCApp()
    force_inline = _env_truthy("DGC_TUI_INLINE", False)
    if force_inline:
        use_alt_screen = False
    else:
        use_alt_screen = _env_truthy(
            "DGC_TUI_ALT_SCREEN",
            _default_alt_screen_for_terminal(),
        )
    run_kwargs = {
        "mouse": _mouse_enabled(),
        "inline": not use_alt_screen,
        "inline_no_clear": not use_alt_screen,
    }
    try:
        app.run(**run_kwargs)
    except KeyboardInterrupt:
        _restore_terminal_state()
        with contextlib.suppress(Exception):
            sys.stdout.write("\n")
            sys.stdout.flush()
