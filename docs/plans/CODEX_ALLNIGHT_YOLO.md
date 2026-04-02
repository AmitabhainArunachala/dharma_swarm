---
title: Codex Allnight YOLO
path: docs/plans/CODEX_ALLNIGHT_YOLO.md
slug: codex-allnight-yolo
doc_type: documentation
status: active
summary: This is the Codex-native overnight lane for dharma swarm.
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - docs/missions/CODEX_ALLNIGHT_YOLO_MISSION.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- verification
- product_strategy
- operations
- machine_learning
inspiration:
- verification
- operator_runtime
connected_python_files:
- dharma_swarm/codex_overnight.py
- scripts/codex_overnight_autopilot.py
- scripts/dgc_max_stress.py
- scripts/live_organism_run.py
- scripts/verification_lane.py
connected_python_modules:
- dharma_swarm.codex_overnight
- scripts.codex_overnight_autopilot
- scripts.dgc_max_stress
- scripts.live_organism_run
- scripts.verification_lane
connected_relevant_files:
- docs/missions/CODEX_ALLNIGHT_YOLO_MISSION.md
- dharma_swarm/codex_overnight.py
- scripts/codex_overnight_autopilot.py
- scripts/dgc_max_stress.py
- scripts/live_organism_run.py
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/plans/CODEX_ALLNIGHT_YOLO.md
  retrieval_terms:
  - codex
  - allnight
  - yolo
  - native
  - overnight
  - lane
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.55
  coordination_comment: This is the Codex-native overnight lane for dharma swarm.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/plans/CODEX_ALLNIGHT_YOLO.md reinforces its salience without needing a separate message.
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
# Codex Allnight YOLO

This is the Codex-native overnight lane for `dharma_swarm`.

It is designed to do one thing well: wake up, inspect the live repo, choose a
bounded slice, ship it with verification, and leave a clean morning handoff.

## Launch

Default aggressive launch:

```bash
dgc swarm yolo
```

Explicit Codex launch with mission file:

```bash
dgc swarm codex-night yolo 10 \
  --mission-file docs/missions/CODEX_ALLNIGHT_YOLO_MISSION.md \
  --label allnight-yolo
```

Optional knobs:

```bash
dgc swarm codex-night start 6 \
  --yolo \
  --mission-file docs/missions/CODEX_ALLNIGHT_YOLO_MISSION.md \
  --model gpt-5.4 \
  --max-cycles 8 \
  --poll-seconds 20 \
  --cycle-timeout 7200 \
  --label allnight-yolo
```

## Artifacts

Each run writes under `~/.dharma/logs/codex_overnight/<run_id>/`:

- `run_manifest.json`: operator label, mission, settings, git snapshot, latest cycle
- `mission_brief.md`: the exact mission text used for the run
- `report.md`: rolling cycle ledger
- `latest_last_message.txt`: latest Codex result block
- `morning_handoff.md`: human-facing handoff

A copy of the latest handoff is also written to:

- `~/.dharma/shared/codex_overnight_handoff.md`

## Status

```bash
dgc swarm codex-night status
dgc swarm codex-night report
```

The status helper now shows the current heartbeat, manifest, and morning
handoff if they exist.
