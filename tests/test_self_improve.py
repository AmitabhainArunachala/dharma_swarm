"""Tests for the Self-Improvement Cycle."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from dharma_swarm.self_improve import (
    CycleReport,
    SelfImprovementCycle,
    _new_cycle_id,
    _touches_protected,
    is_enabled,
    cmd_self_improve_status,
    cmd_self_improve_history,
)


class TestCycleReport:
    def test_defaults(self):
        r = CycleReport()
        assert r.cycle_id == ""
        assert r.enabled is False
        assert r.improved is False
        assert r.proposals_generated == 0

    def test_to_dict(self):
        r = CycleReport(cycle_id="abc", improved=True, improvement_delta=0.05)
        d = r.to_dict()
        assert d["cycle_id"] == "abc"
        assert d["improved"] is True
        assert d["improvement_delta"] == 0.05


class TestIsEnabled:
    def test_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("DHARMA_SELF_IMPROVE", raising=False)
        assert is_enabled() is False

    def test_enabled_with_1(self, monkeypatch):
        monkeypatch.setenv("DHARMA_SELF_IMPROVE", "1")
        assert is_enabled() is True

    def test_enabled_with_true(self, monkeypatch):
        monkeypatch.setenv("DHARMA_SELF_IMPROVE", "true")
        assert is_enabled() is True

    def test_disabled_with_0(self, monkeypatch):
        monkeypatch.setenv("DHARMA_SELF_IMPROVE", "0")
        assert is_enabled() is False


class TestTouchesProtected:
    def test_detects_protected(self):
        mock_p = MagicMock()
        mock_p.component = "dharma_swarm/telos_gates.py"
        result = _touches_protected([mock_p])
        assert len(result) == 1

    def test_allows_normal(self):
        mock_p = MagicMock()
        mock_p.component = "dharma_swarm/foo.py"
        result = _touches_protected([mock_p])
        assert len(result) == 0


class TestNewCycleId:
    def test_format(self):
        cid = _new_cycle_id()
        assert len(cid) == 15  # YYYYMMDD_HHMMSS
        assert "_" in cid


class TestSelfImprovementCycle:
    @pytest.mark.asyncio
    async def test_disabled_returns_early(self, monkeypatch):
        monkeypatch.delenv("DHARMA_SELF_IMPROVE", raising=False)
        cycle = SelfImprovementCycle()
        report = await cycle.run_cycle()
        assert report.enabled is False
        assert "disabled" in report.lesson_learned.lower()

    @pytest.mark.asyncio
    async def test_enabled_cycle(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DHARMA_SELF_IMPROVE", "1")
        monkeypatch.setattr("dharma_swarm.self_improve.CYCLE_DIR", tmp_path)

        # Mock all heavy operations
        async def mock_eval():
            return {"total": 9, "passed": 8, "failed": 1, "pass_at_1": 0.889}

        cycle = SelfImprovementCycle()
        cycle._run_eval = mock_eval
        cycle._run_review = lambda cid: []  # No findings
        cycle._run_tests = lambda: True

        report = await cycle.run_cycle()
        assert report.enabled is True
        assert "No actionable findings" in report.lesson_learned

    @pytest.mark.asyncio
    async def test_with_proposals(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DHARMA_SELF_IMPROVE", "1")
        monkeypatch.setattr("dharma_swarm.self_improve.CYCLE_DIR", tmp_path)

        async def mock_eval():
            return {"total": 9, "passed": 9, "failed": 0, "pass_at_1": 1.0}

        mock_proposal = MagicMock()
        mock_proposal.component = "dharma_swarm/foo.py"
        mock_proposal.description = "fix thing"

        cycle = SelfImprovementCycle()
        cycle._run_eval = mock_eval
        cycle._run_review = lambda cid: [mock_proposal]
        cycle._run_tests = lambda: True
        cycle._write_instinct = lambda r: None

        report = await cycle.run_cycle()
        assert report.proposals_generated == 1
        assert report.proposals_gated == 1

    @pytest.mark.asyncio
    async def test_blocks_locally_modified_target_components(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DHARMA_SELF_IMPROVE", "1")
        monkeypatch.setattr("dharma_swarm.self_improve.CYCLE_DIR", tmp_path)
        monkeypatch.setattr(
            "dharma_swarm.self_improve._find_locally_modified_components",
            lambda components: ["dharma_swarm/foo.py"],
            raising=False,
        )

        async def mock_eval():
            return {"total": 9, "passed": 9, "failed": 0, "pass_at_1": 1.0}

        mock_proposal = MagicMock()
        mock_proposal.component = "dharma_swarm/foo.py"
        mock_proposal.description = "fix thing"
        mock_proposal.diff = "--- a/dharma_swarm/foo.py\n+++ b/dharma_swarm/foo.py\n"

        cycle = SelfImprovementCycle()
        cycle._run_eval = mock_eval
        cycle._run_review = lambda cid: [mock_proposal]
        cycle._run_tests = lambda: pytest.fail("tests should not run when target component is dirty")

        report = await cycle.run_cycle()
        assert report.proposals_generated == 1
        assert report.proposals_blocked == 1
        assert "local changes" in report.lesson_learned.lower()

    @pytest.mark.asyncio
    async def test_failed_tests_force_targeted_rollback(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DHARMA_SELF_IMPROVE", "1")
        monkeypatch.setattr("dharma_swarm.self_improve.CYCLE_DIR", tmp_path)
        monkeypatch.setattr(
            "dharma_swarm.self_improve._find_locally_modified_components",
            lambda components: [],
            raising=False,
        )

        eval_steps = [
            {"total": 9, "passed": 9, "failed": 0, "pass_at_1": 1.0},
            {"total": 9, "passed": 9, "failed": 0, "pass_at_1": 1.0},
        ]

        mock_proposal = MagicMock()
        mock_proposal.component = "dharma_swarm/foo.py"
        mock_proposal.description = "fix thing"
        mock_proposal.diff = (
            "--- a/dharma_swarm/foo.py\n"
            "+++ b/dharma_swarm/foo.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )

        apply_result = MagicMock(
            success=True,
            files_changed=["dharma_swarm/foo.py"],
            backup_paths={
                str(tmp_path / "foo.py"): str(tmp_path / "foo.py.bak"),
            },
            error="",
        )
        mock_applier = MagicMock()
        mock_applier.apply = AsyncMock(return_value=apply_result)
        mock_applier.rollback = AsyncMock()

        monkeypatch.setattr(
            "dharma_swarm.diff_applier.DiffApplier",
            lambda workspace: mock_applier,
        )

        with patch("dharma_swarm.self_improve.subprocess.run") as checkout_run:
            cycle = SelfImprovementCycle()
            cycle._run_eval = AsyncMock(side_effect=eval_steps)
            cycle._run_review = lambda cid: [mock_proposal]
            cycle._run_tests = AsyncMock(return_value=False)
            cycle._write_instinct = lambda r: None

            report = await cycle.run_cycle()

        assert report.tests_passed is False
        assert report.improved is False
        assert report.rollback_executed is True
        assert "tests failed" in report.lesson_learned.lower()
        assert mock_applier.rollback.await_count == 1
        checkout_run.assert_not_called()

    def test_load_history_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.self_improve.CYCLE_DIR", tmp_path)
        assert SelfImprovementCycle.load_history() == []

    def test_load_history_with_data(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.self_improve.CYCLE_DIR", tmp_path)
        report = {"cycle_id": "test", "improved": True}
        (tmp_path / "cycle_test.json").write_text(json.dumps(report))
        history = SelfImprovementCycle.load_history()
        assert len(history) == 1
        assert history[0]["cycle_id"] == "test"

    def test_load_latest(self, tmp_path, monkeypatch):
        monkeypatch.setattr("dharma_swarm.self_improve.CYCLE_DIR", tmp_path)
        report = {"cycle_id": "latest_test", "improved": False}
        (tmp_path / "cycle_latest_test.json").write_text(json.dumps(report))
        latest = SelfImprovementCycle.load_latest()
        assert latest is not None
        assert latest["cycle_id"] == "latest_test"


class TestCLI:
    def test_status_disabled(self, monkeypatch, tmp_path):
        monkeypatch.delenv("DHARMA_SELF_IMPROVE", raising=False)
        monkeypatch.setattr("dharma_swarm.self_improve.CYCLE_DIR", tmp_path)
        rc = cmd_self_improve_status()
        assert rc == 0

    def test_history_empty(self, monkeypatch, tmp_path):
        monkeypatch.setattr("dharma_swarm.self_improve.CYCLE_DIR", tmp_path)
        rc = cmd_self_improve_history()
        assert rc == 0
