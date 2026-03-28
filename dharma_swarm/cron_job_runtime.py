"""Durable runtime state for cron and launchd jobs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _new_run_id() -> str:
    return f"cron_{uuid4().hex[:16]}"


class CronJobRunStatus(str, Enum):
    PLANNED = "planned"
    SUBMITTED = "submitted"
    WAITING_EXTERNAL = "waiting_external"
    READY_TO_RESUME = "ready_to_resume"
    BLOCKED_BUDGET = "blocked_budget"
    FAILED = "failed"
    COMPLETED = "completed"


class CronJobExecutionResult(BaseModel):
    """Structured result returned by a cron job handler."""

    status: CronJobRunStatus = CronJobRunStatus.COMPLETED
    output: str = ""
    error: str = ""
    next_action: str = ""
    wake_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CronJobRun(BaseModel):
    """Durable record for a single cron/launchd execution attempt."""

    run_id: str = Field(default_factory=_new_run_id)
    job_id: str
    job_name: str = ""
    handler: str = "headless_prompt"
    status: CronJobRunStatus = CronJobRunStatus.PLANNED
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    finished_at: datetime | None = None
    output_file: str = ""
    output_preview: str = ""
    error: str = ""
    next_action: str = ""
    wake_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CronJobRuntimeStore:
    """Filesystem-backed state store for cron jobs."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else (Path.home() / ".dharma" / "cron" / "state")
        self.latest_dir = self.base_dir / "latest"
        self.history_dir = self.base_dir / "history"

    def create_run(
        self,
        *,
        job_id: str,
        job_name: str,
        handler: str,
        now: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CronJobRun:
        current = now or _utc_now()
        run = CronJobRun(
            job_id=job_id,
            job_name=job_name,
            handler=handler,
            created_at=current,
            updated_at=current,
            metadata=dict(metadata or {}),
        )
        self._persist(run)
        return run

    def transition(
        self,
        job_id: str,
        run_id: str,
        *,
        status: CronJobRunStatus,
        now: datetime | None = None,
        output_file: str | None = None,
        output_preview: str | None = None,
        error: str | None = None,
        next_action: str | None = None,
        wake_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CronJobRun:
        current = self.load_latest(job_id)
        if current is None or current.run_id != run_id:
            raise KeyError(f"Latest run for {job_id} does not match {run_id}")

        current_time = now or _utc_now()
        merged_metadata = {**current.metadata, **(metadata or {})}
        terminal = status in {
            CronJobRunStatus.BLOCKED_BUDGET,
            CronJobRunStatus.FAILED,
            CronJobRunStatus.COMPLETED,
        }
        updated = current.model_copy(
            update={
                "status": status,
                "updated_at": current_time,
                "finished_at": current_time if terminal else current.finished_at,
                "output_file": current.output_file if output_file is None else output_file,
                "output_preview": current.output_preview if output_preview is None else output_preview,
                "error": current.error if error is None else error,
                "next_action": current.next_action if next_action is None else next_action,
                "wake_at": current.wake_at if wake_at is None else wake_at,
                "metadata": merged_metadata,
            }
        )
        self._persist(updated)
        return updated

    def load_latest(self, job_id: str) -> CronJobRun | None:
        path = self.latest_dir / f"{job_id}.json"
        if not path.exists():
            return None
        return CronJobRun.model_validate_json(path.read_text(encoding="utf-8"))

    def list_history(self, job_id: str) -> list[CronJobRun]:
        path = self.history_dir / f"{job_id}.jsonl"
        if not path.exists():
            return []
        history: list[CronJobRun] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            history.append(CronJobRun.model_validate_json(line))
        return history

    def mark_ready_if_due(
        self,
        job_id: str,
        *,
        now: datetime | None = None,
    ) -> CronJobRun | None:
        latest = self.load_latest(job_id)
        if latest is None or latest.status is not CronJobRunStatus.WAITING_EXTERNAL:
            return None
        if latest.wake_at is None:
            return None
        current = now or _utc_now()
        if latest.wake_at > current:
            return None
        return self.transition(
            job_id,
            latest.run_id,
            status=CronJobRunStatus.READY_TO_RESUME,
            now=current,
            metadata={"resume_from_wait_state": True},
        )

    def _persist(self, run: CronJobRun) -> None:
        self.latest_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)
        (self.latest_dir / f"{run.job_id}.json").write_text(
            run.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )
        with (self.history_dir / f"{run.job_id}.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(run.model_dump_json() + "\n")


__all__ = [
    "CronJobExecutionResult",
    "CronJobRun",
    "CronJobRunStatus",
    "CronJobRuntimeStore",
]
