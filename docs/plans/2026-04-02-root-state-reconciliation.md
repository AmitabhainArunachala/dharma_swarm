---
title: Root State Reconciliation
path: docs/plans/2026-04-02-root-state-reconciliation.md
slug: root-state-reconciliation
doc_type: plan
status: active
summary: Reconciles the current root cleanup state against earlier root-drain wave notes so historical snapshots do not get mistaken for present repo truth.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE2.md
  - docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE4.md
  - docs/plans/2026-04-02-root-residue-classification.md
  - docs/plans/2026-04-02-root-next-tranche-plan.md
  - docs/architecture/GENOME_WIRING.md
  - docs/architecture/SWARMLENS_MASTER_SPEC.md
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
  - docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE2.md
  - docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE4.md
- docs/plans/2026-04-02-root-residue-classification.md
- docs/plans/2026-04-02-root-next-tranche-plan.md
- docs/architecture/GENOME_WIRING.md
- docs/architecture/SWARMLENS_MASTER_SPEC.md
- LIVING_LAYERS.md
- PRODUCT_SURFACE.md
- program.md
- program_ecosystem.md
improvement:
  room_for_improvement:
  - Add explicit backlink counts once the next root tranche begins.
  - Mark older root-drain wave notes as historical snapshots if they continue to confuse later runs.
  - Recompute this note after the program runbook pair or LIVING_LAYERS changes state.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-root-state-reconciliation.md
  retrieval_terms:
  - root
  - state
  - reconciliation
  - wave
  - historical
  - snapshot
  evergreen_potential: medium
stigmergy:
  meaning: This note separates historical root-drain snapshots from present root-cleanup truth so later agents do not reopen already-resolved state by accident.
  state: active
  semantic_weight: 0.81
  coordination_comment: Use this file when older wave notes disagree with the current root classification docs.
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
# Root State Reconciliation

## Purpose

Some older root-drain notes still describe `GENOME_WIRING.md` and `SWARMLENS_MASTER_SPEC.md` as root-resident or deferred root files.

Those notes are useful historical snapshots, but they are no longer the best expression of current state.

This note records the current root truth without rewriting the historical wave notes.

## Current Root Truth

These files have already left root:

- `docs/architecture/GENOME_WIRING.md`
- `docs/architecture/SWARMLENS_MASTER_SPEC.md`

These files remain the active root decision set:

- `LIVING_LAYERS.md`
- `PRODUCT_SURFACE.md`
- `program.md`
- `program_ecosystem.md`

## How To Read Older Wave Notes

Treat these as historical snapshots, not current-state sources:

- `docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE2.md`
- `docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE4.md`

They still correctly describe what was true at that wave boundary, but they are not the final source of truth for the present root layout.

## Current Source Of Truth Order

For present root cleanup state, prefer:

1. `docs/plans/2026-04-02-root-residue-classification.md`
2. `docs/plans/2026-04-02-root-next-tranche-plan.md`
3. `docs/plans/2026-04-02-root-future-move-preaudit.md`
4. this reconciliation note

Use the older wave notes only for historical sequence and rationale.

## Why This Matters

Without this distinction, later cleanup passes can waste time:

- re-auditing already moved files as if they still lived at root
- reopening closed root decisions
- mistaking historical deferments for current blockers

The point is not to erase the older notes.
The point is to keep present truth and historical truth from impersonating each other.
