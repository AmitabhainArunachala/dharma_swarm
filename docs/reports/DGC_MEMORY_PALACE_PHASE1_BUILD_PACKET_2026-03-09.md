# DGC Memory Palace Phase 1 Build Packet

Date: 2026-03-09  
Phase: canonical event spine plus unified index  
Primary roadmap: [`/Users/dhyana/dharma_swarm/docs/reports/DGC_MEMORY_PALACE_EXECUTION_ROADMAP_2026-03-09.md`](/Users/dhyana/dharma_swarm/docs/reports/DGC_MEMORY_PALACE_EXECUTION_ROADMAP_2026-03-09.md)

## A. Mission

- `OBSERVED`: the canonical runtime already has the ingress seams Phase 1 needs: validated runtime envelopes in [`/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L40`](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L40), orchestrator lifecycle emission in [`/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py#L188`](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py#L188), bus publish/fan-out in [`/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L186`](/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L186), and typed artifacts in [`/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L256`](/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L256).
- `OBSERVED`: HYPER and SCOUT agree the missing canonical substrate is event ingress plus unified retrieval, not another ad hoc memory silo. [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L16`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_HYPER_REVIEW_2026-03-09.md#L16) [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L13`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L13) [`/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L21`](/Users/dhyana/dharma_swarm/docs/reports/DGC_TO_DHARMA_SWARM_SCOUT_REPORT_2026-03-09.md#L21)

Phase 1 delivers one canonical substrate that can later power retrieval, temporal ranking, feedback logging, and graph expansion.

## B. Files To Create

- `dharma_swarm/engine/event_memory.py`
- `dharma_swarm/engine/unified_index.py`
- `dharma_swarm/engine/chunker.py`
- `tests/test_event_memory.py`
- `tests/test_unified_index.py`
- `tests/test_event_memory_integration.py`

## C. Existing Files To Touch

- [`/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L68`](/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L68)
- [`/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L243`](/Users/dhyana/dharma_swarm/dharma_swarm/context.py#L243)
- [`/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py#L188`](/Users/dhyana/dharma_swarm/dharma_swarm/orchestrator.py#L188)

Do not modify:

- [`/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L17`](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L17) contract semantics
- [`/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L94`](/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L94) into the persistence layer
- [`/Users/dhyana/dharma_swarm/dharma_swarm/memory.py#L77`](/Users/dhyana/dharma_swarm/dharma_swarm/memory.py#L77) table schema unless explicitly required later

## D. Required Storage Schema

Use one SQLite database for Phase 1.

Required tables:

1. `event_log`
   - `event_id TEXT PRIMARY KEY`
   - `session_id TEXT NOT NULL`
   - `trace_id TEXT NOT NULL`
   - `event_type TEXT NOT NULL`
   - `source TEXT NOT NULL`
   - `agent_id TEXT NOT NULL`
   - `emitted_at TEXT NOT NULL`
   - `payload_json TEXT NOT NULL`
   - `checksum TEXT NOT NULL`
   - `ingested_at TEXT NOT NULL`

2. `source_documents`
   - `doc_id TEXT PRIMARY KEY`
   - `source_kind TEXT NOT NULL`
   - `source_path TEXT NOT NULL`
   - `source_hash TEXT NOT NULL`
   - `source_ref TEXT DEFAULT ''`
   - `metadata_json TEXT NOT NULL`
   - `updated_at TEXT NOT NULL`

3. `source_chunks`
   - `chunk_id TEXT PRIMARY KEY`
   - `doc_id TEXT NOT NULL`
   - `chunk_index INTEGER NOT NULL`
   - `text TEXT NOT NULL`
   - `metadata_json TEXT NOT NULL`
   - `chunk_hash TEXT NOT NULL`
   - foreign key to `source_documents(doc_id)`

4. `index_runs`
   - `run_id TEXT PRIMARY KEY`
   - `source_kind TEXT NOT NULL`
   - `started_at TEXT NOT NULL`
   - `completed_at TEXT`
   - `status TEXT NOT NULL`
   - `stats_json TEXT NOT NULL`

Required indexes:

- `event_log(session_id, emitted_at)`
- `event_log(trace_id, emitted_at)`
- `event_log(event_type, emitted_at)`
- `source_documents(source_kind, source_path)`
- `source_documents(source_hash)`
- `source_chunks(doc_id, chunk_index)`

## E. Required Public Interfaces

### `EventMemoryStore`

Methods:

- `init_db() -> None`
- `ingest_envelope(envelope: RuntimeEnvelope) -> bool`
- `replay_session(session_id: str, limit: int = 1000) -> list[dict[str, Any]]`
- `replay_trace(trace_id: str, limit: int = 1000) -> list[dict[str, Any]]`
- `search_events(query: str, limit: int = 20) -> list[dict[str, Any]]`

Rules:

- reject invalid envelopes using the canonical validator in [`/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L167`](/Users/dhyana/dharma_swarm/dharma_swarm/runtime_contract.py#L167)
- treat duplicate `event_id` as a no-op, not an error
- preserve original payload and checksum verbatim

### `UnifiedIndex`

Methods:

- `index_document(source_kind: str, source_path: str, text: str, metadata: dict[str, Any]) -> str`
- `index_note_file(path: Path, metadata: dict[str, Any] | None = None) -> str`
- `search(query: str, limit: int = 10, filters: dict[str, Any] | None = None) -> list[tuple[KnowledgeRecord, float]]`
- `reindex_changed(paths: list[Path]) -> dict[str, int]`
- `stats() -> dict[str, int]`

Rules:

- preserve the `KnowledgeStore` abstraction in [`/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L68`](/Users/dhyana/dharma_swarm/dharma_swarm/engine/knowledge_store.py#L68)
- do not break current tests in [`/Users/dhyana/dharma_swarm/tests/test_engine_knowledge_store.py#L12`](/Users/dhyana/dharma_swarm/tests/test_engine_knowledge_store.py#L12)
- chunking must be deterministic for unchanged documents

## F. Phase 1 Data Sources

Initial sources only:

1. runtime envelopes
   - source: canonical runtime contract
   - ingress path: orchestrator lifecycle and later session bridge

2. message artifacts
   - source: bus attachments
   - ingress path: existing artifact support in [`/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L256`](/Users/dhyana/dharma_swarm/dharma_swarm/message_bus.py#L256)

3. note or markdown files
   - source: canonical memory-vault or research-note paths
   - ingress path: explicit index calls, not filesystem watchers yet

Do not ingest yet:

- graph edges
- FSRS state
- summarization layers
- multimodal proxies

## G. Chunking Rules

- `OBSERVED`: the retrieval research recommends markdown-header-aware chunking, not generic sliding windows. [`/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L439`](/Users/dhyana/Downloads/pkm_research_domains_1_3.md#L439)

Required behavior:

- split on markdown headers first
- preserve header ancestry in chunk metadata
- cap chunk size to a deterministic token-ish bound
- never emit empty chunks
- hash chunk text plus normalized metadata for dedupe

## H. Integration Points

1. `orchestrator.py`
   - after `_emit_lifecycle_event`, allow optional event-memory ingestion hook
   - keep ingestion best-effort and non-blocking

2. `context.py`
   - replace or augment `read_memory_context()` with unified-index reads for recent and relevant memory
   - keep the existing fallback behavior when the index is absent

3. `knowledge_store.py`
   - keep current interface stable
   - allow a stronger backend or facade later without contract breakage

## I. Test Gates

Required tests:

1. `test_ingest_valid_runtime_envelope`
2. `test_duplicate_event_id_is_ignored`
3. `test_replay_session_returns_ordered_events`
4. `test_index_document_is_incremental_for_unchanged_source`
5. `test_markdown_chunking_preserves_header_metadata`
6. `test_unified_index_search_returns_chunk_metadata`
7. `test_context_falls_back_when_index_absent`
8. `test_event_and_note_records_can_coexist_in_one_search_surface`

Integration proof:

- a synthetic task emits lifecycle events through the orchestrator and those events become searchable without modifying message-bus persistence semantics

## J. Delegation Split

### Agent A: storage and replay

- build `EventMemoryStore`
- add schema migration and replay tests

### Agent B: chunking and indexing

- build `chunker.py`
- build `UnifiedIndex`
- add incremental indexing tests

### Agent C: canonical integration

- wire optional hooks into `orchestrator.py`
- wire context fallback into `context.py`
- keep public contracts stable

Principal review required before merge:

- schema names
- event record contract
- chunk metadata contract
- any change to `KnowledgeStore` surface

## K. Definition Of Done

- one canonical SQLite database stores replayable events and indexed text chunks
- search works across indexed documents through a stable facade
- unchanged documents do not re-chunk or duplicate on reindex
- runtime events are replayable by session and trace
- all new tests pass and existing memory/knowledge-store tests remain green

If Phase 1 lands cleanly, Phase 2 can start without revisiting architecture.
