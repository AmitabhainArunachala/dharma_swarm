"""Evolution panel widget — fitness sparkline + archive DataTable.

Shows the evolution archive entries and fitness trend over time.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Sparkline, Static

INDIGO = "#94A3B8"
ASH = "#A7AEBE"


class EvolutionSparkline(Vertical):
    """Fitness trend sparkline with label."""

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold {INDIGO}]FITNESS TREND[/bold {INDIGO}]",
            classes="section-header",
        )
        yield Sparkline([], id="evo-sparkline")

    def update_fitness(self, scores: list[float]) -> None:
        """Update sparkline with fitness scores."""
        spark = self.query_one("#evo-sparkline", Sparkline)
        spark.data = scores if scores else [0.0]


class ArchiveTable(DataTable):
    """DataTable showing evolution archive entries."""

    def on_mount(self) -> None:
        self.add_columns(
            "ID", "Component", "Type", "Fitness", "Status", "Tier", "Timestamp"
        )
        self.cursor_type = "row"

    def update_entries(self, entries: list[Any]) -> None:
        """Populate from ArchiveEntry objects (newest first)."""
        self.clear()
        for entry in entries:
            eid = getattr(entry, "id", "?")[:8]
            component = getattr(entry, "component", "")
            change_type = getattr(entry, "change_type", "")
            fitness = getattr(entry, "fitness", None)
            fit_val = f"{fitness.weighted():.3f}" if fitness else "—"
            status = getattr(entry, "status", "")
            tier = getattr(entry, "evidence_tier", "")
            ts = getattr(entry, "timestamp", "")
            if isinstance(ts, str) and len(ts) > 19:
                ts = ts[:19]
            self.add_row(eid, component, change_type, fit_val, status, tier, ts)


class EvolutionTab(Vertical):
    """Composite widget for the Evolution tab."""

    def compose(self) -> ComposeResult:
        yield EvolutionSparkline(id="evo-sparkline-container")
        yield ArchiveTable(id="evo-table-container")
