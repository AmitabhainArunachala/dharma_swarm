---
title: Generated Artifact Control Center
path: docs/plans/2026-04-02-generated-artifact-control-center.md
slug: generated-artifact-control-center
doc_type: plan
status: active
summary: Compact entrypoint for the generated-artifact and report-boundary cleanup seam, separating retained generated families, historical reports, and current generated-report policy.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
  - docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
  - reports/generated/README.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- operations
- documentation
- verification
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
- docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
- docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md
- docs/plans/2026-04-02-generated-packet-path-resolution-design.md
- reports/generated/README.md
- reports/historical/GODEL_CLAW_V1_REPORT.md
improvement:
  room_for_improvement:
  - Keep the retained packet-family preaudit current as code, tests, and mission docs change.
  - Keep this control note separate from root cleanup so the two seams do not collapse together.
  - Add a generated-family validation checklist if more report moves are attempted.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-generated-artifact-control-center.md
  retrieval_terms:
  - generated
  - artifact
  - control
  - reports
  - quarantine
  - boundary
  evergreen_potential: high
stigmergy:
  meaning: This file gives later cleanup runs one current entrypoint into the generated-artifact doctrine instead of scattering the logic across report and docs notes.
  state: active
  semantic_weight: 0.84
  coordination_comment: Start here when deciding whether a report-family path is generated state, retained packet material, or durable authored evidence.
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
# Generated Artifact Control Center

## Purpose

This is the compact current entrypoint for the generated-artifact cleanup seam.

Use it to distinguish:

- retained generated report artifacts
- path-coupled generated packet families
- durable historical authored reports
- current generated-report policy

## Start Here

Read these first:

1. [GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md](/Users/dhyana/dharma_swarm/docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md)
2. [2026-04-02-reports-cartography-and-cleanup-plan.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md)
3. [reports/generated/README.md](/Users/dhyana/dharma_swarm/reports/generated/README.md)
4. [2026-04-02-retained-generated-packet-families-preaudit.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md)
5. [2026-04-02-generated-packet-path-resolution-design.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-packet-path-resolution-design.md)

## Current Generated Truth

These are the current generated-report categories:

- low-coupling generated artifacts already quarantined:
  - `reports/generated/nightwatch/`
- retained generated packet families that are still path-coupled:
  - `reports/dual_engine_swarm_20260313_run/`
  - `reports/psmv_hyperfiles_20260313/`
- generated branch state that should not be treated as source of truth:
  - `.dharma_psmv_hyperfile_branch/`
  - `.dharma_psmv_hyperfile_branch_v2/`

## Historical Keep

These are not generated-state cleanup targets:

- `reports/historical/`

Treat that subtree as durable historical authored evidence, not as quarantine material.

## Rule

Do not move a generated family just because it looks machine-produced.

First decide:

1. is it low-coupling retained artifact material?
2. is it still path-coupled to code, tests, or mission docs?
3. is it actually historical authored evidence instead?

Only after that should relocation or retention be chosen.

## Active Packet-Family Blocker Map

For the two retained packet families, use:

- [2026-04-02-retained-generated-packet-families-preaudit.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md)

That note names the exact code, test, mission-doc, and packet-report blockers that still keep those families in place.

## Path-Resolution Enabling Seam

When work is ready to remove hardcoded code/test references without moving files yet, use:

- [2026-04-02-generated-packet-path-resolution-design.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-packet-path-resolution-design.md)
