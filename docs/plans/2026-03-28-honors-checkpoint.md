# Honors Checkpoint Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a contract-driven honors checkpoint so analytical completions must defend themselves with evidence, auditability, and system awareness before the orchestrator accepts them.

**Architecture:** Keep one execution lane. Add canonical contract and checkpoint models in the mission-contract layer, inject the contract into the runner prompt, generate a defense packet and judge pack inside `AgentRunner`, and enforce the final verdict again inside `Orchestrator`.

**Tech Stack:** Python 3, pydantic, pytest, existing agent runner and orchestrator paths

---

### Task 1: Lock contract and checkpoint tests

**Files:**
- Modify: `tests/test_mission_contract.py`
- Modify: `tests/test_agent_runner_semantic_acceptance.py`
- Modify: `tests/test_orchestrator.py`

**Step 1: Write the failing test**

Add coverage for:
- honors contract parsing and normalization from task metadata
- runner rejecting an answer that is semantically valid but fails the honors checkpoint
- runner persisting a defense packet and judge pack on success
- orchestrator refusing to mark a task completed when a runner returns a result without a passing honors checkpoint

**Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_mission_contract.py tests/test_agent_runner_semantic_acceptance.py tests/test_orchestrator.py -q`
Expected: FAIL on the new honors-checkpoint assertions.

### Task 2: Add canonical honors-checkpoint models

**Files:**
- Modify: `dharma_swarm/mission_contract.py`

**Step 1: Write minimal implementation**

Add:
- `CompletionContract`
- `DefensePacket`
- `JudgeGate`
- `JudgePack`
- `HonorsCheckpoint`
- helpers to read/write a contract from task metadata and validate a stored checkpoint

**Step 2: Run focused tests**

Run: `python3 -m pytest tests/test_mission_contract.py -q`
Expected: PASS.

### Task 3: Inject the contract and generate the checkpoint

**Files:**
- Modify: `dharma_swarm/agent_runner.py`

**Step 1: Write minimal implementation**

Implement:
- contract prompt injection in `_build_prompt()`
- honors checkpoint evaluation after semantic acceptance
- repair-loop reuse when the honors checkpoint fails
- persistence of the accepted checkpoint onto `task.metadata`

**Step 2: Run focused tests**

Run: `python3 -m pytest tests/test_agent_runner_semantic_acceptance.py -q`
Expected: PASS.

### Task 4: Enforce the checkpoint in the orchestrator

**Files:**
- Modify: `dharma_swarm/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

**Step 1: Write minimal implementation**

Implement:
- fail-closed completion verification when a task declares a contract
- metadata persistence of checkpoint score summary on successful completion

**Step 2: Run focused tests**

Run: `python3 -m pytest tests/test_orchestrator.py -q`
Expected: PASS.

### Task 5: Verify the slice end to end

**Files:**
- None

**Step 1: Run final verification**

Run: `python3 -m pytest tests/test_mission_contract.py tests/test_agent_runner_semantic_acceptance.py tests/test_orchestrator.py -q`
Expected: PASS.
