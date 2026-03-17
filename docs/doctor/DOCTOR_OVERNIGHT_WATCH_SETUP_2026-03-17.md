# Doctor Overnight Watch Setup

Date: 2026-03-17

## What changed

- Added `message_bus_integrity` to `dharma_swarm/doctor.py`.
  - Verifies the canonical shared bus at `~/.dharma/db/messages.db`.
  - Checks SQLite journal mode, message/event counts, shadow bus paths, and whether the bus is acting like a mailbox only.
- Added `doctor_schedule` to `dharma_swarm/doctor.py`.
  - Verifies that unattended `doctor_assurance` cron jobs are actually configured and not overdue.
- Marked Doctor cron jobs as `urgent` in `create_doctor_job()`.
  - This prevents Doctor sweeps from being silently deferred during the scheduler's local quiet hours.
- Fixed `install_launchd_service()` so the cron launchd plist is written with absolute paths instead of raw `~`.
  - This makes the unattended cron daemon installable and restartable under launchd.
- Added focused regression tests in `tests/test_doctor.py` for both checks.
 - Added a regression test in `tests/test_custodians.py` for absolute-path launchd plist rendering.

## Overnight cadence

The following Doctor jobs are now armed:

- `doctor_assurance`
  - schedule: `every 360m`
  - mode: full sweep
- `doctor_assurance_quicknight`
  - job id: `8bac179a9272`
  - schedule: `every 120m`
  - mode: quick sweep
  - next run at creation: `2026-03-16T17:22:31.188497+00:00`

This leaves the deeper 6-hour sweep in place and adds a lighter 2-hour guardrail overnight.

## Repair status

After the repair pass:

- both Doctor jobs have executed once via cron tick
- both Doctor jobs are now marked `urgent: true`
- launchd plist is installed at `~/Library/LaunchAgents/com.dharma.cron-daemon.plist`
- cron daemon PID file was refreshed and the daemon process was verified alive

Note: the Doctor cron jobs currently show `last=error` because Doctor itself is surfacing real repo failures. That is expected and means the scheduler is executing the jobs.

## What Doctor now surfaces on this machine

Latest quick run shows:

- stale PID state still present
- shared message bus is active but mostly mailbox-only
- Redis is down locally
- dashboard route drift still exists
- typed API envelope drift still exists
- CODEX/Anthropic provider naming drift still exists
- context isolation leak still exists
- lifecycle gaps still exist

## Why this is orthogonal

These changes do not alter:

- daemon startup
- orchestrator behavior
- provider routing
- task execution
- telic lifecycle writes

They only improve detection, visibility, and unattended monitoring while the main stabilization lane keeps changing runtime code.
