---
title: Generated Verification Reports Index
path: reports/generated/verification/README.md
slug: generated-verification-reports-index
doc_type: readme
status: reference
summary: Index for relocated generated verification probe artifacts retained for audit or replay value under reports/generated/verification.
source:
  provenance: repo_local
  kind: generated_reports_index
  origin_signals:
  - reports/generated/README.md
  - docs/plans/2026-04-03-verification-family-retention-policy.md
  - docs/plans/2026-04-03-verification-probe-citation-census.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- verification
- operations
- documentation
- knowledge_management
inspiration:
- verification
- canonical_truth
connected_relevant_files:
- reports/generated/README.md
- docs/plans/2026-04-03-verification-family-retention-policy.md
- docs/plans/2026-04-03-verification-probe-citation-census.md
- docs/plans/2026-04-03-uncited-verification-probe-relocation-preplan.md
improvement:
  room_for_improvement:
  - Keep this subtree limited to uncited or generated-only verification artifacts.
  - Add finer sub-indexing only if the verification generated set grows materially.
  - Recheck whether any relocated artifact becomes live-cited later.
  next_review_at: '2026-04-04T12:00:00+09:00'
pkm:
  note_class: readme
  vault_path: reports/generated/verification/README.md
  retrieval_terms:
  - generated
  - verification
  - probes
  - reports
  - audit
  - replay
  evergreen_potential: high
stigmergy:
  meaning: This file makes the generated verification subtree legible as retained generated evidence rather than a silent spillover from reports/verification.
  state: reference
  semantic_weight: 0.8
  coordination_comment: Use this file before citing or relocating generated verification probe artifacts.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T01:40:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Generated Verification Reports

This subtree contains generated verification probe artifacts that were moved out of `reports/verification/` because they were not live-cited outside cleanup doctrine at move time.

These files may still have audit or replay value, but they are not:

- canonical product truth
- authored verification manifest material
- cited path-stable evidence

## Current Families

- relocated uncited probe traces from `reports/verification/`

## Rules

- keep only generated verification artifacts here
- do not move live-cited evidence into this subtree without handling citations in the same tranche
- do not treat this subtree as authored verification doctrine
