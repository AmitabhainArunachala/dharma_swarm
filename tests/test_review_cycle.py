"""Tests for the Review Cycle Report Generator."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dharma_swarm import iteration_depth, review_cycle
from dharma_swarm.review_cycle import (
    _section_initiatives,
    _section_evolution,
    _section_stigmergy,
    _section_tests,
    _section_memory,
    generate_review,
    generate_review_sync,
    review_run_fn,
    create_review_cron_job,
)


@pytest.fixture(autouse=True)
def isolate_dirs(tmp_path, monkeypatch):
    """Redirect all storage to temp directory."""
    monkeypatch.setattr(review_cycle, "DHARMA_DIR", tmp_path)
    monkeypatch.setattr(review_cycle, "REVIEWS_DIR", tmp_path / "reviews")
    monkeypatch.setattr(iteration_depth, "ITERATION_DIR", tmp_path / "iteration")
    monkeypatch.setattr(
        iteration_depth, "INITIATIVES_FILE", tmp_path / "iteration" / "initiatives.jsonl"
    )
    monkeypatch.setattr(
        iteration_depth, "QUEUE_FILE", tmp_path / "iteration" / "queue.jsonl"
    )


# ── Section: Initiatives ─────────────────────────────────────────────


class TestSectionInitiatives:
    def test_empty_ledger(self):
        result = _section_initiatives()
        assert "Initiative Depth Tracker" in result
        assert "Total" in result

    def test_with_initiatives(self):
        ledger = iteration_depth.IterationLedger()
        ledger.create("Feature Alpha", tags=["core"])
        b = ledger.create("Feature Beta")
        ledger.record_iteration(b.id, "first pass")

        result = _section_initiatives()
        assert "Feature Alpha" in result
        assert "Feature Beta" in result
        assert "Anti-Amnesia Check" in result

    def test_shallow_warning(self):
        ledger = iteration_depth.IterationLedger()
        init = ledger.create("Shallow Thing")
        ledger.record_iteration(init.id, "one pass")

        result = _section_initiatives()
        assert "Shallow Implementations" in result or "shallow" in result.lower()


# ── Section: Evolution ───────────────────────────────────────────────


class TestSectionEvolution:
    @pytest.mark.asyncio
    async def test_no_archive(self, tmp_path):
        """Should handle missing archive gracefully."""
        result = await _section_evolution(hours=6.0)
        assert "Evolution Archive" in result

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Should catch errors and return error section."""
        with patch("dharma_swarm.review_cycle._section_evolution") as mock:
            mock.return_value = "## Evolution Archive\n*Error*\n"
            result = await mock()
            assert "Evolution Archive" in result


# ── Section: Tests ───────────────────────────────────────────────────


class TestSectionTests:
    @pytest.mark.asyncio
    async def test_test_section_runs(self):
        """Should produce a test results section."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "100 passed\n"
        mock_result.stderr = ""
        with patch("dharma_swarm.review_cycle.subprocess.run", return_value=mock_result):
            result = await _section_tests()
        assert "Test Results" in result
        assert "100 passed" in result


# ── Section: Stigmergy ───────────────────────────────────────────────


class TestSectionStigmergy:
    @pytest.mark.asyncio
    async def test_stigmergy_section(self):
        result = await _section_stigmergy(hours=6.0)
        assert "Stigmergy" in result


# ── Section: Memory ──────────────────────────────────────────────────


class TestSectionMemory:
    @pytest.mark.asyncio
    async def test_no_memory_db(self, tmp_path):
        """Should handle missing memory DB."""
        result = await _section_memory()
        assert "Memory" in result


# ── Full Report ──────────────────────────────────────────────────────


class TestGenerateReview:
    @pytest.mark.asyncio
    async def test_report_generated(self, tmp_path):
        """Full report should be generated and saved."""
        report = await generate_review(
            hours=1.0,
            run_tests=False,  # Skip tests for speed
            output_dir=tmp_path / "reviews",
        )
        assert "dharma_swarm Review" in report
        assert "Anti-amnesia attestation" in report

        # Check file was written
        review_files = list((tmp_path / "reviews").glob("review_*.md"))
        assert len(review_files) == 1

    @pytest.mark.asyncio
    async def test_report_includes_all_sections(self, tmp_path):
        report = await generate_review(
            hours=1.0,
            run_tests=False,
            output_dir=tmp_path / "reviews",
        )
        assert "Evolution Archive" in report
        assert "Stigmergy" in report
        assert "Initiative Depth Tracker" in report
        assert "Memory" in report

    @pytest.mark.asyncio
    async def test_report_with_tests_mocked(self, tmp_path):
        """Full report with mocked test runner."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "200 passed\n"
        mock_result.stderr = ""
        with patch("dharma_swarm.review_cycle.subprocess.run", return_value=mock_result):
            report = await generate_review(
                hours=1.0,
                run_tests=True,
                output_dir=tmp_path / "reviews",
            )
        assert "200 passed" in report

    def test_sync_wrapper(self, tmp_path):
        report = generate_review_sync(
            hours=1.0,
            run_tests=False,
            output_dir=tmp_path / "reviews",
        )
        assert "dharma_swarm Review" in report


# ── Cron Integration ─────────────────────────────────────────────────


class TestCronIntegration:
    def test_review_run_fn(self, tmp_path, monkeypatch):
        """review_run_fn should return (success, output, error)."""
        monkeypatch.setattr(review_cycle, "REVIEWS_DIR", tmp_path / "reviews")

        with patch.object(review_cycle, "generate_review_sync") as mock:
            mock.return_value = "# Review\nAll good"
            success, output, error = review_run_fn({"name": "test"})
            assert success is True
            assert "Review" in output
            assert error is None

    def test_review_run_fn_error(self, monkeypatch):
        """review_run_fn should handle errors gracefully."""
        with patch.object(review_cycle, "generate_review_sync") as mock:
            mock.side_effect = RuntimeError("boom")
            success, output, error = review_run_fn({"name": "test"})
            assert success is False
            assert error is not None

    def test_create_review_cron_job(self, tmp_path, monkeypatch):
        """Should create 6-hour review cron job."""
        from dharma_swarm import cron_scheduler

        cron_dir = tmp_path / "cron"
        monkeypatch.setattr(cron_scheduler, "DHARMA_DIR", tmp_path)
        monkeypatch.setattr(cron_scheduler, "CRON_DIR", cron_dir)
        monkeypatch.setattr(cron_scheduler, "JOBS_FILE", cron_dir / "jobs.json")
        monkeypatch.setattr(cron_scheduler, "OUTPUT_DIR", cron_dir / "output")
        monkeypatch.setattr(cron_scheduler, "LOCK_FILE", cron_dir / ".tick.lock")

        job = create_review_cron_job()
        assert job["name"] == "6h-review-cycle"
        assert job["schedule"]["kind"] == "interval"
        assert job["schedule"]["minutes"] == 360  # 6 hours

    def test_create_review_cron_job_idempotent(self, tmp_path, monkeypatch):
        """Should not create duplicate jobs."""
        from dharma_swarm import cron_scheduler

        cron_dir = tmp_path / "cron"
        monkeypatch.setattr(cron_scheduler, "DHARMA_DIR", tmp_path)
        monkeypatch.setattr(cron_scheduler, "CRON_DIR", cron_dir)
        monkeypatch.setattr(cron_scheduler, "JOBS_FILE", cron_dir / "jobs.json")
        monkeypatch.setattr(cron_scheduler, "OUTPUT_DIR", cron_dir / "output")
        monkeypatch.setattr(cron_scheduler, "LOCK_FILE", cron_dir / ".tick.lock")

        job1 = create_review_cron_job()
        job2 = create_review_cron_job()
        assert job1["id"] == job2["id"]  # same job returned
