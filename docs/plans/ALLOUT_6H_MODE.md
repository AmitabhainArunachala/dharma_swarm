---
title: AllOut 6-Hour Mode
path: docs/plans/ALLOUT_6H_MODE.md
slug: allout-6-hour-mode
doc_type: documentation
status: active
summary: 'Purpose: run an autonomous 6-hour loop that: 1. Runs core DGC checks/tests. 2. Reads 10 local files per cycle. 3. Generates a fresh 3-5 step action plan. 4. Repeats until time window ends.'
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - scripts/start_allout_tmux.sh
  - scripts/status_allout_tmux.sh
  - scripts/stop_allout_tmux.sh
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- software_architecture
inspiration:
- knowledge_management
- software_architecture
connected_python_files:
- scripts/allout_autopilot.py
- scripts/dgc_full_power_probe.py
- scripts/dgc_max_stress.py
- scripts/experiments/test_full_loop.py
- scripts/ginko_run_signals.py
connected_python_modules:
- scripts.allout_autopilot
- scripts.dgc_full_power_probe
- scripts.dgc_max_stress
- scripts.experiments.test_full_loop
- scripts.ginko_run_signals
connected_relevant_files:
- scripts/start_allout_tmux.sh
- scripts/status_allout_tmux.sh
- scripts/stop_allout_tmux.sh
- scripts/allout_autopilot.py
- scripts/dgc_full_power_probe.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/plans/ALLOUT_6H_MODE.md
  retrieval_terms:
  - allout
  - mode
  - hour
  - purpose
  - run
  - autonomous
  - loop
  - runs
  - core
  - dgc
  - checks
  - tests
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.6
  coordination_comment: 'Purpose: run an autonomous 6-hour loop that: 1. Runs core DGC checks/tests. 2. Reads 10 local files per cycle. 3. Generates a fresh 3-5 step action plan. 4. Repeats until time window ends.'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/plans/ALLOUT_6H_MODE.md reinforces its salience without needing a separate message.
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
# AllOut 6-Hour Mode

Purpose: run an autonomous 6-hour loop that:
1. Runs core DGC checks/tests.
2. Reads 10 local files per cycle.
3. Generates a fresh 3-5 step action plan.
4. Repeats until time window ends.

## Start

```bash
cd ~/dharma_swarm && POLL_SECONDS=300 USE_CAFFEINATE=1 scripts/start_allout_tmux.sh 6
```

## Status

```bash
cd ~/dharma_swarm && scripts/status_allout_tmux.sh
```

## Stop

```bash
cd ~/dharma_swarm && scripts/stop_allout_tmux.sh
```

## Artifacts

- Heartbeat: `~/.dharma/allout_heartbeat.json`
- Logs: `~/.dharma/logs/allout/<run_id>/allout.log`
- Snapshots: `~/.dharma/logs/allout/<run_id>/snapshots.jsonl`
- Cycle action plans: `~/.dharma/shared/allout_todo_cycle_*.md`
- Morning summary: `~/.dharma/shared/allout_morning_<run_id>.md`
