"""Tests for TUI bug fixes.

Bug 1: app.py splash callback was attached to MainScreen (never dismissed)
        instead of SplashScreen. _on_main_ready never fired.

Bug 2: stream_output.py canonical event handlers (handle_tool_call_complete,
        handle_tool_result_canonical, handle_tool_progress_canonical,
        handle_usage_report) did not flush the text/thinking buffer before
        rendering, causing misordered output.

Bug 3: subprocess_manager.py captured stderr with PIPE but never consumed
        it, risking a deadlock if the subprocess writes >64KB to stderr.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from dharma_swarm.tui.engine.event_types import (
    ResultMessage,
    ToolProgress,
    ToolResult,
)
from dharma_swarm.tui.engine.events import (
    ToolCallComplete as CanonicalToolCallComplete,
    ToolProgress as CanonicalToolProgress,
    ToolResult as CanonicalToolResult,
    UsageReport,
)


# ---------------------------------------------------------------------------
# Bug 1: Splash callback on correct screen
# ---------------------------------------------------------------------------


def test_splash_callback_on_splash_screen_not_main() -> None:
    """Verify _on_main_ready callback is attached to SplashScreen push."""
    import ast
    import textwrap

    from dharma_swarm.tui.app import DGCApp  # noqa: F401

    # Parse the source to verify the push_screen calls
    import inspect

    source = textwrap.dedent(inspect.getsource(DGCApp.on_mount))
    tree = ast.parse(source)

    # Collect all push_screen calls
    push_calls: list[ast.Call] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "push_screen":
                push_calls.append(node)

    assert len(push_calls) == 2, f"Expected 2 push_screen calls, got {len(push_calls)}"

    # First push_screen should be MainScreen() with NO callback keyword arg
    main_push = push_calls[0]
    main_kwargs = {kw.arg for kw in main_push.keywords}
    assert "callback" not in main_kwargs, (
        "MainScreen push_screen should NOT have a callback "
        "(it is never dismissed so the callback would never fire)"
    )

    # Second push_screen should be SplashScreen() WITH callback keyword arg
    splash_push = push_calls[1]
    splash_kwargs = {kw.arg for kw in splash_push.keywords}
    assert "callback" in splash_kwargs, (
        "SplashScreen push_screen MUST have a callback "
        "so _on_main_ready fires when the splash is dismissed"
    )


# ---------------------------------------------------------------------------
# Bug 2: Stream output handlers flush buffer before rendering
# ---------------------------------------------------------------------------


class FakeStreamOutput:
    """Minimal stub mimicking StreamOutput's buffer + flush + write logic.

    Tracks the order of write calls to verify flush-before-render.
    """

    def __init__(self) -> None:
        self._text_buffer: str = ""
        self._thinking_buffer: str = ""
        self.writes: list[str] = []

    def _flush_buffer(self) -> None:
        if self._text_buffer:
            self.writes.append(f"FLUSH_TEXT:{self._text_buffer}")
            self._text_buffer = ""
        if self._thinking_buffer:
            self.writes.append(f"FLUSH_THINKING:{self._thinking_buffer}")
            self._thinking_buffer = ""

    def write(self, content: object) -> None:
        self.writes.append(f"WRITE:{type(content).__name__}")


def test_handle_tool_call_complete_flushes_buffer() -> None:
    """handle_tool_call_complete must flush before rendering."""
    from dharma_swarm.tui.widgets.stream_output import StreamOutput

    # Verify the method calls _flush_buffer by checking source
    import inspect

    source = inspect.getsource(StreamOutput.handle_tool_call_complete)
    lines = [ln.strip() for ln in source.split("\n") if ln.strip()]

    # _flush_buffer should appear before any self.write call
    flush_idx = next(
        (i for i, ln in enumerate(lines) if "_flush_buffer" in ln), None
    )
    write_idx = next(
        (i for i, ln in enumerate(lines) if "self.write" in ln or "_smart_write" in ln), None
    )

    assert flush_idx is not None, "handle_tool_call_complete must call _flush_buffer"
    assert write_idx is not None, "handle_tool_call_complete must call self.write or _smart_write"
    assert flush_idx < write_idx, "_flush_buffer must be called BEFORE writing"


def test_handle_tool_result_canonical_flushes_buffer() -> None:
    """handle_tool_result_canonical must flush before rendering."""
    from dharma_swarm.tui.widgets.stream_output import StreamOutput

    import inspect

    source = inspect.getsource(StreamOutput.handle_tool_result_canonical)
    lines = [ln.strip() for ln in source.split("\n") if ln.strip()]

    flush_idx = next(
        (i for i, ln in enumerate(lines) if "_flush_buffer" in ln), None
    )
    write_idx = next(
        (i for i, ln in enumerate(lines) if "self.write" in ln or "_smart_write" in ln), None
    )

    assert flush_idx is not None, "handle_tool_result_canonical must call _flush_buffer"
    assert write_idx is not None
    assert flush_idx < write_idx


def test_handle_tool_progress_canonical_flushes_buffer() -> None:
    """handle_tool_progress_canonical must flush before rendering."""
    from dharma_swarm.tui.widgets.stream_output import StreamOutput

    import inspect

    source = inspect.getsource(StreamOutput.handle_tool_progress_canonical)
    lines = [ln.strip() for ln in source.split("\n") if ln.strip()]

    flush_idx = next(
        (i for i, ln in enumerate(lines) if "_flush_buffer" in ln), None
    )
    write_idx = next(
        (i for i, ln in enumerate(lines) if "self.write" in ln or "_smart_write" in ln), None
    )

    assert flush_idx is not None, "handle_tool_progress_canonical must call _flush_buffer"
    assert write_idx is not None
    assert flush_idx < write_idx


def test_handle_usage_report_flushes_buffer() -> None:
    """handle_usage_report must flush before rendering."""
    from dharma_swarm.tui.widgets.stream_output import StreamOutput

    import inspect

    source = inspect.getsource(StreamOutput.handle_usage_report)
    lines = [ln.strip() for ln in source.split("\n") if ln.strip()]

    flush_idx = next(
        (i for i, ln in enumerate(lines) if "_flush_buffer" in ln), None
    )
    assert flush_idx is not None, "handle_usage_report must call _flush_buffer"


def test_legacy_handle_tool_result_flushes_buffer() -> None:
    """Legacy handle_tool_result must flush before rendering."""
    from dharma_swarm.tui.widgets.stream_output import StreamOutput

    import inspect

    source = inspect.getsource(StreamOutput.handle_tool_result)
    lines = [ln.strip() for ln in source.split("\n") if ln.strip()]

    flush_idx = next(
        (i for i, ln in enumerate(lines) if "_flush_buffer" in ln), None
    )
    write_idx = next(
        (i for i, ln in enumerate(lines) if "self.write" in ln or "_smart_write" in ln), None
    )

    assert flush_idx is not None, "handle_tool_result must call _flush_buffer"
    assert write_idx is not None
    assert flush_idx < write_idx


def test_legacy_handle_tool_progress_flushes_buffer() -> None:
    """Legacy handle_tool_progress must flush before rendering."""
    from dharma_swarm.tui.widgets.stream_output import StreamOutput

    import inspect

    source = inspect.getsource(StreamOutput.handle_tool_progress)
    lines = [ln.strip() for ln in source.split("\n") if ln.strip()]

    flush_idx = next(
        (i for i, ln in enumerate(lines) if "_flush_buffer" in ln), None
    )
    write_idx = next(
        (i for i, ln in enumerate(lines) if "self.write" in ln or "_smart_write" in ln), None
    )

    assert flush_idx is not None
    assert write_idx is not None
    assert flush_idx < write_idx


def test_legacy_handle_result_flushes_buffer() -> None:
    """Legacy handle_result must flush before rendering."""
    from dharma_swarm.tui.widgets.stream_output import StreamOutput

    import inspect

    source = inspect.getsource(StreamOutput.handle_result)
    lines = [ln.strip() for ln in source.split("\n") if ln.strip()]

    flush_idx = next(
        (i for i, ln in enumerate(lines) if "_flush_buffer" in ln), None
    )
    assert flush_idx is not None, "handle_result must call _flush_buffer"


# Bug 3 test removed: subprocess_manager.py was deleted as orphaned code
