# Coalgebra DSEIntegrator DSE Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add the missing `dharma_swarm/coalgebra_dseintegrator_dse_integration.py` bridge so the coalgebra-facing DSE integration surface exists, is importable, and is backed by focused tests and a cluster spec.

**Architecture:** Keep the module thin. Re-export the canonical runtime types from `dharma_swarm.dse_integration`, add one small coalgebra-focused artifact builder that summarizes the monad/coalgebra/sheaf seam without duplicating integrator logic, and document the contract in a cluster spec.

**Tech Stack:** Python 3, Pydantic, pytest, existing `dharma_swarm.coalgebra` and `dharma_swarm.dse_integration` modules

---

### Task 1: Red test for the missing bridge

**Files:**
- Create: `tests/test_coalgebra_dseintegrator_dse_integration.py`
- Test: `tests/test_coalgebra_dseintegrator_dse_integration.py`

**Step 1: Write the failing test**

```python
from dharma_swarm.coalgebra_dseintegrator_dse_integration import (
    DSECycleBridge,
    build_dse_cycle_bridge,
)
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_coalgebra_dseintegrator_dse_integration.py -q`
Expected: FAIL with `ModuleNotFoundError` for `dharma_swarm.coalgebra_dseintegrator_dse_integration`

### Task 2: Minimal implementation

**Files:**
- Create: `dharma_swarm/coalgebra_dseintegrator_dse_integration.py`
- Modify: `docs/clusters/coalgebra_dseintegrator_dse_integration_spec.md`
- Test: `tests/test_coalgebra_dseintegrator_dse_integration.py`

**Step 1: Write minimal implementation**

```python
class DSECycleBridge(BaseModel):
    ...

def build_dse_cycle_bridge(...):
    ...
```

The implementation should:
- re-export `CoordinationSnapshot`, `DSEIntegrator`, and `ObservationWindow`
- normalize an `EvolutionObservation` plus optional coordination snapshot/context
- derive booleans for monadic observation, coordination availability, and fixed-point pressure

**Step 2: Run tests to verify they pass**

Run: `pytest tests/test_coalgebra_dseintegrator_dse_integration.py -q`
Expected: PASS

### Task 3: Archive and verify

**Files:**
- Create: `/Users/dhyana/.dharma/shared/coalgebra_dseintegrator_dse_integration_artifact_2026-03-20.md`

**Step 1: Write the shared-ledger artifact**

Record:
- artifact paths
- exact pytest command
- concrete observed result
- cluster-thesis summary

**Step 2: Final verification**

Run: `git diff -- dharma_swarm/coalgebra_dseintegrator_dse_integration.py docs/clusters/coalgebra_dseintegrator_dse_integration_spec.md tests/test_coalgebra_dseintegrator_dse_integration.py docs/plans/2026-03-20-coalgebra-dseintegrator-dse-integration.md`
Expected: only the intended bridge/spec/test/plan changes
