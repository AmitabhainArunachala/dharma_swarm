# Ontology Phase 2 SQLite Unification Spec

Date: 2026-03-19
Status: active implementation packet
Scope: ontology durability, queryability, and convergence

## 1. Purpose

Phase 1 established a shared in-process ontology singleton.

Phase 2 makes that singleton durable, queryable, and authoritative by moving
live ontology state off JSON snapshots and onto a SQLite-backed runtime store.

This packet is the canonical spec for that work.

## 2. Verified Starting Point

As of this packet, the repo state is:

- Shared registry singleton exists in `dharma_swarm/ontology_runtime.py`
- API startup preloads the shared registry in `api/main.py`
- API and router reads largely use the shared registry
- `TelicSeam` uses the shared registry and persists after writes
- `ontology_agents.py` uses validated `create_object()` / `update_object()`
- TUI ontology reads now use the shared registry
- Default ontology persistence is still JSON at `~/.dharma/ontology.json`
- Lineage persistence is separate SQLite at `~/.dharma/lineage.db`
- `OntologyHub` is not present in the current tree and must be introduced in
  this phase
- One production write bypass remains: `custodians.py` still writes
  `registry._objects[...] = obj` on the create path

This means the ontology is shared, but it is not yet backed by one canonical
durable operational plane.

## 3. Objective

Make the ontology runtime work like this:

1. Schema loads from code
2. Live objects, links, and action log load from SQLite
3. Lineage uses the same SQLite database file
4. Callers continue to use `get_shared_registry()` and
   `persist_shared_registry()`
5. No production caller writes directly to `registry._objects`

## 4. Non-Goals

This phase must not widen into:

- Ontology MCP server work
- ConceptGraph unification
- UI redesign
- Full mandatory ontology writeback membrane for orchestrator/task board
- Intelligence adapter work
- Replacing `ontology.py` as the schema authority

## 5. Canonical Architecture After Phase 2

### 5.1 Schema Authority

`dharma_swarm/ontology.py`

This remains the only source of truth for:

- `ObjectType`
- `LinkDef`
- `ActionDef`
- validation rules
- security and telos metadata

SQLite stores live instances, not schema definitions.

### 5.2 Runtime Ontology Store

Create:

- `dharma_swarm/ontology_hub.py`

Responsibilities:

- persist `OntologyObj` instances
- persist `Link` instances
- persist `ActionExecution` log rows
- provide FTS-backed object search
- load DB state into an `OntologyRegistry`
- flush an in-memory `OntologyRegistry` back into SQLite

### 5.3 Shared Runtime Access Layer

Update:

- `dharma_swarm/ontology_runtime.py`

Responsibilities:

- resolve canonical ontology DB path
- initialize/load the shared runtime registry
- import legacy JSON once when needed
- persist the shared registry into SQLite
- expose a stable public access surface for callers

### 5.4 Shared Lineage Database

Update:

- `dharma_swarm/lineage.py`

Responsibilities:

- keep `LineageGraph` as its own class
- point its default `db_path` at the shared ontology DB
- continue using lineage tables in the same database file

This gives one durable file containing:

- ontology objects
- ontology links
- ontology action log
- lineage edges
- lineage inputs
- lineage outputs

## 6. SQLite Data Model

`ontology_hub.py` should create:

- `_meta`
- `objects`
- `links`
- `action_log`
- `objects_fts`

Suggested columns:

### 6.1 `objects`

- `id TEXT PRIMARY KEY`
- `type_name TEXT NOT NULL`
- `properties TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `created_by TEXT NOT NULL`
- `updated_at TEXT NOT NULL`
- `version INTEGER NOT NULL`

### 6.2 `links`

- `id TEXT PRIMARY KEY`
- `link_name TEXT NOT NULL`
- `source_id TEXT NOT NULL`
- `source_type TEXT NOT NULL`
- `target_id TEXT NOT NULL`
- `target_type TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- `created_by TEXT NOT NULL`
- `metadata TEXT NOT NULL`
- `witness_quality REAL NOT NULL`

### 6.3 `action_log`

- `id TEXT PRIMARY KEY`
- `action_name TEXT NOT NULL`
- `object_id TEXT NOT NULL`
- `object_type TEXT NOT NULL`
- `input_params TEXT NOT NULL`
- `result TEXT NOT NULL`
- `gate_results TEXT NOT NULL`
- `executed_by TEXT NOT NULL`
- `executed_at TEXT NOT NULL`
- `duration_ms REAL NOT NULL`
- `error TEXT NOT NULL`

### 6.4 `objects_fts`

FTS5 virtual table over:

- `type_name`
- serialized searchable object content

## 7. Required Public Interfaces

### 7.1 `OntologyHub`

Required minimum surface:

- `OntologyHub(db_path: Path | None = None)`
- `load_into_registry(registry: OntologyRegistry) -> dict[str, int]`
- `sync_from_registry(registry: OntologyRegistry) -> dict[str, int]`
- `store_object(obj: OntologyObj) -> None`
- `store_link(link: Link) -> None`
- `store_action(execution: ActionExecution) -> None`
- `load_object(obj_id: str) -> OntologyObj | None`
- `load_objects_by_type(type_name: str, limit: int = 100) -> list[OntologyObj]`
- `search_objects(query: str, type_name: str | None = None, limit: int = 50) -> list[OntologyObj]`
- `close() -> None`

### 7.2 `ontology_runtime.py`

Keep these public names stable:

- `ontology_path(...)`
- `get_shared_registry(...)`
- `persist_shared_registry(...)`
- `reset_shared_registry()`

The implementation may switch from JSON to SQLite under the hood, but callers
must not need to change.

## 8. Required Registry API Addition

Add a validated exact-ID upsert path to `dharma_swarm/ontology.py`.

Suggested API:

- `put_object(obj: OntologyObj, *, updated_by: str = "system") -> tuple[OntologyObj | None, list[str]]`

Reason:

`create_object()` auto-generates IDs. Some subsystems need stable deterministic
IDs, which currently pressures them to bypass validation and write directly to
`registry._objects`.

`put_object()` must:

- validate against the registered type
- insert exact object ID when absent
- update mutable fields when present
- increment version or preserve version by explicit rule
- return validation errors instead of bypassing them

## 9. Migration Plan

### Step 1: Introduce the SQLite runtime store

Create `dharma_swarm/ontology_hub.py` with unit tests.

### Step 2: Rewire shared runtime access

Update `ontology_runtime.py` so:

- canonical path is a SQLite DB path
- schema still comes from `OntologyRegistry.create_dharma_registry()`
- live objects/links/actions load from SQLite
- persistence writes to SQLite

### Step 3: Preserve legacy state

Add one-time import behavior:

- if DB is empty
- and legacy `ontology.json` exists
- then import JSON into SQLite
- record completion in `_meta`

Do not require operators to manually migrate first.

### Step 4: Unify lineage database location

Update `lineage.py` default path to the same DB file used by
`ontology_runtime.py`.

Update runtime callers, especially:

- `dharma_swarm/swarm.py`

### Step 5: Eliminate direct object-store writes

Add `put_object()` and patch production callers that still bypass validation,
especially:

- `dharma_swarm/custodians.py`

### Step 6: Remove split ontology read paths

Update routes that still read ad hoc file-backed ontology views, especially:

- `api/routers/graphql_router.py`

These reads should use the shared registry and lineage service instead.

## 10. Files To Create

- `dharma_swarm/ontology_hub.py`
- `tests/test_ontology_hub.py`
- `tests/test_ontology_runtime_sqlite.py`

## 11. Files To Update

- `dharma_swarm/ontology_runtime.py`
- `dharma_swarm/ontology.py`
- `dharma_swarm/lineage.py`
- `dharma_swarm/telic_seam.py`
- `dharma_swarm/swarm.py`
- `dharma_swarm/custodians.py`
- `dharma_swarm/api.py`
- `api/main.py`
- `api/routers/graphql_router.py`
- relevant tests that currently assume JSON persistence

## 12. Acceptance Criteria

Phase 2 is done when all of the following are true:

- shared ontology state survives process restart from SQLite
- lineage survives process restart from the same SQLite file
- API, TUI, and GraphQL read the same ontology state
- `TelicSeam` writes are durable across restart
- production code does not write directly to `registry._objects`
- legacy `ontology.json` can be imported automatically on first load
- targeted ontology, API, and lineage tests pass

## 13. Verification Minimum

At minimum, the implementation must pass:

- `tests/test_api.py`
- `tests/test_telic_seam.py`
- `tests/test_ontology_registry.py`
- `tests/test_lineage.py`
- `tests/test_graphql_router.py`
- new `tests/test_ontology_hub.py`
- new `tests/test_ontology_runtime_sqlite.py`

## 14. Risks

### 14.1 Schema drift

If SQLite starts storing schema definitions, code and runtime truth can diverge.

Mitigation:

- store instances only
- regenerate schema from code on load

### 14.2 Split persistence truth

If JSON remains a peer persistence backend, operators will not know which copy
is authoritative.

Mitigation:

- SQLite becomes canonical
- JSON becomes import-only or emergency export

### 14.3 Validation bypass recurrence

If deterministic-ID callers cannot use a validated API, they will keep writing
to private stores.

Mitigation:

- add `put_object()`
- block new production `._objects` writes in review

## 15. Agent Instructions

Any agent working this phase should:

- read this file first
- then read `specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_TODO_2026-03-19.md`
- avoid widening scope into MCP, ConceptGraph, or UI
- keep `ontology.py` authoritative for schema
- prefer small, test-backed slices over broad rewrites
