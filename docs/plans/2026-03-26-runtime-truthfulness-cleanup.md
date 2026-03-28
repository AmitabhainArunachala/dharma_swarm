# Runtime Truthfulness Cleanup Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make operator-facing status and doctor output reflect the canonical live runtime state under `~/.dharma`.

**Architecture:** Keep the runtime contract narrow. `dgc status` should read canonical pulse artifacts instead of legacy `~/dgc-core` state, and doctor should treat `daemon.pid` plus real live processes as authoritative while relegating `orchestrator.pid` to legacy noise. No broader control-plane redesign in this pass.

**Tech Stack:** Python 3, pytest, existing DGC CLI/doctor modules

---

### Task 1: Lock failing truthfulness tests

**Files:**
- Modify: `tests/test_dgc_cli.py`
- Modify: `tests/test_doctor.py`

**Step 1: Write failing test**

Add coverage for:
- `cmd_status()` reporting recent pulse activity from canonical `~/.dharma` artifacts when `~/dgc-core/daemon/state.json` is absent.
- `_check_daemon_integrity()` not warning solely because `orchestrator.pid` is stale when the canonical runtime is otherwise healthy.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dgc_cli.py tests/test_doctor.py -k "status or daemon_integrity" -q`
Expected: FAIL on the new assertions.

### Task 2: Implement minimal runtime truth cleanup

**Files:**
- Modify: `dharma_swarm/dgc_cli.py`
- Modify: `dharma_swarm/doctor.py`
- Modify: `dharma_swarm/living_map.py`

**Step 1: Write minimal implementation**

Implement:
- A small canonical pulse summary helper in `dgc_cli.py` that inspects `~/.dharma/logs/pulse.log`, `~/.dharma/pulse.log`, and/or `~/.dharma/cron/pulse_*.md`.
- `cmd_status()` fallback to that helper instead of printing `Pulse: not yet run` based only on the legacy `~/dgc-core` state file.
- Doctor daemon integrity logic that ignores `orchestrator.pid` for inconsistency warnings while still detecting duplicate live processes.
- Remove dead legacy `orchestrator.pid` read from `living_map.py`.

**Step 2: Run focused tests**

Run: `pytest tests/test_dgc_cli.py tests/test_doctor.py tests/test_living_map.py -q`
Expected: PASS.

### Task 3: Verify operator output against current live artifacts

**Files:**
- None

**Step 1: Run manual verification commands**

Run:
- `python3 -m dharma_swarm.dgc_cli status`
- `python3 -m dharma_swarm.dgc_cli doctor --quick`

Expected:
- `status` no longer says `Pulse: not yet run` when canonical pulse artifacts exist.
- `doctor` daemon integrity does not mention stale legacy `orchestrator.pid` as a primary inconsistency.
