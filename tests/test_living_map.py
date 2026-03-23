"""Tests for living_map.py — real-time system map generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from dharma_swarm.living_map import (
    _age_str,
    _pid_alive,
    _read_daemon_status,
    _read_evolution,
    _read_mission,
    _read_now,
    _read_shared_notes,
    _read_stigmergy,
    _read_swarm_rv,
    _read_trishula,
    _status_icon,
    generate,
    generate_json,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


class TestStatusIcon:
    def test_alive(self):
        assert _status_icon(True) == "●"

    def test_dead(self):
        assert _status_icon(False) == "○"


class TestAgeStr:
    def test_empty(self):
        assert _age_str("") == "unknown age"

    def test_unknown(self):
        assert _age_str("unknown") == "unknown age"

    def test_recent_utc(self):
        now = datetime.now(timezone.utc)
        result = _age_str(now.isoformat())
        assert "h ago" in result or "0h ago" in result

    def test_old_date(self):
        result = _age_str("2024-01-01T00:00:00+00:00")
        assert "d ago" in result

    def test_invalid_format(self):
        assert _age_str("not-a-date") == "unknown age"


class TestPidAlive:
    def test_self_alive(self):
        import os
        assert _pid_alive(os.getpid()) is True

    def test_nonexistent_pid(self):
        # PID 99999999 should not exist
        assert _pid_alive(99999999) is False


# ---------------------------------------------------------------------------
# File-reading functions (monkeypatched)
# ---------------------------------------------------------------------------


class TestReadNow:
    def test_reads_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.STATE_DIR", tmp_path)
        (tmp_path / "NOW.json").write_text(
            json.dumps({"identity": {"version": "1.0"}}), encoding="utf-8"
        )
        data = _read_now()
        assert data["identity"]["version"] == "1.0"

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.STATE_DIR", tmp_path)
        assert _read_now() == {}


class TestReadMission:
    def test_reads_json(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        (tmp_path / "mission.json").write_text(
            json.dumps({"mission": "test"}), encoding="utf-8"
        )
        data = _read_mission()
        assert data["mission"] == "test"

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        assert _read_mission() == {}


class TestReadStigmergy:
    def test_reads_marks(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        marks = [
            json.dumps({"path": "/test/mark", "salience": 0.8, "timestamp": "2024-01-01"}),
            json.dumps({"path": "/test/mark2", "salience": 0.5, "timestamp": "2024-01-02"}),
        ]
        (stig_dir / "marks.jsonl").write_text("\n".join(marks), encoding="utf-8")
        data = _read_stigmergy()
        assert data["count"] == 2
        assert len(data["recent"]) == 2

    def test_missing_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        data = _read_stigmergy()
        assert data["count"] == 0
        assert data["recent"] == []


class TestReadSharedNotes:
    def test_with_files(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "note1.md").write_text("hello world", encoding="utf-8")
        (shared / "note2.md").write_text("more content", encoding="utf-8")
        data = _read_shared_notes()
        assert data["count"] == 2
        assert data["total_kb"] >= 0

    def test_no_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        data = _read_shared_notes()
        assert data["count"] == 0


class TestReadDaemonStatus:
    def test_with_pid_file(self, tmp_path, monkeypatch):
        import os
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        (tmp_path / "daemon.pid").write_text(str(os.getpid()), encoding="utf-8")
        data = _read_daemon_status()
        assert data["running"] is True
        assert data["pid"] == os.getpid()

    def test_no_pid_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        data = _read_daemon_status()
        assert data["running"] is False
        assert data["pid"] is None

    def test_stale_pid_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        (tmp_path / "daemon.pid").write_text("99999999", encoding="utf-8")
        data = _read_daemon_status()
        assert data["running"] is False


class TestReadTrishula:
    def test_with_messages(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        # Trishula reads from ~/trishula/inbox, need to monkeypatch Path.home
        inbox = tmp_path / "trishula" / "inbox"
        inbox.mkdir(parents=True)
        (inbox / "msg1.json").write_text("{}", encoding="utf-8")
        (inbox / "msg2.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        data = _read_trishula()
        assert data["message_count"] == 2

    def test_no_inbox(self, tmp_path, monkeypatch):
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        data = _read_trishula()
        assert data["message_count"] == 0


class TestReadEvolution:
    def test_counts_entries(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        evo_dir = tmp_path / "evolution"
        evo_dir.mkdir()
        (evo_dir / "e1.json").write_text('{"a": 1}', encoding="utf-8")
        (evo_dir / "e2.jsonl").write_text(
            '{"x": 1}\n{"y": 2}\n', encoding="utf-8"
        )
        data = _read_evolution()
        assert data["entries"] >= 1

    def test_no_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        data = _read_evolution()
        assert data["entries"] == 0


# ---------------------------------------------------------------------------
# Swarm R_V reader
# ---------------------------------------------------------------------------


class TestReadSwarmRv:
    def test_expanding(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        # Different topics each mark → low similarity → EXPANDING
        marks = [
            json.dumps({"path": "/alpha/one/two"}),
            json.dumps({"path": "/beta/three/four"}),
            json.dumps({"path": "/gamma/five/six"}),
            json.dumps({"path": "/delta/seven/eight"}),
        ]
        (stig_dir / "marks.jsonl").write_text("\n".join(marks), encoding="utf-8")
        data = _read_swarm_rv()
        assert data["level"] == "EXPANDING"

    def test_contracting(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        # Same topics repeated → high Jaccard → CONTRACTING
        marks = [json.dumps({"path": "/test/same/path"})] * 10
        (stig_dir / "marks.jsonl").write_text("\n".join(marks), encoding="utf-8")
        data = _read_swarm_rv()
        assert data["level"] == "CONTRACTING (L3 risk)"

    def test_no_marks(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        data = _read_swarm_rv()
        assert data["level"] == "UNKNOWN"

    def test_single_mark(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        (stig_dir / "marks.jsonl").write_text(
            json.dumps({"path": "/test"}), encoding="utf-8"
        )
        data = _read_swarm_rv()
        assert data["level"] == "UNKNOWN"


# ---------------------------------------------------------------------------
# Map generation
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_returns_string(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        monkeypatch.setattr("dharma_swarm.living_map.STATE_DIR", tmp_path)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = generate()
        assert isinstance(result, str)
        assert "DHARMA SWARM" in result
        assert "LIVING MAP" in result

    def test_contains_layers(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        monkeypatch.setattr("dharma_swarm.living_map.STATE_DIR", tmp_path)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        result = generate()
        assert "LAYER 0" in result
        assert "LAYER 1" in result
        assert "TRIPLE MAPPING" in result


class TestGenerateJson:
    def test_returns_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        monkeypatch.setattr("dharma_swarm.living_map.STATE_DIR", tmp_path)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        data = generate_json()
        assert isinstance(data, dict)
        assert "generated_at" in data
        assert "now" in data
        assert "stigmergy" in data
        assert "colony_rv" in data

    def test_json_serializable(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.living_map.DHARMA_DIR", tmp_path)
        monkeypatch.setattr("dharma_swarm.living_map.STATE_DIR", tmp_path)
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        data = generate_json()
        # Should not raise
        json.dumps(data)
