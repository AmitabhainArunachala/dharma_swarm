---
document_id: dse-phase-03-information-geometry
title: Phase 3 Build Packet - Information Geometry
status: READY
system: DHARMA SWARM
component: Dharmic Singularity Engine
doc_type: build_packet
phase: 3
created: "2026-03-10"
last_modified: "2026-03-10"
owners:
  - Codex
tags:
  - dse
  - phase-3
  - information-geometry
  - meta-evolution
external_sources:
  - path: /Users/dhyana/Downloads/categorical_foundations.pdf
    role: chapter_5_foundation
  - path: /Users/dhyana/Downloads/dharmic_singularity_engine_mega_prompt.md
    role: phase_3_spec
connections:
  upstream:
    - docs/dse/DSE_FOUNDATIONS_SUMMARY.md
    - docs/dse/DSE_ARCHITECTURE_MAP.md
    - docs/dse/DSE_TEST_INVARIANTS.md
    - docs/dse/packets/PHASE_02_COALGEBRAIC_EVOLUTION.md
allowed_paths:
  - dharma_swarm/info_geometry.py
  - dharma_swarm/meta_evolution.py
  - tests/test_info_geometry.py
---

# Goal

Add a practical information-geometry layer for Darwin meta-evolution without forcing a new heavyweight numerical dependency or rewriting the existing meta-evolution engine.

## Repo Reality

- `meta_evolution.py` already adapts Darwin hyperparameters through bounded mutation and crossover.
- The project does not declare `numpy` as a required runtime dependency.
- The best first move is therefore a stdlib-first geometry module plus adapters around `MetaParameters`.

## Recommended Design

Create `dharma_swarm/info_geometry.py` with:

1. `StatisticalManifold`
   Provides Fisher-style metric, geodesic distance, and KL divergence over finite parameter vectors.

2. `NaturalGradientOptimizer`
   Produces natural-gradient directions and one-step updates over those vectors.

3. `DharmicAttractor`
   Encodes a first-pass "pull toward dharma" as constraint-aware pressure rather than as a hard rewrite of Darwin behavior.

4. Meta-parameter adapters
   Convert `MetaParameters` to and from a geometry-friendly vector surface.

## Integration Rules

1. Keep the first implementation stdlib-only.
2. Do not rewrite `meta_evolution.py`; adapt around it.
3. Preserve normalized fitness weights on any roundtrip through the manifold.
4. Any dharmic pressure term must be additive and optional, not silently hard-coded into Darwin.

## Acceptance Criteria

- Fisher metric is positive definite on sampled vectors,
- geodesic distance is symmetric and zero on identical points,
- KL divergence is non-negative,
- natural-gradient steps can be applied to `MetaParameters` without breaking normalization,
- covariance-collapse helper reports sensible participation-ratio behavior for identity and rank-1 matrices.
