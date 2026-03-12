"""Main chat output widget — append-only RichLog for Claude Code streaming.

Uses RichLog (append-only) rather than Markdown (full re-render) because:
1. Append-only is O(1) per token; Markdown re-render is O(n).
2. RichLog supports mixed Rich renderables (Markdown + Syntax + Panel).

The widget accumulates streaming deltas in a buffer and flushes at ~15 fps
via a timer, batching rapid token arrivals into single render calls.

Scroll behaviour: auto-scroll is paused when the user scrolls up (mouse
wheel, Page Up, arrow keys). A visual indicator appears. Auto-scroll
re-engages when the user presses End, or scrolls back to the bottom.

Copy: Ctrl+C copies the last complete assistant reply to clipboard.
Full conversation can be copied via /copy command. Shift+mouse drag
uses native terminal selection for arbitrary text.
"""

from __future__ import annotations

import subprocess

from textual import events
from textual.timer import Timer
from textual.widgets import RichLog
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from dharma_swarm.tui.engine.event_types import (
    AssistantMessage,
    ResultMessage,
    StreamDelta,
    ToolProgress,
    ToolResult,
)
from dharma_swarm.tui.engine.events import (
    ThinkingComplete as CanonicalThinkingComplete,
    ThinkingDelta as CanonicalThinkingDelta,
    TextComplete as CanonicalTextComplete,
    TextDelta as CanonicalTextDelta,
    ToolCallComplete as CanonicalToolCallComplete,
    ToolProgress as CanonicalToolProgress,
    ToolResult as CanonicalToolResult,
    UsageReport as CanonicalUsageReport,
)

# Keys that indicate the user is intentionally scrolling UP
_SCROLL_UP_KEYS = {"up", "pageup", "home"}
# Keys that indicate the user wants to return to bottom
_SCROLL_BOTTOM_KEYS = {"end"}


class StreamOutput(RichLog):
    """Main output widget — renders Claude's streaming response.

    Handles all event types from the engine layer:
    - StreamDelta: token-level text/thinking deltas (buffered, flushed at 15fps)
    - AssistantMessage: complete assistant turn with content blocks
    - ToolResult: tool execution results with success/error styling
    - ToolProgress: periodic heartbeat while tools run
    - ResultMessage: session completion summary

    Scroll lock: when user scrolls up via mouse wheel or keyboard, auto_scroll
    is disabled. It re-enables when user presses End or scrolls to the very
    bottom. A CSS class 'scroll-locked' is toggled for visual indication
    (e.g. scrollbar color change).

    Copy: tracks the last complete assistant reply text for Ctrl+C copying.
    """

    DEFAULT_CSS = """
    StreamOutput {
        background: $surface;
        scrollbar-background: $surface;
        scrollbar-color: $text-muted;
        padding: 0 1;
    }
    """

    FLUSH_FPS: float = 15.0

    def __init__(self, **kwargs: object) -> None:
        super().__init__(wrap=True, highlight=True, markup=True, **kwargs)
        self._text_buffer: str = ""
        self._thinking_buffer: str = ""
        self._flush_timer: Timer | None = None
        self._scroll_locked: bool = False
        # Track the last complete reply for copy
        self._last_reply_text: str = ""
        self._current_reply_accumulator: str = ""

    def on_mount(self) -> None:
        """Start the buffer flush timer at ~15 fps."""
        self._flush_timer = self.set_interval(
            1.0 / self.FLUSH_FPS, self._flush_buffer
        )

    def on_unmount(self) -> None:
        """Clean up the flush timer."""
        if self._flush_timer is not None:
            self._flush_timer.stop()
            self._flush_timer = None

    # ── Scroll-lock logic ──────────────────────────────────────────────

    def _lock_scroll(self) -> None:
        """Pause auto-scroll — user is reading history."""
        if not self._scroll_locked:
            self._scroll_locked = True
            self.auto_scroll = False
            self.add_class("scroll-locked")

    def _unlock_scroll(self) -> None:
        """Resume auto-scroll — user returned to bottom."""
        if self._scroll_locked:
            self._scroll_locked = False
            self.auto_scroll = True
            self.remove_class("scroll-locked")
            self.scroll_end(animate=False)

    def _is_near_bottom(self) -> bool:
        """Return True if within 3 lines of the bottom."""
        return (self.max_scroll_y - self.scroll_y) <= 3

    def on_mouse_scroll_up(self, _event: events.MouseScrollUp) -> None:
        """User scrolled up with mouse wheel — lock scroll."""
        self._lock_scroll()

    def on_mouse_scroll_down(self, _event: events.MouseScrollDown) -> None:
        """User scrolled down with mouse wheel — unlock if at bottom."""
        if self._is_near_bottom():
            self._unlock_scroll()

    async def _on_key(self, event: events.Key) -> None:
        """Handle scroll-related keys."""
        if event.key in _SCROLL_UP_KEYS:
            self._lock_scroll()
        elif event.key in _SCROLL_BOTTOM_KEYS:
            self._unlock_scroll()
        elif event.key == "down" or event.key == "pagedown":
            # Check after scrolling if we reached bottom
            await super()._on_key(event)
            if self._is_near_bottom():
                self._unlock_scroll()
            return
        await super()._on_key(event)

    def scroll_to_bottom(self) -> None:
        """Public API: force scroll to bottom and re-enable auto-scroll."""
        self._unlock_scroll()

    def _smart_write(self, content: object, **kwargs: object) -> None:
        """Write content respecting scroll lock.

        If user has scrolled up, we still append content (it goes to the
        bottom of the buffer) but we explicitly pass scroll_end=False to
        prevent the viewport from jumping.
        """
        if self._scroll_locked:
            self.write(content, scroll_end=False, **kwargs)  # type: ignore[arg-type]
        else:
            self.write(content, **kwargs)

    # ── Copy support ──────────────────────────────────────────────────

    def get_last_reply(self) -> str:
        """Return the text of the last complete assistant reply."""
        return self._last_reply_text

    def copy_last_reply_to_clipboard(self) -> bool:
        """Copy the last assistant reply to system clipboard. Returns success."""
        text = self._last_reply_text
        if not text:
            return False
        try:
            proc = subprocess.run(
                ["pbcopy"],
                input=text,
                capture_output=True,
                text=True,
                timeout=5,
            )
            return proc.returncode == 0
        except Exception:
            return False

    # ── Event handlers ────────────────────────────────────────────────

    def handle_stream_delta(self, delta: StreamDelta) -> None:
        """Accumulate token-level deltas into the appropriate buffer."""
        if delta.delta_type == "text_delta":
            self._text_buffer += delta.content
            self._current_reply_accumulator += delta.content
        elif delta.delta_type == "thinking_delta":
            self._thinking_buffer += delta.content

    def handle_assistant_complete(self, msg: AssistantMessage) -> None:
        """Render a complete assistant message with all content blocks."""
        self._flush_buffer()
        reply_parts: list[str] = []
        for block in msg.content_blocks:
            block_type = block.get("type", "")

            if block_type == "text":
                text = block.get("text", "")
                reply_parts.append(text)
                self._smart_write(Markdown(text))

            elif block_type == "tool_use":
                tool_input = str(block.get("input", {}))
                if len(tool_input) > 300:
                    tool_input = tool_input[:300] + "..."
                tool_panel = Panel(
                    Syntax(tool_input, "json", theme="monokai", word_wrap=True),
                    title=f"[bold]Tool: {block.get('name', 'unknown')}[/bold]",
                    border_style="#C2956B",
                    subtitle=f"id: {block.get('id', '?')[:12]}...",
                )
                self._smart_write(tool_panel)

            elif block_type == "thinking":
                self._smart_write(
                    Panel(
                        Text(block.get("thinking", ""), style="dim"),
                        title="[dim]Thinking[/dim]",
                        border_style="#9B85B8",
                        expand=False,
                    )
                )
        if reply_parts:
            self._last_reply_text = "\n\n".join(reply_parts)

    def handle_tool_result(self, result: ToolResult) -> None:
        """Render a tool execution result with success/error styling."""
        self._flush_buffer()
        style = "#C25B52" if result.is_error else "#5D8C6E"
        icon = "\u2717" if result.is_error else "\u2713"
        duration = f" ({result.duration_ms}ms)" if result.duration_ms else ""
        content = result.content
        if len(content) > 500:
            content = content[:500] + f"\n... ({len(result.content)} chars total)"
        self._smart_write(
            Panel(
                Text(content),
                title=f"{icon} {result.tool_name or 'tool'}{duration}",
                border_style=style,
            )
        )

    def handle_tool_progress(self, progress: ToolProgress) -> None:
        """Render a tool progress heartbeat."""
        self._flush_buffer()
        self._smart_write(
            Text(
                f"  \u23f3 {progress.tool_name} running... "
                f"({progress.elapsed_seconds:.1f}s)",
                style="dim #C2956B",
            )
        )

    def handle_result(self, result: ResultMessage) -> None:
        """Render session completion summary."""
        self._flush_buffer()
        # Finalize the reply accumulator
        if self._current_reply_accumulator.strip():
            self._last_reply_text = self._current_reply_accumulator.strip()
        self._current_reply_accumulator = ""

        if result.is_error:
            error_detail = (
                ", ".join(result.errors) if result.errors else "unknown"
            )
            self._smart_write(
                Text(
                    f"\n\u2717 Error: {result.subtype} -- {error_detail}",
                    style="bold #C25B52",
                )
            )
        else:
            self._smart_write(
                Text(
                    f"\n\u2713 Done -- {result.num_turns} turns, "
                    f"${result.total_cost_usd:.4f}, "
                    f"{result.duration_ms / 1000:.1f}s",
                    style="dim #5D8C6E",
                )
            )

    # ── Canonical event handlers (v1.1 provider-agnostic layer) ─────

    def handle_text_delta(self, delta: CanonicalTextDelta) -> None:
        self._text_buffer += delta.content
        self._current_reply_accumulator += delta.content

    def handle_text_complete(self, msg: CanonicalTextComplete) -> None:
        self._flush_buffer()
        self._smart_write(Markdown(msg.content))
        # Save complete reply
        self._last_reply_text = msg.content
        self._current_reply_accumulator = ""

    def handle_thinking_delta(self, delta: CanonicalThinkingDelta) -> None:
        self._thinking_buffer += delta.content

    def handle_thinking_complete(self, msg: CanonicalThinkingComplete) -> None:
        self._flush_buffer()
        title = "[dim]Thinking[/dim]"
        if msg.is_redacted:
            self._smart_write(
                Panel(
                    Text("[redacted thinking]", style="dim"),
                    title=title,
                    border_style="#9B85B8",
                    expand=False,
                )
            )
            return
        self._smart_write(
            Panel(
                Text(msg.content, style="dim"),
                title=title,
                border_style="#9B85B8",
                expand=False,
            )
        )

    def handle_tool_call_complete(self, tool_call: CanonicalToolCallComplete) -> None:
        self._flush_buffer()
        args = tool_call.arguments
        if len(args) > 300:
            args = args[:300] + "..."
        subtitle = f"id: {tool_call.tool_call_id[:12]}..."
        if tool_call.provider_options.get("requires_confirmation"):
            subtitle += " | gated"
        self._smart_write(
            Panel(
                Syntax(args, "json", theme="monokai", word_wrap=True),
                title=f"[bold]Tool: {tool_call.tool_name or 'unknown'}[/bold]",
                border_style="#C2956B",
                subtitle=subtitle,
            )
        )

    def handle_tool_result_canonical(self, result: CanonicalToolResult) -> None:
        self._flush_buffer()
        style = "#C25B52" if result.is_error else "#5D8C6E"
        icon = "\u2717" if result.is_error else "\u2713"
        duration = f" ({result.duration_ms}ms)" if result.duration_ms else ""
        content = result.content
        if len(content) > 500:
            content = content[:500] + f"\n... ({len(result.content)} chars total)"
        self._smart_write(
            Panel(
                Text(content),
                title=f"{icon} {result.tool_name or 'tool'}{duration}",
                border_style=style,
            )
        )

    def handle_tool_progress_canonical(self, progress: CanonicalToolProgress) -> None:
        self._flush_buffer()
        self._smart_write(
            Text(
                f"  \u23f3 {progress.tool_name} running... "
                f"({progress.elapsed_seconds:.1f}s)",
                style="dim #C2956B",
            )
        )

    def handle_usage_report(self, usage: CanonicalUsageReport) -> None:
        self._flush_buffer()
        if usage.total_cost_usd is None:
            return
        self._smart_write(
            Text(
                f"  [usage] in={usage.input_tokens} out={usage.output_tokens} "
                f"cost=${usage.total_cost_usd:.4f}",
                style="dim #5D8C6E",
            )
        )

    # ── Convenience writers ───────────────────────────────────────────

    def write_system(self, msg: str) -> None:
        """Write a system/status message. Callers should include Rich markup."""
        self._smart_write(msg)

    def write_user(self, msg: str) -> None:
        """Write the user's prompt with a bold indicator."""
        self._smart_write(Text(f"\n> {msg}", style="bold"))
        # Reset reply accumulator for new turn
        self._current_reply_accumulator = ""

    def write_error(self, msg: str) -> None:
        """Write an error message. Callers should include Rich markup."""
        self._smart_write(msg)

    # ── Internal ──────────────────────────────────────────────────────

    def _flush_buffer(self) -> None:
        """Flush accumulated token buffers to the display.

        Called at ~15 fps by the timer. Batching avoids per-token render
        overhead while keeping latency below ~67ms.
        """
        if self._text_buffer:
            self._smart_write(Text(self._text_buffer, style=""))
            self._text_buffer = ""
        if self._thinking_buffer:
            self._smart_write(Text(self._thinking_buffer, style="dim italic"))
            self._thinking_buffer = ""
