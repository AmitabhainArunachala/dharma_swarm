"""Tests for the Cron Scheduler."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from dharma_swarm import cron_scheduler


@pytest.fixture(autouse=True)
def isolate_cron_dir(tmp_path, monkeypatch):
    """Redirect cron storage to a temp directory."""
    cron_dir = tmp_path / "cron"
    monkeypatch.setattr(cron_scheduler, "DHARMA_DIR", tmp_path)
    monkeypatch.setattr(cron_scheduler, "CRON_DIR", cron_dir)
    monkeypatch.setattr(cron_scheduler, "JOBS_FILE", cron_dir / "jobs.json")
    monkeypatch.setattr(cron_scheduler, "OUTPUT_DIR", cron_dir / "output")
    monkeypatch.setattr(cron_scheduler, "LOCK_FILE", cron_dir / ".tick.lock")


class TestParseDuration:
    """Tests for parse_duration()."""

    def test_minutes(self):
        assert cron_scheduler.parse_duration("30m") == 30
        assert cron_scheduler.parse_duration("5min") == 5
        assert cron_scheduler.parse_duration("1minute") == 1

    def test_hours(self):
        assert cron_scheduler.parse_duration("2h") == 120
        assert cron_scheduler.parse_duration("1hr") == 60

    def test_days(self):
        assert cron_scheduler.parse_duration("1d") == 1440
        assert cron_scheduler.parse_duration("2days") == 2880

    def test_invalid(self):
        with pytest.raises(ValueError):
            cron_scheduler.parse_duration("abc")
        with pytest.raises(ValueError):
            cron_scheduler.parse_duration("10x")


class TestParseSchedule:
    """Tests for parse_schedule()."""

    def test_duration_one_shot(self):
        result = cron_scheduler.parse_schedule("30m")
        assert result["kind"] == "once"
        assert "run_at" in result
        assert result["display"] == "once in 30m"

    def test_interval(self):
        result = cron_scheduler.parse_schedule("every 2h")
        assert result["kind"] == "interval"
        assert result["minutes"] == 120
        assert result["display"] == "every 120m"

    def test_timestamp(self):
        result = cron_scheduler.parse_schedule("2026-03-15T14:00:00")
        assert result["kind"] == "once"
        assert "2026-03-15" in result["run_at"]

    def test_invalid_schedule(self):
        with pytest.raises(ValueError, match="Invalid schedule"):
            cron_scheduler.parse_schedule("garbage input")


class TestJobCRUD:
    """Tests for job create/read/update/delete."""

    def test_create_and_get(self):
        job = cron_scheduler.create_job("Run tests", "30m", name="test_job")
        assert job["name"] == "test_job"
        assert job["prompt"] == "Run tests"
        assert job["enabled"] is True

        fetched = cron_scheduler.get_job(job["id"])
        assert fetched is not None
        assert fetched["id"] == job["id"]

    def test_list_jobs(self):
        cron_scheduler.create_job("Job A", "1h")
        cron_scheduler.create_job("Job B", "every 30m")
        jobs = cron_scheduler.list_jobs()
        assert len(jobs) == 2

    def test_remove_job(self):
        job = cron_scheduler.create_job("Temp job", "30m")
        assert cron_scheduler.remove_job(job["id"]) is True
        assert cron_scheduler.get_job(job["id"]) is None

    def test_remove_nonexistent(self):
        assert cron_scheduler.remove_job("nonexistent") is False

    def test_one_shot_auto_repeat_1(self):
        job = cron_scheduler.create_job("Once", "30m")
        assert job["repeat"]["times"] == 1

    def test_interval_repeat_none(self):
        job = cron_scheduler.create_job("Forever", "every 1h")
        assert job["repeat"]["times"] is None


class TestMarkJobRun:
    """Tests for mark_job_run()."""

    def test_mark_success(self):
        job = cron_scheduler.create_job("Test", "every 1h")
        cron_scheduler.mark_job_run(job["id"], True)
        updated = cron_scheduler.get_job(job["id"])
        assert updated["last_status"] == "ok"
        assert updated["last_error"] is None
        assert updated["repeat"]["completed"] == 1

    def test_mark_failure(self):
        job = cron_scheduler.create_job("Test", "every 1h")
        cron_scheduler.mark_job_run(job["id"], False, "boom")
        updated = cron_scheduler.get_job(job["id"])
        assert updated["last_status"] == "error"
        assert updated["last_error"] == "boom"

    def test_one_shot_removed_after_run(self):
        job = cron_scheduler.create_job("Once", "30m")
        assert job["repeat"]["times"] == 1
        cron_scheduler.mark_job_run(job["id"], True)
        assert cron_scheduler.get_job(job["id"]) is None  # auto-removed


class TestGetDueJobs:
    """Tests for get_due_jobs()."""

    def test_due_job_returned(self):
        # Create a job with next_run in the past
        job = cron_scheduler.create_job("Due now", "every 1h")
        # Manually set next_run to past
        jobs = cron_scheduler.load_jobs()
        jobs[0]["next_run_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        cron_scheduler.save_jobs(jobs)

        due = cron_scheduler.get_due_jobs(quiet_hours=set())
        assert len(due) == 1
        assert due[0]["id"] == job["id"]

    def test_future_job_not_due(self):
        cron_scheduler.create_job("Future", "every 1h")
        due = cron_scheduler.get_due_jobs(quiet_hours=set())
        assert len(due) == 0

    def test_disabled_job_skipped(self):
        job = cron_scheduler.create_job("Disabled", "every 1h")
        jobs = cron_scheduler.load_jobs()
        jobs[0]["enabled"] = False
        jobs[0]["next_run_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        cron_scheduler.save_jobs(jobs)

        due = cron_scheduler.get_due_jobs(quiet_hours=set())
        assert len(due) == 0


class TestSaveJobOutput:
    """Tests for save_job_output()."""

    def test_output_saved(self):
        output_file = cron_scheduler.save_job_output("job123", "# Result\nDone!")
        assert output_file.exists()
        assert output_file.read_text() == "# Result\nDone!"


class TestTick:
    """Tests for the tick() function."""

    def test_tick_no_jobs(self):
        executed = cron_scheduler.tick(verbose=False)
        assert executed == 0

    def test_tick_executes_due_jobs(self):
        job = cron_scheduler.create_job("Tick test", "every 1h")
        jobs = cron_scheduler.load_jobs()
        jobs[0]["next_run_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        cron_scheduler.save_jobs(jobs)

        def run_fn(j):
            return True, f"Ran: {j['name']}", None

        executed = cron_scheduler.tick(
            quiet_hours=set(), verbose=False, run_fn=run_fn
        )
        assert executed == 1
