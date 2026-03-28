# Primary Drivers + Tiny Router Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `Codex + Opus` the canonical sovereign drivers while adding `tiny-router` shadow transition signals ahead of ingress routing and memory capture.

**Architecture:** Add explicit lane-role metadata and canonical priority helpers in `model_hierarchy.py`, then make `provider_policy.py` consume those helpers instead of relying on mixed hardcoded tuples. Add a shadow-only `tiny-router` adapter that emits transition labels into `router_v1` and `conversation_memory` metadata without replacing provider selection.

**Tech Stack:** Python, pytest, existing DGC routing stack, Hugging Face `tgupj/tiny-router` label schema

---

### Task 1: Lock the canonical driver-role contract

**Files:**
- Modify: `dharma_swarm/model_hierarchy.py`
- Test: `tests/test_provider_policy.py`

**Step 1: Write the failing test**

Add an invariant test asserting:
- only the sovereign Opus/Codex lanes are marked primary
- delegated support lists include GLM/Kimi/MiniMax-capable providers
- escalation/tooling priorities start with the sovereign lanes

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_provider_policy.py -q`
Expected: FAIL because the canonical role helpers do not exist yet.

**Step 3: Write minimal implementation**

Add lane-role constants/helpers in `model_hierarchy.py` and rewire `provider_policy.py` to consume them.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_provider_policy.py -q`
Expected: PASS

### Task 2: Add tiny-router shadow inference

**Files:**
- Create: `dharma_swarm/tiny_router_shadow.py`
- Modify: `dharma_swarm/router_v1.py`
- Test: `tests/test_tiny_router_shadow.py`
- Test: `tests/test_router_v1.py`

**Step 1: Write the failing test**

Add tests asserting:
- the shadow adapter emits `relation_to_previous`, `actionability`, `retention`, and `urgency`
- `router_v1.enrich_route_request()` includes those signals in route context

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tiny_router_shadow.py tests/test_router_v1.py -q`
Expected: FAIL because the adapter and enriched metadata do not exist yet.

**Step 3: Write minimal implementation**

Create the adapter with a deterministic shadow classifier and integrate it into `router_v1`.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_tiny_router_shadow.py tests/test_router_v1.py -q`
Expected: PASS

### Task 3: Thread transition signals into memory capture

**Files:**
- Modify: `dharma_swarm/engine/conversation_memory.py`
- Test: `tests/test_conversation_memory.py`

**Step 1: Write the failing test**

Add a test asserting recorded turns persist tiny-router-style transition metadata using prior turn context.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_conversation_memory.py -q`
Expected: FAIL because recorded turn metadata does not include transition labels.

**Step 3: Write minimal implementation**

Compute and persist shadow transition metadata during `record_turn()` without changing harvest semantics.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_conversation_memory.py -q`
Expected: PASS

### Task 4: Verify the combined contract

**Files:**
- Modify: `docs/reports/DGC_DECISION_ONTOLOGY_UPGRADE_2026-03-14.md`
- Test: `tests/test_provider_policy.py`
- Test: `tests/test_thinkodynamic_director.py`

**Step 1: Write the failing test**

Add tests asserting the provider/router contract and director contract agree on the same sovereign/delegated shape.

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_provider_policy.py tests/test_thinkodynamic_director.py -q`
Expected: FAIL if code and doctrine diverge.

**Step 3: Write minimal implementation**

Update doctrine text and any remaining routing defaults needed for consistency.

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_provider_policy.py tests/test_thinkodynamic_director.py -q`
Expected: PASS

### Task 5: Final verification

**Files:**
- Verify: `tests/test_provider_policy.py`
- Verify: `tests/test_router_v1.py`
- Verify: `tests/test_tiny_router_shadow.py`
- Verify: `tests/test_conversation_memory.py`
- Verify: `tests/test_thinkodynamic_director.py`

**Step 1: Run targeted suite**

Run: `pytest tests/test_provider_policy.py tests/test_router_v1.py tests/test_tiny_router_shadow.py tests/test_conversation_memory.py tests/test_thinkodynamic_director.py -q`

**Step 2: Fix regressions until green**

Keep edits minimal and local to routing/memory canon.

**Step 3: Summarize remaining drift**

Capture any residual old-model defaults or routing surfaces that still need cleanup.
