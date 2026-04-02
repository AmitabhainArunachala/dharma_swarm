---
title: Substrate Layer Policy
path: docs/plans/2026-04-02-substrate-layer-policy.md
slug: substrate-layer-policy
doc_type: plan
status: active
summary: Defines how foundations, lodestones, and mode_pack should be treated during repo cleanup so conceptual canon, orienting seeds, and operational workflow contracts stop being mixed together.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - foundations/INDEX.md
  - lodestones/README.md
  - mode_pack/README.md
  - docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- software_architecture
- documentation
- operations
- verification
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
  - docs/plans/2026-04-02-cleanup-control-center.md
  - foundations/INDEX.md
  - lodestones/README.md
- mode_pack/README.md
- docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md
- docs/plans/2026-04-02-root-residue-classification.md
improvement:
  room_for_improvement:
  - Add per-directory validation checks once the next cleanup tranche starts moving files across these boundaries.
  - Revisit whether any file inside foundations or lodestones has already matured into architecture or spec truth.
  - Add explicit examples of files that should stay put versus files that should graduate outward.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-substrate-layer-policy.md
  retrieval_terms:
  - substrate
  - policy
  - foundations
  - lodestones
  - mode_pack
  - cleanup
  evergreen_potential: high
stigmergy:
  meaning: This file tells future cleanup runs how to treat the substrate-adjacent directories without collapsing them into one indistinct layer.
  state: active
  semantic_weight: 0.83
  coordination_comment: Use this file before relocating or reclassifying content in foundations, lodestones, or mode_pack.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Substrate Layer Policy

## Purpose

`foundations/`, `lodestones/`, and `mode_pack/` should not be cleaned as if they were one kind of content.

They are three different layers:

- conceptual canon
- orienting substrate
- operational workflow contract

The cleanup program needs to preserve those differences.

## Policy Matrix

| Directory | Role | Authority Type | What It Is Not | Cleanup Posture |
|-----------|------|----------------|----------------|-----------------|
| `foundations/` | conceptual substrate and pillar-level canon | deep conceptual canon | not product doctrine, not generated state, not prompt-bank residue | keep in place, strengthen indexing, do not casually drain into `docs/` |
| `lodestones/` | orienting seeds, reframes, bridges, and attractors | directional / interpretive | not normative product truth, not architecture canon by default | keep in place, index locally, allow selective graduation only when a file clearly matures |
| `mode_pack/` | live workflow and contract layer | operational reference | not philosophy, not archive, not general prose canon | keep in place as a runtime-support surface, not a docs-cleanup casualty |

## Directory-Specific Rules

### `foundations/`

Treat this as the repo's deeper conceptual substrate.

Rules:

- keep the directory intact as its own layer
- prefer better indexing over relocation
- only move a file out if it has clearly become active architecture doctrine or normative spec truth

### `lodestones/`

Treat this as an orienting layer.

Rules:

- allow generative, seed-like, or reframe-heavy material to remain here
- do not force lodestones to sound more canonical than they are
- promote a file outward only when it has clearly hardened into:
  - `foundations/` conceptual canon
  - `docs/architecture/` live architecture doctrine
  - `specs/` normative engineering truth

### `mode_pack/`

Treat this as an operational contract surface.

Rules:

- keep machine-readable and workflow-facing artifacts here
- do not fold it into substrate prose merely because it is small
- evaluate it more like runtime support or operator contract than like philosophy

## Practical Consequence For Cleanup

When a file in these directories looks “odd,” ask:

1. is it conceptual canon?
2. is it orienting or generative?
3. is it an operational contract?

Only after that should you ask whether it needs to move.

This reverses the bad cleanup instinct of deciding by filename vibe or directory size.

## Recommended Next Step

The next safe cleanup move after this policy pass is not a bulk substrate move.

It is a bounded review of the root over-authority candidates:

- `docs/architecture/GENOME_WIRING.md`
- `LIVING_LAYERS.md`
- `docs/architecture/SWARMLENS_MASTER_SPEC.md`

That review should use this substrate policy to decide whether each file belongs in:

- `docs/architecture/`
- `foundations/`
- `lodestones/`
- `specs/`

or should remain where it is for now.
