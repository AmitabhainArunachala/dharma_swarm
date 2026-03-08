"""Main chat output widget — append-only RichLog for Claude Code streaming.

Uses RichLog (append-only) rather than Markdown (full re-render) because:
1. Append-only is O(1) per token; Markdown re-render is O(n).
2. RichLog auto-scrolls to bottom.
3. RichLog supports mixed Rich renderables (Markdown + Syntax + Panel).

The widget accumulates streaming deltas in a buffer and flushes at ~15 fps
via a timer, batching rapid token arrivals into single render calls.
"""

from __future__ import annotations

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


class StreamOutput(RichLog):
    """Main output widget — renders Claude's streaming response.

    Handles all event types from the engine layer:
    - StreamDelta: token-level text/thinking deltas (buffered, flushed at 15fps)
    - AssistantMessage: complete assistant turn with content blocks
    - ToolResult: tool execution results with success/error styling
    - ToolProgress: periodic heartbeat while tools run
    - ResultMessage: session completion summary
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

    # ── Event handlers ────────────────────────────────────────────────

    def handle_stream_delta(self, delta: StreamDelta) -> None:
        """Accumulate token-level deltas into the appropriate buffer."""
        if delta.delta_type == "text_delta":
            self._text_buffer += delta.content
        elif delta.delta_type == "thinking_delta":
            self._thinking_buffer += delta.content

    def handle_assistant_complete(self, msg: AssistantMessage) -> None:
        """Render a complete assistant message with all content blocks."""
        self._flush_buffer()
        for block in msg.content_blocks:
            block_type = block.get("type", "")

            if block_type == "text":
                self.write(Markdown(block.get("text", "")))

            elif block_type == "tool_use":
                tool_input = str(block.get("input", {}))
                if len(tool_input) > 300:
                    tool_input = tool_input[:300] + "..."
                tool_panel = Panel(
                    Syntax(tool_input, "json", theme="monokai", word_wrap=True),
                    title=f"[bold]Tool: {block.get('name', 'unknown')}[/bold]",
                    border_style="yellow",
                    subtitle=f"id: {block.get('id', '?')[:12]}...",
                )
                self.write(tool_panel)

            elif block_type == "thinking":
                self.write(
                    Panel(
                        Text(block.get("thinking", ""), style="dim"),
                        title="[dim]Thinking[/dim]",
                        border_style="blue",
                        expand=False,
                    )
                )

    def handle_tool_result(self, result: ToolResult) -> None:
        """Render a tool execution result with success/error styling."""
        self._flush_buffer()
        style = "red" if result.is_error else "green"
        icon = "\u2717" if result.is_error else "\u2713"
        duration = f" ({result.duration_ms}ms)" if result.duration_ms else ""
        content = result.content
        if len(content) > 500:
            content = content[:500] + f"\n... ({len(result.content)} chars total)"
        self.write(
            Panel(
                Text(content),
                title=f"{icon} {result.tool_name or 'tool'}{duration}",
                border_style=style,
            )
        )

    def handle_tool_progress(self, progress: ToolProgress) -> None:
        """Render a tool progress heartbeat."""
        self._flush_buffer()
        self.write(
            Text(
                f"  \u23f3 {progress.tool_name} running... "
                f"({progress.elapsed_seconds:.1f}s)",
                style="dim yellow",
            )
        )

    def handle_result(self, result: ResultMessage) -> None:
        """Render session completion summary."""
        self._flush_buffer()
        if result.is_error:
            error_detail = (
                ", ".join(result.errors) if result.errors else "unknown"
            )
            self.write(
                Text(
                    f"\n\u2717 Error: {result.subtype} -- {error_detail}",
                    style="bold red",
                )
            )
        else:
            self.write(
                Text(
                    f"\n\u2713 Done -- {result.num_turns} turns, "
                    f"${result.total_cost_usd:.4f}, "
                    f"{result.duration_ms / 1000:.1f}s",
                    style="dim green",
                )
            )

    # ── Canonical event handlers (v1.1 provider-agnostic layer) ─────

    def handle_text_delta(self, delta: CanonicalTextDelta) -> None:
        self._text_buffer += delta.content

    def handle_text_complete(self, msg: CanonicalTextComplete) -> None:
        self._flush_buffer()
        self.write(Markdown(msg.content))

    def handle_thinking_delta(self, delta: CanonicalThinkingDelta) -> None:
        self._thinking_buffer += delta.content

    def handle_thinking_complete(self, msg: CanonicalThinkingComplete) -> None:
        self._flush_buffer()
        title = "[dim]Thinking[/dim]"
        if msg.is_redacted:
            self.write(
                Panel(
                    Text("[redacted thinking]", style="dim"),
                    title=title,
                    border_style="blue",
                    expand=False,
                )
            )
            return
        self.write(
            Panel(
                Text(msg.content, style="dim"),
                title=title,
                border_style="blue",
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
        self.write(
            Panel(
                Syntax(args, "json", theme="monokai", word_wrap=True),
                title=f"[bold]Tool: {tool_call.tool_name or 'unknown'}[/bold]",
                border_style="yellow",
                subtitle=subtitle,
            )
        )

    def handle_tool_result_canonical(self, result: CanonicalToolResult) -> None:
        self._flush_buffer()
        style = "red" if result.is_error else "green"
        icon = "\u2717" if result.is_error else "\u2713"
        duration = f" ({result.duration_ms}ms)" if result.duration_ms else ""
        content = result.content
        if len(content) > 500:
            content = content[:500] + f"\n... ({len(result.content)} chars total)"
        self.write(
            Panel(
                Text(content),
                title=f"{icon} {result.tool_name or 'tool'}{duration}",
                border_style=style,
            )
        )

    def handle_tool_progress_canonical(self, progress: CanonicalToolProgress) -> None:
        self._flush_buffer()
        self.write(
            Text(
                f"  \u23f3 {progress.tool_name} running... "
                f"({progress.elapsed_seconds:.1f}s)",
                style="dim yellow",
            )
        )

    def handle_usage_report(self, usage: CanonicalUsageReport) -> None:
        self._flush_buffer()
        if usage.total_cost_usd is None:
            return
        self.write(
            Text(
                f"  [usage] in={usage.input_tokens} out={usage.output_tokens} "
                f"cost=${usage.total_cost_usd:.4f}",
                style="dim green",
            )
        )

    # ── Convenience writers ───────────────────────────────────────────

    def write_system(self, msg: str) -> None:
        """Write a system/status message. Callers should include Rich markup."""
        self.write(msg)

    def write_user(self, msg: str) -> None:
        """Write the user's prompt with a bold indicator."""
        self.write(Text(f"\n> {msg}", style="bold"))

    def write_error(self, msg: str) -> None:
        """Write an error message. Callers should include Rich markup."""
        self.write(msg)

    # ── Internal ──────────────────────────────────────────────────────

    def _flush_buffer(self) -> None:
        """Flush accumulated token buffers to the display.

        Called at ~15 fps by the timer. Batching avoids per-token render
        overhead while keeping latency below ~67ms.
        """
        if self._text_buffer:
            self.write(Text(self._text_buffer, style=""))
            self._text_buffer = ""
        if self._thinking_buffer:
            self.write(Text(self._thinking_buffer, style="dim italic"))
            self._thinking_buffer = ""
