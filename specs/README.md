---
title: DHARMA Specs Index
path: specs/README.md
slug: dharma-specs-index
doc_type: readme
status: canonical
summary: Entry point for formal, protocol, and verification-oriented specifications in the DHARMA SWARM repo.
source:
  provenance: repo_local
  kind: readme
  origin_signals:
  - specs/TaskBoardCoordination.tla
  - specs/KERNEL_CORE_SPEC.md
  - specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- verification
- software_architecture
- knowledge_management
- operations
inspiration:
- verification
- operator_runtime
connected_relevant_files:
- specs/TaskBoardCoordination.tla
- specs/TaskBoardCoordination.cfg
- specs/KERNEL_CORE_SPEC.md
- specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md
- spec-forge/README.md
- docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
improvement:
  room_for_improvement:
  - Keep this directory focused on formal and protocol-level truth.
  - Mark versioned or superseded specs explicitly.
  - Move non-spec planning material elsewhere over time.
  next_review_at: '2026-04-01T23:59:00+09:00'
pkm:
  note_class: readme
  vault_path: specs/README.md
  retrieval_terms:
  - specs
  - verification
  - protocol
  - formal
  evergreen_potential: high
stigmergy:
  meaning: This file declares what counts as a spec in this repo.
  state: canonical
  semantic_weight: 0.95
  coordination_comment: Use this file to decide whether a document belongs in `specs/` or somewhere else.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-01T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# DHARMA Specs Index

`specs/` is not the general design backlog. It is the specification layer.

Files here should be one of:

- formal models
- protocol specs
- invariant definitions
- bounded subsystem specs with clear implementation targets

If a document is mostly a mission brief, planning memo, prompt, or historical note, it belongs elsewhere.

`specs/` is also not the incubation lane. Draft and exploratory spec work belongs in [spec-forge/README.md](/Users/dhyana/dharma_swarm/spec-forge/README.md), not here.

## Priority Specs

Current high-signal specs in this directory:

- [TaskBoardCoordination.tla](/Users/dhyana/dharma_swarm/specs/TaskBoardCoordination.tla) and [TaskBoardCoordination.cfg](/Users/dhyana/dharma_swarm/specs/TaskBoardCoordination.cfg): formal task-board coordination model
- [KERNEL_CORE_SPEC.md](/Users/dhyana/dharma_swarm/specs/KERNEL_CORE_SPEC.md): bounded core-kernel specification
- [ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md](/Users/dhyana/dharma_swarm/specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md): active ontology runtime spec
- [ONTOLOGY_PHASE2_SQLITE_UNIFICATION_TODO_2026-03-19.md](/Users/dhyana/dharma_swarm/specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_TODO_2026-03-19.md): working companion list for that ontology pass
- [STIGMERGY_11_LAYER_SPEC_2026-03-23.md](/Users/dhyana/dharma_swarm/specs/STIGMERGY_11_LAYER_SPEC_2026-03-23.md): structured subsystem spec

## Classification Rules

- Formal artifacts such as `.tla`, `.cfg`, and machine-checkable models belong here.
- Narrow subsystem specifications can live here if they define durable contracts or invariants.
- Versioned specs must clearly state whether they supersede an earlier version.
- Broad product strategy, prompts, and implementation plans do not belong here.

## Relation To The Rest Of The Repo

- `README.md` and `CLAUDE.md` define operator-level orientation.
- `docs/` defines prose canon, plans, prompts, and archive material.
- `reports/` stores historical outputs and audits.
- `specs/` defines precise contracts that should outlive any one planning wave.
- `spec-forge/` is the draft and incubation lane for candidate specs that are not yet normative.

## Specs vs Spec-Forge

Use `specs/` when a document is:

- normative
- protocol-defining
- intended to be cited as current contract truth
- expected to survive beyond one build wave

Use `spec-forge/` when a document is:

- exploratory
- incubating
- draft architecture or build handoff material
- still being forged into a future spec rather than serving as current truth

## Cleanup Direction

This directory still contains some mixed-purpose material. The cleanup goal is:

- keep formal and protocol-level truth here
- move planning-heavy docs out over time
- make supersession and status explicit for every versioned spec
- keep `spec-forge/` as the place where emerging specs mature before entering `specs/`

For the governing repo-wide ontology, see [REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md).
