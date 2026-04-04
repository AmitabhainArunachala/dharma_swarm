---
title: Architecture Index
path: docs/architecture/README.md
slug: architecture-index
doc_type: readme
status: active
summary: Index for subsystem architecture docs that matter operationally but should not compete with repo-level canon.
source:
  provenance: repo_local
  kind: readme
  origin_signals:
    - docs/README.md
    - docs/architecture/ORCHESTRATOR_LEDGERS.md
    - docs/architecture/PROVIDER_MATRIX_HARNESS.md
    - docs/architecture/SWARMLENS_MASTER_SPEC.md
    - docs/architecture/DGC_STRESS_HARNESS.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
  - software_architecture
  - verification
  - knowledge_management
  - operations
inspiration:
  - operator_runtime
  - canonical_truth
connected_relevant_files:
  - docs/README.md
  - docs/architecture/ORCHESTRATOR_LEDGERS.md
  - docs/architecture/PROVIDER_MATRIX_HARNESS.md
  - docs/architecture/SWARMLENS_MASTER_SPEC.md
  - docs/architecture/DGC_STRESS_HARNESS.md
  - docs/plans/2026-04-02-top-level-docs-canon-map.md
improvement:
  room_for_improvement:
    - Group architecture docs by subsystem family if the subtree keeps growing.
    - Separate normative architecture contracts from more advisory structure notes when needed.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: readme
  vault_path: docs/architecture/README.md
  retrieval_terms:
    - docs
    - architecture
    - subsystem
    - index
  evergreen_potential: high
stigmergy:
  meaning: This file makes the architecture subtree legible so subsystem docs stop competing with repo-level canon.
  state: active
  semantic_weight: 0.84
  coordination_comment: Use this file when deciding whether a doc belongs under architecture rather than top-level docs.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# Architecture Index

`docs/architecture/` is for subsystem structure notes and architecture-local operator docs.

Use it for:

- subsystem architecture
- structure notes
- operator-facing technical runbooks that are too specific for top-level canon

Current examples:

- [DGC_STRESS_HARNESS.md](/Users/dhyana/dharma_swarm/docs/architecture/DGC_STRESS_HARNESS.md)
- [ORCHESTRATOR_LEDGERS.md](/Users/dhyana/dharma_swarm/docs/architecture/ORCHESTRATOR_LEDGERS.md)
- [PROVIDER_MATRIX_HARNESS.md](/Users/dhyana/dharma_swarm/docs/architecture/PROVIDER_MATRIX_HARNESS.md)
- [SWARMLENS_MASTER_SPEC.md](/Users/dhyana/dharma_swarm/docs/architecture/SWARMLENS_MASTER_SPEC.md)

Rule:

- if a file is real and useful but too subsystem-local to act as repo-level canon, it belongs here
