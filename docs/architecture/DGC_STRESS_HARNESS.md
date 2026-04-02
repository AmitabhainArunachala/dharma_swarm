---
title: DGC Stress Harness
path: docs/architecture/DGC_STRESS_HARNESS.md
slug: dgc-stress-harness
doc_type: documentation
status: active
summary: 'This harness is wired into the CLI as:'
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - scripts/dgc_max_stress.py
  - dharma_swarm/dgc_cli.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- swarm_intelligence
- multi_agent_systems
- research_methodology
- machine_learning
inspiration:
- stigmergy
- operator_runtime
- research_synthesis
connected_python_files:
- scripts/dgc_max_stress.py
- dharma_swarm/dgc_cli.py
connected_python_modules:
- scripts.dgc_max_stress
- dharma_swarm.dgc_cli
connected_relevant_files:
- scripts/dgc_max_stress.py
- dharma_swarm/dgc_cli.py
- docs/plans/ALLOUT_6H_MODE.md
- docs/plans/ALL_NIGHT_BUILD_CONCLAVE_2026-03-20.md
- docs/ASCII_STUDIO_SETUP.md
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/architecture/DGC_STRESS_HARNESS.md
  retrieval_terms:
  - dgc
  - stress
  - harness
  - wired
  - cli
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.55
  coordination_comment: 'This harness is wired into the CLI as:'
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/architecture/DGC_STRESS_HARNESS.md reinforces its salience without needing a separate message.
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
# DGC Stress Harness

This harness is wired into the CLI as:

```bash
dgc stress [options]
```

Implementation entrypoints:

- `scripts/dgc_max_stress.py`
- `dharma_swarm/dgc_cli.py` (`cmd_stress`)

## What It Tests

The run executes these phases end-to-end:

1. `preflight`
- Verifies binaries, keys, and baseline DGC status/health commands.

2. `research agents`
- Spawns two dedicated stress-research agents and tasks.
- Focuses on stress vectors and adversarial breakpoints.

3. `orchestrator load`
- Spawns N agents, creates M tasks, dispatches until completion/timeout.
- Measures completion, failures, and throughput.

4. `evolution stress`
- Submits safe + intentionally harmful proposals.
- Validates gate rejections, archive behavior, canary promote/rollback, policy compile.

5. `CLI flood`
- Parallel command pressure across status, dharma, gates, route, compose, autonomy,
  context-search, stigmergy, and hum.

6. `external research` (optional)
- Runs direct `claude -p` and `codex exec` probes with bounded timeout.

## Artifacts

Each run writes:

- `~/.dharma/shared/dgc_max_stress_<RUN_ID>.json`
- `~/.dharma/shared/dgc_max_stress_<RUN_ID>.md`

## Recommended Profiles

Fast synthetic reliability check:

```bash
dgc stress --profile quick --provider-mode mock
```

Maximum synthetic load:

```bash
dgc stress --profile max --provider-mode mock
```

Live-provider integration smoke:

```bash
dgc stress \
  --profile quick \
  --provider-mode claude \
  --orchestration-timeout-sec 30 \
  --external-research \
  --external-timeout-sec 45
```

## Reading Results

Prioritize these fields in the report:

- `phase_research_agents.wait.complete`
- `phase_orchestrator_load.counts` (`completed`, `failed`, `other`)
- `phase_evolution` (`rejected`, `canary_promote`, `canary_rollback`)
- `phase_cli_flood.pass_rate`
- `phase_external_research` (`rc`, `elapsed_sec`, `stderr_tail`)

`counts.other > 0` or `research complete=false` indicates timeout/starvation under the selected provider/timeout settings.
