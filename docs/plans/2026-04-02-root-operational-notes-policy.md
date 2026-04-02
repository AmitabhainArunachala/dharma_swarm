---
title: Root Operational Notes Policy
path: docs/plans/2026-04-02-root-operational-notes-policy.md
slug: root-operational-notes-policy
doc_type: plan
status: active
summary: Classifies the remaining root operational-note files so product truth, autoresearch runbooks, and ecosystem instructions stop sharing the same level of authority by default.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
    - PRODUCT_SURFACE.md
    - program.md
    - program_ecosystem.md
    - docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
  - repository_hygiene
  - operations
  - software_architecture
  - knowledge_management
inspiration:
  - canonical_truth
  - operator_runtime
connected_relevant_files:
  - docs/plans/2026-04-02-cleanup-control-center.md
  - PRODUCT_SURFACE.md
  - program.md
  - program_ecosystem.md
  - docs/README.md
  - docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md
  - docs/plans/2026-04-02-root-residue-classification.md
  - docs/plans/2026-04-02-program-pair-relocation-preaudit.md
improvement:
  room_for_improvement:
    - Decide whether autoresearch runbooks should become a dedicated docs subtree instead of living at root.
    - Distinguish operator-facing quick-start notes from long-run automation prompts more sharply.
    - Add explicit rule text to docs/README once the destination policy is settled.
    - Record the exact landing path and runtime-coupling blocker for the `program*` pair so the future move can be code-aware instead of speculative.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-root-operational-notes-policy.md
  retrieval_terms:
    - root
    - operational notes
    - product surface
    - program
    - ecosystem
  evergreen_potential: medium
stigmergy:
  meaning: This file separates root-level product truth from root-level autoresearch instructions so the repo root can stay legible.
  state: active
  semantic_weight: 0.8
  coordination_comment: Use this file before relocating or retaining PRODUCT_SURFACE.md, program.md, or program_ecosystem.md.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# Root Operational Notes Policy

## Problem

The repo root still contains three files that are not the same kind of truth:

- `PRODUCT_SURFACE.md`
- `program.md`
- `program_ecosystem.md`

They all look important, but they do different jobs:

- product-surface doctrine
- single-repo autoresearch runbook
- multi-repo autoresearch runbook

Leaving them all at root preserves convenience, but it also makes the root feel more canonical and more cluttered than it should.

## Per-File Read

### `PRODUCT_SURFACE.md`

Current character:

- short
- high-signal
- declarative
- product-truth oriented

Assessment:

- strongest case for remaining at root, if any of the three do
- it acts more like a compact doctrine file than a workflow memo

### `program.md`

Current character:

- runbook-like
- agent/autoresearch workflow instructions
- operational and procedural, not canonical product truth

Assessment:

- semantically real, but less root-worthy than `PRODUCT_SURFACE.md`
- likely belongs in a future operator-runbooks or missions/plans-adjacent location

### `program_ecosystem.md`

Current character:

- companion runbook to `program.md`
- broader ecosystem workflow
- explicitly procedural

Assessment:

- even less root-worthy than `program.md`
- likely should live near other runbook or autonomy-operation docs rather than repo bootstrap

## Current Best Policy

### Keep At Root For Now

- `PRODUCT_SURFACE.md`

Reason:

- it is short, clear, and still serves as a high-level product-truth statement
- it complements `README.md` rather than duplicating it

### Future Move Candidates

- `program.md`
- `program_ecosystem.md`

Reason:

- they are workflow instructions, not root bootstrap
- they likely belong together in a later bounded tranche
- moving one without the other would create unnecessary asymmetry

## Exact Landing Recommendation

If and when the paired move is taken, the best current destination is:

- `docs/plans/program.md`
- `docs/plans/program_ecosystem.md`

Reason:

- both files read as operator runbooks and bounded automation instructions rather than canon
- `docs/plans/` already exists and is the least-surprising non-root home
- `docs/missions/` is the wrong fit because that subtree is dominated by dated campaign, swarm, and execution packets rather than evergreen runbooks
- creating a new `docs/operator/`, `docs/runbooks/`, or `docs/operations/` subtree just for this pair would be premature in the current cleanup phase
- keeping the pair together matters more than achieving a perfect subcategory on this tranche

## Why This Is Not Safe To Move As Pure Docs Cleanup Yet

This pair is still coupled to runtime-aware logic and a test:

- `dharma_swarm/long_context_sidecar_eval.py` reads `repo_root / "program.md"`
- `tests/test_long_context_sidecar_eval.py` writes and expects `program.md` at repo root

That means the relocation is no longer a prose-only move.
It is a code-aware move and should be taken only in a tranche that explicitly permits narrow runtime and test updates.
The good news is that the blocker is narrow: current evidence points to these two files as the only hard path assumptions that must be repaired.

## Current Decision

- keep `PRODUCT_SURFACE.md` at root
- defer the `program*` pair move for now
- when the move is taken, move both together to:
  - `docs/plans/program.md`
  - `docs/plans/program_ecosystem.md`
- include the required code/test path repair in the same bounded tranche
- do not route the pair through `docs/missions/`
- do not create a new subtree for them until there are more operator-runbook docs that justify it

## Recommended Next Move

Do not move `PRODUCT_SURFACE.md` yet.

When the root operational-note tranche is eventually taken, move:

- `program.md`
- `program_ecosystem.md`

together into a clearer operator-runbook or plans-adjacent location.

Use `docs/plans/2026-04-02-program-pair-relocation-preaudit.md` as the move precheck before taking that tranche.

## Why This Matters

This keeps the root from over-rotating in either direction:

- not every important file must stay at root
- not every important file should be moved immediately

The right cleanup is to preserve one compact product-truth note while preparing the procedural runbooks for a later paired move.
