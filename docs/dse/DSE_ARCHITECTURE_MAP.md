---
document_id: dse-architecture-map
title: Dharmic Singularity Engine Architecture Map
status: ACTIVE
system: DHARMA SWARM
component: Dharmic Singularity Engine
doc_type: architecture_map
created: "2026-03-10"
last_modified: "2026-03-10"
owners:
  - Codex
tags:
  - dse
  - architecture
  - integration
external_sources:
  - path: /Users/dhyana/Downloads/dharmic_singularity_engine_mega_prompt.md
    role: target_architecture
connections:
  upstream:
    - docs/dse/DSE_FOUNDATIONS_SUMMARY.md
  peers:
    - docs/dse/DSE_PHASE_ROADMAP.md
    - docs/dse/DSE_TEST_INVARIANTS.md
  downstream:
    - docs/dse/packets/PHASE_01_SELF_OBSERVATION_MONAD.md
    - docs/dse/packets/PHASE_02_COALGEBRAIC_EVOLUTION.md
    - docs/dse/packets/PHASE_03_INFORMATION_GEOMETRY.md
    - docs/dse/packets/PHASE_04_SHEAF_COORDINATION.md
---

# Architecture Map

This file maps the Dharmic Singularity Engine concept onto the current `dharma_swarm` codebase. The mega prompt's file sizes are stale; the table below reflects the repo as of March 10, 2026.

## Existing Modules

| Module | Current Size | Current Role | Target DSE Role | Early Strategy |
|---|---:|---|---|---|
| `dharma_swarm/rv.py` | 426 | R_V measurement, reading model, correlator support | measurement engine inside the self-observation monad | wrap, do not replace |
| `dharma_swarm/evolution.py` | 1896 | Darwin orchestration, proposal lifecycle, drift review | internal substrate for coalgebraic stepping | adapt via wrapper |
| `dharma_swarm/archive.py` | 509 | lineage, fitness, archive persistence | carrier of trajectory observations and promotion state | extend compatibly |
| `dharma_swarm/elegance.py` | 345 | code elegance scoring | fitness projection inside coalgebra observations | reuse |
| `dharma_swarm/metrics.py` | 410 | behavioral signatures | observation manifold features and bridge inputs | reuse |
| `dharma_swarm/bridge.py` | 583 | RV to behavior correlation | naturality/consistency seam between mechanistic and behavioral signals | extend lightly |
| `dharma_swarm/monitor.py` | 510 | anomaly detection | source for drift and instability signals | reuse |
| `dharma_swarm/telos_gates.py` | 586 | dharmic gate checks | invariant-preserving transition filter | preserve |
| `dharma_swarm/selector.py` | 241 | parent selection | selection morphism inside evolution wrapper | reuse |
| `dharma_swarm/fitness_predictor.py` | 243 | predictive scoring | meta-evolution input surface | reuse |
| `dharma_swarm/providers.py` | 1519 | provider routing and policy surface | later target for paradigm/topos phases, not Phase 1 | leave alone for now |

## New Modules Proposed by the Mega Prompt

| Proposed Module | Purpose | Recommended Delivery Mode |
|---|---|---|
| `dharma_swarm/monad.py` | self-observation monad over current RV machinery | implement first |
| `dharma_swarm/coalgebra.py` | observation wrapper over Darwin evolution | implement second |
| `dharma_swarm/info_geometry.py` | geometric meta-evolution | implemented as a stdlib-first adapter over `MetaParameters` and `meta_evolution.py` |
| `dharma_swarm/sheaf.py` | multi-agent consistency and obstruction tracking | implemented over `AgentState`, `Message`, and `anekanta_gate` |
| `dharma_swarm/godel_engine.py` | controlled paradigm shifts | defer until policy/context boundaries are explicit |
| `dharma_swarm/adjunction.py` | typed inter-layer composition | defer until earlier structures exist |

## Critical Repo Reality Gaps

### 1. No Canonical `SystemState`

The mega prompt assumes a single `SystemState`. The repo does not currently define one. Early DSE work should therefore use typed wrappers over existing values:

- `RVReading`
- `Proposal`
- `ArchiveEntry`
- serializable mappings or typed snapshots

Do not invent a giant universal state object in Phase 1.

### 2. `evolution.py` Is Already Rich and Large

The mega prompt describes a 447-line `evolution.py`. The real file is 1896 lines and already contains retrospective and drift logic. The correct move is an adapter layer, not a ground-up refactor.

### 3. Behavior Already Matters

The repo already contains a mechanistic-to-behavior bridge. That makes the DSE framing stronger, because it can build on an existing observational seam instead of introducing one from scratch.

## Recommended Layering

```text
rv.py
  -> monad.py
     -> coalgebra.py
        -> info_geometry.py
        -> sheaf.py
        -> godel_engine.py
           -> adjunction.py
```

This keeps the later layers dependent on explicit interfaces rather than directly on the internal structure of `evolution.py`.

## File Boundary Guidance

For the next implementation passes:

- Phase 1 should stay close to `rv.py`, `bridge.py`, and new tests.
- Phase 2 should wrap `evolution.py` and touch archive types only where needed for observation surfaces.
- `providers.py` should remain out of scope until a later phase explicitly targets paradigm or routing abstractions.
