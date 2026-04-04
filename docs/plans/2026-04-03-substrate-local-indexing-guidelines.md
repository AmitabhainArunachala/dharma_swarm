---
title: Substrate Local Indexing Guidelines
path: docs/plans/2026-04-03-substrate-local-indexing-guidelines.md
slug: substrate-local-indexing-guidelines
doc_type: plan
status: active
summary: Defines the local labeling rules for foundations, lodestones, and mode_pack so substrate entrypoints keep canon, orienting material, and operational contract surfaces clearly separated.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/plans/2026-04-02-substrate-layer-policy.md
  - docs/plans/2026-04-03-substrate-directory-cartography.md
  - docs/plans/2026-04-03-substrate-graduation-candidates.md
  - foundations/INDEX.md
  - lodestones/README.md
  - mode_pack/README.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- documentation
- software_architecture
- operations
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-02-substrate-layer-policy.md
- docs/plans/2026-04-03-substrate-directory-cartography.md
- docs/plans/2026-04-03-substrate-graduation-candidates.md
- foundations/INDEX.md
- lodestones/README.md
- mode_pack/README.md
improvement:
  room_for_improvement:
  - Expand this into subtree-specific templates only if local indexes start diverging again.
  - Add examples of bad label drift if future substrate edits become noisy.
  - Keep this guide short and operational rather than philosophical.
  next_review_at: '2026-04-05T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-03-substrate-local-indexing-guidelines.md
  retrieval_terms:
  - substrate
  - indexing
  - labels
  - canon
  - lodestones
  - mode_pack
  evergreen_potential: medium
stigmergy:
  meaning: This file keeps substrate entrypoint language consistent so local indexes do not silently collapse canon, interpretation, and operational contract into one category.
  state: active
  semantic_weight: 0.79
  coordination_comment: Use this guide when editing local substrate indexes or README files.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T20:24:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Substrate Local Indexing Guidelines

## Purpose

The substrate cleanup lane now has policy, cartography, and graduation-watch notes.

This guide makes the next rule explicit:

- local indexes should repeat the same boundary language
- they should not invent new authority categories ad hoc

## Label Set

Use these labels consistently:

### `foundations/`

- conceptual canon
- synthesis
- conceptual reference
- graduation-watch candidate

Avoid:

- runtime truth
- normative implementation truth
- miscellaneous inspiration

### `lodestones/`

- orienting substrate
- seed
- reframe
- bridge
- grounding
- graduation-watch candidate

Avoid:

- settled canon
- final doctrine
- normative product truth

### `mode_pack/`

- operational contract surface
- shared workflow vocabulary
- installer-backed runtime support

Avoid:

- substrate prose
- philosophical canon
- speculative research bucket

## Usage Rule

When editing a local substrate index:

1. name the directory role first
2. name the allowed local categories second
3. name graduation-watch candidates separately from stay-put content
4. avoid describing the whole directory as “canonical” unless the canon type is explicit

## Current Application

This guidance is already reflected in:

- [foundations/INDEX.md](/Users/dhyana/dharma_swarm/foundations/INDEX.md)
- [lodestones/README.md](/Users/dhyana/dharma_swarm/lodestones/README.md)
- [mode_pack/README.md](/Users/dhyana/dharma_swarm/mode_pack/README.md)

## Control Entry Points

- [substrate-layer-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-substrate-layer-policy.md)
- [substrate-directory-cartography.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-substrate-directory-cartography.md)
- [substrate-graduation-candidates.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-substrate-graduation-candidates.md)
