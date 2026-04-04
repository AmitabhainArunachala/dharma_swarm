---
title: Cleanup Control Center
path: docs/plans/2026-04-02-cleanup-control-center.md
slug: cleanup-control-center
doc_type: plan
status: active
summary: Compact index for the current non-TUI repo hygiene control layer, separating live policy, current-state reconciliation, and historical cleanup waves.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md
  - docs/plans/2026-04-02-root-residue-classification.md
  - docs/plans/2026-04-02-root-next-tranche-plan.md
  - docs/plans/2026-04-02-substrate-layer-policy.md
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
- docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md
- docs/plans/2026-04-02-generated-artifact-control-center.md
- docs/plans/2026-04-03-tui-baseline-protection-note.md
- docs/plans/2026-04-03-autonomous-cleanup-overnight-control.md
- docs/plans/2026-04-03-autonomous-build-skill-issues-and-fixes.md
- docs/plans/2026-04-02-root-residue-classification.md
- docs/plans/2026-04-02-root-helper-artifact-policy.md
- docs/plans/2026-04-02-root-operational-notes-policy.md
- docs/plans/2026-04-02-root-next-tranche-plan.md
- docs/plans/2026-04-02-root-future-move-preaudit.md
- docs/plans/2026-04-02-living-layers-preaudit.md
- docs/plans/2026-04-02-root-state-reconciliation.md
- docs/plans/2026-04-02-substrate-layer-policy.md
- docs/plans/ROOT_DRAIN_PASS_2026-04-01.md
- docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE2.md
- docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE3.md
- docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE4.md
improvement:
  room_for_improvement:
  - Keep this index compact; do not let it become another sprawling doctrine file.
  - Add or remove linked controls as the active cleanup surface changes.
  - Mark completed control docs more explicitly if they stop driving current work.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-cleanup-control-center.md
  retrieval_terms:
  - cleanup
  - control
  - center
  - repo hygiene
  - root
  - substrate
  - generated artifacts
  - tui baseline
  evergreen_potential: high
stigmergy:
  meaning: This file gives later cleanup runs one current entrypoint into the active non-TUI hygiene control surface.
  state: active
  semantic_weight: 0.87
  coordination_comment: Start here when you need the current repo-hygiene doctrine without rereading every individual plan file.
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
# Cleanup Control Center

## Purpose

This is the compact current entrypoint for the non-TUI repo hygiene lane.

Use it to distinguish:

- live cleanup policy
- current-state reconciliation
- deferred preaudits
- historical wave notes

Do not treat every cleanup note as equal authority.

## Start Here

If you need the current cleanup state first, read these in order:

1. [repo-dirt-taxonomy-and-run-plan.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md)
2. [root-residue-classification.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-residue-classification.md)
3. [root-next-tranche-plan.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-next-tranche-plan.md)
4. [root-state-reconciliation.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-state-reconciliation.md)

If the question is about report noise, generated-state retention, or packet-family quarantine, branch immediately to:

- [generated-artifact-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-artifact-control-center.md)

If the question is about whether repo dirt invalidates the Bun TUI lane, or how cleanup should coexist with the TUI freeze baseline, read:

- [tui-baseline-protection-note.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-tui-baseline-protection-note.md)

If the question is about running this lane overnight under bounded autonomy, read:

- [autonomous-cleanup-overnight-control.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-autonomous-cleanup-overnight-control.md)
- [autonomous-build-skill-issues-and-fixes.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-autonomous-build-skill-issues-and-fixes.md)

## Live Policy Docs

These govern present cleanup decisions:

- [root-helper-artifact-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-helper-artifact-policy.md)
- [root-operational-notes-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-operational-notes-policy.md)
- [substrate-layer-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-substrate-layer-policy.md)

## Active Substrate Support Docs

Use these when the question is about substrate directory shape, graduation-watch candidates, or local authority labels:

- [substrate-directory-cartography.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-substrate-directory-cartography.md)
- [substrate-graduation-candidates.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-substrate-graduation-candidates.md)
- [substrate-local-indexing-guidelines.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-substrate-local-indexing-guidelines.md)

## Parallel Control Seam

This cleanup lane also has one bounded parallel control surface:

- [generated-artifact-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-artifact-control-center.md)

Use it for generated-state, retained packet families, and report-boundary decisions. Do not mix that seam back into root cleanup unless a path explicitly crosses both.

## Protected Hot-Lane Boundary

The TUI lane is excluded from this cleanup program, but not because it is unreal.

Use:

- [tui-baseline-protection-note.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-tui-baseline-protection-note.md)

to preserve the stronger truth: dirty repo state and valid TUI convergence are coexisting realities, not one verdict.

## Deferred But Important Preaduits

These are not move instructions by themselves. They preserve unresolved classification logic:

- [root-future-move-preaudit.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-future-move-preaudit.md)
- [living-layers-preaudit.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-living-layers-preaudit.md)

## Historical Wave Notes

These are historical cleanup snapshots, not the best source of present state:

- [ROOT_DRAIN_PASS_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/plans/ROOT_DRAIN_PASS_2026-04-01.md)
- [ROOT_DRAIN_PASS_2026-04-01_WAVE2.md](/Users/dhyana/dharma_swarm/docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE2.md)
- [ROOT_DRAIN_PASS_2026-04-01_WAVE3.md](/Users/dhyana/dharma_swarm/docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE3.md)
- [ROOT_DRAIN_PASS_2026-04-01_WAVE4.md](/Users/dhyana/dharma_swarm/docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE4.md)

Each of those files now carries its own historical-status marker and should be read as sequence/rationale evidence only.

## Current Root Truth

At the moment, the root prose situation is:

- keep at root for now:
  - `README.md`
  - `CLAUDE.md`
  - `PRODUCT_SURFACE.md`
- defer, do not move yet:
  - `LIVING_LAYERS.md`
- paired future move candidates:
  - `program.md`
  - `program_ecosystem.md`
  - precheck: `docs/plans/2026-04-02-program-pair-relocation-preaudit.md`
- already out of root:
  - `docs/architecture/GENOME_WIRING.md`
  - `docs/architecture/SWARMLENS_MASTER_SPEC.md`

## Current Substrate Truth

- `foundations/` = conceptual substrate and pillar-level canon
- `lodestones/` = orienting seeds, reframes, and bridges
- `mode_pack/` = operational workflow contract layer

## Rule

When older cleanup notes disagree with newer ones:

1. prefer current-state and policy docs
2. use preaudits for unresolved cases
3. use historical wave notes only for sequence and rationale
