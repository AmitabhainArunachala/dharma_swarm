# Status And Doctor Truthfulness Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make runtime status and doctor output reflect the canonical `~/.dharma` control-plane state instead of legacy absorbed paths.

**Architecture:** Keep `daemon.pid` and `~/.dharma` pulse artifacts as the authoritative runtime contract. Treat `orchestrator.pid` as legacy cleanup evidence only, while preserving a warning when it exists. Tighten doctor metadata so cached reports expose a real generation timestamp.

**Tech Stack:** Python, pytest, existing DGC CLI and doctor diagnostics.

---

### Task 1: Lock failing tests for canonical status behavior

**Files:**
- Modify: `tests/test_dgc_cli.py`
- Test: `tests/test_dgc_cli.py`

**Step 1: Write the failing test**

Add a test that points `DHARMA_STATE` and `HOME` at a temp runtime, writes a fresh `pulse.log`, and asserts `cmd_status()` does not print `Pulse: not yet run`.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dgc_cli.py -k status -q`
Expected: FAIL because `cmd_status()` still reads `~/dgc-core/daemon/state.json`.

**Step 3: Write minimal implementation**

Update `cmd_status()` to derive pulse/truthfulness from canonical `~/.dharma` artifacts first, then fall back gracefully.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_dgc_cli.py -k status -q`
Expected: PASS.

### Task 2: Lock failing tests for doctor legacy PID semantics

**Files:**
- Modify: `tests/test_doctor.py`
- Test: `tests/test_doctor.py`

**Step 1: Write the failing test**

Add a test where `daemon.pid` is live and `orchestrator.pid` is stale, and assert doctor reports a warning that names the legacy PID file without treating it as the owning runtime signal.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_doctor.py -k daemon_integrity -q`
Expected: FAIL until doctor semantics are tightened.

**Step 3: Write minimal implementation**

Update doctor PID inspection to prioritize `daemon.pid`, keep `orchestrator.pid` as a legacy signal, and improve the warning detail/fix guidance.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_doctor.py -k daemon_integrity -q`
Expected: PASS.

### Task 3: Lock failing tests for doctor metadata

**Files:**
- Modify: `tests/test_doctor.py`
- Test: `tests/test_doctor.py`

**Step 1: Write the failing test**

Add a test asserting `write_doctor_artifacts()` persists a non-null `generated_at` timestamp when absent from the incoming report.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_doctor.py -k generated_at -q`
Expected: FAIL because the cached latest report currently shows `generated_at: null`.

**Step 3: Write minimal implementation**

Populate `generated_at` once during artifact writing and keep it stable across latest/history outputs.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_doctor.py -k generated_at -q`
Expected: PASS.

### Task 4: Verify targeted runtime diagnostics

**Files:**
- Modify: `dharma_swarm/dgc_cli.py`
- Modify: `dharma_swarm/doctor.py`
- Test: `tests/test_dgc_cli.py`
- Test: `tests/test_doctor.py`

**Step 1: Run focused verification**

Run: `pytest tests/test_dgc_cli.py tests/test_doctor.py -q`
Expected: PASS with the new invariants covered.

**Step 2: Spot-check operator truthfulness**

Run: `dgc status` and `dgc doctor latest`
Expected: status reflects canonical pulse evidence; doctor still warns about duplicate runtimes/legacy leftovers truthfully.
