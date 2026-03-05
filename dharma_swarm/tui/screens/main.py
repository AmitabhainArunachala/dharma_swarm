"""Main workspace screen — status bar, chat output, prompt input, footer.

This is the primary DGC workspace where all interaction happens. It composes
the core widget trio (StatusBar, StreamOutput, PromptInput) into a vertical
layout with the footer providing key bindings.

Widget imports are deferred to handle the case where the widgets package
has not yet been built. When widgets are unavailable, placeholder Textual
widgets are used so the screen can still be imported and tested.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, RichLog, Static, Input

# Attempt to import custom widgets; fall back to stubs if not yet built.
try:
    from ..widgets.stream_output import StreamOutput
except ImportError:
    StreamOutput = None  # type: ignore[assignment, misc]

try:
    from ..widgets.prompt_input import PromptInput
except ImportError:
    PromptInput = None  # type: ignore[assignment, misc]

try:
    from ..widgets.status_bar import StatusBar
except ImportError:
    StatusBar = None  # type: ignore[assignment, misc]


class _StubStatusBar(Static):
    """Fallback status bar when the real widget is not yet available."""

    DEFAULT_CSS = """
    _StubStatusBar {
        dock: top;
        height: 1;
        background: #252018;
        color: #a89880;
    }
    """

    def __init__(self) -> None:
        super().__init__("DGC | status bar stub — build widgets layer to activate")


class _StubPromptInput(Input):
    """Fallback prompt input when the real widget is not yet available."""

    DEFAULT_CSS = """
    _StubPromptInput {
        dock: bottom;
        margin: 0 1;
        border: tall #8A6A1A;
        background: #252018;
    }
    """

    def __init__(self) -> None:
        super().__init__(placeholder="Type here... (stub — build widgets layer to activate)")


class MainScreen(Screen):
    """Primary DGC workspace — status bar, chat output, prompt input."""

    DEFAULT_CSS = """
    MainScreen {
        layout: vertical;
    }

    #main-area {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        # Status bar
        if StatusBar is not None:
            yield StatusBar()
        else:
            yield _StubStatusBar()

        # Main content area
        with Vertical(id="main-area"):
            if StreamOutput is not None:
                yield StreamOutput(id="stream-output")
            else:
                yield RichLog(
                    id="stream-output",
                    highlight=True,
                    markup=True,
                    wrap=True,
                )

        # Prompt input
        if PromptInput is not None:
            yield PromptInput(id="prompt-input")
        else:
            yield _StubPromptInput()

        yield Footer()

    def on_mount(self) -> None:
        """Focus the prompt input on mount."""
        self.set_timer(0.1, self._focus_input)

    def _focus_input(self) -> None:
        """Set focus to the prompt input widget."""
        try:
            self.query_one("#prompt-input").focus()
        except Exception:
            pass

    @property
    def stream_output(self) -> RichLog:
        """Access the stream output widget (RichLog or StreamOutput)."""
        return self.query_one("#stream-output", RichLog)

    @property
    def status_bar(self) -> Static:
        """Access the status bar widget."""
        if StatusBar is not None:
            return self.query_one(StatusBar)
        return self.query_one(_StubStatusBar)

    @property
    def prompt_input(self) -> Input:
        """Access the prompt input widget."""
        if PromptInput is not None:
            return self.query_one("#prompt-input", PromptInput)
        return self.query_one("#prompt-input", _StubPromptInput)
