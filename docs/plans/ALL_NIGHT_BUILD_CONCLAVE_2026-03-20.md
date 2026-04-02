---
title: All-Night Build Conclave
path: docs/plans/ALL_NIGHT_BUILD_CONCLAVE_2026-03-20.md
slug: all-night-build-conclave
doc_type: documentation
status: active
summary: Goal
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - scripts/dashboard_ctl.sh
  - scripts/start_allout_tmux.sh
  - scripts/start_codex_overnight_tmux.sh
  - scripts/start_caffeine_tmux.sh
  - scripts/start_merge_control_tmux.sh
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- knowledge_management
- verification
- product_strategy
- frontend_engineering
inspiration:
- verification
- operator_runtime
- product_surface
connected_python_files:
- dharma_swarm/dgc_cli.py
connected_python_modules:
- dharma_swarm.dgc_cli
connected_relevant_files:
- scripts/dashboard_ctl.sh
- scripts/start_allout_tmux.sh
- scripts/start_codex_overnight_tmux.sh
- scripts/start_caffeine_tmux.sh
- scripts/start_merge_control_tmux.sh
improvement:
  room_for_improvement:
  - Strengthen cross-links to adjacent docs and implementing modules.
  - Separate durable knowledge from transient session context.
  - Add a tighter summary for first-pass retrieval.
  - Review whether this file should stay in `docs` or be consolidated elsewhere.
  next_review_at: '2026-04-01T00:43:19+09:00'
pkm:
  note_class: documentation
  vault_path: docs/plans/ALL_NIGHT_BUILD_CONCLAVE_2026-03-20.md
  retrieval_terms:
  - all
  - night
  - build
  - conclave
  - '2026'
  - goal
  evergreen_potential: medium
stigmergy:
  meaning: This file is a shared environmental trace in the DHARMA corpus. Its path, recency, and linked surfaces guide future agent attention; its frontmatter now adds machine-readable coordination cues.
  state: working
  semantic_weight: 0.6
  coordination_comment: Goal
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising docs/plans/ALL_NIGHT_BUILD_CONCLAVE_2026-03-20.md reinforces its salience without needing a separate message.
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
# All-Night Build Conclave

## Goal

Use the existing `dharma_swarm` machinery to run one coherent overnight build loop instead of five overlapping ones.

This is not a plan to make Dharma Swarm replace the external builder swarm tonight.
It is a plan to make Dharma Swarm become the coordination membrane around that swarm.

## Canonical Control Planes

### 1. Launchd owns the product shell

Use launchd to keep the operator surface alive:

- `scripts/com.dharma.dashboard-api.plist`
- `scripts/com.dharma.dashboard-web.plist`
- `bash scripts/dashboard_ctl.sh start`

This keeps:

- backend on `127.0.0.1:8420`
- dashboard on `127.0.0.1:3420`

alive independently of terminal tabs.

### 2. Tmux owns the overnight workers

Use tmux for the autonomous overnight loops:

- `scripts/start_allout_tmux.sh`
- `scripts/start_codex_overnight_tmux.sh`
- `scripts/start_caffeine_tmux.sh`
- optionally `scripts/start_merge_control_tmux.sh`

These are the builder swarm, not the product shell.

### 3. Caffeinate owns machine wakefulness

Use `caffeinate` for any loop intended to survive the night.
The tmux launchers already support this. Do not rely on open tabs to keep the machine awake.

## Night Topology

### Runtime lane

- launchd keeps `3420` and `8420` alive
- `dashboard/runtime` is the truth page
- `dashboard/command-post` is the operator cockpit

### Index lane

Before or alongside the build loops, index the repo:

- `python3 -m dharma_swarm.dgc_cli semantic digest --root ~/dharma_swarm --include-tests`
- `python3 -m dharma_swarm.dgc_cli semantic brief --root ~/dharma_swarm`
- `python3 -m dharma_swarm.dgc_cli xray ~/dharma_swarm --packet`

This gives the night a live concept graph, campaign briefs, and a repo-level architecture packet.

### CEO / wedge lane

Use the mode-pack contract, not free-form inspiration:

- `dharma-ceo-review`
- `dharma-eng-review`
- `dharma-preflight-review`
- `dharma-qa`
- `dharma-retro`

Those aliases are installed by `bash scripts/install_mode_pack.sh --target repo`.

### Tactical build lane

Let `codex_overnight` do one bounded slice per cycle with a mission brief and morning handoff:

- repeated implement/verify cycles
- files changed recorded per cycle
- `run_manifest.json`
- `morning_handoff.md`

### Director lane

Let `thinkodynamic_director` feed and reprioritize the system-level task stream.
This is the broad orchestration lane, not the sharp surgical lane.

### QA / guardrail lane

Use the caffeine loop for repeated health and focused test slices through the night.
It is the night watch, not the primary builder.

## External Swarm Mapping

Right now you are using external Codex and Claude sessions to build Dharma Swarm.
That is fine. The right overnight structure is:

- Dharma Swarm observes and coordinates the builders
- external Codex sessions execute bounded build slices
- Claude lanes handle CEO / architecture / review / retro roles
- GSuite is an artifact sink, not an orchestrator

There is no first-class GSuite integration in this repo yet, so the correct role for it tonight is morning artifact distribution, not live control.

## One Canonical Night

Use one entrypoint:

```bash
bash scripts/start_build_conclave.sh 8
```

That should:

- run mission preflight
- install the mode pack locally
- start the dashboard launch agents
- start a repo-index tmux lane
- start the director lane
- start the codex overnight lane with a real mission brief
- start the caffeine maintenance lane

## Success Criteria By Morning

By morning, the night should leave:

- stable `3420` and `8420`
- one current repo semantic digest
- one fresh semantic brief packet
- one fresh repo xray packet
- one codex overnight handoff
- one director heartbeat
- one caffeine log
- one clearer product wedge and next-step execution order

## What Not To Do

- Do not use the older detached `start_overnight.sh` path as the primary night owner.
- Do not let random tabs become process supervisors.
- Do not run multiple overlapping night control planes with no single owner.
- Do not make the dashboard depend directly on outside runtimes like CLIProxyAPI for core control-plane behavior.

## Immediate Next Upgrade

After this night path is stable, the next real step is a unified overnight status surface in the dashboard that aggregates:

- launchd product shell state
- tmux worker sessions
- heartbeats
- manifests
- morning handoffs

That is when Dharma Swarm starts becoming the real operator membrane around the external builder swarm.
