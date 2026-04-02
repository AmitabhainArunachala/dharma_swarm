---
title: Root Drain Pass Wave 3
path: docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE3.md
slug: root-drain-pass-wave-3
doc_type: plan
status: archival
summary: Historical snapshot of the third root-drain wave on 2026-04-01. Useful for prompt-artifact rehoming rationale, but not the best source of present root state.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/prompts/README.md
  - docs/prompts/ORTHOGONAL_UPGRADE_PROMPT.md
  - docs/prompts/STRATEGIC_PROMPT.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- documentation
- operations
- verification
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-02-root-state-reconciliation.md
- docs/plans/2026-04-02-cleanup-control-center.md
- docs/prompts/README.md
- docs/prompts/ORTHOGONAL_UPGRADE_PROMPT.md
- docs/prompts/STRATEGIC_PROMPT.md
improvement:
  room_for_improvement:
  - Preserve this as a historical prompt-rehoming record rather than mutating it into current policy.
  - Use newer control docs for present state and current prompt taxonomy.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE3.md
  retrieval_terms:
  - root drain
  - wave 3
  - prompts
  - historical
  - rehoming
  evergreen_potential: medium
stigmergy:
  meaning: This file records the historical prompt-artifact root-drain wave and should not be mistaken for current-state doctrine.
  state: archive
  semantic_weight: 0.68
  coordination_comment: Historical snapshot only; use current cleanup control docs for present truth.
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
# Root Drain Pass Wave 3

Date: 2026-04-01
Repo: `dharma_swarm`
Scope: prompt artifact rehoming

This pass moved reusable prompt artifacts out of repo root and into `docs/prompts/`.

Historical status:

- this note is a wave snapshot from 2026-04-01
- it is useful for rationale and sequence
- it is not the best source of current root state
- for current truth, use `docs/plans/2026-04-02-cleanup-control-center.md`

## Moved Files

| Old path | New path |
|----------|----------|
| `MEGA_PROMPT_STRANGE_LOOP.md` | `docs/prompts/MEGA_PROMPT_STRANGE_LOOP.md` |
| `MEGA_PROMPT_v2.md` | `docs/prompts/MEGA_PROMPT_v2.md` |
| `MEGA_PROMPT_v3.md` | `docs/prompts/MEGA_PROMPT_v3.md` |
| `MEGA_PROMPT_v4.md` | `docs/prompts/MEGA_PROMPT_v4.md` |
| `STRANGE_LOOP_COMPLETE_PROMPT.md` | `docs/prompts/STRANGE_LOOP_COMPLETE_PROMPT.md` |
| `STRANGE_LOOP_COMPLETE_PROMPT_v2.md` | `docs/prompts/STRANGE_LOOP_COMPLETE_PROMPT_v2.md` |
| `ORTHOGONAL_UPGRADE_PROMPT.md` | `docs/prompts/ORTHOGONAL_UPGRADE_PROMPT.md` |
| `PALANTIR_UPGRADE_PROMPT.md` | `docs/prompts/PALANTIR_UPGRADE_PROMPT.md` |
| `STRATEGIC_PROMPT.md` | `docs/prompts/STRATEGIC_PROMPT.md` |

## Why These Moved

- they are reusable prompt artifacts, not bootstrap truth
- they were polluting repo root with high-volume coordination material
- they now have a dedicated home and index in `docs/prompts/README.md`

## Notes

- frontmatter paths were normalized after relocation
- in-repo text references were updated to point at the new locations
- historical JSON manifests that captured old paths were left untouched as historical evidence

## Deferred

Prompt-adjacent runtime and architecture notes remain where they are until their stronger coupling is resolved:

- `GENOME_WIRING.md`
- `LIVING_LAYERS.md`
- `SWARMLENS_MASTER_SPEC.md`
- `docs/architecture/VERIFICATION_LANE.md`

## Result

Repo root is now materially less noisy, and prompt artifacts have a first-class non-root home.
