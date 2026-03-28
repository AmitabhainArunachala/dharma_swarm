"""Tests for launchd_job_runner."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import dharma_swarm.launchd_job_runner as runner
from dharma_swarm.cron_job_runtime import CronJobExecutionResult, CronJobRunStatus


def _configure_runner_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    package_dir = repo_root / "dharma_swarm"
    package_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runner, "__file__", str(package_dir / "launchd_job_runner.py"))
    monkeypatch.setattr(runner.Path, "home", lambda: tmp_path)
    return repo_root


def _write_cron_jobs(repo_root: Path, jobs: list[dict[str, object]]) -> None:
    (repo_root / "cron_jobs.json").write_text(
        json.dumps(jobs, indent=2),
        encoding="utf-8",
    )


def _last_run_payload(tmp_path: Path, job_id: str) -> dict[str, object]:
    return json.loads(
        (tmp_path / ".dharma" / "cron" / "last_run" / f"{job_id}.json").read_text(
            encoding="utf-8"
        )
    )


def _latest_runtime_payload(tmp_path: Path, job_id: str) -> dict[str, object]:
    return json.loads(
        (tmp_path / ".dharma" / "cron" / "state" / "latest" / f"{job_id}.json").read_text(
            encoding="utf-8"
        )
    )


class TestLaunchdJobRunner:
    def test_no_args(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(runner.sys, "argv", ["launchd_job_runner"])
        assert runner.main() == 1

    def test_waiting_external_run_is_persisted(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        repo_root = _configure_runner_paths(monkeypatch, tmp_path)
        _write_cron_jobs(
            repo_root,
            [{"id": "waiter", "name": "Waiter", "enabled": True, "handler": "headless_prompt"}],
        )
        monkeypatch.setattr(runner.sys, "argv", ["launchd_job_runner", "waiter"])

        wake_at = datetime(2026, 3, 27, 12, 0, tzinfo=timezone.utc)
        monkeypatch.setattr(
            "dharma_swarm.cron_runner.execute_cron_job",
            lambda job: CronJobExecutionResult(
                status=CronJobRunStatus.WAITING_EXTERNAL,
                output="Submitted external benchmark job",
                next_action="Collect benchmark outputs",
                wake_at=wake_at,
                metadata={"job_id": "bench-123"},
            ),
        )
        monkeypatch.setattr(
            runner,
            "_utc_now",
            lambda: datetime(2026, 3, 27, 11, 0, tzinfo=timezone.utc),
        )

        assert runner.main() == 0

        latest = _latest_runtime_payload(tmp_path, "waiter")
        assert latest["status"] == "waiting_external"
        assert latest["next_action"] == "Collect benchmark outputs"
        assert latest["metadata"]["job_id"] == "bench-123"

        last_run = _last_run_payload(tmp_path, "waiter")
        assert last_run["status"] == "waiting_external"
        assert last_run["wake_at"] == wake_at.isoformat()
        assert last_run["success"] is True

    def test_due_wait_state_is_marked_ready_then_resubmitted(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        repo_root = _configure_runner_paths(monkeypatch, tmp_path)
        _write_cron_jobs(
            repo_root,
            [{"id": "waiter", "name": "Waiter", "enabled": True, "handler": "headless_prompt"}],
        )

        first_now = datetime(2026, 3, 27, 11, 0, tzinfo=timezone.utc)
        second_now = first_now + timedelta(minutes=10)
        wake_at = first_now + timedelta(minutes=5)
        call_count = {"count": 0}
        resume_contexts: list[dict[str, object]] = []

        def _fake_execute(job: dict[str, object]) -> CronJobExecutionResult:
            call_count["count"] += 1
            if call_count["count"] == 1:
                return CronJobExecutionResult(
                    status=CronJobRunStatus.WAITING_EXTERNAL,
                    output="Submitted external benchmark job",
                    next_action="Collect benchmark outputs",
                    wake_at=wake_at,
                    metadata={"job_id": "bench-123"},
                )
            resume_contexts.append(dict(job.get("_resume_state") or {}))
            return CronJobExecutionResult(
                status=CronJobRunStatus.COMPLETED,
                output="Collected benchmark outputs",
                metadata={"resumed": True},
            )

        monkeypatch.setattr("dharma_swarm.cron_runner.execute_cron_job", _fake_execute)
        monkeypatch.setattr(runner.sys, "argv", ["launchd_job_runner", "waiter"])

        monkeypatch.setattr(runner, "_utc_now", lambda: first_now)
        assert runner.main() == 0

        monkeypatch.setattr(runner, "_utc_now", lambda: second_now)
        assert runner.main() == 0

        assert call_count["count"] == 2
        assert resume_contexts
        assert resume_contexts[0]["status"] == "ready_to_resume"
        assert resume_contexts[0]["next_action"] == "Collect benchmark outputs"

        latest = _latest_runtime_payload(tmp_path, "waiter")
        assert latest["status"] == "completed"
        assert latest["metadata"]["resume_from_wait_state"] is True

        history_path = tmp_path / ".dharma" / "cron" / "state" / "history" / "waiter.jsonl"
        history = [json.loads(line) for line in history_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        statuses = [entry["status"] for entry in history]
        assert "waiting_external" in statuses
        assert "ready_to_resume" in statuses
        assert statuses[-1] == "completed"
