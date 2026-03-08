# Orchestrator Ledgers

This documents the new session-scoped orchestration ledgers.

## What gets written

- `task_ledger.jsonl`
  - dispatch assignment/blocking events
  - result persistence events
- `progress_ledger.jsonl`
  - task start/complete/fail events
  - normalized failure signatures

## Default location

`~/.dharma/ledgers/<session_id>/`

Where `<session_id>` defaults to UTC timestamp (`YYYYMMDDTHHMMSSZ`).

## Environment overrides

- `DGC_LEDGER_DIR`:
  - base directory for ledger sessions
- `DGC_SESSION_ID`:
  - explicit session folder name

## Hook-ready lifecycle stream

When `message_bus.publish()` is available, the orchestrator emits topic events:

- Topic: `orchestrator.lifecycle`
- Event metadata includes:
  - `event`
  - `task_id`
  - `agent_id`
  - event-specific details (e.g. `failure_signature`, `duration_sec`)

## Event names

- Task ledger:
  - `dispatch_assigned`
  - `dispatch_blocked`
  - `result_persisted`
- Progress ledger:
  - `task_started`
  - `task_completed`
  - `task_failed`
  - `task_blocked`

