"""Cron Scheduler — file-based job scheduling for dharma_swarm.

Inspired by Hermes Agent's cron/scheduler.py and cron/jobs.py.

Jobs are stored in ~/.dharma/cron/jobs.json. Each job has:
  - prompt: the task to execute
  - schedule: duration ("30m"), interval ("every 2h"), cron ("0 9 * * *"),
    or timestamp ("2026-03-15T14:00")
  - delivery: where to send results ("local", "telegram:<chat_id>", etc.)

``tick()`` checks for due jobs, acquires a file lock, and executes them.
Integrates with YogaScheduler quiet hours — jobs are deferred during
quiet hours unless marked urgent.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────

DHARMA_DIR = Path(os.getenv("DHARMA_HOME", Path.home() / ".dharma"))
CRON_DIR = DHARMA_DIR / "cron"
JOBS_FILE = CRON_DIR / "jobs.json"
OUTPUT_DIR = CRON_DIR / "output"
LOCK_FILE = CRON_DIR / ".tick.lock"

# Default quiet hours (2-4 AM local)
DEFAULT_QUIET_HOURS: set[int] = {2, 3, 4}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_dirs() -> None:
    """Create cron directories with secure permissions."""
    CRON_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CRON_DIR, 0o700)
        os.chmod(OUTPUT_DIR, 0o700)
    except (OSError, NotImplementedError):
        pass


# ── Schedule Parsing ─────────────────────────────────────────────────

_DURATION_RE = re.compile(
    r"^(\d+)\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$"
)
_MULTIPLIERS = {"m": 1, "h": 60, "d": 1440}


def parse_duration(s: str) -> int:
    """Parse duration string into minutes. E.g. '30m' → 30, '2h' → 120."""
    match = _DURATION_RE.match(s.strip().lower())
    if not match:
        raise ValueError(f"Invalid duration: '{s}'. Use '30m', '2h', or '1d'")
    value = int(match.group(1))
    unit = match.group(2)[0]  # first char
    return value * _MULTIPLIERS[unit]


def parse_schedule(schedule: str) -> dict[str, Any]:
    """Parse schedule string into structured format.

    Returns dict with:
        - kind: "once" | "interval" | "cron"
        - For "once": "run_at" (ISO timestamp)
        - For "interval": "minutes" (int)
        - For "cron": "expr" (cron expression)
        - display: human-readable description
    """
    schedule = schedule.strip()
    original = schedule

    # "every X" pattern → recurring interval
    if schedule.lower().startswith("every "):
        duration_str = schedule[6:].strip()
        minutes = parse_duration(duration_str)
        return {"kind": "interval", "minutes": minutes, "display": f"every {minutes}m"}

    # Cron expression (5+ space-separated fields of digits/*/-)
    parts = schedule.split()
    if len(parts) >= 5 and all(re.match(r"^[\d\*\-,/]+$", p) for p in parts[:5]):
        try:
            from croniter import croniter
            croniter(schedule)  # validate
        except ImportError:
            raise ValueError(
                "Cron expressions require 'croniter' package. "
                "Install with: pip install croniter"
            )
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{schedule}': {e}")
        return {"kind": "cron", "expr": schedule, "display": schedule}

    # ISO timestamp
    if "T" in schedule or re.match(r"^\d{4}-\d{2}-\d{2}", schedule):
        try:
            dt = datetime.fromisoformat(schedule.replace("Z", "+00:00"))
            return {
                "kind": "once",
                "run_at": dt.isoformat(),
                "display": f"once at {dt.strftime('%Y-%m-%d %H:%M')}",
            }
        except ValueError as e:
            raise ValueError(f"Invalid timestamp '{schedule}': {e}")

    # Duration → one-shot from now
    try:
        minutes = parse_duration(schedule)
        run_at = _utc_now() + timedelta(minutes=minutes)
        return {
            "kind": "once",
            "run_at": run_at.isoformat(),
            "display": f"once in {original}",
        }
    except ValueError:
        pass

    raise ValueError(
        f"Invalid schedule '{original}'. Use:\n"
        f"  - Duration: '30m', '2h', '1d' (one-shot)\n"
        f"  - Interval: 'every 30m', 'every 2h' (recurring)\n"
        f"  - Cron: '0 9 * * *' (cron expression)\n"
        f"  - Timestamp: '2026-03-15T14:00:00' (one-shot at time)"
    )


def compute_next_run(
    schedule: dict[str, Any],
    last_run_at: str | None = None,
) -> str | None:
    """Compute the next run time for a schedule. Returns ISO string or None."""
    now = _utc_now()

    if schedule["kind"] == "once":
        run_at = datetime.fromisoformat(schedule["run_at"])
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        return schedule["run_at"] if run_at > now else None

    elif schedule["kind"] == "interval":
        minutes = schedule["minutes"]
        if last_run_at:
            last = datetime.fromisoformat(last_run_at)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            next_run = last + timedelta(minutes=minutes)
        else:
            next_run = now + timedelta(minutes=minutes)
        return next_run.isoformat()

    elif schedule["kind"] == "cron":
        try:
            from croniter import croniter
            cron = croniter(schedule["expr"], now)
            return cron.get_next(datetime).isoformat()
        except ImportError:
            return None

    return None


# ── Job CRUD ─────────────────────────────────────────────────────────

def load_jobs() -> list[dict[str, Any]]:
    """Load all jobs from storage."""
    _ensure_dirs()
    if not JOBS_FILE.exists():
        return []
    try:
        with open(JOBS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("jobs", [])
    except (json.JSONDecodeError, IOError):
        return []


def save_jobs(jobs: list[dict[str, Any]]) -> None:
    """Atomically save all jobs to storage."""
    _ensure_dirs()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(JOBS_FILE.parent), suffix=".tmp", prefix=".jobs_"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(
                {"jobs": jobs, "updated_at": _utc_now().isoformat()},
                f,
                indent=2,
            )
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, JOBS_FILE)
        try:
            os.chmod(JOBS_FILE, 0o600)
        except (OSError, NotImplementedError):
            pass
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def create_job(
    prompt: str,
    schedule: str,
    name: str | None = None,
    repeat: int | None = None,
    deliver: str = "local",
    urgent: bool = False,
) -> dict[str, Any]:
    """Create a new cron job.

    Args:
        prompt: The task prompt to execute.
        schedule: Schedule string (see parse_schedule).
        name: Optional friendly name.
        repeat: How many times to run (None = forever, 1 = once).
        deliver: Delivery target ("local", "telegram:<chat_id>", etc.).
        urgent: If True, runs even during quiet hours.
    """
    parsed = parse_schedule(schedule)

    # Auto-set repeat=1 for one-shot schedules
    if parsed["kind"] == "once" and repeat is None:
        repeat = 1

    job_id = uuid.uuid4().hex[:12]
    now = _utc_now().isoformat()

    job: dict[str, Any] = {
        "id": job_id,
        "name": name or prompt[:50].strip(),
        "prompt": prompt,
        "schedule": parsed,
        "schedule_display": parsed.get("display", schedule),
        "repeat": {"times": repeat, "completed": 0},
        "enabled": True,
        "urgent": urgent,
        "created_at": now,
        "next_run_at": compute_next_run(parsed),
        "last_run_at": None,
        "last_status": None,
        "last_error": None,
        "deliver": deliver,
    }

    jobs = load_jobs()
    jobs.append(job)
    save_jobs(jobs)
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    """Get a job by ID."""
    for job in load_jobs():
        if job["id"] == job_id:
            return job
    return None


def list_jobs(include_disabled: bool = False) -> list[dict[str, Any]]:
    """List all jobs, optionally including disabled ones."""
    jobs = load_jobs()
    if not include_disabled:
        jobs = [j for j in jobs if j.get("enabled", True)]
    return jobs


def remove_job(job_id: str) -> bool:
    """Remove a job by ID."""
    jobs = load_jobs()
    original_len = len(jobs)
    jobs = [j for j in jobs if j["id"] != job_id]
    if len(jobs) < original_len:
        save_jobs(jobs)
        return True
    return False


def mark_job_run(
    job_id: str,
    success: bool,
    error: str | None = None,
) -> None:
    """Mark a job as having been run. Updates next_run_at, auto-removes if done."""
    jobs = load_jobs()
    for i, job in enumerate(jobs):
        if job["id"] == job_id:
            now = _utc_now().isoformat()
            job["last_run_at"] = now
            job["last_status"] = "ok" if success else "error"
            job["last_error"] = error if not success else None

            # Increment completed count
            if job.get("repeat"):
                job["repeat"]["completed"] = job["repeat"].get("completed", 0) + 1
                times = job["repeat"].get("times")
                completed = job["repeat"]["completed"]
                if times is not None and completed >= times:
                    jobs.pop(i)
                    save_jobs(jobs)
                    return

            # Compute next run
            job["next_run_at"] = compute_next_run(job["schedule"], now)
            if job["next_run_at"] is None:
                job["enabled"] = False

            save_jobs(jobs)
            return

    save_jobs(jobs)


def get_due_jobs(quiet_hours: set[int] | None = None) -> list[dict[str, Any]]:
    """Get all jobs that are due to run now.

    Non-urgent jobs are skipped during quiet hours.
    """
    now = _utc_now()
    current_hour = datetime.now().hour  # local hour for quiet check
    in_quiet = current_hour in (quiet_hours or DEFAULT_QUIET_HOURS)

    jobs = load_jobs()
    due: list[dict[str, Any]] = []

    for job in jobs:
        if not job.get("enabled", True):
            continue
        next_run = job.get("next_run_at")
        if not next_run:
            continue
        next_dt = datetime.fromisoformat(next_run)
        if next_dt.tzinfo is None:
            next_dt = next_dt.replace(tzinfo=timezone.utc)
        if next_dt <= now:
            if in_quiet and not job.get("urgent", False):
                logger.debug("Job '%s' deferred (quiet hours)", job.get("name"))
                continue
            due.append(job)

    return due


def save_job_output(job_id: str, output: str) -> Path:
    """Save job output to a timestamped markdown file."""
    _ensure_dirs()
    job_dir = OUTPUT_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    timestamp = _utc_now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file = job_dir / f"{timestamp}.md"
    output_file.write_text(output, encoding="utf-8")
    return output_file


# ── Tick ─────────────────────────────────────────────────────────────

def tick(
    quiet_hours: set[int] | None = None,
    verbose: bool = True,
    run_fn: Any = None,
) -> int:
    """Check and run all due jobs.

    Uses a file lock so only one tick runs at a time.

    Args:
        quiet_hours: Hours (local) during which non-urgent jobs are deferred.
        verbose: Whether to log status.
        run_fn: Callable(job_dict) -> (success, output, error). If None,
            jobs are logged but not executed (for testing).

    Returns:
        Number of jobs executed (0 if lock held by another process).
    """
    _ensure_dirs()

    lock_fd = None
    try:
        lock_fd = open(LOCK_FILE, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, IOError):
        logger.debug("Tick skipped — another instance holds the lock")
        if lock_fd is not None:
            lock_fd.close()
        return 0

    try:
        due_jobs = get_due_jobs(quiet_hours)
        now_str = _utc_now().strftime("%H:%M:%S")

        if verbose and not due_jobs:
            logger.info("%s — No jobs due", now_str)
            return 0

        if verbose:
            logger.info("%s — %d job(s) due", now_str, len(due_jobs))

        executed = 0
        for job in due_jobs:
            try:
                if run_fn is not None:
                    success, output, error = run_fn(job)
                else:
                    success = True
                    output = f"# Job: {job.get('name')}\nPrompt: {job['prompt']}\n"
                    error = None

                save_job_output(job["id"], output)
                mark_job_run(job["id"], success, error)
                executed += 1

            except Exception as e:
                logger.error("Error processing job %s: %s", job["id"], e)
                mark_job_run(job["id"], False, str(e))

        return executed
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        lock_fd.close()
