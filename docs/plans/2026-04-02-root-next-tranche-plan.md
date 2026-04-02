---
title: Root Next Tranche Plan
path: docs/plans/2026-04-02-root-next-tranche-plan.md
slug: root-next-tranche-plan
doc_type: plan
status: active
summary: Defines the next bounded root cleanup tranche after the SWARMLENS and GENOME_WIRING moves, with LIVING_LAYERS currently deferred because live backlinks make relocation unsafe and the program files remaining the main operational-note question.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
    - LIVING_LAYERS.md
    - PRODUCT_SURFACE.md
    - program.md
    - program_ecosystem.md
    - docs/plans/2026-04-02-root-operational-notes-policy.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
  - repository_hygiene
  - software_architecture
  - operations
  - knowledge_management
inspiration:
  - canonical_truth
  - repo_hygiene
connected_relevant_files:
  - docs/plans/2026-04-02-cleanup-control-center.md
  - LIVING_LAYERS.md
  - PRODUCT_SURFACE.md
  - program.md
  - program_ecosystem.md
  - docs/plans/2026-04-02-root-operational-notes-policy.md
  - docs/plans/2026-04-02-program-pair-relocation-preaudit.md
  - docs/plans/2026-04-02-root-state-reconciliation.md
  - docs/plans/2026-04-02-root-residue-classification.md
  - docs/plans/2026-04-02-root-and-substrate-classification-map.md
improvement:
  room_for_improvement:
    - Convert the operational-note half into one paired move when the landing zone is chosen.
    - Decide whether LIVING_LAYERS should move intact or split into architecture and substrate portions.
    - Recompute the root dirt set after the historical root drains are fully tracked.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-root-next-tranche-plan.md
  retrieval_terms:
    - root
    - tranche
    - living layers
    - product surface
    - program
  evergreen_potential: medium
stigmergy:
  meaning: This file turns the remaining root cleanup problem into two explicit decisions instead of one vague residue bucket.
  state: active
  semantic_weight: 0.81
  coordination_comment: Use this file to choose the next root cleanup move after the current architecture-local drains.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# Root Next Tranche Plan

## Current Situation

After moving `SWARMLENS_MASTER_SPEC.md` and `GENOME_WIRING.md` out of root, the remaining root prose problem is now much smaller.

It has split into two different decisions:

1. `LIVING_LAYERS.md`
2. `PRODUCT_SURFACE.md` + `program.md` + `program_ecosystem.md`

## Decision 1: `LIVING_LAYERS.md`

This is still the main unresolved architecture/substrate file, but it should stay put for now.

Why it is hard:

- it mixes architecture implementation detail with deeper conceptual framing
- it still has meaningful references from active docs, historical material, code, tests, and runtime-oriented tooling
- its destination is not fully settled between architecture and substrate
- the live backlink surface is too broad to justify a move without a dedicated backlink repair tranche

Best current policy:

- do not move it casually
- defer relocation until the live references are enumerated, a destination class is chosen, and the backlink repair surface is low-risk
- keep it as a review item, not a move item

## Decision 2: Root Operational Notes

These are the remaining root operational-note files:

- `PRODUCT_SURFACE.md`
- `program.md`
- `program_ecosystem.md`

Best current policy:

- keep `PRODUCT_SURFACE.md` at root for now
- treat `program.md` and `program_ecosystem.md` as a paired future move

Why:

- `PRODUCT_SURFACE.md` still acts as a compact product-canon statement
- the two `program*` files are procedural runbooks and belong together semantically
- the best current landing path is `docs/plans/program.md` and `docs/plans/program_ecosystem.md`
- `docs/missions/` is too campaign-shaped and date-shaped to be the right home for these evergreen operator runbooks
- a new `docs/operator/` or `docs/runbooks/` subtree would be overbuilt for only two files right now
- the move is deferred because `dharma_swarm/long_context_sidecar_eval.py` and `tests/test_long_context_sidecar_eval.py` still assume `program.md` at repo root
- the dedicated precheck now lives in `docs/plans/2026-04-02-program-pair-relocation-preaudit.md`
- current evidence suggests those two files are the only hard path blockers, so the later move can stay very small if taken as one bounded code-aware tranche

## Recommended Order

1. finish the lingering plan-map sync after the recent moves
2. document that `LIVING_LAYERS.md` is deferred rather than queued for immediate move
3. then take the paired `program.md` + `program_ecosystem.md` move if the landing zone is clear
   - destination: `docs/plans/program.md` and `docs/plans/program_ecosystem.md`
   - only in a tranche that explicitly allows the required code/test reference repair
   - do not route them through `docs/missions/`

## What This Achieves

This keeps the remaining root cleanup honest:

- one unresolved architecture/substrate file
- one unresolved runbook pair
- one compact product-truth note staying in place for now

That is a much cleaner shape than the earlier “root is still messy” narrative.

Current-state reconciliation:

- `docs/plans/2026-04-02-root-state-reconciliation.md`
