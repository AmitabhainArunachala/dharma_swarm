# Phase 4: LanceDB Memory Palace — Build Report

**Date:** April 7, 2026  
**LanceDB Version:** 0.30.2  

## Changes Made

### 1. `dharma_swarm/memory_palace.py` — LanceDB Integration

**New class: `_LanceDBAdapter`** (lines 47–165)
- Thin wrapper around LanceDB providing `upsert()`, `search()`, `count()` methods
- Uses hash-based deterministic vectors as fallback when no real embedder available
- Graceful degradation: if `lancedb` not installed or connection fails, all methods silently return empty/no-op
- Stores documents with text, source, content_hash, ingested_at, metadata_str, and vector columns
- Cross-session persistence: data written by one adapter instance is retrievable by another pointing to the same path

**Modified: `MemoryPalace.__init__()`**
- Added `self._lance: _LanceDBAdapter | None` attribute
- Both persistent (explicit `state_dir`) and ephemeral (tempdir) modes now initialize a `_LanceDBAdapter`
- LanceDB path: `{state_dir}/lancedb/`

**Modified: `MemoryPalace.ingest()`**
- After existing VectorStore upsert, also upserts into LanceDB for cross-session persistence
- Non-fatal: LanceDB failures logged but never block ingestion

**Modified: `MemoryPalace.recall()`**
- After merging lattice, vector, and graph results, also queries LanceDB for cross-session hits
- LanceDB results are deduplicated against existing results and merged before fusion re-ranking
- Non-fatal: LanceDB failures logged but never block recall

**Modified: `MemoryPalace.stats()`**
- Now includes `lancedb` section with `connected`, `document_count`, `db_path`

### 2. `dharma_swarm/orchestrator.py` — SleepTimeAgent Consolidation Wire

**Added after telos_tracker call (line ~2054):**
- Non-fatal `asyncio.create_task()` call to `SleepTimeAgent.consolidate_knowledge()`
- Passes `task_context=result`, `task_outcome={"success": True, "task_title": ..., "source": "task_completion"}`
- Matches the actual `consolidate_knowledge()` signature: `(task_context, task_outcome, llm_client, knowledge_store)`
- Wrapped in try/except — never blocks task completion

### 3. `tests/test_memory_palace.py` — Comprehensive Test Suite

**26 tests total, organized in 5 classes:**

- **TestLanceDBAdapter** (9 tests): Direct adapter tests
  - Connection, upsert/count, empty content rejection, search, empty table search
  - Cross-session persistence (key test), graceful degradation when lancedb unavailable
  - Default vector determinism and normalization

- **TestMemoryPalaceLanceDB** (7 tests): Palace+LanceDB integration
  - Connection with/without state_dir, ingest writes to LanceDB
  - Empty/whitespace content rejection, recall includes LanceDB results
  - Cross-session recall (key integration test), stats includes LanceDB

- **TestMemoryPalaceNoLattice** (4 tests): Backward compatibility
- **TestFusionReranking** (3 tests): Re-ranking logic preserved
- **TestPalaceQueryConfig** (3 tests): Query configuration preserved

## Test Results

### Memory Palace Tests
```
26 passed, 2 warnings in 2.23s
```

### Regression Tests
```
tests/test_orchestrator.py + tests/test_agent_runner.py:
53 passed, 1 failed (pre-existing), 3 warnings in 5.19s
```

The single failure (`test_runner_fails_closed_for_tooling_task_on_api_only_provider`) is pre-existing and unrelated to Phase 4 changes — it involves the agent runner's fail-closed contract for missing artifacts.

## Architecture Notes

- LanceDB complements (not replaces) the existing VectorStore (sqlite-vec + TF-IDF)
- VectorStore handles intra-session hybrid retrieval with real TF-IDF embeddings
- LanceDB handles cross-session persistence with hash-based vectors (semantic embeddings can be swapped in later)
- Both are non-fatal — the system degrades gracefully if either is unavailable
- SleepTimeAgent consolidation is fire-and-forget via `asyncio.create_task()` — it runs the PlugMem-inspired knowledge extraction pipeline (propositions + prescriptions) without blocking the task completion path
