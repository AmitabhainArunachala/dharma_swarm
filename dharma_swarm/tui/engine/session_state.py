"""Lightweight state machine tracking a Claude Code session lifecycle.

Pure stdlib — updates in response to parsed events from :mod:`stream_parser`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .event_types import (
    AssistantMessage,
    ResultMessage,
    SystemInit,
    ToolResult,
)
from .events import (
    SessionEnd,
    SessionStart,
    TextComplete,
    ToolCallComplete,
    ToolResult as CanonicalToolResult,
    UsageReport,
)


@dataclass
class SessionState:
    """Tracks the evolving state of a single Claude Code session.

    Feed parsed events via :meth:`handle_event` to keep state current.
    """

    session_id: str | None = None
    model: str = ""
    tools: list[str] = field(default_factory=list)
    total_cost_usd: float = 0.0
    turn_count: int = 0
    is_running: bool = False
    last_tool_use_map: dict[str, str] = field(default_factory=dict)

    def handle_event(self, event: object) -> None:
        """Update state based on a parsed event.

        Args:
            event: Any event dataclass produced by :func:`parse_ndjson_line`.
                   Unknown types are silently ignored.
        """
        if isinstance(event, SystemInit):
            self._handle_init(event)
        elif isinstance(event, SessionStart):
            self._handle_session_start(event)
        elif isinstance(event, AssistantMessage):
            self._handle_assistant(event)
        elif isinstance(event, ToolResult):
            self._handle_tool_result(event)
        elif isinstance(event, ToolCallComplete):
            self._handle_tool_call_complete(event)
        elif isinstance(event, TextComplete):
            self._handle_text_complete(event)
        elif isinstance(event, CanonicalToolResult):
            self._handle_canonical_tool_result(event)
        elif isinstance(event, ResultMessage):
            self._handle_result(event)
        elif isinstance(event, UsageReport):
            self._handle_usage(event)
        elif isinstance(event, SessionEnd):
            self._handle_session_end(event)

    def _handle_init(self, event: SystemInit) -> None:
        self.session_id = event.session_id
        self.model = event.model
        self.tools = list(event.tools)
        self.is_running = True

    def _handle_assistant(self, event: AssistantMessage) -> None:
        self.turn_count += 1
        for block in event.content_blocks:
            if block.get("type") == "tool_use":
                tool_id = block.get("id", "")
                tool_name = block.get("name", "")
                if tool_id:
                    self.last_tool_use_map[tool_id] = tool_name

    def _handle_tool_result(self, event: ToolResult) -> None:
        # Resolve tool_name from the map if the event doesn't carry it
        if not event.tool_name and event.tool_use_id in self.last_tool_use_map:
            # ToolResult is a dataclass — direct attribute assignment works
            object.__setattr__(event, "tool_name", self.last_tool_use_map[event.tool_use_id])

    def _handle_session_start(self, event: SessionStart) -> None:
        self.session_id = event.session_id
        self.model = event.model
        self.tools = list(event.tools_available)
        self.is_running = True

    def _handle_tool_call_complete(self, event: ToolCallComplete) -> None:
        if event.tool_call_id:
            self.last_tool_use_map[event.tool_call_id] = event.tool_name

    def _handle_text_complete(self, event: TextComplete) -> None:
        if event.role == "assistant":
            self.turn_count += 1

    def _handle_canonical_tool_result(self, event: CanonicalToolResult) -> None:
        if not event.tool_name and event.tool_call_id in self.last_tool_use_map:
            object.__setattr__(
                event,
                "tool_name",
                self.last_tool_use_map[event.tool_call_id],
            )

    def _handle_usage(self, event: UsageReport) -> None:
        self.total_cost_usd = event.total_cost_usd or 0.0

    def _handle_result(self, event: ResultMessage) -> None:
        self.total_cost_usd = event.total_cost_usd
        self.is_running = False

    def _handle_session_end(self, event: SessionEnd) -> None:
        self.is_running = False
