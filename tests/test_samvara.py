"""Tests for the Samvara Engine — four-power HOLD cascade."""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from dharma_swarm.samvara import (
    DiagnosticResult,
    Power,
    SamvaraEngine,
    SamvaraState,
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
# Power altitude escalation
# ---------------------------------------------------------------------------


class TestPowerAltitude:
    def test_hold_1_is_mahasaraswati(self):
        assert Power.from_hold_count(1) == Power.MAHASARASWATI

    def test_hold_3_is_mahasaraswati(self):
        assert Power.from_hold_count(3) == Power.MAHASARASWATI

    def test_hold_4_is_mahalakshmi(self):
        assert Power.from_hold_count(4) == Power.MAHALAKSHMI

    def test_hold_7_is_mahakali(self):
        assert Power.from_hold_count(7) == Power.MAHAKALI

    def test_hold_10_is_maheshwari(self):
        assert Power.from_hold_count(10) == Power.MAHESHWARI

    def test_hold_100_is_maheshwari(self):
        assert Power.from_hold_count(100) == Power.MAHESHWARI


# ---------------------------------------------------------------------------
# Engine lifecycle
# ---------------------------------------------------------------------------


class TestSamvaraEngine:
    def test_initial_state(self, state_dir: Path):
        engine = SamvaraEngine(state_dir)
        assert not engine.active
        assert engine.state.consecutive_holds == 0

    def test_single_hold_does_not_activate(self, state_dir: Path):
        engine = SamvaraEngine(state_dir)
        result = asyncio.run(engine.on_hold(coherence=0.35))
        assert not engine.active
        assert engine.state.consecutive_holds == 1
        assert result.power == Power.MAHASARASWATI

    def test_activation_after_threshold(self, state_dir: Path):
        engine = SamvaraEngine(state_dir)
        asyncio.run(engine.on_hold(coherence=0.35))
        asyncio.run(engine.on_hold(coherence=0.33))
        assert engine.active
        assert engine.state.entered_at is not None
        assert engine.state.consecutive_holds == 2

    def test_proceed_resets(self, state_dir: Path):
        engine = SamvaraEngine(state_dir)
        asyncio.run(engine.on_hold(coherence=0.35))
        asyncio.run(engine.on_hold(coherence=0.33))
        assert engine.active
        engine.on_proceed()
        assert not engine.active
        assert engine.state.consecutive_holds == 0
        assert engine.state.exited_at is not None

    def test_altitude_escalation_through_holds(self, state_dir: Path):
        engine = SamvaraEngine(state_dir)
        powers_seen = []
        for i in range(12):
            result = asyncio.run(engine.on_hold(coherence=0.3))
            powers_seen.append(result.power)

        assert powers_seen[0] == Power.MAHASARASWATI
        assert powers_seen[3] == Power.MAHALAKSHMI
        assert powers_seen[6] == Power.MAHAKALI
        assert powers_seen[9] == Power.MAHESHWARI
        assert powers_seen[11] == Power.MAHESHWARI

    def test_history_accumulates(self, state_dir: Path):
        engine = SamvaraEngine(state_dir)
        for _ in range(5):
            asyncio.run(engine.on_hold(coherence=0.3))
        assert len(engine.state.history) == 5


# ---------------------------------------------------------------------------
# Mahasaraswati diagnostics
# ---------------------------------------------------------------------------


class TestMahasaraswati:
    def test_detects_jsonl_witness_blindness(self, state_dir: Path):
        """GPR reads *.json but files are *.jsonl — should be flagged."""
        # Write a JSONL file (the real format)
        witness = state_dir / "witness" / "witness_test.jsonl"
        entries = [
            json.dumps({"outcome": "PASS", "action": "test"}),
            json.dumps({"outcome": "BLOCKED", "action": "test2"}),
        ]
        witness.write_text("\n".join(entries))

        engine = SamvaraEngine(state_dir)
        result = asyncio.run(engine.on_hold(coherence=0.35))

        findings_text = " ".join(result.findings)
        assert "JSONL" in findings_text or "jsonl" in findings_text.lower() or "blind" in findings_text

    def test_detects_corrupt_stigmergy(self, state_dir: Path):
        marks = state_dir / "stigmergy" / "marks.jsonl"
        lines = []
        for i in range(80):
            lines.append(json.dumps({"id": f"m{i}", "observation": f"obs {i}"}))
        for i in range(20):
            lines.append(f"{{corrupt line {i}")
        marks.write_text("\n".join(lines))

        engine = SamvaraEngine(state_dir)
        result = asyncio.run(engine.on_hold(coherence=0.35))

        findings_text = " ".join(result.findings)
        assert "corrupt" in findings_text.lower()


# ---------------------------------------------------------------------------
# Mahalakshmi diagnostics
# ---------------------------------------------------------------------------


class TestMahalakshmi:
    def test_detects_stale_subsystems(self, state_dir: Path):
        """Subsystems that haven't written recently should be flagged."""
        # Create a pulse log that's old
        pulse_log = state_dir / "pulse.log"
        pulse_log.write_text("old pulse")
        # Make it 48 hours old
        old_time = time.time() - 48 * 3600
        import os
        os.utime(pulse_log, (old_time, old_time))

        engine = SamvaraEngine(state_dir)
        # Need 4 holds to reach Mahalakshmi
        for _ in range(3):
            asyncio.run(engine.on_hold(coherence=0.35))
        result = asyncio.run(engine.on_hold(coherence=0.35))

        assert result.power == Power.MAHALAKSHMI
        findings_text = " ".join(result.findings)
        assert "stale" in findings_text.lower() or "missing" in findings_text.lower()


# ---------------------------------------------------------------------------
# Mahakali diagnostics
# ---------------------------------------------------------------------------


class TestMahakali:
    def test_detects_repetitive_stigmergy(self, state_dir: Path):
        """Repeated identical observations = system looping."""
        marks = state_dir / "stigmergy" / "marks.jsonl"
        lines = []
        for _ in range(40):
            lines.append(json.dumps({"observation": "same thing over and over"}))
        for i in range(10):
            lines.append(json.dumps({"observation": f"unique observation {i}"}))
        marks.write_text("\n".join(lines))

        engine = SamvaraEngine(state_dir)
        # Need 7 holds to reach Mahakali
        for _ in range(6):
            asyncio.run(engine.on_hold(coherence=0.3))
        result = asyncio.run(engine.on_hold(coherence=0.3))

        assert result.power == Power.MAHAKALI
        findings_text = " ".join(result.findings)
        assert "repetition" in findings_text.lower() or "looping" in findings_text.lower()


# ---------------------------------------------------------------------------
# Maheshwari diagnostics
# ---------------------------------------------------------------------------


class TestMaheshwari:
    def test_aggregates_prior_findings(self, state_dir: Path):
        # Set up witness logs so Mahasaraswati finds something
        witness = state_dir / "witness" / "witness_test.jsonl"
        witness.write_text(json.dumps({"outcome": "PASS", "action": "x"}))

        engine = SamvaraEngine(state_dir)
        # Run 10 holds to reach Maheshwari
        for _ in range(9):
            asyncio.run(engine.on_hold(coherence=0.3))
        result = asyncio.run(engine.on_hold(coherence=0.3))

        assert result.power == Power.MAHESHWARI
        assert "accumulated" in " ".join(result.findings).lower()
        assert any("LEVERAGED" in c for c in result.corrections)


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


class TestSamvaraPersistence:
    def test_state_persists_and_loads(self, state_dir: Path):
        engine = SamvaraEngine(state_dir)
        asyncio.run(engine.on_hold(coherence=0.35))
        asyncio.run(engine.on_hold(coherence=0.33))
        assert engine.active

        # Load into new engine
        engine2 = SamvaraEngine(state_dir)
        loaded = engine2.load_state()
        assert loaded.active
        assert loaded.consecutive_holds == 2

    def test_diagnostic_result_serializes(self):
        result = DiagnosticResult(
            power=Power.MAHASARASWATI,
            hold_count=1,
            findings=["test finding"],
            corrections=["test correction"],
            coherence_before=0.35,
            coherence_after=0.35,
        )
        d = result.to_dict()
        assert d["power"] == "mahasaraswati"
        assert d["delta"] == 0.0
