"""Standalone runner for a single cron job by ID.

Designed for launchd invocation — each job runs in its own process,
independent of the daemon or orchestrator.

Usage:
    python3 -m dharma_swarm.launchd_job_runner <job_id>

Exit codes:
    0 — success
    1 — job not found or disabled
    2 — execution error
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dharma_swarm.cron_job_runtime import (
    CronJobExecutionResult,
    CronJobRun,
    CronJobRunStatus,
    CronJobRuntimeStore,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _output_preview(text: str, *, limit: int = 240) -> str:
    collapsed = " ".join(part.strip() for part in text.splitlines() if part.strip())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3] + "..."


def _write_last_run(
    last_run_dir: Path,
    *,
    job_id: str,
    timestamp: str,
    run: CronJobRun | None,
    success: bool,
    output_file: Path | None = None,
    error: str | None = None,
) -> None:
    payload = {
        "job_id": job_id,
        "timestamp": timestamp,
        "success": success,
        "output_file": str(output_file) if output_file is not None else "",
        "error": error,
    }
    if run is not None:
        payload.update(
            {
                "run_id": run.run_id,
                "status": run.status.value,
                "next_action": run.next_action,
                "wake_at": run.wake_at.isoformat() if run.wake_at else None,
            }
        )
    (last_run_dir / f"{job_id}.json").write_text(json.dumps(payload, indent=2))


def _maybe_write_output(
    output_dir: Path,
    *,
    job_id: str,
    timestamp: str,
    result: CronJobExecutionResult,
) -> Path | None:
    if not result.output.strip():
        return None
    out_file = output_dir / f"{job_id}_{timestamp}.md"
    out_file.write_text(result.output)
    return out_file


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python3 -m dharma_swarm.launchd_job_runner <job_id>", file=sys.stderr)
        return 1

    job_id = sys.argv[1]

    # Unset env vars that prevent claude -p nesting
    for var in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT"):
        os.environ.pop(var, None)

    # Load cron_jobs.json from repo root
    cron_file = Path(__file__).parent.parent / "cron_jobs.json"
    if not cron_file.exists():
        print(f"cron_jobs.json not found at {cron_file}", file=sys.stderr)
        return 1

    jobs = json.loads(cron_file.read_text())
    job = next((j for j in jobs if j.get("id") == job_id), None)

    if job is None:
        print(f"Job '{job_id}' not found in cron_jobs.json", file=sys.stderr)
        return 1

    if not job.get("enabled", True):
        print(f"Job '{job_id}' is disabled", file=sys.stderr)
        return 1

    # Ensure output directories exist
    output_dir = Path.home() / ".dharma" / "cron"
    last_run_dir = output_dir / "last_run"
    runtime_store = CronJobRuntimeStore(output_dir / "state")
    output_dir.mkdir(parents=True, exist_ok=True)
    last_run_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    now = _utc_now()

    try:
        from dharma_swarm.cron_runner import execute_cron_job

        ready_wait = runtime_store.mark_ready_if_due(job_id, now=now)
        latest = runtime_store.load_latest(job_id)
        if latest is not None and latest.status is CronJobRunStatus.WAITING_EXTERNAL:
            _write_last_run(
                last_run_dir,
                job_id=job_id,
                timestamp=timestamp,
                run=latest,
                success=True,
            )
            print(f"WAITING: {job_id} until {latest.wake_at.isoformat() if latest.wake_at else 'external signal'}")
            return 0

        run = runtime_store.create_run(
            job_id=job_id,
            job_name=str(job.get("name", job_id)),
            handler=str(job.get("handler", "headless_prompt")),
            now=now,
            metadata={
                "resume_from_wait_state": ready_wait is not None,
                "resume_from_run_id": ready_wait.run_id if ready_wait is not None else "",
            },
        )
        run = runtime_store.transition(
            job_id,
            run.run_id,
            status=CronJobRunStatus.SUBMITTED,
            now=now,
        )

        execution_job = dict(job)
        if ready_wait is not None:
            execution_job["_resume_state"] = ready_wait.model_dump(mode="json")

        result = execute_cron_job(execution_job)
        out_file = _maybe_write_output(output_dir, job_id=job_id, timestamp=timestamp, result=result)
        status = result.status
        if status not in {
            CronJobRunStatus.WAITING_EXTERNAL,
            CronJobRunStatus.BLOCKED_BUDGET,
            CronJobRunStatus.FAILED,
            CronJobRunStatus.COMPLETED,
        }:
            status = CronJobRunStatus.FAILED
            result = result.model_copy(update={"error": result.error or f"Unsupported cron job status: {result.status.value}"})

        run = runtime_store.transition(
            job_id,
            run.run_id,
            status=status,
            now=_utc_now(),
            output_file=str(out_file) if out_file is not None else "",
            output_preview=_output_preview(result.output),
            error=result.error,
            next_action=result.next_action,
            wake_at=result.wake_at,
            metadata=result.metadata,
        )

        success = status in {
            CronJobRunStatus.COMPLETED,
            CronJobRunStatus.WAITING_EXTERNAL,
            CronJobRunStatus.READY_TO_RESUME,
        }
        _write_last_run(
            last_run_dir,
            job_id=job_id,
            timestamp=timestamp,
            run=run,
            success=success,
            output_file=out_file,
            error=None if success else (result.error or None),
        )

        if success and status is CronJobRunStatus.WAITING_EXTERNAL:
            print(f"WAITING: {job_id} until {run.wake_at.isoformat() if run.wake_at else 'external signal'}")
            return 0
        if success:
            print(f"OK: {job_id} -> {out_file}")
            return 0
        else:
            print(f"FAILED: {job_id} — {result.error}", file=sys.stderr)
            return 2

    except Exception as e:
        latest = runtime_store.load_latest(job_id)
        if latest is not None and latest.status in {
            CronJobRunStatus.PLANNED,
            CronJobRunStatus.SUBMITTED,
        }:
            latest = runtime_store.transition(
                job_id,
                latest.run_id,
                status=CronJobRunStatus.FAILED,
                now=_utc_now(),
                error=str(e)[:500],
            )
        _write_last_run(
            last_run_dir,
            job_id=job_id,
            timestamp=timestamp,
            run=latest,
            success=False,
            error=str(e)[:500],
        )
        print(f"ERROR: {job_id} — {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
