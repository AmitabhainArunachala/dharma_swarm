"""DGC splash screen — shows ASCII art identity on startup.

Imports the Rich Text splash from :mod:`dharma_swarm.splash` which provides
styled box art with thinkodynamic elements (Sx=x, R_V<1.0, telos gates, etc.).
Falls back to a plain-text version if the splash module is unavailable.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

# Import splash art from existing module — it returns Rich Text objects
try:
    from dharma_swarm.splash import get_splash
except ImportError:
    get_splash = None

_FALLBACK_ART = r"""
    ╔══════════════════════════════════════════╗
    ║       DGC — Dharmic Godel Claw           ║
    ║       Telos: Jagat Kalyan               ║
    ╚══════════════════════════════════════════╝
"""


class SplashScreen(Screen):
    """DGC splash screen shown on startup.

    Press Enter, Escape, or Space to dismiss and proceed to the main workspace.
    """

    BINDINGS = [
        Binding("enter", "dismiss_splash", "Continue"),
        Binding("escape", "dismiss_splash", "Continue"),
        Binding("space", "dismiss_splash", "Continue"),
    ]

    def compose(self) -> ComposeResult:
        if get_splash is not None:
            art_widget = Static(get_splash(), id="splash-art")
        else:
            art_widget = Static(_FALLBACK_ART, id="splash-art")
        yield art_widget
        yield Static(
            "Press [bold]Enter[/bold] to continue",
            id="splash-prompt",
        )

    def action_dismiss_splash(self) -> None:
        """Dismiss the splash screen and return to the caller."""
        self.dismiss()
