---
title: Root Drain Pass Wave 4
path: docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE4.md
slug: root-drain-pass-wave-4
doc_type: plan
status: archival
summary: Historical snapshot of the fourth root-drain wave on 2026-04-01. Useful for archive and verification relocation rationale, but no longer the best source of present root state.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/archive/AGENT_SWARM_SYNTHESIS.md
  - docs/archive/MOONSHOT_COMPLETE.md
  - docs/architecture/VERIFICATION_LANE.md
  - docs/dse/GAIA_UI.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- documentation
- software_architecture
- verification
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-02-root-state-reconciliation.md
- docs/plans/2026-04-02-cleanup-control-center.md
- docs/archive/AGENT_SWARM_SYNTHESIS.md
- docs/archive/MOONSHOT_COMPLETE.md
- docs/architecture/VERIFICATION_LANE.md
- docs/dse/GAIA_UI.md
improvement:
  room_for_improvement:
  - Preserve this as a historical relocation snapshot rather than rewriting it to match later state.
  - Use current root reconciliation docs when judging present root truth.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE4.md
  retrieval_terms:
  - root drain
  - wave 4
  - archive
  - verification
  - historical
  evergreen_potential: medium
stigmergy:
  meaning: This file records a historical archive-and-verification relocation wave and should be read as a snapshot rather than current-state policy.
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
# Root Drain Pass Wave 4

Date: 2026-04-01
Repo: `dharma_swarm`
Scope: archive notes, verification note, and GAIA UI relocation

Historical status:

- this note is a wave snapshot from 2026-04-01
- it is useful for rationale and sequence
- it is not the best source of current root state
- for current truth, use `docs/plans/2026-04-02-root-state-reconciliation.md`

## Moved Files

| Old path | New path |
|----------|----------|
| `AGENT_SWARM_SYNTHESIS.md` | `docs/archive/AGENT_SWARM_SYNTHESIS.md` |
| `MOONSHOT_COMPLETE.md` | `docs/archive/MOONSHOT_COMPLETE.md` |
| `PALANTIR_ONTOLOGY_GAP_ANALYSIS.md` | `docs/archive/PALANTIR_ONTOLOGY_GAP_ANALYSIS.md` |
| `UNASSAILABLE_SYSTEM_BLUEPRINT.md` | `docs/archive/UNASSAILABLE_SYSTEM_BLUEPRINT.md` |
| `xray_report.md` | `reports/historical/xray_report.md` |
| `VERIFICATION_LANE.md` | `docs/architecture/VERIFICATION_LANE.md` |
| `gaia_ui.md` | `docs/dse/GAIA_UI.md` |

## Why This Wave Was Safe

- these files were not part of the dashboard hot path
- none of them were required as canonical bootstrap docs at repo root
- `VERIFICATION_LANE.md` had many documentary references but no strong runtime path coupling
- `gaia_ui.md` belonged with the GAIA documentation set, not beside repo bootstrap files

## Remaining Root Markdown

After this wave, root markdown is down to:

- `README.md`
- `CLAUDE.md`
- `PRODUCT_SURFACE.md`
- `GENOME_WIRING.md`
- `LIVING_LAYERS.md`
- `SWARMLENS_MASTER_SPEC.md`
- `program.md`
- `program_ecosystem.md`

## Why These Still Remain

- `README.md`, `CLAUDE.md`, and `PRODUCT_SURFACE.md` are part of the current canon set
- `GENOME_WIRING.md`, `LIVING_LAYERS.md`, and `SWARMLENS_MASTER_SPEC.md` are referenced by code, tests, or runtime-oriented tooling
- `program.md` and `program_ecosystem.md` are read by sidecar evaluation logic and related tests

## Meaning Of The Current Stop Point

The root is no longer a mixed graveyard of prompts, reports, plans, and speculative notes.

What remains in root is either:

- intentionally canonical, or
- coupled enough to require code-aware migration work rather than pure documentation cleanup
