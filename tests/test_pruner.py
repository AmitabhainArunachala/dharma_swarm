"""Tests for pruner.py — sweep the zen garden."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dharma_swarm.pruner import Pruner, PruneReport


# ---------------------------------------------------------------------------
# PruneReport
# ---------------------------------------------------------------------------


class TestPruneReport:
    def test_defaults(self):
        r = PruneReport()
        assert r.noise_removed == 0
        assert r.signal_remaining == 0
        assert r.actions_taken == []
        assert r.errors == []

    def test_fields_set(self):
        r = PruneReport(stigmergy_archived=5, stigmergy_kept=10)
        assert r.stigmergy_archived == 5
        assert r.stigmergy_kept == 10


# ---------------------------------------------------------------------------
# Pruner construction
# ---------------------------------------------------------------------------


class TestPrunerInit:
    def test_defaults(self):
        p = Pruner()
        assert p._stig_threshold == 0.3
        assert p._bridge_threshold == 0.2
        assert p._trace_max_days == 14
        assert p._dry_run is False

    def test_custom(self):
        p = Pruner(
            stigmergy_threshold=0.5,
            bridge_threshold=0.4,
            trace_max_days=7,
            dry_run=True,
        )
        assert p._stig_threshold == 0.5
        assert p._dry_run is True


# ---------------------------------------------------------------------------
# Stigmergy pruning
# ---------------------------------------------------------------------------


class TestPruneStigmergy:
    @pytest.mark.asyncio
    async def test_archives_low_salience(self, tmp_path):
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        marks = [
            json.dumps({"path": "/high", "salience": 0.8}),
            json.dumps({"path": "/low", "salience": 0.1}),
            json.dumps({"path": "/mid", "salience": 0.5}),
        ]
        (stig_dir / "marks.jsonl").write_text("\n".join(marks), encoding="utf-8")

        pruner = Pruner(state_dir=tmp_path, stigmergy_threshold=0.3)
        report = PruneReport()
        await pruner._prune_stigmergy(report)

        assert report.stigmergy_archived == 1  # salience 0.1
        assert report.stigmergy_kept == 2  # salience 0.8, 0.5
        # Archive file created
        assert (stig_dir / "archive.jsonl").exists()
        # Marks file rewritten without low-salience
        remaining = (stig_dir / "marks.jsonl").read_text().strip().splitlines()
        assert len(remaining) == 2

    @pytest.mark.asyncio
    async def test_dry_run_no_changes(self, tmp_path):
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        marks = [
            json.dumps({"path": "/low", "salience": 0.05}),
        ]
        (stig_dir / "marks.jsonl").write_text("\n".join(marks), encoding="utf-8")

        pruner = Pruner(state_dir=tmp_path, dry_run=True)
        report = PruneReport()
        await pruner._prune_stigmergy(report)

        assert report.stigmergy_archived == 1
        # But file should NOT be modified
        remaining = (stig_dir / "marks.jsonl").read_text().strip().splitlines()
        assert len(remaining) == 1
        assert not (stig_dir / "archive.jsonl").exists()

    @pytest.mark.asyncio
    async def test_no_marks_file(self, tmp_path):
        pruner = Pruner(state_dir=tmp_path)
        report = PruneReport()
        await pruner._prune_stigmergy(report)
        assert report.stigmergy_archived == 0
        assert report.stigmergy_kept == 0

    @pytest.mark.asyncio
    async def test_corrupt_lines_archived(self, tmp_path):
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        marks = [
            json.dumps({"path": "/good", "salience": 0.9}),
            "not json at all",
        ]
        (stig_dir / "marks.jsonl").write_text("\n".join(marks), encoding="utf-8")

        pruner = Pruner(state_dir=tmp_path)
        report = PruneReport()
        await pruner._prune_stigmergy(report)

        assert report.stigmergy_archived == 1  # corrupt line
        assert report.stigmergy_kept == 1


# ---------------------------------------------------------------------------
# Trace pruning
# ---------------------------------------------------------------------------


class TestPruneTraces:
    @pytest.mark.asyncio
    async def test_archives_old_traces(self, tmp_path):
        trace_dir = tmp_path / "traces" / "history"
        trace_dir.mkdir(parents=True)
        archive_dir = tmp_path / "traces" / "archive"

        # Create old file
        old_file = trace_dir / "old_trace.json"
        old_file.write_text("{}", encoding="utf-8")
        # Set mtime to 30 days ago
        old_time = time.time() - (30 * 86400)
        os.utime(old_file, (old_time, old_time))

        # Create recent file
        new_file = trace_dir / "new_trace.json"
        new_file.write_text("{}", encoding="utf-8")

        pruner = Pruner(state_dir=tmp_path, trace_max_days=14)
        report = PruneReport()
        await pruner._prune_traces(report)

        assert report.traces_archived == 1
        assert (archive_dir / "old_trace.json").exists()
        assert (trace_dir / "new_trace.json").exists()

    @pytest.mark.asyncio
    async def test_dry_run_no_move(self, tmp_path):
        trace_dir = tmp_path / "traces" / "history"
        trace_dir.mkdir(parents=True)

        old_file = trace_dir / "old_trace.json"
        old_file.write_text("{}", encoding="utf-8")
        old_time = time.time() - (30 * 86400)
        os.utime(old_file, (old_time, old_time))

        pruner = Pruner(state_dir=tmp_path, trace_max_days=14, dry_run=True)
        report = PruneReport()
        await pruner._prune_traces(report)

        assert report.traces_archived == 1
        # File still in original location
        assert old_file.exists()

    @pytest.mark.asyncio
    async def test_no_trace_dir(self, tmp_path):
        pruner = Pruner(state_dir=tmp_path)
        report = PruneReport()
        await pruner._prune_traces(report)
        assert report.traces_archived == 0

    @pytest.mark.asyncio
    async def test_all_recent(self, tmp_path):
        trace_dir = tmp_path / "traces" / "history"
        trace_dir.mkdir(parents=True)
        (trace_dir / "recent.json").write_text("{}", encoding="utf-8")

        pruner = Pruner(state_dir=tmp_path, trace_max_days=14)
        report = PruneReport()
        await pruner._prune_traces(report)
        assert report.traces_archived == 0


# ---------------------------------------------------------------------------
# Full sweep
# ---------------------------------------------------------------------------


class TestSweep:
    @pytest.mark.asyncio
    async def test_full_sweep(self, tmp_path):
        # Set up stigmergy marks
        stig_dir = tmp_path / "stigmergy"
        stig_dir.mkdir()
        marks = [
            json.dumps({"path": "/keep", "salience": 0.9}),
            json.dumps({"path": "/archive", "salience": 0.1}),
        ]
        (stig_dir / "marks.jsonl").write_text("\n".join(marks), encoding="utf-8")

        # Set up old trace
        trace_dir = tmp_path / "traces" / "history"
        trace_dir.mkdir(parents=True)
        old_file = trace_dir / "old.json"
        old_file.write_text("{}", encoding="utf-8")
        old_time = time.time() - (30 * 86400)
        os.utime(old_file, (old_time, old_time))

        pruner = Pruner(state_dir=tmp_path, trace_max_days=14)
        report = await pruner.sweep()

        assert report.timestamp != ""
        assert report.duration_seconds >= 0
        assert report.stigmergy_archived == 1
        assert report.stigmergy_kept == 1
        assert report.traces_archived == 1
        assert report.noise_removed >= 2  # stigmergy + traces
        assert report.signal_remaining >= 1
        assert len(report.actions_taken) >= 1

    @pytest.mark.asyncio
    async def test_sweep_empty_state(self, tmp_path):
        pruner = Pruner(state_dir=tmp_path)
        report = await pruner.sweep()
        assert report.noise_removed == 0
        assert report.signal_remaining == 0
        assert report.errors == []


# ---------------------------------------------------------------------------
# Print report (smoke test)
# ---------------------------------------------------------------------------


class TestPrintReport:
    def test_prints_without_error(self, capsys):
        r = PruneReport(
            stigmergy_archived=3,
            stigmergy_kept=10,
            bridges_pruned=1,
            bridges_kept=5,
            noise_removed=4,
            signal_remaining=15,
            actions_taken=["Stigmergy: archived 3 low-salience marks"],
        )
        pruner = Pruner()
        pruner.print_report(r)
        out = capsys.readouterr().out
        assert "PRUNER" in out
        assert "Stigmergy" in out

    def test_dry_run_label(self, capsys):
        pruner = Pruner(dry_run=True)
        pruner.print_report(PruneReport())
        out = capsys.readouterr().out
        assert "DRY RUN" in out

    def test_errors_displayed(self, capsys):
        r = PruneReport(errors=["bridges: table not found"])
        pruner = Pruner()
        pruner.print_report(r)
        out = capsys.readouterr().out
        assert "ERRORS" in out
        assert "table not found" in out
