---
title: Orchestrator Ledgers
path: docs/architecture/ORCHESTRATOR_LEDGERS.md
slug: orchestrator-ledgers
doc_type: documentation
status: active
summary: This documents the new session-scoped orchestration ledgers.
source:
  provenance: repo_local
  kind: documentation
  origin_signals: []
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
inspiration:
- operator_runtime
connected_python_files:
- dharma_swarm/message_bus.py
- dharma_swarm/session_event_bridge.py
- dharma_swarm/session_ledger.py
- tests/test_message_bus.py
- tests/test_message_bus_artifacts.py
connected_python_modules:
- dharma_swarm.message_bus
- dharma_swarm.session_event_bridge
- dharma_swarm.session_ledger
- tests.test_message_bus
- tests.test_message_bus_artifacts
connected_relevant_files:
- dharma_swarm/message_bus.py
- dharma_swarm/session_event_bridge.py
- dharma_swarm/session_ledger.py
- tests/test_message_bus.py
- tests/test_message_bus_artifacts.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/architecture/ORCHESTRATOR_LEDGERS.md
  retrieval_terms:
  - orchestrator
  - ledgers
  - documents
  - new
  - session
  - scoped
  - orchestration
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.55
  coordination_comment: This documents the new session-scoped orchestration ledgers.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/architecture/ORCHESTRATOR_LEDGERS.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-01T00:43:19+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file: 
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Orchestrator Ledgers

This documents the new session-scoped orchestration ledgers.

## What gets written

- `task_ledger.jsonl`
  - dispatch assignment/blocking events
  - result persistence events
- `progress_ledger.jsonl`
  - task start/complete/fail events
  - normalized failure signatures

## Default location

`~/.dharma/ledgers/<session_id>/`

Where `<session_id>` defaults to UTC timestamp (`YYYYMMDDTHHMMSSZ`).

## Environment overrides

- `DGC_LEDGER_DIR`:
  - base directory for ledger sessions
- `DGC_SESSION_ID`:
  - explicit session folder name

## Hook-ready lifecycle stream

When `message_bus.publish()` is available, the orchestrator emits topic events:

- Topic: `orchestrator.lifecycle`
- Event metadata includes:
  - `event`
  - `task_id`
  - `agent_id`
  - event-specific details (e.g. `failure_signature`, `duration_sec`)

## Event names

- Task ledger:
  - `dispatch_assigned`
  - `dispatch_blocked`
  - `result_persisted`
- Progress ledger:
  - `task_started`
  - `task_completed`
  - `task_failed`
  - `task_blocked`
