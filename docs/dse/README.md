---
document_id: dse-program-index
title: Dharmic Singularity Engine Program Index
status: ACTIVE
system: DHARMA SWARM
component: Dharmic Singularity Engine
doc_type: program_index
created: "2026-03-10"
last_modified: "2026-03-10"
owners:
  - Codex
tags:
  - dse
  - category-theory
  - evolution
  - architecture
external_sources:
  - path: /Users/dhyana/Downloads/categorical_foundations.pdf
    role: mathematical_foundation
  - path: /Users/dhyana/Downloads/dharmic_singularity_engine_mega_prompt.md
    role: implementation_brief
connections:
  upstream:
    - /Users/dhyana/Downloads/categorical_foundations.pdf
    - /Users/dhyana/Downloads/dharmic_singularity_engine_mega_prompt.md
  downstream:
    - docs/dse/DSE_FOUNDATIONS_SUMMARY.md
    - docs/dse/DSE_ARCHITECTURE_MAP.md
    - docs/dse/DSE_PHASE_ROADMAP.md
    - docs/dse/DSE_TEST_INVARIANTS.md
    - docs/dse/packets/PHASE_01_SELF_OBSERVATION_MONAD.md
    - docs/dse/packets/PHASE_02_COALGEBRAIC_EVOLUTION.md
    - docs/dse/packets/PHASE_03_INFORMATION_GEOMETRY.md
    - docs/dse/packets/PHASE_04_SHEAF_COORDINATION.md
---

# Dharmic Singularity Engine

This directory is the working spec stack for the Dharmic Singularity Engine inside `dharma_swarm`.

## Why This Lives Here

The two source documents are broad and useful, but too large to serve as the day-to-day execution surface for coding agents. The repo needs a narrower stack that:

1. preserves the source-of-truth links,
2. records current code seams in `dharma_swarm/`,
3. breaks the work into bounded implementation packets.

That is what `docs/dse/` is for.

## Authority Order

Use documents in this order when building:

1. `/Users/dhyana/Downloads/categorical_foundations.pdf`
2. `/Users/dhyana/Downloads/dharmic_singularity_engine_mega_prompt.md`
3. `docs/dse/README.md`
4. the specific packet for the phase being implemented
5. current repo code and tests

If the mega prompt and the repo disagree, prefer a wrapper or adapter over a rewrite unless the packet explicitly calls for a deeper refactor.

## Directory Map

- `docs/dse/DSE_FOUNDATIONS_SUMMARY.md`
  Distills the PDF into implementation-facing principles.
- `docs/dse/DSE_ARCHITECTURE_MAP.md`
  Maps the theory and the mega prompt onto the real modules in this repo.
- `docs/dse/DSE_PHASE_ROADMAP.md`
  Gives the recommended execution order across phases 1-7.
- `docs/dse/DSE_TEST_INVARIANTS.md`
  Records the algebraic, behavioral, and compatibility invariants.
- `docs/dse/packets/PHASE_01_SELF_OBSERVATION_MONAD.md`
  First concrete build packet.
- `docs/dse/packets/PHASE_02_COALGEBRAIC_EVOLUTION.md`
  Second concrete build packet.
- `docs/dse/packets/PHASE_03_INFORMATION_GEOMETRY.md`
  Third concrete build packet.
- `docs/dse/packets/PHASE_04_SHEAF_COORDINATION.md`
  Fourth concrete build packet.

## Agent Loading Protocol

For an implementation agent:

1. Read this file.
2. Read `DSE_FOUNDATIONS_SUMMARY.md`.
3. Read `DSE_ARCHITECTURE_MAP.md`.
4. Read only the phase packet you are implementing.
5. Inspect the actual code paths named in that packet before editing.

Do not load the entire PDF and the entire mega prompt into every working turn unless the task is conceptual rather than implementation-focused.

## Current Starting Slice

The first slices are now in place:

- Phase 1: `dharma_swarm/monad.py`
- Phase 2: `dharma_swarm/coalgebra.py`
- Phase 3: `dharma_swarm/info_geometry.py` plus `MetaEvolutionEngine` natural-gradient adapters
- Phase 4: `dharma_swarm/sheaf.py` with message-derived sites and Anekanta-backed obstruction tracking

The initial framing remains the same:

- there is no canonical `SystemState` type yet,
- `rv.py` already has a stable `RVReading` model,
- `bridge.py` already connects mechanistic and behavioral observation,
- `evolution.py` is much larger than the mega prompt assumes and should be wrapped, not rewritten, in early passes.

The practical opening move is therefore:

1. define a minimal self-observation abstraction,
2. keep `rv.py` as the measurement engine,
3. add tests for monad laws around synthetic observations before touching Darwin orchestration.
