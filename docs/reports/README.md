---
title: Reports Index
path: docs/reports/README.md
slug: reports-index
doc_type: readme
status: active
summary: Index for active-reference authored reports, synthesis packets, and operator evidence that remain useful without being canonical doctrine.
source:
  provenance: repo_local
  kind: readme
  origin_signals:
  - docs/README.md
  - docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
  - docs/archive/README.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- documentation
- verification
- software_architecture
inspiration:
- canonical_truth
- repo_topology
connected_relevant_files:
- docs/README.md
- docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
- docs/archive/README.md
- reports/historical/GODEL_CLAW_V1_REPORT.md
improvement:
  room_for_improvement:
  - Group report families if the subtree keeps expanding.
  - Split active-reference reports from packet families more sharply over time.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: readme
  vault_path: docs/reports/README.md
  retrieval_terms:
  - docs
  - reports
  - active reference
  - synthesis
  - evidence
  evergreen_potential: high
stigmergy:
  meaning: This file keeps the docs/reports layer legible by distinguishing active-reference reports from archive and generated state.
  state: active
  semantic_weight: 0.82
  coordination_comment: Use this file before moving a report into archive or treating it as live doctrine.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T12:00:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# Reports Index

`docs/reports/` is for authored reports that still have active reference value.

It is not:

- top-level canon
- bounded execution plans
- prompts
- generated state
- historical packets that no longer deserve active visibility

Use it for:

- evidence-rich synthesis reports
- operator-facing audit summaries still cited by current plans
- domain reports that still influence architecture or product thinking

Keep these separate from:

- [archive/README.md](/Users/dhyana/dharma_swarm/docs/archive/README.md): superseded and historical prose
- [reports/historical/GODEL_CLAW_V1_REPORT.md](/Users/dhyana/dharma_swarm/reports/historical/GODEL_CLAW_V1_REPORT.md): durable historical reports
- generated run output under `reports/generated/` and `reports/**/state/`

Current examples:

- [20-AGENT-DEEP-AUDIT-2026-03-29.md](/Users/dhyana/dharma_swarm/docs/reports/20-AGENT-DEEP-AUDIT-2026-03-29.md)
- [AGENT_PROMPT_SYNTHESIS.md](/Users/dhyana/dharma_swarm/docs/reports/AGENT_PROMPT_SYNTHESIS.md)
- [DGC_DUAL_ENGINE_REALITY_MAP_2026-03-13.md](/Users/dhyana/dharma_swarm/docs/reports/DGC_DUAL_ENGINE_REALITY_MAP_2026-03-13.md)
- [JIKOKU_FINAL_REPORT.md](/Users/dhyana/dharma_swarm/docs/reports/JIKOKU_FINAL_REPORT.md)
- [JIKOKU_SAMAYA_INTEGRATION.md](/Users/dhyana/dharma_swarm/docs/reports/JIKOKU_SAMAYA_INTEGRATION.md)

Rule:

- if a report is still being cited by current plans, prompts, or architecture work, keep it here
- if it is mostly historical context or a dated execution packet, move it to archive
