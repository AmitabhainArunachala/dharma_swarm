"""Tests for upgraded identity sensors and LiveCoherenceSensor."""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path

import pytest

from dharma_swarm.identity import (
    IdentityMonitor,
    LiveCoherenceSensor,
    _bsi_proxy_score,
)


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    """Create a minimal .dharma state tree."""
    (tmp_path / "witness").mkdir()
    (tmp_path / "shared").mkdir()
    (tmp_path / "stigmergy").mkdir()
    (tmp_path / "evolution").mkdir()
    (tmp_path / "meta").mkdir()
    (tmp_path / "db").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# GPR — reads JSONL, parses outcome field
# ---------------------------------------------------------------------------


class TestGPRFixed:
    def test_reads_jsonl_not_json(self, state_dir: Path):
        """GPR should read *.jsonl files and parse 'outcome' field."""
        witness = state_dir / "witness" / "witness_test.jsonl"
        entries = []
        for i in range(10):
            outcome = "PASS" if i < 7 else "BLOCKED"
            entries.append(json.dumps({"outcome": outcome, "action": f"t{i}"}))
        witness.write_text("\n".join(entries))

        monitor = IdentityMonitor(state_dir)
        gpr = asyncio.run(monitor._measure_gpr())
        assert abs(gpr - 0.7) < 0.01

    def test_json_files_ignored(self, state_dir: Path):
        """Old *.json files should NOT be read (they don't exist in live)."""
        # Write a .json file — should be ignored
        (state_dir / "witness" / "old.json").write_text(
            json.dumps({"decision": "allow"})
        )
        monitor = IdentityMonitor(state_dir)
        gpr = asyncio.run(monitor._measure_gpr())
        assert gpr == 0.5  # default — no JSONL files found

    def test_empty_witness_returns_default(self, state_dir: Path):
        monitor = IdentityMonitor(state_dir)
        gpr = asyncio.run(monitor._measure_gpr())
        assert gpr == 0.5

    def test_handles_mixed_valid_corrupt(self, state_dir: Path):
        witness = state_dir / "witness" / "test.jsonl"
        lines = [
            json.dumps({"outcome": "PASS"}),
            "{corrupt",
            json.dumps({"outcome": "BLOCKED"}),
            json.dumps({"outcome": "PASS"}),
        ]
        witness.write_text("\n".join(lines))
        monitor = IdentityMonitor(state_dir)
        gpr = asyncio.run(monitor._measure_gpr())
        # 2 PASS out of 3 valid = 0.667
        assert abs(gpr - 0.667) < 0.01


# ---------------------------------------------------------------------------
# BSI — four proxy metrics
# ---------------------------------------------------------------------------


class TestBSIProxy:
    def test_operational_note_scores_low(self):
        """Pure operational output with no telos connection scores low."""
        text = (
            "Task complete. Fixed the import error in config.py. "
            "Tests pass. Build succeeded. Deployed to staging."
        )
        score = _bsi_proxy_score(text)
        assert score < 0.4

    def test_multi_altitude_note_scores_higher(self):
        """Text connecting ground-level work to telos scores higher."""
        text = (
            "Fixed the daemon PATH bug because without it the cron heartbeat "
            "can't fire, which means the stigmergy coherence signal never "
            "reaches the telos gate. This is samvara — sealing the channel "
            "so the witness can actually observe the evolution of the dharma "
            "kernel. The moksha vector requires this wiring to be intact."
        )
        score = _bsi_proxy_score(text)
        assert score > 0.3

    def test_cross_domain_connection_boosts(self):
        """Text bridging technical and contemplative domains scores well."""
        text = (
            "The daemon API test failure reveals that the ontology router "
            "isn't wired to the friston active inference loop. "
            "This is autopoiesis broken — the witness gate can't perform "
            "pratikraman without stigmergy feedback from the evolution engine."
        )
        score = _bsi_proxy_score(text)
        assert score > 0.25

    def test_empty_text_returns_zero(self):
        assert _bsi_proxy_score("") == 0.0

    def test_short_text_returns_zero(self):
        assert _bsi_proxy_score("too short") == 0.0

    def test_gap_quality_rewards_low_i_density(self):
        """Text with low first-person density and high TTR scores better on gap."""
        # High-quality: no "I", diverse vocabulary
        good = (
            "The system measures coherence through gate passage rate and "
            "stigmergy density. Evolution archives track momentum. "
            "Each subsystem communicates via ontology state changes. "
            "Witness logs record all telos gate decisions for the dharma kernel."
        )
        # Low-quality: lots of "I", repetitive
        poor = (
            "I think I need to fix this. I believe I should check the tests. "
            "I want to make sure I get this right. I feel like I might need "
            "to review the code. I think I could possibly maybe fix it."
        )
        good_score = _bsi_proxy_score(good)
        poor_score = _bsi_proxy_score(poor)
        assert good_score > poor_score


# ---------------------------------------------------------------------------
# RM — filters corrupt marks
# ---------------------------------------------------------------------------


class TestRMFiltered:
    def test_corrupt_marks_excluded(self, state_dir: Path):
        marks = state_dir / "stigmergy" / "marks.jsonl"
        lines = []
        for i in range(80):
            lines.append(json.dumps({"id": f"m{i}", "obs": f"o{i}"}))
        for i in range(20):
            lines.append(f"{{corrupt {i}")
        marks.write_text("\n".join(lines))

        monitor = IdentityMonitor(state_dir)
        rm = asyncio.run(monitor._measure_rm())

        # 80 valid out of 1000 norm = 0.08, vs old behavior: 100/1000 = 0.1
        # Only signal is stigmergy (no archive, shared has 0 .md files)
        assert rm < 0.1  # reflects actual valid count

    def test_all_valid_marks(self, state_dir: Path):
        marks = state_dir / "stigmergy" / "marks.jsonl"
        lines = [json.dumps({"id": f"m{i}"}) for i in range(500)]
        marks.write_text("\n".join(lines))

        monitor = IdentityMonitor(state_dir)
        rm = asyncio.run(monitor._measure_rm())
        # stigmergy: 500/1000=0.5, shared notes: 0/50=0.0 → avg = 0.25
        assert abs(rm - 0.25) < 0.01


# ---------------------------------------------------------------------------
# Full TCS integration
# ---------------------------------------------------------------------------


class TestTCSIntegration:
    def test_tcs_with_real_data(self, state_dir: Path):
        """TCS should reflect actual data, not defaults."""
        # Write witness logs
        witness = state_dir / "witness" / "test.jsonl"
        entries = [json.dumps({"outcome": "PASS"}) for _ in range(8)]
        entries += [json.dumps({"outcome": "BLOCKED"}) for _ in range(2)]
        witness.write_text("\n".join(entries))

        # Write a telos-connected note
        note = state_dir / "shared" / "note1.md"
        note.write_text(
            "Fixed daemon config. The telos gate was blocking because "
            "the ontology witness couldn't reach the stigmergy store. "
            "This is a dharma kernel coherence issue at the evolution layer."
        )

        # Write valid marks
        marks = state_dir / "stigmergy" / "marks.jsonl"
        lines = [json.dumps({"id": f"m{i}"}) for i in range(200)]
        marks.write_text("\n".join(lines))

        monitor = IdentityMonitor(state_dir)
        state = asyncio.run(monitor.measure())

        # GPR should be ~0.8 (8/10 PASS)
        assert state.gpr > 0.7
        # BSI should be non-default (note has telos keywords)
        # RM should reflect 200 valid marks
        assert state.tcs > 0.35  # should be in stable regime
        assert state.regime == "stable"


# ---------------------------------------------------------------------------
# LiveCoherenceSensor
# ---------------------------------------------------------------------------


class TestLiveCoherenceSensor:
    def test_no_daemon_no_data(self, state_dir: Path):
        sensor = LiveCoherenceSensor(state_dir)
        result = sensor.measure()
        assert result["score"] == 0.0
        assert not result["daemon_alive"]
        assert result["freshness_ratio"] == 0.0

    def test_fresh_subsystems(self, state_dir: Path):
        """Fresh data files should register as alive."""
        # Touch recent files
        (state_dir / "pulse.log").write_text("recent pulse")
        (state_dir / "stigmergy" / "marks.jsonl").write_text("{}")
        (state_dir / "evolution" / "archive.jsonl").write_text("{}")
        (state_dir / "db" / "memory.db").write_text("db")

        sensor = LiveCoherenceSensor(state_dir)
        result = sensor.measure()

        # No daemon, but 4/5 subsystems fresh
        assert result["freshness_ratio"] == 0.8
        assert result["score"] > 0.4

    def test_fresh_subsystems_accept_runner_pulse_log(self, state_dir: Path):
        """Runner pulse logs under logs/ should count as live pulse evidence."""
        pulse_log = state_dir / "logs" / "pulse.log"
        pulse_log.parent.mkdir(parents=True)
        pulse_log.write_text("OK: pulse -> /tmp/pulse_1.md", encoding="utf-8")

        sensor = LiveCoherenceSensor(state_dir)
        result = sensor.measure()

        assert result["subsystem_freshness"]["pulse"] is True

    def test_stale_files_not_fresh(self, state_dir: Path):
        pulse = state_dir / "pulse.log"
        pulse.write_text("old")
        old_time = time.time() - 48 * 3600
        os.utime(pulse, (old_time, old_time))

        sensor = LiveCoherenceSensor(state_dir)
        result = sensor.measure()
        assert not result["subsystem_freshness"].get("pulse", True)

    def test_runner_pulse_log_counts_as_fresh_pulse(self, state_dir: Path):
        runner_log = state_dir / "logs" / "pulse.log"
        runner_log.parent.mkdir(parents=True, exist_ok=True)
        runner_log.write_text(
            "OK: pulse -> /Users/dhyana/.dharma/cron/pulse_20260326_125100.md\n",
            encoding="utf-8",
        )

        sensor = LiveCoherenceSensor(state_dir)
        result = sensor.measure()
        assert result["subsystem_freshness"].get("pulse") is True

    def test_daemon_pid_check(self, state_dir: Path):
        """If PID file exists with current process PID, should report alive."""
        pid_file = state_dir / "daemon.pid"
        pid_file.write_text(str(os.getpid()))  # our own PID — definitely alive

        sensor = LiveCoherenceSensor(state_dir)
        result = sensor.measure()
        assert result["daemon_alive"]
        assert result["score"] >= 0.4

    def test_dead_pid(self, state_dir: Path):
        pid_file = state_dir / "daemon.pid"
        pid_file.write_text("999999999")  # unlikely to be alive

        sensor = LiveCoherenceSensor(state_dir)
        result = sensor.measure()
        assert not result["daemon_alive"]

    def test_semantic_pulse_failures_reduce_live_score(self, state_dir: Path):
        pid_file = state_dir / "daemon.pid"
        pid_file.write_text(str(os.getpid()))
        (state_dir / "pulse.log").write_text("ERROR: claude CLI not found in PATH")
        (state_dir / "stigmergy" / "marks.jsonl").write_text("{}")
        (state_dir / "evolution" / "archive.jsonl").write_text("{}")
        (state_dir / "db" / "memory.db").write_text("db")

        sensor = LiveCoherenceSensor(state_dir)
        result = sensor.measure()

        assert result["base_score"] > result["score"]
        assert result["semantic_penalty"] >= 0.35
        assert any(
            item["kind"] == "pulse_binary_missing"
            for item in result["semantic_failures"]
        )
