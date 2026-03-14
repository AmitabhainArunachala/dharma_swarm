"""Agent table widget — sortable agent list with detail panel.

Shows all swarm agents in a DataTable. Selecting a row populates
the detail panel with role info, current task, and recent notes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widgets import DataTable, Static

INDIGO = "#94A3B8"
VERDIGRIS = "#8FA89B"
OCHRE = "#C5B198"
BENGARA = "#C19392"
ASH = "#A7AEBE"
PAPER = "#D8DCE6"

DHARMA_STATE = Path.home() / ".dharma"


def _status_color(status: str) -> str:
    s = status.lower()
    if s == "healthy":
        return VERDIGRIS
    if s == "degraded":
        return OCHRE
    if s in ("critical", "failed"):
        return BENGARA
    return ASH


def _ago(dt: datetime | None) -> str:
    if dt is None:
        return "never"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    return f"{secs // 86400}d"


class AgentListTable(DataTable):
    """DataTable showing all agents with status, provider, metrics."""

    def on_mount(self) -> None:
        self.add_columns("Name", "Status", "Provider", "Last Seen", "Tasks", "Success%")
        self.cursor_type = "row"

    def update_agents(self, agent_health_list: list[Any]) -> None:
        """Populate table from AgentHealth objects."""
        self.clear()
        for ah in agent_health_list:
            name = getattr(ah, "agent_name", "?")
            status = ah.status.value if hasattr(ah, "status") and ah.status else "unknown"
            provider = getattr(ah, "provider", "")
            last_seen = _ago(getattr(ah, "last_seen", None))
            total = getattr(ah, "total_actions", 0)
            success_rate = getattr(ah, "success_rate", 0.0)
            self.add_row(
                name,
                status.upper(),
                provider,
                last_seen,
                str(total),
                f"{success_rate:.0%}",
                key=name,
            )


class AgentDetail(Static):
    """Detail panel for the selected agent."""

    def show_agent(self, agent_name: str, agent_health: Any | None = None) -> None:
        """Display detail for a specific agent."""
        lines: list[str] = []
        lines.append(f"[bold {INDIGO}]{agent_name}[/bold {INDIGO}]")

        if agent_health:
            status = agent_health.status.value if agent_health.status else "unknown"
            sc = _status_color(status)
            total = getattr(agent_health, "total_actions", 0)
            fails = getattr(agent_health, "failures", 0)
            lines.append(f"  Status: [{sc}]{status.upper()}[/{sc}]")
            lines.append(f"  Actions: {total}  Failures: {fails}")
            lines.append(f"  Success: {agent_health.success_rate:.1%}")
            if agent_health.last_seen:
                lines.append(f"  Last seen: {_ago(agent_health.last_seen)} ago")

        # Try to load shared notes
        notes_path = DHARMA_STATE / "shared" / f"{agent_name}_notes.md"
        if notes_path.exists():
            try:
                text = notes_path.read_text(errors="replace")
                # Show last 500 chars
                if len(text) > 500:
                    text = "…" + text[-500:]
                lines.append("")
                lines.append(f"[{INDIGO}]Recent Notes:[/{INDIGO}]")
                # Escape Rich markup in notes content
                safe = text.replace("[", "\\[")
                lines.append(f"[{ASH}]{safe}[/{ASH}]")
            except Exception:
                pass

        self.update("\n".join(lines))

    def clear_detail(self) -> None:
        self.update(f"[{ASH}]Select an agent to view details[/{ASH}]")


class AgentsTab(Vertical):
    """Composite widget for the Agents tab."""

    def compose(self) -> ComposeResult:
        yield AgentListTable(id="agent-table-container")
        with VerticalScroll(id="agent-detail-container"):
            yield AgentDetail(id="agent-detail")

    def on_mount(self) -> None:
        detail = self.query_one("#agent-detail", AgentDetail)
        detail.clear_detail()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail panel when cursor moves."""
        if event.row_key is None:
            return
        agent_name = str(event.row_key.value)
        detail = self.query_one("#agent-detail", AgentDetail)
        # Find the matching AgentHealth from the stored list
        health_data = getattr(self, "_agent_health_map", {})
        detail.show_agent(agent_name, health_data.get(agent_name))
