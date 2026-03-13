"""Multi-line prompt input with Enter-to-submit.

Enter submits the prompt. On terminals supporting the kitty keyboard
protocol (kitty, WezTerm, iTerm2 with CSI u), Shift+Enter inserts a
newline. On other terminals, use Ctrl+J for a newline. Paste (bracketed
paste) works everywhere for multi-line input.
"""

from __future__ import annotations

from textual import events
from textual.message import Message
from textual.widgets import TextArea


class PromptInput(TextArea):
    """Multi-line input with Enter=submit, Shift+Enter or Ctrl+J=newline.

    Features:
    - Auto-resizes height (3 to 12 lines)
    - Posts Submitted message with full text on Enter
    - Shift+Enter (kitty protocol) or Ctrl+J for newline
    - Supports paste (Textual's bracketed paste)
    """

    DEFAULT_CSS = """
    PromptInput {
        height: auto;
        min-height: 3;
        max-height: 12;
        border: tall $accent;
        background: $surface;
    }
    PromptInput:focus {
        border: tall $accent 80%;
    }
    """

    class Submitted(Message):
        """Posted when the user presses Enter with non-empty text."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    def __init__(self, **kwargs: object) -> None:
        super().__init__(language=None, **kwargs)
        self.border_title = "Enter send | Shift+Enter/Ctrl+J newline"

    async def _on_key(self, event: events.Key) -> None:
        """Intercept Enter for submit; allow Shift+Enter and Ctrl+J for newline.

        Textual's key names:
        - ``"enter"``        -> submit
        - ``"shift+enter"``  -> newline (kitty protocol terminals)
        - ``"ctrl+j"``       -> newline (universal fallback)
        """
        if event.key == "enter":
            # Plain Enter -> submit if text is non-empty
            event.stop()
            event.prevent_default()
            text = self.text.strip()
            if text:
                self.post_message(self.Submitted(text))
                self.clear()
            return

        if event.key == "shift+enter":
            # Shift+Enter -> insert newline (kitty protocol terminals)
            event.stop()
            event.prevent_default()
            start, end = self.selection
            self._replace_via_keyboard("\n", start, end)
            return

        if event.key == "ctrl+j":
            # Ctrl+J -> insert newline (universal fallback)
            event.stop()
            event.prevent_default()
            start, end = self.selection
            self._replace_via_keyboard("\n", start, end)
            return

        # All other keys: delegate to parent TextArea
        await super()._on_key(event)
