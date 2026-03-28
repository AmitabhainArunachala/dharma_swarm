# Self-Evolving Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** establish corrected architecture seams for self-evolving integrations and land the first isolated building blocks safely.

**Architecture:** start with pure, low-collision modules: canonical export adapters and runtime field tracking. Keep conversion separate from installation, and keep runtime mutation separate from Darwin core until later phases.

**Tech Stack:** Python 3, stdlib dataclasses/enums/pathlib, pytest

---

### Task 1: Replace the ad hoc spec with a corrected RFC

**Files:**
- Modify: `spec-forge/consciousness-computing/INTEGRATION_SPEC.md`
- Create: `docs/plans/2026-03-26-self-evolving-integration-design.md`

**Step 1: Rewrite the existing integration spec**

Describe the architecture in terms of layers:
- canonical schema/export adapters
- runtime field registry
- causal credit engine
- topology genome
- curriculum engine
- separate offline training lane

**Step 2: Save the approved design**

Save the final design into `docs/plans/2026-03-26-self-evolving-integration-design.md`.

**Step 3: Verify references are correct**

Check that local repo paths and claims match the cloned repos.

### Task 2: Add runtime field tracking substrate

**Files:**
- Create: `dharma_swarm/runtime_fields.py`
- Test: `tests/test_runtime_fields.py`

**Step 1: Write the failing tests**

Cover:
- plain attribute tracking
- nested path tracking through dict/list access
- per-field reset
- full registry reset
- batch registration

**Step 2: Implement the minimal registry**

Add:
- `OptimizableField`
- `RuntimeFieldRegistry`
- snapshot/reset behavior
- nested path tracking

**Step 3: Run the targeted tests**

Run: `pytest tests/test_runtime_fields.py -q`

Expected: PASS

### Task 3: Add canonical export adapters

**Files:**
- Create: `dharma_swarm/agent_export.py`
- Test: `tests/test_agent_export.py`

**Step 1: Write the failing tests**

Cover:
- raw markdown export for Claude Code/Copilot/Qwen
- OpenCode export formatting
- Cursor rule formatting
- color normalization
- relative artifact paths

**Step 2: Implement the minimal export layer**

Add:
- `CanonicalAgentSpec`
- `ExportTarget`
- `ExportArtifact`
- pure render functions only

**Step 3: Run the targeted tests**

Run: `pytest tests/test_agent_export.py -q`

Expected: PASS

### Task 4: Verify the slice

**Files:**
- Test: `tests/test_runtime_fields.py`
- Test: `tests/test_agent_export.py`

**Step 1: Run both test modules together**

Run: `pytest tests/test_runtime_fields.py tests/test_agent_export.py -q`

Expected: PASS

**Step 2: Summarize the next integration seam**

State that the next safe step is wiring `RuntimeFieldRegistry` into runtime startup and defining the `CausalCreditEngine` artifact boundary.
