---
title: DHARMA Spec Forge Index
path: spec-forge/README.md
slug: dharma-spec-forge-index
doc_type: readme
status: canonical
summary: Entry point for incubating, draft, and forge-stage specifications in the DHARMA SWARM repo.
source:
  provenance: repo_local
  kind: readme
  origin_signals:
  - spec-forge/consciousness-computing/INTEGRATION_SPEC.md
  - spec-forge/self-evolving-organism/ARCHITECTURE.md
  - spec-forge/self-evolving-organism/CONSTITUTION.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- knowledge_management
- verification
- operations
inspiration:
- verification
- operator_runtime
connected_relevant_files:
- spec-forge/consciousness-computing/INTEGRATION_SPEC.md
- spec-forge/self-evolving-organism/ARCHITECTURE.md
- spec-forge/self-evolving-organism/CONSTITUTION.md
- spec-forge/self-evolving-organism/TRACEABILITY.md
- specs/README.md
- docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
improvement:
  room_for_improvement:
  - Keep forge material explicitly draft and non-normative.
  - Promote only mature contracts into `specs/`.
  - Add sub-indexes if forge families keep growing.
  next_review_at: '2026-04-02T23:59:00+09:00'
pkm:
  note_class: readme
  vault_path: spec-forge/README.md
  retrieval_terms:
  - spec-forge
  - forge
  - draft
  - incubating
  - spec
  evergreen_potential: high
stigmergy:
  meaning: This file defines what kind of documents belong in the forge layer before they become normative specs.
  state: canonical
  semantic_weight: 0.9
  coordination_comment: Use this file to decide whether an emerging design belongs in `spec-forge/` instead of `specs/`.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# DHARMA Spec Forge Index

`spec-forge/` is the incubation lane for emerging specifications.

This directory is for documents that are still being forged into future contract truth. It is not the same as `specs/`.

## What Belongs Here

Use `spec-forge/` for:

- draft specs
- exploratory architecture
- build handoff material that still shapes the design
- candidate contracts that are not ready to be cited as current truth

If a document is already the repo's normative contract for a subsystem, it should live in `specs/` instead.

## Current Forge Families

- `spec-forge/self-evolving-organism/`: active forge cluster for the self-evolving organism build
- `spec-forge/consciousness-computing/`: narrower integration and RFC-style material
- `spec-forge/micro-saas-research/`: exploratory research-to-spec incubation material

## Forge vs Specs

`specs/`:

- normative
- current contract truth
- formal, protocol, or verification-oriented

`spec-forge/`:

- incubating
- exploratory
- draft or pre-canonical

Promotion from `spec-forge/` to `specs/` should happen only when a document is stable enough to act as current truth rather than design exploration.

## Cross-Reference

For the normative specification layer, see [specs/README.md](/Users/dhyana/dharma_swarm/specs/README.md).

For the repo-wide ontology that separates canon, plans, reports, archive, and forge material, see [REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md).
