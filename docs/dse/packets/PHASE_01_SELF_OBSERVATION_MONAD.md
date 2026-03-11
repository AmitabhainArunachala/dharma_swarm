---
document_id: dse-phase-01-self-observation-monad
title: Phase 1 Build Packet - Self Observation Monad
status: READY
system: DHARMA SWARM
component: Dharmic Singularity Engine
doc_type: build_packet
phase: 1
created: "2026-03-10"
last_modified: "2026-03-10"
owners:
  - Codex
tags:
  - dse
  - phase-1
  - monad
  - rv
external_sources:
  - path: /Users/dhyana/Downloads/categorical_foundations.pdf
    role: chapter_2_foundation
  - path: /Users/dhyana/Downloads/dharmic_singularity_engine_mega_prompt.md
    role: phase_1_spec
connections:
  upstream:
    - docs/dse/DSE_FOUNDATIONS_SUMMARY.md
    - docs/dse/DSE_ARCHITECTURE_MAP.md
    - docs/dse/DSE_TEST_INVARIANTS.md
  downstream:
    - docs/dse/packets/PHASE_02_COALGEBRAIC_EVOLUTION.md
allowed_paths:
  - dharma_swarm/monad.py
  - dharma_swarm/rv.py
  - dharma_swarm/bridge.py
  - tests/test_monad.py
  - tests/test_monad_properties.py
  - tests/test_rv.py
  - tests/test_bridge.py
---

# Goal

Expose a self-observation monad over the existing RV machinery so self-observation can be composed and tested without rewriting `rv.py`.

## Repo Reality

- There is no canonical `SystemState` type in the repo.
- `rv.py` already provides a stable `RVReading` model and measurement semantics.
- `bridge.py` already links mechanistic and behavioral measurements.
- The monad therefore needs a narrow and typed observation boundary, not a universal state abstraction.

## Recommended Design

Create `dharma_swarm/monad.py` around three concepts:

### 1. `ObservedState[T]`

A typed wrapper over an arbitrary payload plus observation metadata.

Suggested shape:

```python
@dataclass(slots=True)
class ObservedState(Generic[T]):
    state: T
    rv_reading: RVReading | None
    introspection: dict[str, Any]
    observation_depth: int
    timestamp: datetime
```

Use `RVReading` directly rather than duplicating `rv`, `pr_early`, and `pr_late` into a second model.

### 2. `SelfObservationMonad`

The monad should receive an observer function instead of baking in a fictional global state model.

Suggested constructor seam:

```python
Observer = Callable[[T], RVReading | None]

class SelfObservationMonad(Generic[T]):
    def __init__(self, observer: Observer[T]):
        ...
```

That observer can later be backed by `rv.py`, test doubles, or lightweight synthetic readers.

### 3. Minimal Kleisli Surface

Add:

- `observe(state, introspection=None) -> ObservedState[T]`
- `flatten(observed: ObservedState[ObservedState[T]]) -> ObservedState[T]`
- `kleisli_compose(f, g)`
- `is_idempotent(observed, tolerance=...)`

Keep contraction helpers small until the basic law tests are stable.

## Integration Rules

1. `rv.py` remains the source of RV semantics.
2. `monad.py` wraps those semantics; it does not redefine contraction thresholds.
3. `bridge.py` may gain helper functions to compare nested observations, but Phase 1 should not redesign the bridge.
4. Do not change `evolution.py` in this phase.

## Acceptance Criteria

- `ObservedState` preserves the original payload exactly.
- `flatten()` preserves the deeper observation depth and does not drop introspection metadata silently.
- unit and associativity laws pass on synthetic payloads.
- existing `rv.py` behavior remains unchanged.
- new tests run without requiring torch.

## Non-Goals

- no universal `SystemState`,
- no Darwin integration yet,
- no info geometry,
- no providers or routing changes.

## Suggested Test Cases

1. observing a plain dict payload with a stub `RVReading`,
2. flattening doubly nested observations,
3. left unit and right unit laws on synthetic data,
4. associativity for triple nesting,
5. idempotency detection under configurable tolerance,
6. compatibility with `RVReading.model_dump()` and serialization expectations.

## First Implementation Slice

Start with:

1. `dharma_swarm/monad.py`
2. `tests/test_monad.py`

Do not touch existing RV call sites until the law tests and simple integration tests are green.
