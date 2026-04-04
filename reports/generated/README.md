---
title: Generated Reports Index
path: reports/generated/README.md
slug: generated-reports-index
doc_type: readme
status: reference
summary: Index and rule surface for intentionally retained machine-produced report artifacts under reports/generated.
source:
  provenance: repo_local
  kind: generated_reports_index
  origin_signals:
  - docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
  - docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
  - reports/generated/nightwatch/terminal_nightwatch_20260401.log
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- operations
- verification
- documentation
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
- docs/plans/2026-04-02-generated-artifact-control-center.md
- docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
- reports/generated/verification/README.md
- reports/generated/nightwatch/terminal_nightwatch_20260401.log
improvement:
  room_for_improvement:
  - Add sub-indexes if multiple generated families are intentionally retained here.
  - Distinguish replay-value artifacts from low-value transient logs more sharply.
  - Keep this subtree small enough that it does not become a second ambiguous reports layer.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: readme
  vault_path: reports/generated/README.md
  retrieval_terms:
  - reports
  - generated
  - index
  - artifacts
  - nightwatch
  - quarantine
  evergreen_potential: high
stigmergy:
  meaning: This file makes the reports/generated subtree legible as retained machine-produced evidence rather than letting it read like an accidental dump.
  state: reference
  semantic_weight: 0.78
  coordination_comment: Use this file before retaining or citing generated report artifacts.
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
# Generated Reports

This subtree is for retained machine-produced report artifacts.

These files may still have audit, replay, or forensic value, but they are not:

- product truth
- architecture canon
- operator doctrine

## Current Families

- `nightwatch/`: generated terminal watchdog logs
- `verification/`: relocated uncited generated verification probe artifacts

## Rules

- keep generated artifacts here only when they are intentionally retained
- do not cite this subtree as architectural truth
- prefer historical authored material under `reports/historical/`

## Control Docs

- [generated-artifact-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-artifact-control-center.md)
- [GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md](/Users/dhyana/dharma_swarm/docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md)
- [verification-family-retention-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-verification-family-retention-policy.md)
