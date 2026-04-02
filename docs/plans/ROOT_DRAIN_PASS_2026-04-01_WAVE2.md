---
title: Root Drain Pass Wave 2
path: docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE2.md
slug: root-drain-pass-wave-2
doc_type: plan
status: archival
summary: Historical snapshot of the second root-drain wave on 2026-04-01. Useful for sequence and rationale, but no longer the best source of present root state.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - NAVIGATION.md
  - INTEGRATION_MAP.md
  - MODEL_ROUTING_CANON.md
  - docs/architecture/NAVIGATION.md
  - docs/architecture/INTEGRATION_MAP.md
  - docs/architecture/MODEL_ROUTING_CANON.md
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
- docs/plans/2026-04-02-root-state-reconciliation.md
- docs/plans/2026-04-02-cleanup-control-center.md
- docs/architecture/NAVIGATION.md
- docs/architecture/INTEGRATION_MAP.md
- docs/architecture/MODEL_ROUTING_CANON.md
improvement:
  room_for_improvement:
  - Preserve this as a historical wave record rather than updating it to match current state.
  - Use current reconciliation docs when present-state truth is needed.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE2.md
  retrieval_terms:
  - root drain
  - wave 2
  - historical
  - root
  - architecture
  evergreen_potential: medium
stigmergy:
  meaning: This file records a historical root-drain wave and should be read as sequence/rationale evidence rather than current-state policy.
  state: archive
  semantic_weight: 0.68
  coordination_comment: Historical snapshot only; use root-state reconciliation docs for current truth.
  trace_role: historical_trace
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
# Root Drain Pass Wave 2

Date: 2026-04-01
Repo: `dharma_swarm`
Scope: second non-hot-path root cleanup wave

This pass moved low-risk architecture notes out of repo root and into `docs/architecture/`.

Historical status:

- this note is a wave snapshot from 2026-04-01
- it is useful for rationale and sequence
- it is not the best source of current root state
- for current truth, use `docs/plans/2026-04-02-root-state-reconciliation.md`

## Moved Files

| Old path | New path |
|----------|----------|
| `NAVIGATION.md` | `docs/architecture/NAVIGATION.md` |
| `INTEGRATION_MAP.md` | `docs/architecture/INTEGRATION_MAP.md` |
| `MODEL_ROUTING_CANON.md` | `docs/architecture/MODEL_ROUTING_CANON.md` |

## Why These Moved In This Wave

- they are human architecture notes, not bootstrap files
- they had mostly documentation references, not runtime-critical path assumptions
- moving them reduces root ambiguity without changing the dashboard hot path

## Intentionally Deferred

These remain at root for now because code, tests, or runtime logic point at them directly:

- `GENOME_WIRING.md`
- `LIVING_LAYERS.md`
- `SWARMLENS_MASTER_SPEC.md`
- `docs/architecture/VERIFICATION_LANE.md`

## Notes

- in-repo references to the moved files were updated to point to their new `docs/architecture/` locations
- the moved files had their frontmatter paths normalized after relocation

## Next Safe Waves

1. decide whether `GENOME_WIRING.md`, `LIVING_LAYERS.md`, and `SWARMLENS_MASTER_SPEC.md` should be moved together with code-path updates
2. add a dedicated `docs/prompts/` index now that prompt artifacts are no longer in root
3. continue draining or archiving remaining root-level non-canonical markdown
