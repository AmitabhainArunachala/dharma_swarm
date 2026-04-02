---
title: Repo Ontology And Hygiene Master Spec
path: docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
slug: repo-ontology-and-hygiene-master-spec
doc_type: spec
status: canonical
summary: "Date: 2026-04-01 Scope: non-hot-path architecture and repository cleanup doctrine. Defines the ontology and precedence rules for the prose and artifact layer."
source:
  provenance: repo_local
  kind: spec
  origin_signals:
  - README.md
  - CLAUDE.md
  - docs/README.md
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
- verification
- product_surface
connected_relevant_files:
- README.md
- CLAUDE.md
- docs/README.md
- docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md
- docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
- reports/repo_xray_2026-03-31.md
improvement:
  room_for_improvement:
  - Keep the canon set small and explicit.
  - Reconcile doctrine language with the latest cleanup tranches.
  - Strengthen links from doctrine to current move waves and validation notes.
  next_review_at: '2026-04-03T00:00:00+09:00'
pkm:
  note_class: spec
  vault_path: docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
  retrieval_terms:
  - repo
  - ontology
  - hygiene
  - canon
  - cleanup
  - precedence
  evergreen_potential: high
stigmergy:
  meaning: This file defines the prose-layer ontology and authority ordering for the DHARMA repo.
  state: canonical
  semantic_weight: 0.95
  coordination_comment: Use this file to decide what class a file belongs to before moving or creating it.
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
# Repo Ontology And Hygiene Master Spec

Date: 2026-04-01
Repo: `dharma_swarm`
Scope: non-hot-path architecture and repository cleanup doctrine
Status: proposed canonical cleanup doctrine

## Executive Thesis

The repo is not failing because it has many files. It is failing because too many files claim to be canonical at the same time.

The underlying defect is ontological:

- root contains strategy, specs, prompts, reports, and operator notes with equal visual status
- `docs/`, `specs/`, `reports/`, `foundations/`, and `spec-forge/` overlap in purpose
- generated state and durable knowledge coexist without a strict boundary
- multiple documents describe product truth, architecture truth, and runtime truth without an explicit precedence order

This spec fixes that by defining a repository ontology and a hygiene contract.

## Diagnosis

Dirty-tree distribution at time of writing:

- `docs`: 209 changed paths
- `reports`: 109 changed paths
- `foundations`: 25 changed paths
- `.dharma_psmv_hyperfile_branch*`: 37 changed paths
- `specs`: 22 changed paths
- `spec-forge`: 17 changed paths
- `dharma_swarm`: 15 changed paths
- `lodestones`: 14 changed paths
- `mode_pack`: 9 changed paths
- `dashboard`: 8 changed paths

Interpretation:

- the repo is dominated by narrative and artifact churn, not by runtime churn
- most confusion comes from documentation ontology, not code architecture alone
- root-level markdown is currently acting as an unbounded semantic junk drawer

## Canonical Precedence Order

When two files disagree, this is the order of truth:

1. Runtime truth
   - executable code in `dharma_swarm/`, `api/`, `dashboard/`
   - tests in `tests/`

2. Operator truth
   - `README.md`
   - explicit launcher and entrypoint files such as `run_operator.sh`, `pyproject.toml`, `dashboard/package.json`

3. Canonical design truth
   - a small number of named master specs in `docs/` or `specs/`

4. Working design packets
   - active plans, mission docs, and build packets

5. Research and foundation synthesis
   - conceptual and exploratory material

6. Reports and generated artifacts
   - inventories, audits, xray outputs, branch state traces, run logs

If a lower layer contradicts a higher layer, the lower layer is non-canonical until reconciled.

## Repository Ontology

Every non-code file must belong to exactly one class.

### Class 1: Canon

Definition:

- durable files that define current operator, product, or architecture truth

Allowed examples:

- `README.md`
- `CLAUDE.md`
- one repo map
- one frontend master spec
- one canonical product-surface statement

Rules:

- must be few
- must be intentionally maintained
- must link directly to implementing code
- must not duplicate one another

### Class 2: Active Spec

Definition:

- implementation-driving design docs for current or imminent work

Allowed examples:

- a current subsystem master spec
- a current migration or architecture packet
- a current formal spec in `specs/`

Rules:

- must have an owner, date, and intended target area
- must state whether it is canonical, advisory, or superseded
- should eventually resolve into code, canon, or archive

### Class 3: Working Plan

Definition:

- execution-oriented planning material for a bounded effort

Allowed examples:

- mission docs
- overnight plans
- batch prompts
- lane maps

Rules:

- time-bounded
- explicitly non-canonical
- must not live at repo root

### Class 4: Foundation

Definition:

- conceptual substrate, philosophical basis, research synthesis, glossary

Allowed examples:

- `foundations/`
- deep theory notes

Rules:

- never describe shipped behavior as if already true
- should support, not override, runtime or product truth

### Class 5: Report

Definition:

- descriptive outputs about the repo or system state at a point in time

Allowed examples:

- xray outputs
- audits
- forensics
- completion reports

Rules:

- historical by default
- should be timestamped
- must not masquerade as enduring architecture truth

### Class 6: Generated State

Definition:

- machine-produced transient traces or shared-branch artifacts

Allowed examples:

- `.dharma_psmv_hyperfile_branch*`
- generated inventories
- branch handoff traces

Rules:

- never canonical
- ideally excluded from normal review flow
- should be isolated from durable human docs

## Directory Contract

This repo needs a sharper directory ontology.

### Root

Root is for:

- bootstrap files
- true operator entrypoints
- one or two canonical orientation docs

Root is not for:

- completion reports
- prompts
- historical plans
- speculative product specs
- audit outputs

Root should converge toward:

- `README.md`
- `CLAUDE.md`
- essential build/runtime files
- a very small number of genuinely canonical notes only if unavoidable

### `docs/`

Purpose:

- active human-readable architecture and implementation doctrine

Allowed subdomains:

- `docs/canon/`
- `docs/plans/`
- `docs/missions/`
- `docs/archive/`
- topic-specific subtrees such as `docs/dse/`

Contract:

- `docs/` is the primary home for durable prose that is not formal verification
- top-level `docs/` should contain only canonical or near-canonical docs
- dated transient docs belong in subdirectories, not the top level

### `specs/`

Purpose:

- formal specs, invariants, protocol specs, and machine-checkable models

Contract:

- if a file in `specs/` is not formal, protocol-level, or verification-oriented, it probably belongs elsewhere
- `specs/README.md` should describe formal and active spec status, not act as a catch-all build packet noticeboard

### `reports/`

Purpose:

- dated descriptive outputs

Contract:

- reports never define product truth
- generated and hand-authored reports can live here, but they must be treated as historical evidence

### `foundations/`

Purpose:

- research substrate and conceptual bedrock

Contract:

- foundational claims should be durable and few
- tactical plans and implementation packets do not belong here

### `.dharma_psmv_*`

Purpose:

- branch-local or run-local shared traces

Contract:

- operational scratch/state only
- should be excluded from ordinary product review and kept semantically separate from docs

## Canonical File Set Recommendation

The repo should converge on a compact canon set.

Recommended top-tier canon:

- `README.md`
- `CLAUDE.md`
- `PRODUCT_SURFACE.md`
- `docs/REPO_LIVING_MAP_2026-03-31.md`
- `docs/SWARM_FRONTEND_MASTER_SPEC_2026-04-01.md`
- `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`

Everything else should explicitly identify as one of:

- active spec
- working plan
- foundation
- report
- generated state
- archived historical material

## Root-Level Remediation

Current root contains many files that should not remain peers of `README.md`.

### Root Files To Reclassify

These are the files or file families that were structurally wrong at root and therefore needed reclassification, regardless of content quality:

- `SWARMLENS_MASTER_SPEC.md`
- `docs/architecture/INTEGRATION_MAP.md`
- `docs/architecture/NAVIGATION.md`
- `FULL_REPO_AUDIT_2026-03-28.md`
- `CONSTITUTIONAL_XRAY_REPORT.md`
- `CONSTITUTIONAL_HARDENING_SPRINT_REPORT.md`
- `DUAL_SPRINT_COMPLETION_REPORT.md`
- `PHASE2_COMPLETION_REPORT.md`
- `PHASE3_COMPLETION_REPORT.md`
- `docs/architecture/VERIFICATION_LANE.md`
- `WAVE2_ACCEPTANCE_CHECKLIST.md`
- `MEGA_PROMPT_*`
- `STRANGE_LOOP_COMPLETE_PROMPT*`
- `docs/prompts/ORTHOGONAL_UPGRADE_PROMPT.md`
- `docs/prompts/PALANTIR_UPGRADE_PROMPT.md`
- `docs/prompts/STRATEGIC_PROMPT.md`
- `docs/archive/UNASSAILABLE_SYSTEM_BLUEPRINT.md`
- `docs/archive/MOONSHOT_COMPLETE.md`
- `GENOME_WIRING.md`

Recommended treatment:

- move reports to `reports/` or `docs/archive/`
- move prompts to `docs/prompts/` or `docs/archive/prompts/`
- move durable architecture notes to `docs/canon/` or `docs/architecture/`
- keep root clear enough that a newcomer can understand the repo in under two minutes

## Naming Contract

Naming is currently semantically noisy.

### Required Naming Rules

1. If dated, the file is historical or versioned, not timeless canon.
2. If a file contains `REPORT`, `AUDIT`, `CHECKLIST`, `MISSION`, or `PROMPT`, it is non-canonical by default.
3. If a file claims `MASTER_SPEC`, it must name its scope narrowly and identify whether it supersedes another file.
4. Root-level files should avoid theatrical naming unless they are intentionally canonical and widely referenced.
5. “Complete”, “unassailable”, “masterpiece”, and similar victory language should not determine placement or authority.

## Lifecycle Contract

Every prose artifact should expose one lifecycle state:

- `canonical`
- `active`
- `advisory`
- `historical`
- `generated`
- `superseded`

And one authority role:

- `operator_truth`
- `product_truth`
- `architecture_truth`
- `plan`
- `research`
- `report`
- `state_trace`

The repo already has rich frontmatter. The problem is not missing metadata. The problem is missing enforcement and precedence.

## Cleanup Program

This should happen in four non-hot-path waves.

### Wave 1: Canon Isolation

Goal:

- identify the true canon and stop the rest from pretending to be canon

Actions:

- bless a compact canonical file set
- add explicit status and authority guidance to canon docs where missing
- stop adding new root-level markdown except for true canon

### Wave 2: Root Drain

Goal:

- remove semantic noise from root

Actions:

- relocate prompts, reports, and historical completion docs
- reserve root for bootstrapping and canon only

### Wave 3: Docs Topology

Goal:

- make `docs/` readable as an information architecture

Actions:

- separate `canon`, `plans`, `missions`, `archive`, and topic domains
- reduce top-level `docs/` clutter
- ensure `docs/README.md` describes the docs ontology, not just one subsystem

### Wave 4: Generated-State Quarantine

Goal:

- isolate run artifacts from durable knowledge

Actions:

- keep `.dharma_psmv_*` explicitly non-canonical
- review whether generated handoff/state artifacts should be ignored, archived, or relocated outside the normal repo surface

## Immediate Non-Hot-Path Priorities

Top 10 cleanup priorities outside the hot path:

1. establish this ontology as the repo-wide cleanup doctrine
2. define the compact canonical file set
3. drain root-level markdown into proper homes
4. rewrite `docs/README.md` into a docs ontology entrypoint
5. sharpen `specs/README.md` so it only speaks for formal and active protocol specs
6. separate reports from architecture truth more aggressively
7. quarantine `.dharma_psmv_*` from ordinary review thinking
8. normalize prompt and mission docs into clearly non-canonical subtrees
9. add an archive/superseded policy for aging master specs
10. only then perform broad renames or moves

## What Not To Do

- do not mix this cleanup with the dashboard hot path
- do not do mass renames before canon is defined
- do not treat every articulate markdown file as equally authoritative
- do not let generated state inherit the status of architecture docs
- do not keep solving ontology confusion with more root-level notes

## Standard For Success

This cleanup succeeds when:

- a new operator can find the canonical truth in under two minutes
- a build agent can tell canon from report from prompt from state trace at a glance
- root no longer behaves like an archaeological midden
- `docs/`, `specs/`, `reports/`, and generated-state areas have non-overlapping meaning
- historical and generated material remain available without polluting active engineering judgment

## Bottom Line

The repo does not need less intelligence. It needs stronger semantic boundaries.

The right cleanup is not cosmetic deletion. It is ontological compression:

- fewer claims to authority
- clearer lifecycle states
- sharper directory meaning
- explicit precedence between code, canon, plans, research, reports, and generated state

That is how this repo becomes legible without flattening its ambition.
