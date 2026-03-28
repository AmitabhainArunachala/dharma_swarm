# Eval Probe Task Report

Timestamp: 2026-03-25T14:10:25Z
Task: `eval_probe_task`
Spec refs:
- `dharma_swarm/ecc_eval_harness.py` (`eval_task_roundtrip`, `eval_fitness_signal_flow`)
- `dharma_swarm/message_bus.py` (cross-process event rail)

## Summary

The real eval harness probe initially failed at `fitness_signal_flow` with
`sqlite3.OperationalError: database is locked` on the shared
`~/.dharma/db/messages.db` bus.

Root-cause evidence:
- `python3 -m dharma_swarm.dgc_cli eval run` failed with `fitness_signal_flow = FAIL`.
- A standalone `MessageBus.emit_event("EVAL_PROBE", ...)` on the shared DB reproduced the same lock.
- `lsof` showed long-lived swarm/daemon Python processes holding the message DB and WAL files open.
- `TaskBoard` and `TelemetryPlaneStore` already use stronger SQLite contention handling than `MessageBus`.

## Fix

Changed `dharma_swarm/message_bus.py` to make the event rail contention-tolerant:
- added connection open helper with `timeout=30s`
- applied per-connection `busy_timeout=30000` and `synchronous=NORMAL`
- added bounded retry for transient `database is locked` errors
- applied the retry path to `emit_event()` and `consume_events()`

Added regression coverage in `tests/test_message_bus.py`:
- `test_emit_event_retries_transient_database_lock`

## Verification

Passed:
- `pytest -q tests/test_message_bus.py`
- `pytest -q tests/test_ecc_eval_harness.py`
- `python3 -m dharma_swarm.dgc_cli eval run`

Final real-harness result:
- `14/14` evals passed
- `fitness_signal_flow` recovered to `PASS`
- `pass@1 = 100%`

## Memory Survival Note

Requested externalization targets `~/.dharma/shared` and `~/.dharma/witness`
were not writable in this sandbox, so this report and the `.codex/memories`
mirror were written instead to avoid losing the finding.
