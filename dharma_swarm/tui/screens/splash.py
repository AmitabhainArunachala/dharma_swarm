"""DGC splash screen — width-aware terminal field."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static

# Import splash art from existing module — it returns Rich Text objects
try:
    from dharma_swarm.splash import get_splash, render_splash_field
except ImportError:
    get_splash = None
    render_splash_field = None

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
            yield Static(get_splash(variant="compact"), id="splash-art")
        else:
            yield Static(_FALLBACK_ART, id="splash-art")

    def on_mount(self) -> None:
        """Render the full-field splash for the current terminal size."""
        self._refresh_splash()

    def on_resize(self, _event: events.Resize) -> None:
        """Keep the splash field aligned to the live viewport size."""
        self._refresh_splash()

    def _select_variant(self) -> str:
        """Select epic / medium / compact splash based on terminal size."""
        if self.size.width >= 100 and self.size.height >= 32:
            return "epic"
        if self.size.width >= 78 and self.size.height >= 28:
            return "medium"
        return "compact"

    def _refresh_splash(self) -> None:
        """Update the splash renderable to fit the current viewport."""
        if get_splash is None:
            return
        variant = self._select_variant()
        if render_splash_field is not None:
            art = render_splash_field(
                width=max(1, self.size.width),
                height=max(1, self.size.height),
                variant=variant,
            )
        else:
            art = get_splash(variant=variant)
        self.query_one("#splash-art", Static).update(art)

    def action_dismiss_splash(self) -> None:
        """Dismiss the splash screen and return to the caller."""
        self.dismiss()
