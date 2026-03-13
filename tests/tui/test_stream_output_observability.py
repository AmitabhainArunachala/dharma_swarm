"""Observability-focused tests for the TUI transcript widget."""

from __future__ import annotations

from textual import events
from rich.text import Text

from dharma_swarm.tui.engine.event_types import ToolProgress
from dharma_swarm.tui.engine.events import TextComplete, UsageReport
from dharma_swarm.tui.widgets.stream_output import StreamOutput


def test_commentary_messages_are_rendered_as_explicit_agent_notes(monkeypatch) -> None:
    output = StreamOutput()
    writes: list[object] = []

    monkeypatch.setattr(output, "_smart_write", lambda content, **kwargs: writes.append(content))
    monkeypatch.setattr(output, "_flush_buffer", lambda: None)

    output.handle_text_complete(
        TextComplete(
            provider_id="codex",
            session_id="sid",
            content="Running `pwd` to verify the current working directory.",
            role="commentary",
        )
    )

    assert len(writes) == 1
    rendered = writes[0]
    assert isinstance(rendered, Text)
    assert "AGENT" in rendered.plain
    assert "Running `pwd`" in rendered.plain


def test_usage_reports_render_with_explicit_usage_prefix(monkeypatch) -> None:
    output = StreamOutput()
    writes: list[object] = []

    monkeypatch.setattr(output, "_smart_write", lambda content, **kwargs: writes.append(content))
    monkeypatch.setattr(output, "_flush_buffer", lambda: None)

    output.handle_usage_report(
        UsageReport(
            provider_id="codex",
            session_id="sid",
            input_tokens=120,
            output_tokens=45,
            total_cost_usd=0.0123,
            model_breakdown={},
        )
    )

    assert len(writes) == 1
    rendered = writes[0]
    assert isinstance(rendered, Text)
    assert "USAGE" in rendered.plain
    assert "in=120 out=45 cost=$0.0123" in rendered.plain


def test_legacy_tool_progress_is_explicit(monkeypatch) -> None:
    output = StreamOutput()
    writes: list[object] = []

    monkeypatch.setattr(output, "_smart_write", lambda content, **kwargs: writes.append(content))
    monkeypatch.setattr(output, "_flush_buffer", lambda: None)

    output.handle_tool_progress(
        ToolProgress(tool_use_id="tool-1", tool_name="shell", elapsed_seconds=2.5)
    )

    assert len(writes) == 1
    rendered = writes[0]
    assert isinstance(rendered, Text)
    assert "TOOL" in rendered.plain
    assert "shell running (2.5s)" in rendered.plain


def test_mouse_scroll_over_output_scrolls_history(monkeypatch) -> None:
    output = StreamOutput()
    calls: list[str] = []

    monkeypatch.setattr(output, "scroll_history_up", lambda: calls.append("up"))
    monkeypatch.setattr(output, "scroll_history_down", lambda: calls.append("down"))

    output.on_mouse_scroll_up(
        events.MouseScrollUp(
            output,
            x=1,
            y=1,
            delta_x=0,
            delta_y=-1,
            button=0,
            shift=False,
            meta=False,
            ctrl=False,
        )
    )
    output.on_mouse_scroll_down(
        events.MouseScrollDown(
            output,
            x=1,
            y=1,
            delta_x=0,
            delta_y=1,
            button=0,
            shift=False,
            meta=False,
            ctrl=False,
        )
    )

    assert calls == ["up", "down"]
