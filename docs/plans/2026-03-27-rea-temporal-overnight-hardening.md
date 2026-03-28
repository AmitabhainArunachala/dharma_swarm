# REA Temporal Overnight Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add REA-style hibernate-and-wake semantics and a hardwired 72-hour self-evolution profile to the existing overnight runtime without creating a second runtime.

**Architecture:** Introduce a small temporal runtime contract that persists run manifests and wait states, then thread it into `overnight_director.py` so overnight execution can hibernate around external waits and resume into the next planned action. Reuse the existing overnight loop, checkpointing, and self-improvement seams rather than replacing them.

**Tech Stack:** Python, pytest, pydantic, existing overnight runtime/state files

---

### Task 1: Temporal Runtime Contracts

**Files:**
- Create: `dharma_swarm/rea_runtime.py`
- Test: `tests/test_rea_runtime.py`

**Step 1: Write the failing tests**

- Assert `all_night_build` and `self_evolution_72h` profiles expose primary/secondary spokes and self-evolution cadence.
- Assert wait states persist, become ready at the correct time, and can be marked resumed.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_rea_runtime.py -q`

**Step 3: Write minimal implementation**

- Add profile, spoke, manifest, and wait-state models.
- Add a filesystem-backed store for manifest and wait-state persistence.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_rea_runtime.py -q`

### Task 2: Overnight Director Integration

**Files:**
- Modify: `dharma_swarm/overnight_director.py`
- Modify: `dharma_swarm/overnight_task_stager.py`
- Test: `tests/test_overnight_director.py`

**Step 1: Write the failing tests**

- Assert `OvernightDirector` writes a temporal manifest for `all_night_build`.
- Assert a task with wait-state metadata yields a `waiting` outcome and records resumable state.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_overnight_director.py -q`

**Step 3: Write minimal implementation**

- Add run profile config to `OvernightConfig`.
- Wire a temporal store into `OvernightDirector`.
- Allow the director to record waiting tasks and resume them later.
- Extend task stager statuses to include `waiting`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_overnight_director.py -q`

### Task 3: 72-Hour Self-Evolution Profile

**Files:**
- Modify: `dharma_swarm/overnight_director.py`
- Test: `tests/test_overnight_director.py`

**Step 1: Write the failing test**

- Assert the 72-hour self-evolution profile is hardwired and uses its own self-improvement cadence.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_overnight_director.py -q`

**Step 3: Write minimal implementation**

- Add a helper entry point for the 72-hour self-evolution campaign.
- Replace hardcoded self-improvement cadence with profile-defined cadence.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_overnight_director.py -q`

### Task 4: Verification

**Files:**
- Verify only

**Step 1: Run focused tests**

Run: `pytest tests/test_rea_runtime.py tests/test_overnight_director.py tests/test_self_improve.py tests/test_codex_overnight.py -q`

**Step 2: Run adjacent seam verification**

Run: `pytest tests/test_orchestrate_live.py tests/test_checkpoint.py tests/test_workflow.py -q`

