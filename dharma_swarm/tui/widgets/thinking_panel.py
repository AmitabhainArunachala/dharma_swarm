"""Collapsible panel for extended thinking display.

Renders Claude's thinking/reasoning content in a collapsible container.
Collapsed by default to keep the main chat flow clean. The user can
expand to inspect the reasoning chain.
"""

from __future__ import annotations

from textual.widgets import Collapsible, Static


class ThinkingPanel(Collapsible):
    """Collapsible panel for extended thinking display.

    Starts collapsed by default. The thinking content is rendered in
    a dim style to visually distinguish it from the main response.
    Supports live updates via ``update_thinking()`` for streaming.
    """

    DEFAULT_CSS = """
    ThinkingPanel {
        margin: 0 2;
        padding: 0;
    }
    ThinkingPanel > Contents {
        color: $text 50%;
    }
    """

    THINKING_CONTENT_CLASS = "thinking-content"

    def __init__(self, thinking_text: str = "", **kwargs: object) -> None:
        self._thinking_text = thinking_text
        super().__init__(
            Static(thinking_text, classes=self.THINKING_CONTENT_CLASS),
            title="Thinking...",
            collapsed=True,
            **kwargs,
        )

    def update_thinking(self, text: str) -> None:
        """Replace the thinking content with new text.

        Safe to call even if the widget tree is not yet mounted --
        failures are silently ignored.
        """
        self._thinking_text = text
        try:
            content = self.query_one(
                f".{self.THINKING_CONTENT_CLASS}", Static
            )
            content.update(text)
        except Exception:
            pass

    @property
    def thinking_text(self) -> str:
        """Return the current thinking content."""
        return self._thinking_text
