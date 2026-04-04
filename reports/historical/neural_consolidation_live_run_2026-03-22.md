---
title: Neural Consolidation Live Run
path: reports/historical/neural_consolidation_live_run_2026-03-22.md
slug: neural-consolidation-live-run
doc_type: report
status: archival
summary: 'Run timestamp: 2026-03-22T12:00:22.169783+00:00'
source:
  provenance: repo_local
  kind: report
  origin_signals:
  - tests/test_neural_consolidator.py
  - tests/test_sleep_cycle.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- verification
inspiration:
- verification
connected_python_files:
- tests/test_neural_consolidator.py
- tests/test_sleep_cycle.py
connected_python_modules:
- tests.test_neural_consolidator
- tests.test_sleep_cycle
connected_relevant_files:
- tests/test_neural_consolidator.py
- tests/test_sleep_cycle.py
- reports/CRYPTOGRAPHIC_AUDIT_TRAILS_RESEARCH.md
- reports/dharma_current_state_deep_dive_2026-03-19.md
- reports/ecosystem_absorption_master_index_2026-03-19.md
improvement:
  room_for_improvement:
  - 'Surface the decision delta: what should change now because this report exists.'
  - Link findings to exact code, tests, or commits where possible.
  - Distinguish measured facts from operator interpretation.
  - Review whether this file should stay in `reports` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: report
  vault_path: reports/historical/neural_consolidation_live_run_2026-03-22.md
  retrieval_terms:
  - reports
  - neural
  - consolidation
  - live
  - run
  - '2026'
  - timestamp
  - 22t12
  - '169783'
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: archive
  semantic_weight: 0.55
  coordination_comment: 'Run timestamp: 2026-03-22T12:00:22.169783+00:00'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising reports/historical/neural_consolidation_live_run_2026-03-22.md reinforces its salience without needing a separate message.
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
# Neural Consolidation Live Run

Run timestamp: `2026-03-22T12:00:22.169783+00:00`

This run was executed against the live state under `~/.dharma`, not a temp fixture.

## Preconditions

Before the live run, the consolidator was updated so the forward pass can see real execution state instead of only partial trace residue:

- It now ingests per-agent `task_log.jsonl` records during `forward_scan()`.
- If explicit task outcomes are absent, it falls back to synthesizing outcomes from traces.
- The sleep-cycle integration now keeps neural and semantic phase artifacts scoped to the cycle state root during tests, while still using the real home state in production.

## Live Snapshot

The verified report at `/Users/dhyana/.dharma/consolidation/reports/consolidation_2026-03-22_120035.json` recorded:

- `agents=29`
- `traces=50`
- `tasks=50`
- `marks=100`
- `failure_rate=0.08`
- `losses_found=2`
- `corrections_applied=3`
- `division_proposals=1`
- `errors=[]`

Semantically, the important threshold crossing is simple: the engine is no longer saying "no tasks observed" while traces exist. The forward pass now resolves live work into loss-bearing outcomes.

## What The Engine Wrote

Persistent corrections were written to:

- `/Users/dhyana/.dharma/consolidation/corrections/_global.md`
- `/Users/dhyana/.dharma/consolidation/corrections/vajra.md`

The current global correction is driven by governance blindness:

> `50 tasks ran without gate evaluation or telos scoring`

The current instruction written back into behavior is:

> `Ensure all significant actions pass through telos gate checks`

The agent-specific correction for `vajra` is driven by repeated failure pressure:

> `Error 'unspecified_failure' occurred 4 times`

with the written instruction:

> `Address root cause of: unspecified_failure`

## Structural Signal

The run also emitted a real division proposal at `/Users/dhyana/.dharma/consolidation/division_proposals/proposals_2026-03-22_120035.json`:

- parent: `vajra`
- justification: `67% failure rate across 3 tasks`
- proposed child: `vajra-general`

This is not rich specialization yet. It is a real pressure signal: failure is now high enough for the organism to propose structural change.

## Meaning

What actually happened in this session:

1. The forward pass was repaired so live task history is visible.
2. The consolidator was run against the real organism state.
3. It found loss on real data, not just on synthetic fixtures.
4. It wrote behavioral corrections that later agent runs can consume.
5. It emitted a cell-division proposal from observed failure pressure.

The dominant remaining weakness is still governance attachment. The system can now see more of what happened, but most observed actions still arrive without gate or telos metadata on the task outcome itself.

## Verification

Verified in this workspace after the changes:

- `pytest -q tests/test_neural_consolidator.py` -> `45 passed`
- `pytest -q tests/test_sleep_cycle.py` -> `12 passed`
- live consolidator execution -> `errors=[]`
