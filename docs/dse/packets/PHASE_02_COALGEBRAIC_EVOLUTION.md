---
document_id: dse-phase-02-coalgebraic-evolution
title: Phase 2 Build Packet - Coalgebraic Evolution
status: READY
system: DHARMA SWARM
component: Dharmic Singularity Engine
doc_type: build_packet
phase: 2
created: "2026-03-10"
last_modified: "2026-03-10"
owners:
  - Codex
tags:
  - dse
  - phase-2
  - coalgebra
  - evolution
external_sources:
  - path: /Users/dhyana/Downloads/categorical_foundations.pdf
    role: chapter_4_foundation
  - path: /Users/dhyana/Downloads/dharmic_singularity_engine_mega_prompt.md
    role: phase_2_spec
connections:
  upstream:
    - docs/dse/DSE_FOUNDATIONS_SUMMARY.md
    - docs/dse/DSE_ARCHITECTURE_MAP.md
    - docs/dse/DSE_TEST_INVARIANTS.md
    - docs/dse/packets/PHASE_01_SELF_OBSERVATION_MONAD.md
allowed_paths:
  - dharma_swarm/coalgebra.py
  - dharma_swarm/evolution.py
  - dharma_swarm/archive.py
  - dharma_swarm/monad.py
  - tests/test_coalgebra.py
  - tests/test_evolution.py
---

# Goal

Wrap the existing Darwin engine in an explicit observation interface so one evolution step can be treated as an observable coalgebra map without rewriting the existing orchestration loop.

## Repo Reality

- `evolution.py` is already 1896 lines and contains much more behavior than the mega prompt assumes.
- `archive.py` already defines `ArchiveEntry` and `FitnessScore`.
- `evolution.py` already integrates gates, testing, archive writes, selectors, and route retrospectives.

The correct first coalgebra pass is therefore an adapter over `DarwinEngine`, not a deep internal refactor.

## Recommended Design

Create `dharma_swarm/coalgebra.py` with:

### 1. `EvolutionObservation`

Prefer a typed observation model that mirrors existing repo types:

```python
class EvolutionObservation(BaseModel):
    next_state: dict[str, Any] | Proposal | ArchiveEntry
    fitness: FitnessScore | float
    rv: RVReading | None
    discoveries: list[str]
    archive_entry_id: str | None = None
```

Use typed compatibility with `ArchiveEntry` and `FitnessScore` rather than reducing everything to plain floats too early.

### 2. `EvolutionCoalgebra`

This should wrap an existing `DarwinEngine` instance and expose:

- `step(...) -> EvolutionObservation`
- `trajectory(initial, n) -> Iterator[EvolutionObservation]`

In the first pass, the "state" can be a narrow state reference such as:

- proposal description plus component path,
- archived parent identifier,
- or a typed snapshot of Darwin inputs.

Do not force a universal state model yet.

### 3. Bisimulation

Implement bisimulation over normalized observations:

- fitness projection,
- RV projection,
- discoveries projection,
- gate/archive outcome projection when relevant.

Compare behavior, not object identity.

## Integration Rules

1. `DarwinEngine` remains the execution substrate.
2. `coalgebra.py` must not bypass gates, archive writes, or selectors.
3. The monad-coalgebra distributive law should be deferred until Phase 1 is implemented and stable.
4. Any archive extensions must remain backward compatible with existing JSONL records.

## Acceptance Criteria

- one wrapper call yields one explicit observation object,
- observations can be generated repeatedly as a trajectory,
- bisimulation tests compare observation streams, not engine internals,
- existing Darwin tests continue to pass unless a deliberate change is documented,
- any new archive metadata has defaults and round-trips cleanly.

## Non-Goals

- no rewrite of `evolution.py`,
- no speculative final coalgebra machinery,
- no provider-routing changes,
- no multi-agent sheaf logic yet.

## Suggested Test Cases

1. wrap a deterministic Darwin stub and emit stable observations,
2. compare two coalgebras with equivalent observation streams,
3. verify archive linkage survives wrapping,
4. verify gates still influence which observations are emitted,
5. verify trajectories are reproducible under fixed inputs.

## First Implementation Slice

Start with:

1. `dharma_swarm/coalgebra.py`
2. `tests/test_coalgebra.py`

Only after the wrapper works should any internal extraction from `evolution.py` be considered.
