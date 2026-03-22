"""Command Center screen — Palantir-grade dashboard for dharma_swarm.

5-tab TabbedContent showing:
  1. Overview — health, stats, anomalies, fitness sparkline, recent activity
  2. Agents  — agent list + detail panel
  3. Evolution — fitness trend sparkline + archive DataTable
  4. Ontology  — type/object tree + detail panel
  5. Lineage   — search input + provenance/impact dual trees

Navigation:
  Ctrl+G or Escape returns to chat.
  1-5 switches tabs.
  r forces refresh.
  Auto-refresh every 10 seconds.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Static, TabbedContent, TabPane

from ..widgets.agent_table import AgentListTable, AgentsTab
from ..widgets.evolution_panel import ArchiveTable, EvolutionSparkline, EvolutionTab
from ..widgets.health_panel import (
    ActivityTable,
    AnomalyPanel,
    HealthPanel,
    OverviewTab,
    StatsPanel,
)
from ..widgets.lineage_explorer import LineageStatsBar, LineageTab
from ..widgets.ontology_browser import OntologyDetail, OntologyTab, OntologyTree

logger = logging.getLogger(__name__)

HOME = Path.home()
DHARMA_STATE = HOME / ".dharma"
VERDIGRIS = "#8FA89B"
INDIGO = "#94A3B8"
ASH = "#A7AEBE"


class CommandCenterScreen(Screen):
    """Full-viewport dashboard showing system state across 5 tabs."""

    CSS_PATH = "../theme/command_center.tcss"

    BINDINGS = [
        Binding("escape", "dismiss_screen", "Back", show=True),
        Binding("ctrl+g", "dismiss_screen", "Back", show=False),
        Binding("r", "refresh_all", "Refresh", show=True),
        Binding("1", "tab_1", "Overview", show=False),
        Binding("2", "tab_2", "Agents", show=False),
        Binding("3", "tab_3", "Evolution", show=False),
        Binding("4", "tab_4", "Ontology", show=False),
        Binding("5", "tab_5", "Lineage", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._monitor: Any = None
        self._registry: Any = None
        self._lineage_graph: Any = None
        self._archive: Any = None
        self._trace_store: Any = None
        self._refresh_timer: Any = None
        self._agent_health_map: dict[str, Any] = {}

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold {VERDIGRIS}]◆ COMMAND CENTER[/bold {VERDIGRIS}]"
            f"  [{ASH}]Ctrl+G: back  r: refresh  1-5: tabs[/{ASH}]",
            id="cc-header",
        )
        with TabbedContent(
            "Overview", "Agents", "Evolution", "Ontology", "Lineage",
            id="cc-tabs",
        ):
            with TabPane("Overview", id="tab-overview"):
                yield OverviewTab()
            with TabPane("Agents", id="tab-agents"):
                yield AgentsTab()
            with TabPane("Evolution", id="tab-evolution"):
                yield EvolutionTab()
            with TabPane("Ontology", id="tab-ontology"):
                yield OntologyTab()
            with TabPane("Lineage", id="tab-lineage"):
                yield LineageTab()
        yield Static(
            f"[{ASH}]Auto-refresh: 10s[/{ASH}]",
            id="cc-footer",
        )

    async def on_mount(self) -> None:
        """Initialize backend objects and start auto-refresh."""
        self._init_backends()
        await self._refresh_all_data()
        self._refresh_timer = self.set_interval(10.0, self._refresh_all_data)

    def on_unmount(self) -> None:
        """Stop auto-refresh timer."""
        if self._refresh_timer:
            self._refresh_timer.stop()

    # ── Backend initialization ──────────────────────────────────────

    def _init_backends(self) -> None:
        """Lazy-initialize backend data sources."""
        try:
            from dharma_swarm.traces import TraceStore
            self._trace_store = TraceStore()
        except Exception:
            logger.debug("TraceStore init failed", exc_info=True)

        try:
            from dharma_swarm.monitor import SystemMonitor
            if self._trace_store:
                self._monitor = SystemMonitor(self._trace_store)
        except Exception:
            logger.debug("SystemMonitor init failed", exc_info=True)

        try:
            from dharma_swarm.ontology_runtime import get_shared_registry
            self._registry = get_shared_registry()
        except Exception:
            logger.debug("OntologyRegistry init failed", exc_info=True)

        try:
            from dharma_swarm.lineage import LineageGraph
            self._lineage_graph = LineageGraph()
        except Exception:
            logger.debug("LineageGraph init failed", exc_info=True)

        try:
            from dharma_swarm.archive import EvolutionArchive
            self._archive = EvolutionArchive()
        except Exception:
            logger.debug("EvolutionArchive init failed", exc_info=True)

    # ── Refresh orchestration ───────────────────────────────────────

    async def _refresh_all_data(self) -> None:
        """Refresh all tabs from backend data."""
        await self._async_refresh_all()

    async def _async_refresh_all(self) -> None:
        """Async refresh all data sources."""
        # Init trace store if needed
        if self._trace_store:
            try:
                await self._trace_store.init()
            except Exception:
                pass

        # Load archive if needed
        if self._archive:
            try:
                await self._archive.load()
            except Exception:
                logger.debug("Archive load failed", exc_info=True)

        # Gather data
        health_report = None
        anomalies: list[Any] = []
        traces: list[Any] = []
        ontology_stats: dict[str, Any] | None = None
        lineage_stats: dict[str, int] | None = None
        archive_entries: list[Any] = []
        fitness_scores: list[float] = []

        if self._monitor:
            try:
                health_report = await self._monitor.check_health()
                anomalies = await self._monitor.detect_anomalies()
            except Exception:
                logger.debug("Health check failed", exc_info=True)

        if self._trace_store:
            try:
                traces = await self._trace_store.get_recent(30)
            except Exception:
                logger.debug("Trace fetch failed", exc_info=True)

        if self._registry:
            try:
                ontology_stats = self._registry.stats()
            except Exception:
                pass

        if self._lineage_graph:
            try:
                lineage_stats = self._lineage_graph.stats()
            except Exception:
                pass

        if self._archive:
            try:
                archive_entries = await self._archive.list_entries()
                fitness_scores = [
                    e.fitness.weighted()
                    for e in archive_entries
                    if e.fitness
                ]
            except Exception:
                logger.debug("Archive list failed", exc_info=True)

        # Also load archive from JSONL directly as fallback
        if not archive_entries:
            archive_entries, fitness_scores = self._load_archive_jsonl()

        # Update UI directly (running on main event loop)
        self._apply_refresh(
            health_report,
            anomalies,
            traces,
            ontology_stats,
            lineage_stats,
            archive_entries,
            fitness_scores,
        )

    def _load_archive_jsonl(self) -> tuple[list[Any], list[float]]:
        """Fallback: read archive.jsonl directly."""
        archive_path = DHARMA_STATE / "evolution" / "archive.jsonl"
        entries: list[dict[str, Any]] = []
        scores: list[float] = []
        if not archive_path.exists():
            return entries, scores
        try:
            for line in archive_path.read_text(errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entries.append(data)
                    fit = data.get("fitness", {})
                    if isinstance(fit, dict):
                        # Calculate weighted fitness manually
                        w = {
                            "correctness": 0.20, "dharmic_alignment": 0.15,
                            "performance": 0.12, "utilization": 0.12,
                            "economic_value": 0.15, "elegance": 0.10,
                            "efficiency": 0.10, "safety": 0.06,
                        }
                        score = sum(fit.get(k, 0.0) * v for k, v in w.items())
                        scores.append(score)
                except (json.JSONDecodeError, ValueError):
                    continue
        except Exception:
            pass
        return entries, scores

    def _apply_refresh(
        self,
        health_report: Any,
        anomalies: list[Any],
        traces: list[Any],
        ontology_stats: dict[str, Any] | None,
        lineage_stats: dict[str, int] | None,
        archive_entries: list[Any],
        fitness_scores: list[float],
    ) -> None:
        """Apply fetched data to all widgets (runs on main thread)."""
        # Overview tab
        try:
            health_panel = self.query_one("#overview-health", HealthPanel)
            if health_report:
                health_panel.update_health(health_report)
            else:
                health_panel.update(f"[{ASH}]Health: backend not available[/{ASH}]")
        except Exception:
            pass

        try:
            stats_panel = self.query_one("#overview-stats", StatsPanel)
            archive_count = len(archive_entries)
            mean_fitness = (
                sum(fitness_scores) / len(fitness_scores) if fitness_scores else None
            )
            stats_panel.update_stats(ontology_stats, lineage_stats, archive_count, mean_fitness)
        except Exception:
            pass

        try:
            anomaly_panel = self.query_one("#overview-anomalies", AnomalyPanel)
            anomaly_panel.update_anomalies(anomalies)
        except Exception:
            pass

        try:
            sparkline = self.query_one("#overview-sparkline")
            if hasattr(sparkline, "data"):
                sparkline.data = fitness_scores[-50:] if fitness_scores else [0.0]
        except Exception:
            pass

        try:
            activity = self.query_one("#overview-activity", ActivityTable)
            activity.update_traces(traces)
        except Exception:
            pass

        # Agents tab
        try:
            agent_table = self.query_one(AgentListTable)
            if health_report and hasattr(health_report, "agent_health"):
                agent_table.update_agents(health_report.agent_health)
                # Store health map for detail panel
                agents_tab = self.query_one(AgentsTab)
                agents_tab._agent_health_map = {
                    ah.agent_name: ah for ah in health_report.agent_health
                }
        except Exception:
            pass

        # Evolution tab
        try:
            evo_spark = self.query_one(EvolutionSparkline)
            evo_spark.update_fitness(fitness_scores)
        except Exception:
            pass

        try:
            archive_table = self.query_one(ArchiveTable)
            # Show newest first
            if archive_entries:
                reversed_entries = list(reversed(archive_entries))
                archive_table.update_entries(reversed_entries[:100])
        except Exception:
            pass

        # Ontology tab
        try:
            if self._registry:
                onto_tree = self.query_one(OntologyTree)
                onto_tree.populate(self._registry)
        except Exception:
            pass

        # Lineage tab — stats only (trees populated on search)
        try:
            lineage_bar = self.query_one(LineageStatsBar)
            lineage_bar.update_stats(lineage_stats)
        except Exception:
            pass

        # Update footer timestamp
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).strftime("%H:%M:%S")
            footer = self.query_one("#cc-footer", Static)
            footer.update(f"[{ASH}]Last refresh: {now} UTC  |  Auto-refresh: 10s[/{ASH}]")
        except Exception:
            pass

    # ── Actions ─────────────────────────────────────────────────────

    def action_dismiss_screen(self) -> None:
        """Return to chat."""
        self.dismiss()

    async def action_refresh_all(self) -> None:
        """Manual refresh triggered by 'r' key."""
        await self._refresh_all_data()

    def action_tab_1(self) -> None:
        self._switch_tab("tab-overview")

    def action_tab_2(self) -> None:
        self._switch_tab("tab-agents")

    def action_tab_3(self) -> None:
        self._switch_tab("tab-evolution")

    def action_tab_4(self) -> None:
        self._switch_tab("tab-ontology")

    def action_tab_5(self) -> None:
        self._switch_tab("tab-lineage")

    def _switch_tab(self, tab_id: str) -> None:
        """Switch to a specific tab by ID."""
        try:
            tabs = self.query_one(TabbedContent)
            tabs.active = tab_id
        except Exception:
            pass
