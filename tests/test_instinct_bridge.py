"""Tests for the Instinct Bridge."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from dharma_swarm.instinct_bridge import (
    InstinctBridge,
    load_observations,
    extract_patterns,
    _path_to_module,
    _extract_from_session,
    emit_fitness_signals,
    write_synthetic_instinct,
    cmd_instincts_status,
)


class TestPathToModule:
    def test_dharma_swarm_path(self):
        result = _path_to_module("/Users/dhyana/dharma_swarm/dharma_swarm/models.py")
        assert result == "models"

    def test_non_python_file(self):
        assert _path_to_module("/some/file.txt") is None

    def test_simple_path(self):
        result = _path_to_module("/some/path/foo.py")
        assert result == "foo"


class TestLoadObservations:
    def test_load_from_file(self, tmp_path, monkeypatch):
        obs_file = tmp_path / "observations.jsonl"
        lines = [
            json.dumps({"tool": "Read", "status": "success", "session_id": "s1"}),
            json.dumps({"tool": "Edit", "status": "success", "session_id": "s1"}),
            json.dumps({"tool": "Bash", "status": "error", "session_id": "s1"}),
        ]
        obs_file.write_text("\n".join(lines) + "\n")

        monkeypatch.setattr("dharma_swarm.instinct_bridge.OBSERVATIONS_FILE", obs_file)
        observations, cursor = load_observations()
        assert len(observations) == 3
        assert cursor == 3

    def test_incremental_load(self, tmp_path, monkeypatch):
        obs_file = tmp_path / "observations.jsonl"
        lines = [
            json.dumps({"tool": "Read", "session_id": "s1"}),
            json.dumps({"tool": "Edit", "session_id": "s1"}),
        ]
        obs_file.write_text("\n".join(lines) + "\n")

        monkeypatch.setattr("dharma_swarm.instinct_bridge.OBSERVATIONS_FILE", obs_file)
        observations, cursor = load_observations(since_line=1)
        assert len(observations) == 1
        assert cursor == 2

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "dharma_swarm.instinct_bridge.OBSERVATIONS_FILE",
            tmp_path / "nope.jsonl",
        )
        obs, cursor = load_observations()
        assert obs == []
        assert cursor == 0


class TestExtractPatterns:
    def test_tool_failure_pattern(self):
        observations = [
            {
                "tool": "Edit",
                "status": "error",
                "file_path": "/Users/dhyana/dharma_swarm/dharma_swarm/models.py",
                "error": "file not found",
                "session_id": "s1",
            },
        ]
        patterns = extract_patterns(observations)
        assert len(patterns) >= 1
        failure = [p for p in patterns if p["type"] == "tool_failure"]
        assert len(failure) == 1
        assert failure[0]["signal"] == "negative"
        assert failure[0]["module"] == "models"

    def test_successful_edit_pattern(self):
        observations = [
            {
                "tool": "Edit",
                "status": "success",
                "file_path": "/Users/dhyana/dharma_swarm/dharma_swarm/foo.py",
                "session_id": "s1",
            },
            {
                "tool": "Bash",
                "status": "success",
                "command": "pytest tests/ -q",
                "session_id": "s1",
            },
        ]
        patterns = extract_patterns(observations)
        successful = [p for p in patterns if p["type"] == "successful_edit"]
        assert len(successful) == 1
        assert successful[0]["signal"] == "positive"

    def test_read_before_edit_pattern(self):
        observations = [
            {
                "tool": "Read",
                "status": "success",
                "file_path": "/Users/dhyana/dharma_swarm/dharma_swarm/config.py",
                "session_id": "s1",
            },
            {
                "tool": "Edit",
                "status": "success",
                "file_path": "/Users/dhyana/dharma_swarm/dharma_swarm/config.py",
                "session_id": "s1",
            },
        ]
        patterns = extract_patterns(observations)
        rbe = [p for p in patterns if p["type"] == "read_before_edit"]
        assert len(rbe) == 1
        assert rbe[0]["signal"] == "instinct"

    def test_no_patterns_on_empty(self):
        assert extract_patterns([]) == []


class TestEmitFitnessSignals:
    @pytest.mark.asyncio
    async def test_emits_signals(self):
        patterns = [
            {"type": "tool_failure", "module": "models", "signal": "negative",
             "confidence": 0.6, "detail": "error"},
            {"type": "successful_edit", "module": "config", "signal": "positive",
             "confidence": 0.8},
            {"type": "read_before_edit", "module": "foo", "signal": "instinct",
             "confidence": 0.5},
        ]
        mock_bus = AsyncMock()
        mock_bus.emit_event.return_value = "ev-1"

        count = await emit_fitness_signals(patterns, bus=mock_bus)
        # Only positive/negative signals emitted, not instinct
        assert count == 2
        assert mock_bus.emit_event.call_count == 2


class TestWriteSyntheticInstinct:
    def test_writes_high_confidence(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.instinct_bridge.INSTINCTS_DIR", tmp_path)
        result = write_synthetic_instinct(
            name="test_instinct",
            description="High fitness pattern",
            confidence=0.8,
        )
        assert result is not None
        assert result.exists()
        content = result.read_text()
        assert "test_instinct" in content
        assert "0.8" in content

    def test_skips_low_confidence(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.instinct_bridge.INSTINCTS_DIR", tmp_path)
        result = write_synthetic_instinct(
            name="weak_pattern",
            description="Low confidence",
            confidence=0.3,
        )
        assert result is None


class TestInstinctBridge:
    @pytest.mark.asyncio
    async def test_process_new_observations(self, tmp_path, monkeypatch):
        obs_file = tmp_path / "observations.jsonl"
        cursor_file = tmp_path / "cursor.json"
        bridge_dir = tmp_path / "bridge"

        monkeypatch.setattr("dharma_swarm.instinct_bridge.OBSERVATIONS_FILE", obs_file)
        monkeypatch.setattr("dharma_swarm.instinct_bridge.CURSOR_FILE", cursor_file)
        monkeypatch.setattr("dharma_swarm.instinct_bridge.BRIDGE_STATE_DIR", bridge_dir)

        obs_file.write_text(
            json.dumps({"tool": "Edit", "status": "error",
                        "file_path": "/dharma_swarm/dharma_swarm/models.py",
                        "error": "fail", "session_id": "s1"}) + "\n"
        )

        mock_bus = AsyncMock()
        mock_bus.emit_event.return_value = "ev-1"

        bridge = InstinctBridge(bus=mock_bus)
        result = await bridge.process_new_observations()
        assert result["observations_read"] == 1
        assert result["patterns_found"] >= 1

    def test_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.instinct_bridge.OBSERVATIONS_FILE",
                            tmp_path / "nope.jsonl")
        monkeypatch.setattr("dharma_swarm.instinct_bridge.CURSOR_FILE",
                            tmp_path / "cursor.json")
        monkeypatch.setattr("dharma_swarm.instinct_bridge.INSTINCTS_DIR",
                            tmp_path / "instincts")

        bridge = InstinctBridge()
        s = bridge.status()
        assert s["observations_file_exists"] is False
        assert s["cursor_position"] == 0

    def test_write_evolution_instincts(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.instinct_bridge.INSTINCTS_DIR", tmp_path)
        entries = [
            {"component": "models", "description": "great pattern",
             "fitness": {"correctness": 0.9, "elegance": 0.8}},
            {"component": "weak", "description": "meh",
             "fitness": {"correctness": 0.2}},
        ]
        bridge = InstinctBridge()
        count = bridge.write_evolution_instincts(entries, fitness_threshold=0.7)
        assert count == 1


class TestCLI:
    def test_cmd_instincts_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.instinct_bridge.OBSERVATIONS_FILE",
                            tmp_path / "nope.jsonl")
        monkeypatch.setattr("dharma_swarm.instinct_bridge.CURSOR_FILE",
                            tmp_path / "cursor.json")
        monkeypatch.setattr("dharma_swarm.instinct_bridge.INSTINCTS_DIR",
                            tmp_path / "instincts")
        rc = cmd_instincts_status()
        assert rc == 0
