---
title: Overnight Autopilot
path: docs/archive/OVERNIGHT_AUTOPILOT.md
slug: overnight-autopilot
doc_type: report
status: archival
summary: 'Primary goal: keep dharma swarm active all night with periodic status, task feed, and quality checks.'
source:
  provenance: repo_local
  kind: report
  origin_signals:
  - scripts/start_overnight.sh
  - scripts/stop_overnight.sh
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- software_architecture
inspiration:
- knowledge_management
- software_architecture
connected_python_files:
- scripts/overnight_autopilot.py
- scripts/codex_overnight_autopilot.py
- scripts/live_organism_run.py
- dharma_swarm/event_log.py
- dharma_swarm/loop_supervisor.py
connected_python_modules:
- scripts.overnight_autopilot
- scripts.codex_overnight_autopilot
- scripts.live_organism_run
- dharma_swarm.event_log
- dharma_swarm.loop_supervisor
connected_relevant_files:
- scripts/start_overnight.sh
- scripts/stop_overnight.sh
- scripts/overnight_autopilot.py
- scripts/codex_overnight_autopilot.py
- scripts/live_organism_run.py
improvement:
  room_for_improvement:
  - 'Surface the decision delta: what should change now because this report exists.'
  - Link findings to exact code, tests, or commits where possible.
  - Distinguish measured facts from operator interpretation.
  - Review whether this file should stay in `docs/reports` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: report
  vault_path: docs/archive/OVERNIGHT_AUTOPILOT.md
  retrieval_terms:
  - reports
  - overnight
  - autopilot
  - primary
  - goal
  - keep
  - all
  - night
  - periodic
  - status
  - task
  - feed
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: archive
  semantic_weight: 0.55
  coordination_comment: 'Primary goal: keep dharma swarm active all night with periodic status, task feed, and quality checks.'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/archive/OVERNIGHT_AUTOPILOT.md reinforces its salience without needing a separate message.
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
# Overnight Autopilot

Primary goal: keep `dharma_swarm` active all night with periodic status, task feed, and quality checks.

## Start

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/start_overnight.sh 8
```

## Stop

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/stop_overnight.sh
```

## Live logs

```bash
tail -f ~/.dharma/logs/overnight_supervisor_stdout.log
```

Per-run artifacts are written under:

```text
~/.dharma/logs/overnight/<run_id>/
```

Key files:
- `autopilot.log` (event log)
- `report.md` (human summary)
- `snapshots.jsonl` (machine-readable loop snapshots)
- `context_*.md` (role/thread context captures)
