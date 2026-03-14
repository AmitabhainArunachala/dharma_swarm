"""Tests for dharma_swarm.auditor — S3* Sporadic Auditor."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.auditor import AuditFinding, Auditor
from dharma_swarm.models import _utc_now


# ------------------------------------------------------------------
# AuditFinding model
# ------------------------------------------------------------------


class TestAuditFinding:
    def test_fields_present(self) -> None:
        """AuditFinding has all expected fields with defaults."""
        f = AuditFinding(audit_type="score_drift", description="test")
        assert f.id  # non-empty
        assert f.audit_type == "score_drift"
        assert f.severity == "low"
        assert f.description == "test"
        assert f.expected == ""
        assert f.actual == ""
        assert f.drift_magnitude == 0.0
        assert isinstance(f.timestamp, datetime)

    def test_custom_severity(self) -> None:
        f = AuditFinding(
            audit_type="notes_mimicry",
            severity="high",
            description="bad",
        )
        assert f.severity == "high"


# ------------------------------------------------------------------
# Auditor constants
# ------------------------------------------------------------------


class TestAuditorTypes:
    def test_audit_types_count(self) -> None:
        """AUDIT_TYPES has exactly 4 entries."""
        assert len(Auditor.AUDIT_TYPES) == 4

    def test_audit_types_contents(self) -> None:
        expected = {"score_drift", "evolution_elegance", "notes_mimicry", "stigmergy_stale"}
        assert set(Auditor.AUDIT_TYPES) == expected


# ------------------------------------------------------------------
# Tick behaviour
# ------------------------------------------------------------------


class TestAuditorTick:
    async def test_tick_returns_finding_or_none(self, tmp_path: Path) -> None:
        """tick() returns AuditFinding or None (never raises)."""
        auditor = Auditor(state_dir=tmp_path)
        result = await auditor.tick()
        assert result is None or isinstance(result, AuditFinding)

    async def test_run_specific_invalid_type(self, tmp_path: Path) -> None:
        """run_specific raises ValueError for unknown audit type."""
        auditor = Auditor(state_dir=tmp_path)
        with pytest.raises(ValueError, match="Unknown audit type"):
            await auditor.run_specific("nonexistent")


# ------------------------------------------------------------------
# Individual audit methods
# ------------------------------------------------------------------


class TestScoreDrift:
    async def test_no_archive(self, tmp_path: Path) -> None:
        """Returns None when no archive exists."""
        auditor = Auditor(state_dir=tmp_path)
        result = await auditor.run_specific("score_drift")
        assert result is None

    async def test_empty_archive(self, tmp_path: Path) -> None:
        """Returns None when archive file is empty."""
        evo = tmp_path / "evolution"
        evo.mkdir()
        (evo / "archive.jsonl").write_text("")
        auditor = Auditor(state_dir=tmp_path)
        result = await auditor.run_specific("score_drift")
        assert result is None

    async def test_valid_scores_no_finding(self, tmp_path: Path) -> None:
        """In-range fitness scores produce no finding."""
        evo = tmp_path / "evolution"
        evo.mkdir()
        entry = {"fitness": {"elegance": 0.8, "correctness": 0.9}}
        (evo / "archive.jsonl").write_text(json.dumps(entry) + "\n")
        auditor = Auditor(state_dir=tmp_path)
        result = await auditor.run_specific("score_drift")
        assert result is None

    async def test_out_of_range_triggers_finding(self, tmp_path: Path) -> None:
        """Fitness value outside [0,1] triggers a finding."""
        evo = tmp_path / "evolution"
        evo.mkdir()
        entry = {"fitness": {"elegance": 1.5}}
        (evo / "archive.jsonl").write_text(json.dumps(entry) + "\n")
        auditor = Auditor(state_dir=tmp_path)
        result = await auditor.run_specific("score_drift")
        assert result is not None
        assert result.severity == "high"
        assert result.audit_type == "score_drift"
        assert "elegance" in result.description


class TestEleganceAudit:
    async def test_audits_real_source(self, tmp_path: Path) -> None:
        """Elegance audit runs against real source files without crashing."""
        auditor = Auditor(state_dir=tmp_path)
        # This exercises the actual elegance module against package source.
        result = await auditor.run_specific("evolution_elegance")
        # Most files should score > 0.2, so expect None.
        assert result is None or isinstance(result, AuditFinding)


class TestNotesMimicry:
    async def test_no_shared_dir(self, tmp_path: Path) -> None:
        """Returns None when shared dir does not exist."""
        auditor = Auditor(state_dir=tmp_path)
        result = await auditor.run_specific("notes_mimicry")
        assert result is None

    async def test_clean_note_no_finding(self, tmp_path: Path) -> None:
        """A plain note without performative language produces no finding."""
        shared = tmp_path / "shared"
        shared.mkdir()
        (shared / "note.md").write_text("System ran 5 tasks. All passed.")
        auditor = Auditor(state_dir=tmp_path)
        result = await auditor.run_specific("notes_mimicry")
        assert result is None


class TestStigmergyStale:
    async def test_no_marks_file(self, tmp_path: Path) -> None:
        """Returns None when marks file does not exist."""
        auditor = Auditor(state_dir=tmp_path)
        result = await auditor.run_specific("stigmergy_stale")
        assert result is None

    async def test_all_fresh_no_finding(self, tmp_path: Path) -> None:
        """All-fresh marks produce no finding."""
        stig = tmp_path / "stigmergy"
        stig.mkdir()
        now = _utc_now().isoformat()
        marks = [{"timestamp": now, "type": "test"} for _ in range(5)]
        (stig / "marks.jsonl").write_text(
            "\n".join(json.dumps(m) for m in marks) + "\n"
        )
        auditor = Auditor(state_dir=tmp_path)
        result = await auditor.run_specific("stigmergy_stale")
        assert result is None

    async def test_mostly_stale_triggers_finding(self, tmp_path: Path) -> None:
        """More than 50% stale marks triggers a finding."""
        stig = tmp_path / "stigmergy"
        stig.mkdir()
        old_ts = (_utc_now() - timedelta(days=30)).isoformat()
        new_ts = _utc_now().isoformat()
        marks = (
            [{"timestamp": old_ts, "type": "old"} for _ in range(8)]
            + [{"timestamp": new_ts, "type": "new"} for _ in range(2)]
        )
        (stig / "marks.jsonl").write_text(
            "\n".join(json.dumps(m) for m in marks) + "\n"
        )
        auditor = Auditor(state_dir=tmp_path)
        result = await auditor.run_specific("stigmergy_stale")
        assert result is not None
        assert result.audit_type == "stigmergy_stale"
        assert result.drift_magnitude == pytest.approx(0.8)


# ------------------------------------------------------------------
# Findings accumulation
# ------------------------------------------------------------------


class TestFindings:
    async def test_findings_accumulate(self, tmp_path: Path) -> None:
        """Multiple findings accumulate in the auditor."""
        evo = tmp_path / "evolution"
        evo.mkdir()
        # Two entries with out-of-range fitness.
        entry = {"fitness": {"x": -5.0}}
        (evo / "archive.jsonl").write_text(json.dumps(entry) + "\n")

        auditor = Auditor(state_dir=tmp_path)
        r1 = await auditor.run_specific("score_drift")
        r2 = await auditor.run_specific("score_drift")

        assert r1 is not None
        assert r2 is not None
        assert len(auditor.findings) == 2

    async def test_clear_findings(self, tmp_path: Path) -> None:
        """clear_findings empties the list."""
        evo = tmp_path / "evolution"
        evo.mkdir()
        entry = {"fitness": {"x": 99.0}}
        (evo / "archive.jsonl").write_text(json.dumps(entry) + "\n")

        auditor = Auditor(state_dir=tmp_path)
        await auditor.run_specific("score_drift")
        assert len(auditor.findings) >= 1
        auditor.clear_findings()
        assert len(auditor.findings) == 0

    async def test_findings_returns_copy(self, tmp_path: Path) -> None:
        """findings property returns a copy, not the internal list."""
        auditor = Auditor(state_dir=tmp_path)
        f1 = auditor.findings
        f2 = auditor.findings
        assert f1 is not f2


class TestAuditorMisc:
    async def test_auditor_with_tmp_state(self, tmp_path: Path) -> None:
        """Auditor works with tmp_path as state_dir."""
        auditor = Auditor(state_dir=tmp_path)
        assert auditor._state_dir == tmp_path
        # Running all audit types should not crash.
        for at in Auditor.AUDIT_TYPES:
            result = await auditor.run_specific(at)
            assert result is None or isinstance(result, AuditFinding)

    def test_repr(self, tmp_path: Path) -> None:
        auditor = Auditor(state_dir=tmp_path)
        r = repr(auditor)
        assert "Auditor" in r
        assert "findings=0" in r
