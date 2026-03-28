"""Tests for dharma_swarm.skill_bridge — file-based skill→swarm routing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm.skill_bridge import SkillBridge


@pytest.fixture()
def bridge(tmp_path: Path) -> SkillBridge:
    inbox = tmp_path / "inbox.jsonl"
    return SkillBridge(inbox_path=inbox)


# ---------------------------------------------------------------------------
# Inbox drain
# ---------------------------------------------------------------------------

class TestDrainInbox:
    def test_empty_inbox(self, bridge: SkillBridge):
        assert bridge.drain_inbox() == []

    def test_reads_entries(self, bridge: SkillBridge):
        entry = {"skill_name": "retro", "timestamp": "2026-01-01T00:00:00Z", "payload": {"findings": []}}
        bridge._inbox.parent.mkdir(parents=True, exist_ok=True)
        bridge._inbox.write_text(json.dumps(entry) + "\n")
        entries = bridge.drain_inbox()
        assert len(entries) == 1
        assert entries[0]["skill_name"] == "retro"

    def test_truncates_after_drain(self, bridge: SkillBridge):
        bridge._inbox.parent.mkdir(parents=True, exist_ok=True)
        bridge._inbox.write_text('{"skill_name":"x","payload":{}}\n')
        bridge.drain_inbox()
        assert bridge._inbox.read_text() == ""

    def test_skips_malformed_lines(self, bridge: SkillBridge):
        bridge._inbox.parent.mkdir(parents=True, exist_ok=True)
        bridge._inbox.write_text('{"skill_name":"good","payload":{}}\nNOT JSON\n')
        entries = bridge.drain_inbox()
        assert len(entries) == 1


# ---------------------------------------------------------------------------
# Process entries — routing
# ---------------------------------------------------------------------------

class TestProcessEntries:
    def test_counts_by_skill(self, bridge: SkillBridge):
        entries = [
            {"skill_name": "retro", "payload": {"findings": []}},
            {"skill_name": "retro", "payload": {"findings": []}},
            {"skill_name": "hypothesis", "payload": {"hypotheses": []}},
        ]
        counts = bridge.process_entries(entries)
        assert counts["retro"] == 2
        assert counts["hypothesis"] == 1

    def test_unknown_skill_counted(self, bridge: SkillBridge):
        entries = [{"skill_name": "unknown_skill", "payload": {}}]
        counts = bridge.process_entries(entries)
        assert counts["unknown_skill"] == 1

    def test_empty_entries(self, bridge: SkillBridge):
        assert bridge.process_entries([]) == {}

    def test_retro_creates_proposals(self, bridge: SkillBridge, tmp_path: Path):
        proposals_file = tmp_path / "evolution" / "pending_proposals.jsonl"
        with patch("dharma_swarm.skill_bridge.PROPOSALS_FILE", proposals_file):
            entries = [{"skill_name": "retro", "payload": {
                "findings": [{"component": "swarm.py", "description": "refactor tick()"}]
            }}]
            bridge.process_entries(entries)
        assert proposals_file.exists()
        line = json.loads(proposals_file.read_text().strip())
        assert line["change_type"] == "retro_finding"
        assert "refactor tick()" in line["description"]

    def test_hypothesis_creates_proposals(self, bridge: SkillBridge, tmp_path: Path):
        proposals_file = tmp_path / "evolution" / "pending_proposals.jsonl"
        with patch("dharma_swarm.skill_bridge.PROPOSALS_FILE", proposals_file):
            entries = [{"skill_name": "hypothesis", "payload": {
                "hypotheses": [{"target_module": "evolution.py", "statement": "increase mutation rate"}]
            }}]
            bridge.process_entries(entries)
        assert proposals_file.exists()
        line = json.loads(proposals_file.read_text().strip())
        assert line["change_type"] == "hypothesis_test"

    def test_diversity_grid_writes_file(self, bridge: SkillBridge, tmp_path: Path):
        grid_path = tmp_path / "evolution" / "diversity_grid.json"
        with patch("dharma_swarm.skill_bridge.STATE_DIR", tmp_path):
            entries = [{"skill_name": "diversity-archive", "payload": {"grid": [[1, 2], [3, 4]]}}]
            bridge.process_entries(entries)
        assert grid_path.exists()
        data = json.loads(grid_path.read_text())
        assert data["grid"] == [[1, 2], [3, 4]]

    def test_process_survives_handler_error(self, bridge: SkillBridge):
        """If one handler fails, others still process."""
        with patch.object(bridge, "_ingest_retro", side_effect=RuntimeError("boom")):
            entries = [
                {"skill_name": "retro", "payload": {}},
                {"skill_name": "knowledge-distiller", "payload": {"entries_compressed": 5}},
            ]
            counts = bridge.process_entries(entries)
        assert counts["retro"] == 1
        assert counts["knowledge-distiller"] == 1
