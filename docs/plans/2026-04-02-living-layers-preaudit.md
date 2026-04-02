---
title: Living Layers Preaudit
path: docs/plans/2026-04-02-living-layers-preaudit.md
slug: living-layers-preaudit
doc_type: plan
status: active
summary: Records why LIVING_LAYERS.md is still a hard root-move case and what must be decided before it can safely leave root.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - LIVING_LAYERS.md
  - docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md
  - docs/plans/2026-04-02-root-future-move-preaudit.md
  - docs/plans/2026-03-28-constitutional-substrate-12-week-plan.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- software_architecture
- documentation
- verification
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
  - docs/plans/2026-04-02-cleanup-control-center.md
  - LIVING_LAYERS.md
  - docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md
  - docs/plans/2026-04-02-root-future-move-preaudit.md
- docs/plans/2026-04-02-substrate-layer-policy.md
- docs/EVOLUTION_PROPOSAL_FLICKER_LOG_INTEGRATION.md
- docs/plans/2026-03-28-constitutional-substrate-12-week-plan.md
improvement:
  room_for_improvement:
  - Count live backlinks more precisely before any move.
  - Decide whether the right solution is relocation or file-splitting.
  - Separate implementation-facing sections from substrate-facing sections if the file is doing two jobs at once.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-living-layers-preaudit.md
  retrieval_terms:
  - living layers
  - preaudit
  - root
  - architecture
  - substrate
  - split
  evergreen_potential: medium
stigmergy:
  meaning: This file captures the unresolved classification logic for LIVING_LAYERS.md so later cleanup does not flatten a genuinely mixed document into the wrong subtree.
  state: active
  semantic_weight: 0.82
  coordination_comment: Use this file before moving or splitting LIVING_LAYERS.md.
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
# Living Layers Preaudit

## Why This File Is Different

`LIVING_LAYERS.md` is not just another root file with the wrong location.

It currently does three things at once:

- explains implementation-facing runtime layers such as `stigmergy.py`
- frames those layers through deeper witness / dynamic-system language
- acts as a conceptual bridge between architecture and substrate

That mixed role is why it still resists a clean relocation.

## Current Signal

- tracked at root
- `doc_type: note`
- `status: active`
- described elsewhere in cleanup doctrine as architecture truth whose root placement inflates authority
- referenced by architecture-facing and substrate-adjacent planning docs

## Destination Tension

### Option 1: Move To `docs/architecture/`

Pros:

- much of the file is implementation-facing
- it discusses concrete runtime modules and mechanics
- this would reduce root over-authority immediately

Cons:

- the file still carries substrate-level framing, not just architecture notes
- moving it whole may disguise that conceptual layer instead of resolving it

### Option 2: Treat As Substrate

Pros:

- the witness / gnani / prakruti framing has real substrate character
- it sits conceptually closer to the foundational and lodestone layers than a narrow subsystem note does

Cons:

- too much of the file is still concretely about runtime architecture
- substrate placement would understate the implementation-facing role it currently plays

### Option 3: Split Later

Pros:

- best matches the evidence if the file is genuinely doing two jobs
- allows one architecture-local document and one substrate-facing companion

Cons:

- higher blast radius than a simple move
- requires real editorial judgment, not just filing discipline

## Current Best Read

The safest truthful answer is:

- do not move `LIVING_LAYERS.md` yet
- treat it as the main unresolved mixed root file
- revisit it after the root and substrate policies have settled downstream expectations

If forced into a single destination today, `docs/architecture/` is the stronger fit, but that would still be a compromise rather than a clean semantic match.

## What Must Be True Before A Move

1. the live backlink surface is enumerated
2. the architecture-vs-substrate decision is made explicitly
3. we decide whether to relocate whole or split

Until then, the right action is disciplined deferral, not opportunistic filing.
