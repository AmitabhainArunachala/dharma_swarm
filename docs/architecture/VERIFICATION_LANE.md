---
title: Verification Lane
path: docs/architecture/VERIFICATION_LANE.md
slug: verification-lane
doc_type: note
status: active
summary: Read-only verifier for the active DGC + dharma swarm system.
source:
  provenance: repo_local
  kind: note
  origin_signals:
  - scripts/start_verification_lane.sh
  - scripts/stop_verification_lane.sh
  - scripts/split_brain_guard.sh
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
connected_python_files:
- dharma_swarm/cli.py
connected_python_modules:
- dharma_swarm.cli
connected_relevant_files:
- scripts/start_verification_lane.sh
- scripts/stop_verification_lane.sh
- scripts/split_brain_guard.sh
- dharma_swarm/cli.py
- docs/archive/AGENT_SWARM_SYNTHESIS.md
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `.` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: note
  vault_path: docs/architecture/VERIFICATION_LANE.md
  retrieval_terms:
  - verification
  - lane
  - read
  - only
  - verifier
  - dgc
  - system
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: active
  semantic_weight: 0.6
  coordination_comment: Read-only verifier for the active DGC + dharma swarm system.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/architecture/VERIFICATION_LANE.md reinforces its salience without needing a separate message.
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
# Verification Lane

Read-only verifier for the active DGC + dharma_swarm system.

It checks:
- process liveness (`overnight`, `daemon`, `sentinel`)
- command health (`dgc status`, `dgc swarm overnight status`, `dharma_swarm.cli status`)
- task/memory DB state
- log freshness

## Start

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/start_verification_lane.sh 8
```

Optional faster loop:

```bash
VERIFY_INTERVAL=120 bash scripts/start_verification_lane.sh 8
```

Override `dgc` binary explicitly (if needed):

```bash
DGC_BIN=/opt/homebrew/bin/dgc VERIFY_INTERVAL=120 bash scripts/start_verification_lane.sh 8
```

## Stop

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/stop_verification_lane.sh
```

## Outputs

Run metadata:

```bash
cat ~/.dharma/verification_lane_run_dir.txt
```

Per-run files:
- `report.md`
- `snapshots.jsonl`
- `verify.log`

## Split-Brain Guard

Check for legacy `DHARMIC_GODEL_CLAW` / `dgc-core` processes:

```bash
cd /Users/dhyana/dharma_swarm
scripts/split_brain_guard.sh
```

Attempt cleanup:

```bash
cd /Users/dhyana/dharma_swarm
scripts/split_brain_guard.sh --fix
```
