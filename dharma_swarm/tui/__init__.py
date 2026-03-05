"""DGC Terminal Interface -- Textual-based TUI for Dharmic Godel Claw.

Public API:
    DGCApp: The main Textual application
    run():  Entry point to launch the TUI
"""

from .app import DGCApp


def run() -> None:
    """Launch the DGC TUI."""
    app = DGCApp()
    app.run()
