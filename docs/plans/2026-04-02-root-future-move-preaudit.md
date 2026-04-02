---
title: Root Future-Move Preaudit
path: docs/plans/2026-04-02-root-future-move-preaudit.md
slug: root-future-move-preaudit
doc_type: plan
status: active
summary: Preserves the destination logic for root over-authority candidates and reflects that GENOME_WIRING and SWARMLENS have already left root while LIVING_LAYERS remains unresolved but is deferred because live backlinks make a move unsafe.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/architecture/GENOME_WIRING.md
  - LIVING_LAYERS.md
  - docs/architecture/SWARMLENS_MASTER_SPEC.md
  - docs/plans/2026-04-02-root-residue-classification.md
  - docs/plans/2026-04-02-substrate-layer-policy.md
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
  - docs/architecture/GENOME_WIRING.md
  - LIVING_LAYERS.md
  - docs/architecture/SWARMLENS_MASTER_SPEC.md
- docs/plans/2026-04-02-root-residue-classification.md
- docs/plans/2026-04-02-substrate-layer-policy.md
- docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md
improvement:
  room_for_improvement:
  - Add exact backlink counts before any relocation tranche begins.
  - Decide whether any code or runtime tooling treats these root paths as hard requirements.
  - Record a destination decision only when the destination subtree owner is clear.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-root-future-move-preaudit.md
  retrieval_terms:
  - root
  - move
  - preaudit
  - genome wiring
  - living layers
  - swarmlens
  evergreen_potential: medium
stigmergy:
  meaning: This file preserves the destination logic for the next root move tranche so cleanup can proceed with evidence and low blast radius.
  state: active
  semantic_weight: 0.8
  coordination_comment: Use this file before moving any of the remaining high-authority root prose candidates.
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
# Root Future-Move Preaudit

## Purpose

This pass now records the state of the former three-file tranche:

- `docs/architecture/GENOME_WIRING.md` has already left root
- `docs/architecture/SWARMLENS_MASTER_SPEC.md` has already left root
- `LIVING_LAYERS.md` remains the main unresolved root over-authority file, but it is currently deferred rather than queued for relocation

The purpose is now to preserve destination logic and blockers without pretending the earlier state still exists.

## Decision Table

| File | Current character | Likely destination | Why not move yet |
|------|-------------------|-------------------|------------------|
| `docs/architecture/GENOME_WIRING.md` | architecture/system wiring note with runtime coupling | `docs/architecture/` | moved out of root, but still needs backlink and canon-scope review |
| `LIVING_LAYERS.md` | conceptual architecture note with substrate overlap | `docs/architecture/` or `foundations/` | mixes implementation-layer discussion with deeper substrate framing, and live backlinks make any move unsafe right now |
| `docs/architecture/SWARMLENS_MASTER_SPEC.md` | product/spec artifact with strong spec character | `docs/architecture/` for now, possibly `specs/` later if it becomes normative | moved out of root, but still needs a judgment about whether it is normative current truth or advisory product strategy |

## File-Specific Read

### `docs/architecture/GENOME_WIRING.md`

Current signal:

- `doc_type: note`
- `status: active`
- reads like a system-wiring and runtime-parameter note rather than a root entrypoint
- already treated by repo hygiene docs as “architecture truth or active spec”

Assessment:

- strongest current fit is `docs/architecture/`
- not substrate in the same sense as `foundations/` or `lodestones/`
- root location gives it more general authority than it likely deserves

### `LIVING_LAYERS.md`

Current signal:

- `doc_type: note`
- `status: active`
- content mixes implementation details from `dharma_swarm/*` with a deeper conceptual framing about witness, stigmergy, and dynamic layers

Assessment:

- the file has one foot in architecture and one foot in substrate
- that makes it a poor candidate for a quick move
- the live backlink surface is broad enough that relocation is unsafe for a generic cleanup tranche
- the current best decision is to defer the move rather than force a destination
- it likely needs either:
  - a dedicated backlink-repair tranche toward `docs/architecture/`, or
  - later splitting if it is doing two jobs at once

### `docs/architecture/SWARMLENS_MASTER_SPEC.md`

Current signal:

- `doc_type: spec`
- `status: active`
- clearly product/spec shaped rather than root bootstrap shaped
- already described in cleanup doctrine as an advisory or product/spec artifact rather than root bootstrap truth

Assessment:

- likely belongs in `specs/` if it is still normative
- likely belongs in `docs/` if it is more strategic/product-facing than contract-like
- not a good root file regardless

## Practical Rule For The Later Move

Do not move architecture-adjacent files together just because they used to live at root.

Move only when:

1. the destination is individually clear
2. the live backlink surface is enumerated
3. the move does not create another ambiguous class boundary

## Current Recommended Order

1. review `docs/architecture/SWARMLENS_MASTER_SPEC.md` later for whether it should remain architecture-local or eventually become a normative spec
2. review `docs/architecture/GENOME_WIRING.md` later for backlink cleanup and final architecture-local status
3. treat `LIVING_LAYERS.md` as deferred until the backlink surface shrinks and the architecture-vs-substrate split is made explicit

Focused file preaudit:

- `docs/plans/2026-04-02-living-layers-preaudit.md`
