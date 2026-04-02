---
title: Architecture Docs Tranche Plan
path: docs/plans/2026-04-02-architecture-docs-tranche-plan.md
slug: architecture-docs-tranche-plan
doc_type: plan
status: active
summary: "Date: 2026-04-02 Purpose: choose the next low-risk architecture-local docs move set after the first top-level docs cleanup tranche."
source:
  provenance: repo_local
  kind: plan
  origin_signals:
  - docs/plans/2026-04-02-top-level-docs-canon-map.md
  - docs/README.md
  - docs/architecture/NAVIGATION.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- knowledge_management
- documentation
- verification
inspiration:
- architecture
- repo_topology
connected_relevant_files:
- docs/README.md
- docs/plans/2026-04-02-top-level-docs-canon-map.md
- docs/architecture/ORCHESTRATOR_LEDGERS.md
- docs/architecture/PROVIDER_MATRIX_HARNESS.md
- docs/architecture/JIKOKU_SAMAYA_ARCHITECTURE.md
improvement:
  room_for_improvement:
  - Keep this plan aligned with the actually executed tranche rather than the initial hypothesis.
  - Record deferred families explicitly when topology constraints block a move.
  next_review_at: '2026-04-03T00:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-architecture-docs-tranche-plan.md
  retrieval_terms:
  - architecture
  - docs
  - tranche
  - plan
  - move
  - canon
  evergreen_potential: medium
stigmergy:
  meaning: This plan captures the bounded architecture-docs move seam and its stop conditions.
  state: working
  semantic_weight: 0.7
  coordination_comment: Use this file to understand why some architecture-local docs moved now while others were deferred.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T00:00:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Architecture Docs Tranche Plan

Date: 2026-04-02
Scope: next non-TUI cleanup seam after the first top-level `docs/` reduction tranche

## Thesis

The next authority-reduction seam is not "move all architecture-looking docs."

The correct next move is:

- move only the architecture-local docs whose destination is obvious
- defer the denser JIKOKU cluster until it can move as a coherent family

That keeps top-level `docs/` cleaner without creating a second navigation mess.

## Candidate Audit

### Move Now: Obvious Architecture-Local Docs

These look safe to move into `docs/architecture/` in a bounded tranche.

#### `docs/architecture/ORCHESTRATOR_LEDGERS.md`

Why:

- clearly architecture-local
- narrow scope
- connected to session/message-bus orchestration internals
- destination is obvious

Reference surface:

- no broad live reference network surfaced in the current scan

Recommendation:

- move next

#### `docs/architecture/PROVIDER_MATRIX_HARNESS.md`

Why:

- clearly architecture/tooling-local
- already treated as an implementation artifact in older plans
- destination is obvious

Reference surface:

- appears in older plans and the canon-map planning docs
- manageable live-reference surface

Recommendation:

- move next

### Defer: JIKOKU Cluster

These should likely leave top-level `docs/`, but not in the next tiny tranche.

#### `docs/architecture/JIKOKU_SAMAYA_ARCHITECTURE.md`
#### `docs/architecture/JIKOKU_SAMAYA_SYSTEM_DIAGRAM.md`

Why defer:

- strongly cross-linked from `docs/reports/JIKOKU_SAMAYA_INTEGRATION.md`
- clearly part of a family with:
  - `docs/architecture/JIKOKU_SAMAYA_EXECUTIVE_SUMMARY.md`
  - `docs/architecture/JIKOKU_SAMAYA_IMPLEMENTATION_ROADMAP.md`
- moving them alone would leave the JIKOKU set split awkwardly across top-level and architecture without an index or family decision

Recommendation:

- move later as one JIKOKU-family tranche, not one file at a time

### Defer: Terminal Specs

#### `docs/TERMINAL_V2_OPERATOR_SHELL_SPEC_2026-04-01.md`
#### `docs/TERMINAL_V3_OPERATOR_INTELLIGENCE_SPEC_2026-04-01.md`

Why defer:

- they are architecture-local in ontology
- but they are adjacent to the hot TUI convergence lane
- moving them while terminal convergence is still active risks unnecessary operator confusion

Recommendation:

- leave in place until the hot lane cools or the TUI docs are explicitly reindexed

## Best Next Batch

The best next merge-safe batch is:

1. `docs/architecture/ORCHESTRATOR_LEDGERS.md`
2. `docs/architecture/PROVIDER_MATRIX_HARNESS.md`

This batch is strong because:

- both files are architecture-local
- both reduce top-level false authority
- neither appears tightly coupled to active top-level operator entrypoints
- both fit naturally into the existing `docs/architecture/` subtree

## Required Companion Changes

If this tranche is executed, also update:

- `docs/README.md`
- any direct provenance/frontmatter references inside the moved files
- narrow live references from planning docs or architecture indexes if they still point to old paths

## Explicit Non-Goals

Do not mix this tranche with:

- JIKOKU-family relocation
- terminal-spec relocation
- root markdown cleanup
- reports cleanup
- archive cleanup

Those are separate seams.

## Stop Point

After moving `docs/architecture/ORCHESTRATOR_LEDGERS.md` and `docs/architecture/PROVIDER_MATRIX_HARNESS.md`, stop.

Then reassess:

- whether top-level `docs/` authority density is meaningfully lower
- whether JIKOKU should become the next family-level docs tranche
- whether terminal docs should wait until the hot lane cools
