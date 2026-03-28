# Runtime Stabilization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore truthful live task flow, reduce wasted timeout failures, extract a maintainable `agent_runner` seam, and safely restart the daemon on verified code.

**Architecture:** Fix the dispatch starvation at the task-state layer first, because the live daemon is idle due to dependency-blocked work being mislabeled as `pending`. Then tighten timeout recovery, extract the semantic-quality/honors path out of `agent_runner.py`, and only then perform runtime maintenance, restart, and commit.

**Tech Stack:** Python 3.14, SQLite, asyncio, pytest, dharma_swarm runtime stack.

---

### Task 1: Document the Starvation Root Cause

**Files:**
- Modify: `docs/plans/2026-03-28-runtime-stabilization.md`
- Read: `dharma_swarm/swarm.py`
- Read: `dharma_swarm/task_board.py`

**Step 1: Capture the live finding**

Record that `~/.dharma/db/tasks.db` has `20` pending tasks, `TaskBoard.get_ready_tasks()` returns `0`, and the blocked chains root in failed dependencies whose rescue exhaustion is misclassified.

**Step 2: Capture the concrete policy mismatch**

Record that `SwarmManager._propagate_dependency_failures()` hard-codes `auto_rescue_count >= 2` while `DEFAULT_CONFIG.swarm.auto_rescue_max_attempts == 1`.

**Step 3: Capture the broader terminality rule**

Record that terminal dependency detection should consider:
- configured rescue limit
- retry budget exhaustion
- rescue eligibility by failure class
- rescue max age

### Task 2: Add Failing Tests for Dependency Terminality

**Files:**
- Modify: `tests/test_orphan_reaper.py`
- Read: `dharma_swarm/swarm.py`
- Read: `dharma_swarm/config.py`

**Step 1: Write a failing test for configured rescue exhaustion**

Add a test proving a child propagates to `FAILED` when its failed parent has `auto_rescue_count == auto_rescue_max_attempts`.

**Step 2: Write a failing test for expired rescue age**

Add a test proving an old failed dependency past the rescue-age window is terminal even if `auto_rescue_count == 0`.

**Step 3: Write a failing test for non-rescuable failure class**

Add a test proving a failed dependency with a non-rescuable failure class is terminal once retry budget is exhausted.

**Step 4: Verify red**

Run: `python3 -m pytest tests/test_orphan_reaper.py -q`
Expected: new tests fail before implementation.

### Task 3: Implement Terminal Dependency Propagation

**Files:**
- Modify: `dharma_swarm/swarm.py`
- Read: `dharma_swarm/orchestrator.py`
- Read: `dharma_swarm/config.py`

**Step 1: Add a helper for failed-dependency terminality**

Implement a helper that decides whether a failed dependency is still automatically rescuable using live policy values instead of hard-coded thresholds.

**Step 2: Update dependency propagation**

Make `_propagate_dependency_failures()` use the helper and query the extra dependency fields it needs (`result`, `updated_at`).

**Step 3: Add blocked-pending observability**

Expose a blocked-pending count or equivalent runtime signal so the daemon can report `pending` versus `ready` truthfully.

**Step 4: Verify green**

Run: `python3 -m pytest tests/test_orphan_reaper.py tests/test_swarm.py -q`
Expected: dependency-propagation tests pass.

### Task 4: Tighten Timeout Recovery

**Files:**
- Modify: `dharma_swarm/agent_runner.py`
- Modify: `tests/test_agent_runner_semantic_acceptance.py`
- Read: `dharma_swarm/orchestrator.py`

**Step 1: Write a failing timeout-repair test**

Add a test showing a long-running attempt can hand off to the existing same-seat repair path or equivalent bounded retry guidance before terminal failure.

**Step 2: Implement minimal timeout repair**

Keep the change bounded: use existing semantic repair machinery where possible instead of inventing a new topology.

**Step 3: Verify green**

Run: `python3 -m pytest tests/test_agent_runner_semantic_acceptance.py tests/test_orchestrator.py -q`

### Task 5: Extract an Agent Runner Quality Seam

**Files:**
- Create: `dharma_swarm/agent_runner_quality.py`
- Modify: `dharma_swarm/agent_runner.py`
- Modify: `tests/test_agent_runner_semantic_acceptance.py`

**Step 1: Move semantic/honors helpers**

Extract the quality-check helpers into a dedicated module without changing behavior.

**Step 2: Update imports and call sites**

Keep `agent_runner.py` behavior identical while shrinking the hot path.

**Step 3: Verify green**

Run: `python3 -m pytest tests/test_agent_runner_semantic_acceptance.py tests/test_agent_runner.py tests/test_agent_runner_routing_feedback.py -q`

### Task 6: Runtime Maintenance, Restart, and Commit

**Files:**
- Modify: runtime state under `~/.dharma/`
- Commit: current git worktree in a preserved checkpoint plus stabilization commit

**Step 1: Inspect large databases and choose safe compaction targets**

Prefer offline `VACUUM` only after daemon stop for files actively used by the swarm.

**Step 2: Stop the live daemon**

Use the active PID and confirm the process is gone before maintenance.

**Step 3: Compact safe SQLite files**

Run `VACUUM` on the live runtime/task/message DBs only while stopped, then measure size deltas.

**Step 4: Restart the swarm daemon**

Use the project launcher and confirm fresh startup plus `route_next` truthfulness in `~/.dharma/logs/daemon.log`.

**Step 5: Commit**

Create:
- one checkpoint commit preserving the current broad worktree
- one stabilization commit for the new targeted fixes

**Step 6: Final verification**

Run targeted pytest suites and report:
- tests run / passed
- live blocked-pending count
- daemon restart timestamp
- compaction deltas
