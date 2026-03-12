"""DGC Terminal Interface -- Textual-based TUI for Dharmic Godel Claw.

Public API:
    DGCApp: The main Textual application
    run():  Entry point to launch the TUI
"""

from __future__ import annotations

import contextlib
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


def run() -> None:
    """Launch the DGC TUI."""
    app = DGCApp()
    try:
        app.run()
    except KeyboardInterrupt:
        _restore_terminal_state()
        with contextlib.suppress(Exception):
            sys.stdout.write("\n")
            sys.stdout.flush()
