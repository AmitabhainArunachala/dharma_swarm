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
from pathlib import Path


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
    output_dir.mkdir(parents=True, exist_ok=True)
    last_run_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")

    try:
        from dharma_swarm.cron_runner import run_cron_job

        success, output, error = run_cron_job(job)

        # Write output
        out_file = output_dir / f"{job_id}_{timestamp}.md"
        out_file.write_text(output)

        # Write last-run status
        last_run = {
            "job_id": job_id,
            "timestamp": timestamp,
            "success": success,
            "output_file": str(out_file),
            "error": error,
        }
        (last_run_dir / f"{job_id}.json").write_text(json.dumps(last_run, indent=2))

        if success:
            print(f"OK: {job_id} -> {out_file}")
            return 0
        else:
            print(f"FAILED: {job_id} — {error}", file=sys.stderr)
            return 2

    except Exception as e:
        # Write error to last-run
        last_run = {
            "job_id": job_id,
            "timestamp": timestamp,
            "success": False,
            "error": str(e)[:500],
        }
        (last_run_dir / f"{job_id}.json").write_text(json.dumps(last_run, indent=2))
        print(f"ERROR: {job_id} — {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
