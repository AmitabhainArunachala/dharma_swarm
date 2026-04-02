---
title: Current Meta Topology Of Dharma Swarm
path: docs/CURRENT_META_TOPOLOGY_2026-04-02.md
slug: current-meta-topology-of-dharma-swarm
doc_type: documentation
status: active
summary: "Date: 2026-04-02 Scope: current-state cartography of the repo, with explicit precedence between map systems, live organism zones, hot change lanes, and cleanup zones."
source:
  provenance: repo_local
  kind: documentation
  origin_signals:
  - docs/REPO_LIVING_MAP_2026-03-31.md
  - docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
  - reports/repo_xray_2026-03-31.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- knowledge_management
- operations
- verification
- product_strategy
inspiration:
- operator_runtime
- product_surface
- verification
connected_relevant_files:
- docs/REPO_LIVING_MAP_2026-03-31.md
- docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
- docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
- reports/repo_xray_2026-03-31.md
improvement:
  room_for_improvement:
  - Keep the precedence stack synchronized with current cleanup tranches.
  - Tighten links to the latest reports and architecture tranche plans.
  next_review_at: '2026-04-03T00:00:00+09:00'
pkm:
  note_class: documentation
  vault_path: docs/CURRENT_META_TOPOLOGY_2026-04-02.md
  retrieval_terms:
  - current
  - topology
  - maps
  - repo
  - cleanup
  - authority
  evergreen_potential: high
stigmergy:
  meaning: This file compresses the repo's current map stack into one operator-facing topology.
  state: working
  semantic_weight: 0.85
  coordination_comment: Use this file to understand where truth, motion, and cleanup pressure currently live.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T00:00:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Current Meta Topology Of Dharma Swarm

Date: 2026-04-02
Repo: `dharma_swarm`
Scope: current-state cartography of the repo, with explicit precedence between map systems, live organism zones, hot change lanes, and cleanup zones
Status: working synthesis

## Why This Exists

The repo already has many maps.
The confusion is not a lack of cartography.
The confusion is that multiple map systems coexist without a clear precedence order.

This document compresses the current state into one operator-facing topology:

1. what parts of the repo are the live executable organism
2. what documents currently function as the best maps
3. which lanes are intentionally hot
4. which dirty zones are mostly documentation and artifact churn
5. what should count as truth when documents disagree

## Precedence Order

When two sources disagree, use this order:

1. Runtime truth
   - live code in `dharma_swarm/`, `api/`, `dashboard/`, `terminal/`
   - tests in `tests/`
2. Operator truth
   - `README.md`
   - `CLAUDE.md`
   - launcher/build entrypoints
3. Canonical repo doctrine
   - `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`
4. Whole-repo orientation
   - `docs/REPO_LIVING_MAP_2026-03-31.md`
5. Measured x-ray
   - `reports/repo_xray_2026-03-31.md`
6. Hot-path / merge / freeze notes
   - `docs/plans/*hot*`
   - `docs/plans/*merge*`
   - `docs/plans/*freeze*`
7. Reports, prompts, generated traces, and historical packets

Anything lower in the stack is non-canonical until reconciled upward.

## The Four Existing Map Systems

### 1. Whole-Repo Orientation Maps

These explain what the repo is and where the major surfaces live.

Primary files:

- `docs/REPO_LIVING_MAP_2026-03-31.md`
- `docs/architecture/NAVIGATION.md`
- `docs/architecture/INTEGRATION_MAP.md`
- `docs/reports/DGC_DUAL_ENGINE_REALITY_MAP_2026-03-13.md`

Best current authority:

- `docs/REPO_LIVING_MAP_2026-03-31.md`

Use for:

- first-pass orientation
- major subsystem discovery
- runtime spine context
- high-signal top-level area identification

### 2. Repo Hygiene / Ontology Maps

These explain why the repo feels confusing and how to classify files.

Primary files:

- `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`
- `docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md`
- `docs/REPO_HYGIENE_TRIAGE_2026-04-01.md`
- `docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md`

Best current authority:

- `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`

Use for:

- deciding what is canon vs report vs plan vs foundation vs generated state
- understanding why docs/reports/root clutter dominate the dirty tree
- cleanup planning outside hot product lanes

### 3. Hot-Path / Change Topology Maps

These describe active mutation zones and merge risk.

Primary files:

- `docs/plans/2026-03-28-dirty-hot-map.md`
- `docs/plans/2026-03-28-hot-seam-freeze-plan.md`
- `docs/plans/2026-03-27-recent-change-merge-map.md`
- `docs/plans/2026-03-27-night-lock-map.md`
- `docs/plans/2026-04-02-terminal-tui-convergence-merge-path.md`

Best current authority for the TUI lane:

- `docs/plans/2026-04-02-terminal-tui-convergence-merge-path.md`

Use for:

- deciding what must freeze
- avoiding hot-lane collisions
- understanding merge blast radius

### 4. Organism / North-Star Conceptual Maps

These describe the intended higher-order system, not just the current file tree.

Primary files:

- `docs/DHARMA_COMMAND_NORTH_STAR_SPEC_2026-04-01.md`
- `docs/dse/DSE_ARCHITECTURE_MAP.md`
- `docs/plans/2026-03-26-living-agent-roaming-onboarding-architecture.md`

Best current authority:

- `docs/DHARMA_COMMAND_NORTH_STAR_SPEC_2026-04-01.md`

Use for:

- product direction
- layered organism design
- browser cockpit north star

Do not use these as evidence that the current repo already manifests that state.

## Live Executable Organism

These directories are the actual working system, not just commentary about it.

### Runtime / Python organism core

- `dharma_swarm/`

Important signals:

- large runtime center of gravity
- main coordinator, routing, ontology, evolution, runtime state, provider plumbing
- still contains the old Textual TUI shell
- now also contains the new `operator_core/` convergence seam

### Bun operator shell

- `terminal/`

Important signals:

- active TUI convergence lane
- real shell plumbing and tests
- still partly scaffold/protocol-string driven

### Browser cockpit

- `dashboard/`

Important signals:

- active web operator surface
- also dirty and evolving
- not the active focus of the current hot TUI convergence lane

### Backend/API

- `api/`

Important signals:

- FastAPI runtime surface
- connects live system state to operator surfaces

### Verification

- `tests/`

Important signals:

- unusually large test mirror relative to code
- important truth source when docs and narrative drift

## Current Hot Lane

The intentionally hot lane right now is the TUI convergence path:

- `terminal/`
- `dharma_swarm/operator_core/`
- `dharma_swarm/terminal_bridge.py`
- `dharma_swarm/tui/engine/session_store.py`
- `dharma_swarm/tui/engine/governance.py`
- new operator-core tests under `tests/`

Interpretation:

- this lane is allowed to stay dirty
- its dirt is not the main repo-hygiene problem
- the main hygiene problem is elsewhere

## Current Structural Reality Of The TUI

The TUI is not fake.
It already has real operator muscle.

What is already real:

- Bun shell with live bridge wiring and keyboard-first operator flow
- Python provider/event engine
- shared `operator_core` seam for contracts, session persistence, session views, and permissions
- real tests covering Bun protocol/rendering and shared-core slices

What is still transitional:

- `dharma_swarm/terminal_bridge.py` is still too central
- Bun still consumes too much truth as preview strings and protocol-shaped summaries
- old Python Textual shell still exists as a second substantial UI architecture

Current best reading:

- strong operator shell seam: yes
- one clean brain: not yet
- full living-organism console: not yet

## Dirty Tree Topology

Current top-level dirty distribution is dominated by non-runtime churn:

- `docs`: 242 paths
- `reports`: 111
- `dharma_swarm`: 36
- `dashboard`: 33
- `foundations`: 25
- `.dharma_psmv_hyperfile_branch`: 25
- `specs`: 22
- `spec-forge`: 17
- `tests`: 15
- `lodestones`: 14
- `.dharma_psmv_hyperfile_branch_v2`: 12
- `scripts`: 10
- `mode_pack`: 9

Interpretation:

- the repo is globally dirty
- most of that dirt is not core runtime mutation
- most confusion comes from narrative and artifact churn
- the TUI lane is only one dirty zone among many

## Cleanliness Reality

Two apparently contradictory statements are both true:

1. The repo is dirty.
2. The TUI convergence architecture is getting cleaner.

Why:

- whole-repo git hygiene is poor
- but the TUI hot lane is moving toward a better structure via `operator_core`

So:

- whole-repo clean: false
- hot-lane architectural convergence: true

## Generated State Boundary

These path families should not be treated as architecture truth:

- `.dharma_psmv_hyperfile_branch/**`
- `.dharma_psmv_hyperfile_branch_v2/**`
- `reports/**/state/**`
- `reports/nightwatch/*.log`

These are:

- generated branch state
- generated run artifacts
- logs
- audit traces

They may have replay or forensic value.
They are not implementation canon.

## The Strongest Current Canonical Cartographic Stack

If a new agent needs the current repo topology fast, the best reading stack is:

1. `README.md`
2. `CLAUDE.md`
3. `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`
4. `docs/REPO_LIVING_MAP_2026-03-31.md`
5. `reports/repo_xray_2026-03-31.md`
6. `docs/plans/2026-04-02-terminal-tui-convergence-merge-path.md`
7. `docs/DHARMA_COMMAND_NORTH_STAR_SPEC_2026-04-01.md`

That sequence gives:

- operator truth
- file-ontology doctrine
- whole-repo orientation
- measured inventory
- current hot-lane risk map
- long-range product direction

## Repo Zones

### Zone A: Live Product / Runtime

Keep mentally primary:

- `dharma_swarm/`
- `api/`
- `dashboard/`
- `terminal/`
- `tests/`

### Zone B: Canon / Doctrine

Keep small and authoritative:

- `README.md`
- `CLAUDE.md`
- top-level canonical docs under `docs/`

### Zone C: Active Planning

Treat as execution packets, not truth:

- `docs/plans/`
- selected active `specs/`

### Zone D: Conceptual Foundation

Keep intellectually important but operationally secondary:

- `foundations/`
- `lodestones/`
- `mode_pack/`

### Zone E: Historical / Generated Evidence

Treat as useful but non-canonical:

- `reports/`
- generated branch state families
- xray outputs
- run logs

## Immediate Strategic Reading

The repo does not currently need more raw maps.
It needs:

1. one explicit precedence order between maps
2. one accepted distinction between executable truth and narrative truth
3. one accepted dirty allowlist for the hot TUI lane
4. one cleanup posture for everything else

This document is intended to serve as that current synthesis until a stricter canon set is ratified.
