---
title: TUI Baseline Protection Note
path: docs/plans/2026-04-03-tui-baseline-protection-note.md
slug: tui-baseline-protection-note
doc_type: plan
status: active
summary: Records the current Bun TUI/operator cockpit lane as a real converged product seam with a known freeze baseline, and defines how non-TUI cleanup should avoid polluting that lane.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/HOT_PATH_INTEGRATION_PROTOCOL_2026-04-01.md
  - docs/plans/2026-04-02-non-tui-repo-hygiene-map.md
  - user_handoff_tui_team_2026-04-03
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- operations
- documentation
- repository_hygiene
- verification
inspiration:
- operator_runtime
- canonical_truth
connected_relevant_files:
- docs/HOT_PATH_INTEGRATION_PROTOCOL_2026-04-01.md
- docs/plans/2026-04-02-cleanup-control-center.md
- docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md
- docs/plans/2026-04-02-non-tui-repo-hygiene-map.md
- docs/plans/2026-04-02-current-meta-topology-of-dharma-swarm.md
improvement:
  room_for_improvement:
  - Update this note only when the accepted TUI baseline or replay strategy materially changes.
  - Keep this as a boundary-protection note, not a product-spec surrogate.
  - Add a clean replay checklist later if branch extraction work begins.
  next_review_at: '2026-04-04T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-03-tui-baseline-protection-note.md
  retrieval_terms:
  - bun tui
  - baseline
  - protection
  - freeze point
  - cleanup boundary
  - hot lane
  evergreen_potential: medium
stigmergy:
  meaning: This file prevents non-TUI cleanup work from narratively collapsing dirty-repo truth into false claims about the Bun TUI lane.
  state: active
  semantic_weight: 0.9
  coordination_comment: Read this before using repo dirt as evidence about the TUI lane or before mixing cleanup changes into TUI product work.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T00:42:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# TUI Baseline Protection Note

## Purpose

This note exists so the non-TUI cleanup lane does not misread overall repo dirt as evidence that the Bun TUI/operator cockpit lane is structurally incoherent.

Those are separate truths.

## Current Accepted Truth

1. The overall repository is still dirty.
2. The Bun TUI/operator cockpit lane is materially real and much farther along than the surrounding repo cleanliness would suggest.

Do not collapse those into one judgment.

## Known Freeze Point

Accepted baseline:

- commit: `1d8dae2`
- message: `Freeze Bun TUI convergence baseline`

Treat that commit as the clean reference point for the converged Bun TUI lane.

## What Is Real In The TUI Lane

The TUI lane is no longer just a scaffold.

The current accepted handoff says it has materially landed:

- typed sessions
- typed approvals
- typed runtime/control payloads
- typed routing/model payloads
- typed agent surfaces
- reconnect and authoritative resync hardening
- approval durability on canonical transcript events
- runtime control recording honesty
- a real tmux-based TTY harness

That means the correct posture is:

- structurally coherent
- valid freeze point exists
- ready for focused product polish and cockpit-feel work
- not blocked on total repo purification

## What Non-TUI Cleanup Must Not Do

Do not use the dirty worktree as proof that the TUI lane is fake, immature, or architecturally void.

Do not:

- merge omnibus repo-cleanup churn into TUI product commits
- narratively collapse repo dirt into TUI invalidation
- force TUI product work to wait for whole-repo hygiene completion
- treat later mixed commits as evidence that the freeze baseline was not real

## Correct Support Posture

The cleanup lane should support the TUI lane by:

1. protecting the accepted baseline
2. isolating non-TUI cleanup churn on separate branches or slices
3. helping separate:
   - TUI product deltas
   - repo hygiene deltas
   - docs/artifact/admin churn
4. preserving intentional cherry-pick or replay paths from the clean baseline

## Branch Strategy

Recommended strategy:

1. branch from `1d8dae2`
2. replay only clean TUI deltas there
3. keep repo hygiene on separate branches
4. cherry-pick intentionally
5. do not merge dirty omnibus commits into the TUI lane

## Implication For This Cleanup Program

The non-TUI hygiene lane should continue in parallel, but it should explicitly treat the Bun TUI lane as:

- real
- converged enough to protect
- separate from repo-wide prose and artifact cleanup

That means repo cleanliness remains a valid systems problem without becoming a false indictment of the TUI architecture itself.
