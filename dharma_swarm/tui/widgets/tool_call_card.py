"""Compact tool call display with status coloring.

Renders as a single line with a colored left border indicating state:
running (yellow), success (green), or error (red). The status reactive
triggers CSS class updates for border styling.
"""

from __future__ import annotations

from textual.reactive import reactive
from textual.widget import Widget
from rich.text import Text


class ToolCallCard(Widget):
    """Compact tool call display -- shows name, status, duration.

    Reactive attributes:
    - tool_name: name of the tool being called
    - tool_id: unique identifier for this call
    - status: one of "running", "success", "error"
    - elapsed: wall-clock seconds since tool started
    - summary: optional one-line summary of the result
    """

    tool_name: reactive[str] = reactive("")
    tool_id: reactive[str] = reactive("")
    status: reactive[str] = reactive("running")
    elapsed: reactive[float] = reactive(0.0)
    summary: reactive[str] = reactive("")

    DEFAULT_CSS = """
    ToolCallCard {
        height: auto;
        margin: 0 0 1 0;
        padding: 0 1;
    }
    ToolCallCard.-running {
        border-left: thick $warning;
    }
    ToolCallCard.-success {
        border-left: thick $success;
    }
    ToolCallCard.-error {
        border-left: thick $error;
    }
    """

    STATUS_ICONS: dict[str, str] = {
        "running": "\u23f3",
        "success": "\u2713",
        "error": "\u2717",
    }

    STATUS_COLORS: dict[str, str] = {
        "running": "#B0895A",   # Kitsurubami
        "success": "#738C78",   # Rokusho
        "error": "#9A5E55",     # Bengara
    }

    def on_mount(self) -> None:
        """Apply initial CSS class based on default status."""
        self.add_class(f"-{self.status}")

    def render(self) -> Text:
        """Render the tool call as a single styled line."""
        icon = self.STATUS_ICONS.get(self.status, "?")
        color = self.STATUS_COLORS.get(self.status, "white")

        elapsed_str = f" ({self.elapsed:.1f}s)" if self.elapsed > 0 else ""
        summary_str = f" -- {self.summary}" if self.summary else ""

        return Text.from_markup(
            f"[{color}]{icon}[/{color}] "
            f"[bold]{self.tool_name}[/bold]"
            f"{elapsed_str}{summary_str}"
        )

    def watch_status(self, old_status: str, new_status: str) -> None:
        """Update CSS classes when status changes."""
        self.remove_class(f"-{old_status}")
        self.add_class(f"-{new_status}")
