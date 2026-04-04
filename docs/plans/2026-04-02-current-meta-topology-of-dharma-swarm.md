---
title: Current Meta Topology Of Dharma Swarm
path: docs/plans/2026-04-02-current-meta-topology-of-dharma-swarm.md
slug: current-meta-topology-of-dharma-swarm
doc_type: plan
status: active
summary: "Date: 2026-04-02 Purpose: synthesize the repo's current maps, topologies, and authority boundaries into one operator-facing reality map."
source:
  provenance: repo_local
  kind: plan
  origin_signals:
  - docs/REPO_LIVING_MAP_2026-03-31.md
  - docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
  - reports/repo_xray_2026-03-31.md
  - docs/plans/2026-03-28-dirty-hot-map.md
  - docs/plans/2026-04-02-terminal-tui-convergence-merge-path.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
---
# Current Meta Topology Of Dharma Swarm

Date: 2026-04-02
Scope: `/Users/dhyana/dharma_swarm`
Purpose: provide one operator-facing synthesis of the repo's current maps, topologies, authority boundaries, and active heat.

## Plain Thesis

The repo does not mainly lack maps.
It already has many maps.

The real problem is that they are distributed across different layers with weak precedence:

- whole-repo orientation maps
- inventory and x-ray maps
- hygiene and ontology doctrine
- hot-path and merge-path maps
- conceptual organism architecture maps

The result is not absence of structure.
It is competing structure.

This document defines the current stack in one place.

## Canonical Reading Order

If someone needs to understand the repo quickly and truthfully, read in this order:

1. `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`
2. `docs/REPO_LIVING_MAP_2026-03-31.md`
3. `reports/repo_xray_2026-03-31.md`
4. `docs/plans/2026-03-28-dirty-hot-map.md`
5. `docs/plans/2026-04-02-terminal-tui-convergence-merge-path.md`
6. `docs/DHARMA_COMMAND_NORTH_STAR_SPEC_2026-04-01.md`

Why this order:

- hygiene doctrine explains why the repo feels confusing
- living map gives broad orientation
- x-ray gives measured inventory
- hot maps explain what is actively moving
- convergence map explains the TUI blast radius
- north star explains where one important surface is trying to go

## The Actual Map Stack

### 1. Hygiene Doctrine

Primary file:

- `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`

Function:

- explains the root defect: too many files claim to be canonical at once
- defines the repo ontology classes
- defines a precedence order between runtime truth, operator truth, canon, plans, foundations, and reports

Status:

- strongest current doctrine for understanding repo disorder

### 2. Whole-Repo Orientation

Primary file:

- `docs/REPO_LIVING_MAP_2026-03-31.md`

Function:

- gives the best broad operator-facing map of the whole repo
- identifies major zones, runtime spine, product surfaces, and large hotspots

Status:

- best current first-pass orientation map

### 3. Static Inventory / X-Ray

Primary file:

- `reports/repo_xray_2026-03-31.md`

Function:

- quantifies file counts, language mix, biggest modules, import topology, and hotspot concentration

Status:

- best measured evidence map
- descriptive, not normative

### 4. Hot-Path / Change Topology

Primary files:

- `docs/plans/2026-03-28-dirty-hot-map.md`
- `docs/plans/2026-03-27-recent-change-merge-map.md`
- `docs/plans/2026-04-02-terminal-tui-convergence-merge-path.md`

Function:

- explain where the repo is actively changing
- identify blast-radius files and merge-risk seams
- distinguish hot lanes from general repo structure

Status:

- best maps of motion rather than shape

### 5. Conceptual / Organism Architecture

Primary files:

- `docs/DHARMA_COMMAND_NORTH_STAR_SPEC_2026-04-01.md`
- `docs/architecture/INTEGRATION_MAP.md`
- `docs/reports/DGC_DUAL_ENGINE_REALITY_MAP_2026-03-13.md`

Function:

- describe the system as organism, command layer, dual engine, and long-run product
- explain semantic and execution couplings

Status:

- high-value conceptual maps
- not sufficient by themselves for repo hygiene or day-to-day merge safety

## The Repo’s Current Topological Zones

The repo currently behaves like a layered organism with overlapping authority.

### Zone A: Live Executable Organism

Primary directories:

- `dharma_swarm/`
- `api/`
- `dashboard/`
- `terminal/`
- `tests/`

Meaning:

- this is the executable system
- if these files and tests disagree with docs, code wins

Current reality:

- live code is real
- architecture is still split in places
- TUI convergence is active here

### Zone B: Operator Doctrine And Architecture

Primary directories:

- `docs/`
- `specs/`

Meaning:

- this is where human-readable intended structure lives
- some of this is canonical, some is active packet material

Current reality:

- useful but crowded
- too many near-canonical docs live side by side

### Zone C: Historical Evidence And Generated Narration

Primary directories:

- `reports/`
- `.dharma_psmv_hyperfile_branch*`

Meaning:

- generated traces
- audits
- x-rays
- completion packets
- branch artifacts

Current reality:

- large source of perceived dirt
- should not be confused with executable product truth

### Zone D: Conceptual Substrate

Primary directories:

- `foundations/`
- `lodestones/`
- selected `docs/dse/`

Meaning:

- philosophy, substrate, research, and conceptual framing

Current reality:

- important for long-run identity
- should not override runtime facts

## Authority Precedence

When two layers disagree, use this order:

1. executable code and tests
2. operator entrypoints and launch surfaces
3. canonical doctrine docs
4. active plans and migration packets
5. research and conceptual substrate
6. reports and generated artifacts

This is the single most important rule for reducing confusion.

## Current Heat Topology

As of the current local state, the repo is globally very dirty, but the heat is not evenly meaningful.

Top-level dirty concentration from current `git status --short`:

- `docs`: 242
- `reports`: 111
- `dharma_swarm`: 36
- `dashboard`: 33
- `foundations`: 25
- `.dharma_psmv_hyperfile_branch`: 25
- `specs`: 22
- `spec-forge`: 17
- `tests`: 15
- `lodestones`: 14

Interpretation:

- the repo’s mess is dominated by prose and artifact churn
- not by the primary runtime alone

## The Hot TUI Lane

The current intentionally hot lane is the terminal convergence effort.

Primary files and zones:

- `terminal/`
- `dharma_swarm/operator_core/`
- `dharma_swarm/terminal_bridge.py`
- `dharma_swarm/tui/engine/session_store.py`
- `dharma_swarm/tui/engine/governance.py`
- supporting tests in `tests/`

Meaning:

- this lane is allowed to remain hot and somewhat dirty during convergence
- it should not be used as evidence that the entire repo is unclean in the same way

Risk:

- `terminal_bridge.py` is still a semantic danger zone because it can become a second brain

## Current Structural Fault Lines

These are the main topology fractures in the system.

### 1. Too Many Canonical-Looking Docs

Symptoms:

- root markdown sprawl
- many architecture notes with similar authority weight
- reports and doctrine sitting near each other visually

Effect:

- operators and agents cannot tell what actually governs the repo

### 2. Executable Split-Brain In Operator Surfaces

Symptoms:

- Bun shell in `terminal/`
- Python Textual shell in `dharma_swarm/tui/`
- large bridge seam in `dharma_swarm/terminal_bridge.py`

Effect:

- shell semantics can drift unless `operator_core` becomes the only brain

### 3. Generated State Mixed With Durable Knowledge

Symptoms:

- branch artifact trees and generated packets are near normal docs
- reports accumulate without clear archival boundaries

Effect:

- scan noise
- retrieval confusion
- inflated sense of active product complexity

### 4. Conceptual Maps And Runtime Maps Competing

Symptoms:

- organism and north-star docs describe truths not yet fully embodied in code
- runtime maps describe local reality more narrowly

Effect:

- aspiration can be mistaken for implementation

## What Is Already Good

The repo is not map-poor.
It already has strong ingredients:

- a useful living map
- a useful measured x-ray
- a good hygiene doctrine
- concrete hot-path notes
- multiple architecture theses

The issue is not missing intelligence.
It is missing nesting and precedence.

## Current Best Mental Model

If you need one clean mental picture, use this:

- `dharma_swarm/`, `api/`, `dashboard/`, `terminal/`, `tests/` are the living executable organism
- `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md` explains how repo truth should be classified
- `docs/REPO_LIVING_MAP_2026-03-31.md` explains the broad structure
- `reports/repo_xray_2026-03-31.md` gives the measured inventory
- `docs/plans/*hot-map*` and `*merge-path*` explain current movement and risk
- the TUI convergence lane is a special hot zone, not the whole repo

## Immediate Implications

1. Do not create another competing whole-repo map unless it replaces one.
2. Treat hygiene doctrine as the interpretation layer for all cleanup.
3. Treat the x-ray as evidence, not policy.
4. Treat hot-path notes as motion maps, not permanent architecture truth.
5. Keep the TUI lane hot, but do not let its heat justify global disorder.
6. Clean the rest of the repo by clarifying ontology first, not by random deletion.

## Next Useful Artifact

The next high-leverage follow-on should be a repo hygiene map that classifies the rest of the repo into:

- canonical keep
- active but bounded
- archive candidate
- generated/noise
- duplicate/deprecated
- do-not-touch hot lane

That would convert this topology into an actionable cleanup program.
