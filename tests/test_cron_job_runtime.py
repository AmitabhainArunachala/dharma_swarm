from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from dharma_swarm.cron_job_runtime import CronJobRunStatus, CronJobRuntimeStore


def test_mark_ready_if_due_transitions_waiting_run(tmp_path: Path) -> None:
    store = CronJobRuntimeStore(tmp_path)
    now = datetime(2026, 3, 27, 11, 0, tzinfo=timezone.utc)
    wake_at = now + timedelta(minutes=5)

    run = store.create_run(
        job_id="waiter",
        job_name="Waiter",
        handler="headless_prompt",
        now=now,
    )
    store.transition(
        "waiter",
        run.run_id,
        status=CronJobRunStatus.WAITING_EXTERNAL,
        now=now,
        next_action="Collect benchmark outputs",
        wake_at=wake_at,
        metadata={"job_id": "bench-123"},
    )

    assert store.mark_ready_if_due("waiter", now=now + timedelta(minutes=1)) is None

    ready = store.mark_ready_if_due("waiter", now=now + timedelta(minutes=10))
    assert ready is not None
    assert ready.status is CronJobRunStatus.READY_TO_RESUME
    assert ready.next_action == "Collect benchmark outputs"

    latest = store.load_latest("waiter")
    assert latest is not None
    assert latest.status is CronJobRunStatus.READY_TO_RESUME
