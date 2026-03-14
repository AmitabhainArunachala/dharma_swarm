"""Health panel widget — overview health, stats, anomalies, activity.

Shows system health status, per-agent health, ontology/lineage stats,
fitness sparkline, anomaly list, and recent trace activity.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Sparkline, Static

# Hokusai palette
VERDIGRIS = "#8FA89B"
OCHRE = "#C5B198"
BENGARA = "#C19392"
INDIGO = "#94A3B8"
PAPER = "#D8DCE6"
ASH = "#A7AEBE"


def _status_color(status: str) -> str:
    """Map health status string to Hokusai palette color."""
    s = status.lower()
    if s == "healthy":
        return VERDIGRIS
    if s == "degraded":
        return OCHRE
    if s == "critical":
        return BENGARA
    return ASH


def _ago(dt: datetime | None) -> str:
    """Human-readable time-ago string."""
    if dt is None:
        return "never"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


class HealthPanel(Static):
    """Renders system health status and per-agent health."""

    def update_health(self, health_report: Any) -> None:
        """Refresh display with a HealthReport object."""
        lines: list[str] = []
        status = getattr(health_report, "overall_status", None)
        status_val = status.value if status else "unknown"
        color = _status_color(status_val)
        lines.append(f"[bold {INDIGO}]HEALTH[/bold {INDIGO}]")
        lines.append(f"  Overall: [bold {color}]{status_val.upper()}[/bold {color}]")
        lines.append("")

        agent_health = getattr(health_report, "agent_health", [])
        if agent_health:
            lines.append(f"  [{INDIGO}]Agents:[/{INDIGO}]")
            for ah in agent_health:
                ac = _status_color(ah.status.value if ah.status else "unknown")
                ago = _ago(ah.last_seen)
                lines.append(
                    f"    [{ac}]●[/{ac}] {ah.agent_name:<16} "
                    f"[{ac}]{ah.status.value.upper():<10}[/{ac}] {ago}"
                )
        else:
            lines.append(f"  [{ASH}]No agent data[/{ASH}]")

        traces = getattr(health_report, "traces_last_hour", 0)
        fail_rate = getattr(health_report, "failure_rate", 0.0)
        lines.append("")
        lines.append(f"  Traces (1h): {traces}  Fail rate: {fail_rate:.1%}")

        self.update("\n".join(lines))


class StatsPanel(Static):
    """Renders ontology and lineage statistics."""

    def update_stats(
        self,
        ontology_stats: dict[str, Any] | None = None,
        lineage_stats: dict[str, int] | None = None,
        archive_count: int = 0,
        mean_fitness: float | None = None,
    ) -> None:
        """Refresh with stats dictionaries."""
        lines: list[str] = []
        lines.append(f"[bold {INDIGO}]SYSTEM STATS[/bold {INDIGO}]")

        if ontology_stats:
            types = ontology_stats.get("registered_types", 0)
            objects = ontology_stats.get("total_objects", 0)
            links = ontology_stats.get("total_links", 0)
            actions = ontology_stats.get("registered_actions", 0)
            lines.append(
                f"  Types: {types}    Objects: {objects}    "
                f"Links: {links}    Actions: {actions}"
            )
        else:
            lines.append(f"  [{ASH}]Ontology: not loaded[/{ASH}]")

        if lineage_stats:
            edges = lineage_stats.get("total_edges", 0)
            artifacts = lineage_stats.get("unique_artifacts", 0)
            pipelines = lineage_stats.get("unique_pipelines", 0)
            lines.append(
                f"  Edges: {edges}    Artifacts: {artifacts}    Pipelines: {pipelines}"
            )
        else:
            lines.append(f"  [{ASH}]Lineage: not loaded[/{ASH}]")

        fit_str = f"{mean_fitness:.3f}" if mean_fitness is not None else "—"
        lines.append(f"  Archive: {archive_count}    Mean fitness: {fit_str}")

        self.update("\n".join(lines))


class AnomalyPanel(Static):
    """Renders detected anomalies."""

    def update_anomalies(self, anomalies: list[Any]) -> None:
        """Refresh with anomaly list."""
        if not anomalies:
            self.update("")
            return
        lines = [f"[bold {BENGARA}]ANOMALIES ({len(anomalies)})[/bold {BENGARA}]"]
        for a in anomalies[:5]:
            sev = getattr(a, "severity", "?")
            desc = getattr(a, "description", str(a))
            atype = getattr(a, "anomaly_type", "")
            sc = BENGARA if sev == "high" else OCHRE if sev == "medium" else ASH
            lines.append(f"  [{sc}]▲ {atype}: {desc}[/{sc}]")
        self.update("\n".join(lines))


class ActivityTable(DataTable):
    """Recent trace activity as a DataTable."""

    def on_mount(self) -> None:
        self.add_columns("Time", "Agent", "Action", "State", "Files")
        self.cursor_type = "row"

    def update_traces(self, traces: list[Any]) -> None:
        """Refresh with trace entries."""
        self.clear()
        for t in traces[:30]:
            ts = ""
            if hasattr(t, "timestamp"):
                raw = t.timestamp
                if isinstance(raw, datetime):
                    ts = raw.strftime("%H:%M:%S")
                else:
                    ts = str(raw)[-8:]
            agent = getattr(t, "agent", "")
            action = getattr(t, "action", "")
            state = getattr(t, "state", "")
            files = ", ".join(getattr(t, "files_changed", [])[:2])
            self.add_row(ts, agent, action, state, files)


class OverviewTab(Vertical):
    """Composite widget for the Overview tab."""

    def compose(self) -> ComposeResult:
        with Horizontal(id="overview-top"):
            yield HealthPanel(id="overview-health")
            yield StatsPanel(id="overview-stats")
        yield AnomalyPanel(id="overview-anomalies")
        yield Sparkline([], id="overview-sparkline")
        yield ActivityTable(id="overview-activity")
