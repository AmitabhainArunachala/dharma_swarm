---
title: Ontology Phase 2 SQLite Unification TODO
path: specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_TODO_2026-03-19.md
slug: ontology-phase-2-sqlite-unification-todo
doc_type: spec
status: reference
summary: 'Pinned execution companion checklist for the ontology Phase 2 SQLite unification spec. Subordinate to specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md.'
source:
  provenance: repo_local
  kind: spec
  origin_signals:
  - specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md
  - dharma_swarm/ontology_hub.py
  - tests/test_ontology_hub.py
  - dharma_swarm/ontology_runtime.py
  - tests/test_ontology_runtime_sqlite.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- verification
- frontend_engineering
inspiration:
- verification
- operator_runtime
- product_surface
connected_python_files:
- dharma_swarm/ontology_hub.py
- tests/test_ontology_hub.py
- dharma_swarm/ontology_runtime.py
- tests/test_ontology_runtime_sqlite.py
- dharma_swarm/ontology.py
connected_python_modules:
- dharma_swarm.ontology_hub
- tests.test_ontology_hub
- dharma_swarm.ontology_runtime
- tests.test_ontology_runtime_sqlite
- dharma_swarm.ontology
connected_relevant_files:
- specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md
- specs/README.md
- dharma_swarm/ontology_hub.py
- tests/test_ontology_hub.py
- dharma_swarm/ontology_runtime.py
- tests/test_ontology_runtime_sqlite.py
improvement:
  room_for_improvement:
  - Keep checklist semantics subordinate to the canonical ontology spec.
  - Archive or demote this companion if a later wave makes the checklist obsolete.
  - Link future verification reruns back to the governing spec rather than treating this file as standalone truth.
  next_review_at: '2026-04-05T12:00:00+09:00'
pkm:
  note_class: checklist
  vault_path: specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_TODO_2026-03-19.md
  retrieval_terms:
  - specs
  - ontology
  - phase2
  - sqlite
  - unification
  - todo
  - companion checklist
  - execution
  evergreen_potential: high
stigmergy:
  meaning: This file is an execution companion checklist for the ontology Phase 2 spec and should be used as subordinate implementation tracking, not independent canonical truth.
  state: reference
  semantic_weight: 0.72
  coordination_comment: 'Pinned companion checklist for specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md.'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_TODO_2026-03-19.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: constraint_and_design_trace
curation:
  last_frontmatter_refresh: '2026-04-03T20:34:00+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file: 
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Ontology Phase 2 SQLite Unification TODO

Date: 2026-03-19
Status: pinned execution companion checklist
Canonical spec: `specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md`

This file is a companion checklist for the canonical ontology Phase 2 spec.
Use the spec as current contract truth and this file as execution tracking.

Progress update:

- Workstream A is complete
- Workstream B is complete
- Workstream C compatibility import/export path is complete
- Workstream D is complete
- Workstream E is complete
- Workstream F is complete
- Verification gate is complete

## 1. Rule Of Engagement

Do not widen this phase into:

- Ontology MCP
- ConceptGraph merge
- intelligence adapters
- dashboard redesign
- broad runtime writeback refactors

Finish SQLite durability and convergence first.

## 2. Workstream A: Introduce SQLite Ontology Store

- [x] Create `dharma_swarm/ontology_hub.py`
- [x] Add `_meta`, `objects`, `links`, `action_log`, and `objects_fts`
- [x] Implement `store_object()`
- [x] Implement `store_link()`
- [x] Implement `store_action()`
- [x] Implement `load_object()`
- [x] Implement `load_objects_by_type()`
- [x] Implement `search_objects()`
- [x] Implement `load_into_registry()`
- [x] Implement `sync_from_registry()`
- [x] Add `tests/test_ontology_hub.py`

## 3. Workstream B: Rewire Shared Runtime Persistence

- [x] Update `dharma_swarm/ontology_runtime.py` to use SQLite as canonical store
- [x] Keep `get_shared_registry()` public contract unchanged
- [x] Keep `persist_shared_registry()` public contract unchanged
- [x] Add canonical DB path resolution
- [x] Load schema from `OntologyRegistry.create_dharma_registry()`
- [x] Load live instances from SQLite into the shared registry
- [x] Add `tests/test_ontology_runtime_sqlite.py`

## 4. Workstream C: Legacy JSON Import

- [x] Detect first-run empty DB
- [x] Import legacy `ontology.json` into SQLite if present
- [x] Mark migration completion in `_meta`
- [x] Ensure repeated startups do not re-import
- [x] Keep JSON as fallback export or migration input only

## 5. Workstream D: Validated Exact-ID Upsert

- [x] Add `put_object()` to `dharma_swarm/ontology.py`
- [x] Validate exact-ID create path against registered type
- [x] Support exact-ID update path without bypassing validation
- [x] Patch `dharma_swarm/custodians.py` to stop writing `registry._objects[...]`
- [x] Search for and remove any remaining production `._objects` writes

## 6. Workstream E: Shared Lineage DB

- [x] Change `LineageGraph` default DB path to the shared ontology DB
- [x] Update `dharma_swarm/swarm.py` to stop pointing at separate `lineage.db`
- [x] Verify lineage tables coexist cleanly with ontology tables
- [x] Update lineage tests as needed

## 7. Workstream F: Collapse Split Read Paths

- [x] Replace file-backed ontology reads in `api/routers/graphql_router.py`
- [x] Use shared registry queries for ontology object lookup
- [x] Use shared lineage service for connection/provenance queries where needed
- [x] Verify API, router, and GraphQL tests against the unified path

## 8. Verification Gate

- [x] Run `pytest -q tests/test_api.py`
- [x] Run `pytest -q tests/test_telic_seam.py`
- [x] Run `pytest -q tests/test_ontology_registry.py`
- [x] Run `pytest -q tests/test_lineage.py`
- [x] Run `pytest -q tests/test_graphql_router.py`
- [x] Run `pytest -q tests/test_ontology_hub.py`
- [x] Run `pytest -q tests/test_ontology_runtime_sqlite.py`

## 9. Definition Of Done

- [x] SQLite is the canonical ontology persistence backend
- [x] Shared registry reloads from SQLite after restart
- [x] Lineage and ontology share one database file
- [x] Production code no longer writes directly to `registry._objects`
- [x] API, TUI, and GraphQL read the same ontology state
- [x] Legacy JSON state can be imported once without manual repair

## 10. If You Are The Next Agent

Recommended execution order:

1. Workstream A
2. Workstream B
3. Workstream C
4. Workstream D
5. Workstream E
6. Workstream F
7. Verification Gate

Do not skip D. If deterministic-ID callers still lack a validated path, the
system will keep regressing back to private store mutation.
