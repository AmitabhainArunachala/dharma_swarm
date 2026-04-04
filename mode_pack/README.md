---
title: Dharma Swarm Mode Pack
path: mode_pack/README.md
slug: dharma-swarm-mode-pack
doc_type: readme
status: reference
summary: The mode pack is the operational workflow and contract layer for shared modes, not a substrate prose directory.
source:
  provenance: repo_local
  kind: readme
  origin_signals:
  - scripts/install_mode_pack.sh
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- multi_agent_systems
- software_architecture
- research_methodology
- verification
- product_strategy
- frontend_engineering
inspiration:
- verification
- operator_runtime
- product_surface
- research_synthesis
connected_python_files:
- scripts/live_claude_code.py
- dharma_swarm/contracts/intelligence_kaizenops.py
- scripts/live_organism_run.py
- scripts/self_optimization/run_production_self_optimization.py
- tests/test_agent_install.py
connected_python_modules:
- scripts.live_claude_code
- dharma_swarm.contracts.intelligence_kaizenops
- scripts.live_organism_run
- scripts.self_optimization.run_production_self_optimization
- tests.test_agent_install
connected_relevant_files:
- scripts/install_mode_pack.sh
- scripts/live_claude_code.py
- dharma_swarm/contracts/intelligence_kaizenops.py
- scripts/live_organism_run.py
- scripts/self_optimization/run_production_self_optimization.py
- mode_pack/claude/autonomous-build/SKILL.md
- docs/plans/2026-04-03-autonomous-cleanup-overnight-control.md
- scripts/start_autonomous_cleanup_tmux.sh
- docs/plans/2026-04-02-substrate-layer-policy.md
- docs/plans/2026-04-03-substrate-directory-cartography.md
- docs/plans/2026-04-03-substrate-graduation-candidates.md
improvement:
  room_for_improvement:
  - Keep entry points and commands aligned with the current runtime.
  - Add sharper cross-links into the most active specs, tests, and dashboards.
  - Keep operational contract semantics distinct from substrate prose semantics.
  - Recheck mode descriptions only when the contract schema changes materially.
  next_review_at: '2026-04-05T12:00:00+09:00'
pkm:
  note_class: readme
  vault_path: mode_pack/README.md
  retrieval_terms:
  - mode
  - pack
  - operational
  - shared
  - workflow
  - layer
  - contract
  - operator
  evergreen_potential: high
stigmergy:
  meaning: This file is the entry surface for the operational mode contract layer and should not be confused with substrate prose or repo doctrine.
  state: canonical
  semantic_weight: 0.88
  coordination_comment: Use this file when reasoning about shared operating modes, installers, and contract-backed workflow semantics.
  levels:
    sematectonic:
      what_it_is: The document itself is the mark. Its existence, filename, location, and revision history attract or repel future work.
      access_mark: Opening, linking, and revising mode_pack/README.md reinforces its salience without needing a separate message.
    marker_based:
      what_it_is: The frontmatter is an explicit annotation layer on top of the document.
      semantic_mark: Semantic weight, improvement prompts, related files, and provenance comments tell later agents how to use this document.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T20:20:00+09:00'
  curated_by_model: Codex (GPT-5)
  source_model_in_file: 
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Dharma Swarm Mode Pack

The mode pack is the operational workflow and contract layer for the system.

It is not part of the prose substrate.
It belongs with runnable operator workflow semantics, shared mode vocabulary, and machine-readable contract surfaces.

It is not another vague prompt bank. It is a set of explicit operating modes
with:

- a machine-readable contract
- Claude skill wrappers
- runtime aliases for Codex, DGC, and OpenClaw
- one installer for repo-local usage

## Why it exists

The system already has strong infrastructure:

- `DGC` for execution and delegation
- `Dharma Swarm` for intelligence and orchestration
- `KaizenOps` for audit and control
- `OpenClaw` for agent shells

What was missing was a clean layer of explicit cognitive gears.

This pack provides that layer.

## Layer Role

Treat `mode_pack/` as:

- operational contract surface
- shared workflow vocabulary
- installer-backed runtime support

Do not treat it as `foundations/`-style canon or `lodestones/`-style orienting prose.

## Canonical modes

| Slug | Purpose |
|------|---------|
| `ceo-review` | Reframe the problem and find the strongest product wedge |
| `autonomous-build` | Run a bounded overnight cleanup or build lane with explicit boundaries and stop rules |
| `eng-review` | Lock architecture, interfaces, failure modes, and tests |
| `preflight-review` | Review a diff or plan for production-grade risks |
| `ship` | Execute the release workflow for a ready branch |
| `qa` | Run structured product QA with evidence |
| `browse` | Use browser automation as an operational tool |
| `retro` | Turn completed work into concrete learning |
| `incident-commander` | Coordinate live incident response and recovery |

## Files

- `contracts/mode_pack.v1.json`
  Machine-readable source of truth.

- `claude/<mode>/SKILL.md`
  Repo-local Claude skill wrappers.

- `../dharma_swarm/mode_pack.py`
  Python loader for the contract.

- `../scripts/install_mode_pack.sh`
  Symlink installer for repo-local or user-level Claude skill usage.

## Install into this repo

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/install_mode_pack.sh --target repo
```

This creates symlinks in:

```text
/Users/dhyana/dharma_swarm/.claude/skills/
```

Aliases are prefixed with `dharma-` to avoid collisions with `gstack`.

Examples:

- `dharma-ceo-review`
- `dharma-eng-review`
- `dharma-preflight-review`
- `dharma-ship`
- `dharma-qa`
- `dharma-browse`
- `dharma-retro`
- `dharma-incident-commander`

## Install for user-level Claude Code

```bash
cd /Users/dhyana/dharma_swarm
bash scripts/install_mode_pack.sh --target user
```

This installs into:

```text
~/.claude/skills/
```

## Runtime mapping

The contract contains aliases for:

- `claude_skill`
- `codex_mode`
- `dgc_lane`
- `openclaw_profile`

That keeps one canonical mode vocabulary while allowing each runtime to expose
its own surface name.

## Design rules

- Modes are explicit and narrow.
- Each mode has required outputs.
- Each mode has escalation triggers.
- Each mode has non-goals.
- Modes are designed to hand off cleanly to the next mode.

The intended sequence is:

```text
ceo-review -> eng-review -> implementation -> preflight-review -> ship -> qa -> retro
```

Incidents route through:

```text
incident-commander -> eng-review / qa / ship
```

For long-running bounded execution, use:

```text
autonomous-build -> preflight-review / retro
```

Repo-local launcher:

```bash
bash scripts/start_autonomous_cleanup_tmux.sh
```
