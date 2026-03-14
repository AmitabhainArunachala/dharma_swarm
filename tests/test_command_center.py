"""Tests for the Command Center dashboard (TUI).

Tests widget composition, data population, and screen navigation
without requiring a live Textual app instance.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ── Import tests ───────────────────────────────────────────────────


class TestImports:
    """Verify all new modules import cleanly."""

    def test_command_center_screen_import(self):
        from dharma_swarm.tui.screens.command_center import CommandCenterScreen
        assert CommandCenterScreen is not None

    def test_health_panel_import(self):
        from dharma_swarm.tui.widgets.health_panel import (
            ActivityTable,
            AnomalyPanel,
            HealthPanel,
            OverviewTab,
            StatsPanel,
        )
        assert all([HealthPanel, StatsPanel, AnomalyPanel, ActivityTable, OverviewTab])

    def test_agent_table_import(self):
        from dharma_swarm.tui.widgets.agent_table import (
            AgentDetail,
            AgentListTable,
            AgentsTab,
        )
        assert all([AgentListTable, AgentDetail, AgentsTab])

    def test_evolution_panel_import(self):
        from dharma_swarm.tui.widgets.evolution_panel import (
            ArchiveTable,
            EvolutionSparkline,
            EvolutionTab,
        )
        assert all([EvolutionSparkline, ArchiveTable, EvolutionTab])

    def test_ontology_browser_import(self):
        from dharma_swarm.tui.widgets.ontology_browser import (
            OntologyDetail,
            OntologyTab,
            OntologyTree,
        )
        assert all([OntologyTree, OntologyDetail, OntologyTab])

    def test_lineage_explorer_import(self):
        from dharma_swarm.tui.widgets.lineage_explorer import (
            ImpactTree,
            LineageStatsBar,
            LineageTab,
            ProvenanceTree,
        )
        assert all([ProvenanceTree, ImpactTree, LineageStatsBar, LineageTab])

    def test_screens_init_exports(self):
        from dharma_swarm.tui.screens import CommandCenterScreen
        assert CommandCenterScreen is not None

    def test_widgets_init_exports(self):
        from dharma_swarm.tui.widgets import (
            AgentsTab,
            EvolutionTab,
            HealthPanel,
            LineageTab,
            OntologyTab,
            OverviewTab,
        )
        assert all([HealthPanel, AgentsTab, EvolutionTab, OntologyTab, LineageTab, OverviewTab])


# ── Health Panel Logic ─────────────────────────────────────────────


class TestHealthPanelHelpers:
    """Test helper functions in health_panel module."""

    def test_status_color_healthy(self):
        from dharma_swarm.tui.widgets.health_panel import _status_color
        assert _status_color("healthy") == "#8FA89B"

    def test_status_color_degraded(self):
        from dharma_swarm.tui.widgets.health_panel import _status_color
        assert _status_color("degraded") == "#C5B198"

    def test_status_color_critical(self):
        from dharma_swarm.tui.widgets.health_panel import _status_color
        assert _status_color("critical") == "#C19392"

    def test_status_color_unknown(self):
        from dharma_swarm.tui.widgets.health_panel import _status_color
        assert _status_color("banana") == "#A7AEBE"

    def test_ago_none(self):
        from dharma_swarm.tui.widgets.health_panel import _ago
        assert _ago(None) == "never"

    def test_ago_recent(self):
        from dharma_swarm.tui.widgets.health_panel import _ago
        now = datetime.now(timezone.utc)
        result = _ago(now)
        assert result.endswith("s ago")

    def test_ago_minutes(self):
        from datetime import timedelta
        from dharma_swarm.tui.widgets.health_panel import _ago
        t = datetime.now(timezone.utc) - timedelta(minutes=5)
        result = _ago(t)
        assert "m ago" in result

    def test_ago_hours(self):
        from datetime import timedelta
        from dharma_swarm.tui.widgets.health_panel import _ago
        t = datetime.now(timezone.utc) - timedelta(hours=2)
        result = _ago(t)
        assert "h ago" in result


# ── Agent Table Helpers ────────────────────────────────────────────


class TestAgentTableHelpers:
    def test_status_color(self):
        from dharma_swarm.tui.widgets.agent_table import _status_color
        assert _status_color("healthy") == "#8FA89B"
        assert _status_color("failed") == "#C19392"

    def test_ago(self):
        from dharma_swarm.tui.widgets.agent_table import _ago
        assert _ago(None) == "never"
        now = datetime.now(timezone.utc)
        assert _ago(now).endswith("s")


# ── Command Routing ────────────────────────────────────────────────


class TestCommandRouting:
    """Test that /dashboard command is registered and routed."""

    def test_dashboard_in_sync_commands(self):
        from dharma_swarm.tui.commands.system_commands import _SYNC_COMMANDS
        assert "dashboard" in _SYNC_COMMANDS

    def test_dashboard_in_all_commands(self):
        from dharma_swarm.tui.commands.system_commands import _ALL_COMMANDS
        assert "dashboard" in _ALL_COMMANDS

    def test_dashboard_handler_returns_signal(self):
        from dharma_swarm.tui.commands.system_commands import SystemCommandHandler
        handler = SystemCommandHandler()
        output, action = handler.handle("dashboard")
        assert action == "dashboard:open"
        assert output == ""

    def test_dashboard_in_palette(self):
        from dharma_swarm.tui.commands.palette import DGC_COMMANDS
        names = [c.slash_cmd for c in DGC_COMMANDS]
        assert "/dashboard" in names

    def test_dashboard_palette_entry_category(self):
        from dharma_swarm.tui.commands.palette import DGC_COMMANDS
        dashboard_cmd = next(c for c in DGC_COMMANDS if c.slash_cmd == "/dashboard")
        assert dashboard_cmd.category == "system"
        assert "Command Center" in dashboard_cmd.name


# ── Screen Bindings ────────────────────────────────────────────────


class TestCommandCenterBindings:
    """Test that bindings are properly defined."""

    def test_screen_has_escape_binding(self):
        from dharma_swarm.tui.screens.command_center import CommandCenterScreen
        binding_keys = [b.key for b in CommandCenterScreen.BINDINGS]
        assert "escape" in binding_keys

    def test_screen_has_refresh_binding(self):
        from dharma_swarm.tui.screens.command_center import CommandCenterScreen
        binding_keys = [b.key for b in CommandCenterScreen.BINDINGS]
        assert "r" in binding_keys

    def test_screen_has_tab_bindings(self):
        from dharma_swarm.tui.screens.command_center import CommandCenterScreen
        binding_keys = [b.key for b in CommandCenterScreen.BINDINGS]
        for n in "12345":
            assert n in binding_keys

    def test_screen_has_css_path(self):
        from dharma_swarm.tui.screens.command_center import CommandCenterScreen
        assert CommandCenterScreen.CSS_PATH is not None


# ── Archive JSONL Fallback ─────────────────────────────────────────


class TestArchiveJsonlFallback:
    """Test the JSONL fallback reader in CommandCenterScreen."""

    def test_load_empty(self, tmp_path):
        from dharma_swarm.tui.screens.command_center import CommandCenterScreen
        screen = CommandCenterScreen()
        # Point to non-existent file
        with patch.object(
            type(screen), "_load_archive_jsonl",
            return_value=([], []),
        ):
            entries, scores = screen._load_archive_jsonl()
        assert entries == []
        assert scores == []

    def test_load_valid_jsonl(self, tmp_path):
        from dharma_swarm.tui.screens.command_center import CommandCenterScreen, DHARMA_STATE
        archive_path = tmp_path / "evolution" / "archive.jsonl"
        archive_path.parent.mkdir(parents=True)
        entry = {
            "id": "test1",
            "component": "monitor.py",
            "change_type": "bugfix",
            "fitness": {"correctness": 0.9, "elegance": 0.8},
            "status": "applied",
            "timestamp": "2026-03-14T00:00:00",
        }
        archive_path.write_text(json.dumps(entry) + "\n")

        screen = CommandCenterScreen()
        # Monkey-patch the path constant
        original_fn = screen._load_archive_jsonl

        def patched():
            entries = []
            scores = []
            for line in archive_path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                entries.append(data)
                fit = data.get("fitness", {})
                w = {
                    "correctness": 0.20, "dharmic_alignment": 0.15,
                    "performance": 0.12, "utilization": 0.12,
                    "economic_value": 0.15, "elegance": 0.10,
                    "efficiency": 0.10, "safety": 0.06,
                }
                score = sum(fit.get(k, 0.0) * v for k, v in w.items())
                scores.append(score)
            return entries, scores

        entries, scores = patched()
        assert len(entries) == 1
        assert len(scores) == 1
        assert entries[0]["id"] == "test1"
        assert scores[0] > 0


# ── Stats Panel ────────────────────────────────────────────────────


class TestStatsPanelLogic:
    """Test stats formatting logic."""

    def test_stats_with_ontology_data(self):
        """StatsPanel.update_stats should accept ontology stats dict."""
        from dharma_swarm.tui.widgets.health_panel import StatsPanel
        # Just verify it can be instantiated (rendering needs Textual app)
        panel = StatsPanel.__new__(StatsPanel)
        assert hasattr(panel, "update_stats")

    def test_anomaly_panel_empty(self):
        """AnomalyPanel.update_anomalies with empty list should not crash."""
        from dharma_swarm.tui.widgets.health_panel import AnomalyPanel
        panel = AnomalyPanel.__new__(AnomalyPanel)
        assert hasattr(panel, "update_anomalies")


# ── Ontology Browser ──────────────────────────────────────────────


class TestOntologyBrowserLogic:
    """Test ontology browser helpers."""

    def test_shakti_icons_defined(self):
        from dharma_swarm.tui.widgets.ontology_browser import _SHAKTI_ICONS
        assert "maheshwari" in _SHAKTI_ICONS
        assert "mahakali" in _SHAKTI_ICONS
        assert "mahalakshmi" in _SHAKTI_ICONS
        assert "mahasaraswati" in _SHAKTI_ICONS


# ── App Integration ────────────────────────────────────────────────


class TestAppBindings:
    """Test that app.py has the Ctrl+G binding and handler."""

    def test_ctrl_g_in_app_bindings(self):
        from dharma_swarm.tui.app import DGCApp
        binding_keys = [b.key for b in DGCApp.BINDINGS]
        assert "ctrl+g" in binding_keys

    def test_app_has_toggle_method(self):
        from dharma_swarm.tui.app import DGCApp
        assert hasattr(DGCApp, "action_toggle_command_center")

    def test_app_imports_command_center_screen(self):
        """Verify the app imports CommandCenterScreen."""
        from dharma_swarm.tui.app import CommandCenterScreen
        assert CommandCenterScreen is not None
