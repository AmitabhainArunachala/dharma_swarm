---
title: Non-TUI Repo Hygiene Map
path: docs/plans/2026-04-02-non-tui-repo-hygiene-map.md
slug: non-tui-repo-hygiene-map
doc_type: plan
status: active
summary: "Date: 2026-04-02 Purpose: classify the repo outside the hot terminal convergence lane into keep, archive, generated, deprecated, and cleanup-first zones."
source:
  provenance: repo_local
  kind: plan
  origin_signals:
  - docs/plans/2026-04-02-current-meta-topology-of-dharma-swarm.md
  - docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
  - reports/repo_xray_2026-03-31.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
---
# Non-TUI Repo Hygiene Map

Date: 2026-04-02
Scope: `/Users/dhyana/dharma_swarm` excluding the hot TUI convergence lane

## Excluded Hot Lane

These paths are intentionally hot and are not the target of this cleanup map:

- `terminal/`
- `dharma_swarm/operator_core/`
- `dharma_swarm/terminal_bridge.py`
- `dharma_swarm/tui/engine/session_store.py`
- `dharma_swarm/tui/engine/governance.py`
- related operator-core tests

Everything else should be judged on long-run repo hygiene.

## Plain Thesis

Outside the hot TUI lane, the repo's disorder is dominated by:

- documentation sprawl
- historical and generated report accumulation
- root markdown clutter
- overlapping spec and prompt layers
- conceptual substrate mixed too closely with live doctrine

This is good news.
It means the repo can become much cleaner without touching the most dangerous live runtime seam.

## Classification Matrix

### 1. Canonical Keep

These should stay live and become more explicit, not less.

Top-level:

- `README.md`
- `CLAUDE.md`
- `pyproject.toml`
- `run_operator.sh`
- `api/`
- `dharma_swarm/`
- `dashboard/`
- `tests/`
- `.github/`

Docs and reference doctrine:

- `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`
- `docs/REPO_LIVING_MAP_2026-03-31.md`
- `docs/README.md`
- `specs/README.md`

Formal or likely durable spec material:

- `specs/Dharma_Corpus_Schema.md`
- `specs/KERNEL_CORE_SPEC.md`
- `specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md`
- `specs/TaskBoardCoordination.cfg`
- `specs/TaskBoardCoordination.tla`

Interpretation:

- these define runtime, operator, or formal truth
- they should be stabilized and clearly marked as canonical or active

### 2. Active But Bounded

These are legitimate working areas, but they should not sprawl or masquerade as canon.

Directories:

- `docs/plans/`
- `docs/missions/`
- `docs/architecture/`
- `docs/dse/`
- `docs/research/`
- `api/routers/`
- `dashboard/src/`
- `scripts/`
- `research/`
- `benchmarks/`
- `tools/`
- `desktop-shell/`
- `roaming_mailbox/`

Selected roots:

- `LIVING_LAYERS.md`
- `PRODUCT_SURFACE.md`
- `program.md`
- `program_ecosystem.md`

Interpretation:

- these are real working surfaces
- they need sharper boundaries and fewer top-level strays

### 3. Archive Candidate

These look useful historically, but they should stop competing with current truth.

Directories:

- `docs/archive/`
- `reports/historical/`
- `reports/architectural/`
- `reports/deployment_checks/`
- `reports/dashboard/restore_backups_2026-03-19/`
- `reports/gaia_eco_pilot_20260327/`
- `docs/merge/`
- `docs/clusters/`
- `spinouts/`

Likely reclassifiable root or near-root material:

- `CODEBASE_STRUCTURE_ANALYSIS.txt`
- `docs/architecture/SWARMLENS_MASTER_SPEC.md`
- `docs/architecture/GENOME_WIRING.md`

Interpretation:

- these should be preserved if valuable
- some belong in architecture-local doctrine rather than archive
- they should not remain mixed into current operating surfaces

### 4. Generated / Noise

These are high-volume and should not be treated as live human doctrine.

Directories:

- `.dharma_psmv_hyperfile_branch/`
- `.dharma_psmv_hyperfile_branch_v2/`
- `reports/psmv_hyperfiles_20260313/`
- `reports/dual_engine_swarm_20260313_run/`
- `reports/dgc_self_proving_packet_20260313/`
- `reports/witness/`
- `reports/nightwatch/`
- `reports/verification/`
- `.pytest_cache/`
- `.tmp_supervisor_smoke/`
- `dharma_swarm.egg-info/`

Files:

- `reports/repo_xray_2026-03-31.json`
- `synthesizer_memory.json`

Interpretation:

- keep if needed for evidence
- isolate from normal review flow
- do not let them compete with live design truth

### 5. Duplicate / Deprecated / Reclassify

These are not necessarily bad, but they are the most likely ontology-confusion sources.

Specs:

- `specs/DGC_TERMINAL_ARCHITECTURE.md`
- `specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md`
- `docs/prompts/PARALLEL_BUILD_AGENT_PROMPTS_2026-03-19.md`
- `docs/prompts/SOVEREIGN_BUILD_PHASE_MASTER_PROMPT_2026-03-19.md`
- `docs/archive/VERIFICATION_COMPLETE.md`

Docs likely needing reclassification or consolidation:

- `docs/TERMINAL_V2_OPERATOR_SHELL_SPEC_2026-04-01.md`
- `docs/TERMINAL_V3_OPERATOR_INTELLIGENCE_SPEC_2026-04-01.md`
- `docs/TERMINAL_REBUILD_2026-04-01.md`
- `docs/TERMINAL_OVERNIGHT_SUPERVISOR_2026-04-01.md`
- `docs/TERMINAL_FEASIBILITY_DECISION_2026-04-01.md`
- `docs/TERMINAL_ALPHA_FREEZE_2026-04-01.md`
- `docs/DHARMA_COMMAND_WORLD_CLASS_PRODUCT_SPEC_2026-04-01.md`
- `docs/DHARMA_COMMAND_POWER_BUILD_LOOP_SPEC_2026-04-01.md`
- `docs/HOT_PATH_INTEGRATION_PROTOCOL_2026-04-01.md`

Root markdown clutter likely needing relocation:

- `PRODUCT_SURFACE.md`
- `program.md`
- `program_ecosystem.md`
- `LIVING_LAYERS.md`
- `docs/architecture/GENOME_WIRING.md`
- `docs/architecture/SWARMLENS_MASTER_SPEC.md`

Interpretation:

- several of these may be valuable
- the problem is coexistence without an authority label

### 6. Cleanup-First

These are the highest-value non-TUI cleanup targets.

#### A. `docs/`

Why first:

- highest dirty count
- most ontology confusion
- most near-canonical drift

Main hotspots:

- `docs/reports/`
- `docs/plans/`
- `docs/missions/`
- top-level `docs/*.md`

Needed action:

- reduce top-level `docs/` to canon or near-canon only
- push transient packets into subdirectories
- archive superseded terminal and command specs

#### B. `reports/`

Why second:

- huge artifact footprint
- high noise-to-live-signal ratio

Main hotspots:

- `reports/psmv_hyperfiles_20260313/`
- `reports/dual_engine_swarm_20260313_run/`
- `reports/dgc_self_proving_packet_20260313/`
- `reports/verification/`

Needed action:

- split into `historical evidence` vs `generated artifacts`
- reduce top-level report clutter

#### C. Root Markdown Surface

Why third:

- creates immediate false-canon effect

Main clutter:

- `PRODUCT_SURFACE.md`
- `program.md`
- `program_ecosystem.md`
- `LIVING_LAYERS.md`
- `docs/architecture/GENOME_WIRING.md`
- `docs/architecture/SWARMLENS_MASTER_SPEC.md`
- `CODEBASE_STRUCTURE_ANALYSIS.txt`

Needed action:

- keep only true operator entrypoints and a very small canon set at root

#### D. `specs/` and `spec-forge/`

Why fourth:

- formal and non-formal material are mixed

Needed action:

- keep formal specs in `specs/`
- move prompt packets or planning packets elsewhere
- decide whether `spec-forge/` is active incubation or archive substrate

#### E. `foundations/`, `lodestones/`, `mode_pack/`

Why fifth:

- not the biggest dirt source
- but conceptually close enough to live doctrine to confuse agents

Needed action:

- preserve as substrate
- make explicit that these are foundation layers, not current runtime truth

## Top-Level Directory Assessment

### Keep Live

- `api/`
- `dashboard/`
- `dharma_swarm/`
- `tests/`
- `scripts/`
- `tools/`
- `.github/`

### Bounded Working Domains

- `docs/`
- `specs/`
- `research/`
- `benchmarks/`
- `desktop-shell/`
- `roaming_mailbox/`

### Likely Archive / Historical

- `reports/architectural/`
- `reports/historical/`
- `spinouts/`

### Generated / Quarantine

- `.dharma_psmv_hyperfile_branch/`
- `.dharma_psmv_hyperfile_branch_v2/`
- portions of `reports/`

### Conceptual Substrate

- `foundations/`
- `lodestones/`
- `mode_pack/`
- parts of `spec-forge/`

## Conflict Risks While Cleaning Around The Hot Lane

1. Moving terminal-adjacent docs too early can break context for the TUI convergence pass.
2. Reclassifying shared operator docs without a canon label may create new confusion instead of removing it.
3. Broad root-drain passes can accidentally sweep up still-active build packets.
4. `dashboard/` is active product work and should not be treated like inert clutter.
5. `dharma_swarm/` outside the TUI files is still live runtime code and should not be “cleaned” like docs.

## Recommended Cleanup Order

1. Freeze and label the hot TUI lane as excluded.
2. Reduce top-level `docs/` to canon, doctrine, and true near-canon only.
3. Reclassify `reports/` into historical vs generated.
4. Drain root markdown clutter into canonical homes or archive.
5. Separate formal `specs/` from prompt/build packets.
6. Mark `foundations/`, `lodestones/`, and `mode_pack/` as substrate, not live doctrine.

## Immediate Practical Rule

For the rest of the repo, outside the TUI lane:

- if it defines live runtime behavior, keep it close
- if it describes current doctrine, mark it clearly
- if it is a plan, bound it
- if it is a report, historicize it
- if it is generated, quarantine it
- if it duplicates something else, force an authority decision

That is the shortest path to an orderly repo without cooling the terminal rebuild.
