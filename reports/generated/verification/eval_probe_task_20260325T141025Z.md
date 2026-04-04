---
title: Eval Probe Task Report
path: reports/generated/verification/eval_probe_task_20260325T141025Z.md
slug: eval-probe-task-report
doc_type: report
status: active
summary: 'Timestamp: 2026-03-25T14:10:25Z Task: eval probe task Spec refs: - dharma swarm/ecc eval harness.py (eval task roundtrip, eval fitness signal flow) - dharma swarm/message bus.py (cross-process event rail)'
source:
  provenance: repo_local
  kind: report
  origin_signals:
  - dharma_swarm/ecc_eval_harness.py
  - dharma_swarm/message_bus.py
  - tests/test_message_bus.py
  - tests/test_ecc_eval_harness.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- verification
- operations
inspiration:
- verification
- operator_runtime
connected_python_files:
- dharma_swarm/ecc_eval_harness.py
- dharma_swarm/message_bus.py
- tests/test_message_bus.py
- tests/test_ecc_eval_harness.py
- dharma_swarm/dgc_cli.py
connected_python_modules:
- dharma_swarm.ecc_eval_harness
- dharma_swarm.message_bus
- tests.test_message_bus
- tests.test_ecc_eval_harness
- dharma_swarm.dgc_cli
connected_relevant_files:
- dharma_swarm/ecc_eval_harness.py
- dharma_swarm/message_bus.py
- tests/test_message_bus.py
- tests/test_ecc_eval_harness.py
- dharma_swarm/dgc_cli.py
improvement:
  room_for_improvement:
  - 'Surface the decision delta: what should change now because this report exists.'
  - Link findings to exact code, tests, or commits where possible.
  - Distinguish measured facts from operator interpretation.
  - Review whether this file should stay in `reports/verification` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: report
  vault_path: reports/generated/verification/eval_probe_task_20260325T141025Z.md
  retrieval_terms:
  - reports
  - verification
  - eval
  - probe
  - task
  - 20260325t141025z
  - timestamp
  - '2026'
  - 25t14
  - 25z
  - refs
  - ecc
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.6
  coordination_comment: 'Timestamp: 2026-03-25T14:10:25Z Task: eval probe task Spec refs: - dharma swarm/ecc eval harness.py (eval task roundtrip, eval fitness signal flow) - dharma swarm/message bus.py (cross-process event rail)'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising reports/generated/verification/eval_probe_task_20260325T141025Z.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: diagnostic_or_evidence_trace
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
# Eval Probe Task Report

Timestamp: 2026-03-25T14:10:25Z
Task: `eval_probe_task`
Spec refs:
- `dharma_swarm/ecc_eval_harness.py` (`eval_task_roundtrip`, `eval_fitness_signal_flow`)
- `dharma_swarm/message_bus.py` (cross-process event rail)

## Summary

The real eval harness probe initially failed at `fitness_signal_flow` with
`sqlite3.OperationalError: database is locked` on the shared
`~/.dharma/db/messages.db` bus.

Root-cause evidence:
- `python3 -m dharma_swarm.dgc_cli eval run` failed with `fitness_signal_flow = FAIL`.
- A standalone `MessageBus.emit_event("EVAL_PROBE", ...)` on the shared DB reproduced the same lock.
- `lsof` showed long-lived swarm/daemon Python processes holding the message DB and WAL files open.
- `TaskBoard` and `TelemetryPlaneStore` already use stronger SQLite contention handling than `MessageBus`.

## Fix

Changed `dharma_swarm/message_bus.py` to make the event rail contention-tolerant:
- added connection open helper with `timeout=30s`
- applied per-connection `busy_timeout=30000` and `synchronous=NORMAL`
- added bounded retry for transient `database is locked` errors
- applied the retry path to `emit_event()` and `consume_events()`

Added regression coverage in `tests/test_message_bus.py`:
- `test_emit_event_retries_transient_database_lock`

## Verification

Passed:
- `pytest -q tests/test_message_bus.py`
- `pytest -q tests/test_ecc_eval_harness.py`
- `python3 -m dharma_swarm.dgc_cli eval run`

Final real-harness result:
- `14/14` evals passed
- `fitness_signal_flow` recovered to `PASS`
- `pass@1 = 100%`

## Memory Survival Note

Requested externalization targets `~/.dharma/shared` and `~/.dharma/witness`
were not writable in this sandbox, so this report and the `.codex/memories`
mirror were written instead to avoid losing the finding.
