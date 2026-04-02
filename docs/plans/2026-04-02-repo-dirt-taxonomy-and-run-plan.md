---
title: Repo Dirt Taxonomy And Run Plan
path: docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md
slug: repo-dirt-taxonomy-and-run-plan
doc_type: plan
status: active
summary: Breaks the current dirty worktree into expected hot-lane churn, structured cleanup churn, generated-state churn, and suspicious residue so cleanup runs can be sequenced intentionally.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
    - git status --short
    - docs/plans/2026-04-02-current-meta-topology-of-dharma-swarm.md
    - docs/plans/2026-04-02-non-tui-repo-hygiene-map.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
  - knowledge_management
  - software_architecture
  - operations
  - repository_hygiene
inspiration:
  - repo_hygiene
  - canonical_truth
connected_relevant_files:
  - docs/plans/2026-04-02-cleanup-control-center.md
  - docs/plans/2026-04-02-generated-artifact-control-center.md
  - docs/plans/2026-04-02-current-meta-topology-of-dharma-swarm.md
  - docs/plans/2026-04-02-non-tui-repo-hygiene-map.md
  - docs/plans/2026-04-02-frontmatter-alignment-map.md
  - docs/plans/2026-04-02-specs-spec-forge-seam-plan.md
  - docs/plans/2026-04-02-root-residue-classification.md
  - docs/plans/2026-04-02-root-helper-artifact-policy.md
  - docs/plans/2026-04-02-root-operational-notes-policy.md
  - docs/plans/2026-04-02-root-next-tranche-plan.md
  - docs/plans/2026-04-02-substrate-layer-policy.md
improvement:
  room_for_improvement:
    - Convert this taxonomy into a small recurring cleanup dashboard.
    - Recompute counts after the next specs tranche lands.
    - Split root-level residue into active canon versus archive candidates.
    - Keep generated-artifact handling linked to its own control surface rather than burying it inside root cleanup notes.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md
  retrieval_terms:
    - repo dirt
    - cleanup
    - taxonomy
    - git status
    - hygiene
  evergreen_potential: medium
stigmergy:
  meaning: This file explains why the repo looks dirty and turns that noise into explicit cleanup classes.
  state: active
  semantic_weight: 0.86
  coordination_comment: Use this file to decide whether a dirty path is expected hot-lane churn, structured cleanup work, generated-state noise, or something that deserves scrutiny.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# Repo Dirt Taxonomy And Run Plan

## Current Reality

The repo is still globally dirty, but the dirt is not one thing.

Current control entrypoint:

- `docs/plans/2026-04-02-cleanup-control-center.md`

There are no current merge-conflict files. The main issue is that active work from several categories is showing up in one worktree at the same time.

Recent top-level dirty counts from `git status --short`:

- `docs`: 264
- `reports`: 120
- `dharma_swarm`: 37
- `dashboard`: 33
- `.dharma_psmv_hyperfile_branch`: 25
- `foundations`: 25
- `specs`: 22
- `spec-forge`: 18
- `tests`: 17
- `lodestones`: 14
- `.dharma_psmv_hyperfile_branch_v2`: 12
- `scripts`: 10
- `mode_pack`: 9

## The Four Dirt Classes

### 1. Expected Hot-Lane Dirt

This is not a cleanup failure. It is intentional active work.

Examples:

- `terminal/`
- `dashboard/`
- `dharma_swarm/`
- parts of `tests/`

Interpretation:

- these paths are actively evolving
- they should be stabilized in bounded implementation slices, not forced clean prematurely

### 2. Structured Cleanup Dirt

This is good dirt. It comes from deliberate reclassification and relocation work.

Examples:

- `docs/`
- parts of `specs/`
- parts of `reports/`
- root-level markdown draining into better homes

Interpretation:

- this is the repo getting more truthful
- it often appears noisy in Git because moves, adds, deletes, frontmatter edits, and backlink repairs all happen together

### 3. Generated-State Dirt

This is artifact-like churn that should eventually be isolated, not treated as live canon.

Examples:

- `.dharma_psmv_hyperfile_branch`
- `.dharma_psmv_hyperfile_branch_v2`
- parts of `reports/`

Interpretation:

- these paths are one of the biggest reasons the tree feels dirtier than the live product actually is
- some are safe to quarantine
- some still have path coupling and must stay in place for now

Current control entrypoint:

- `docs/plans/2026-04-02-generated-artifact-control-center.md`

### 4. Suspicious Or Root-Residue Dirt

This is where scrutiny is still warranted.

Examples:

- lingering root-level deletes and top-level markdown residue
- untracked helper scripts and references directories
- any path whose role is unclear from location alone
- helper-analysis artifacts such as `CODEBASE_STRUCTURE_ANALYSIS.txt`
- operational lock/state files whose role should be decided explicitly, such as `uv.lock`

Interpretation:

- this is the class most likely to contain “why is this even here?” confusion
- these paths should be triaged deliberately rather than folded into generic cleanup

## What Is Driving The Noise Right Now

The repo feels unexpectedly dirty because several large processes are overlapping:

1. hot product development
2. prose and ontology cleanup
3. root-drain and authority reduction
4. frontmatter normalization
5. generated artifact quarantine

That means a single `git status` view is mixing:

- active engineering
- semantic filing work
- metadata repair
- historical relocation
- generated-state handling

## What Is Actually Healthy About The Current State

Even though the raw count is still high:

- there are no merge-conflict files right now
- dangerous root-drain ambiguity has already been stabilized
- top-level `docs/` is becoming less false-canonical
- frontmatter is increasingly aligned with file placement
- generated report quarantine has started
- the next seams are becoming clearer instead of more confused

## What Still Needs Tight Control

### Root-Level Residue

Several root-level files still show deletes or churn. That is one of the clearest remaining sources of “why is the repo this dirty?” confusion.

See: `docs/plans/2026-04-02-root-residue-classification.md`
See also:

- `docs/plans/2026-04-02-root-helper-artifact-policy.md`
- `docs/plans/2026-04-02-root-operational-notes-policy.md`
- `docs/plans/2026-04-02-root-next-tranche-plan.md`

### Specs vs Forge

`specs/` is now documented well, but still contains a few plainly non-normative files.

### Generated Packet Families

Some generated families can be moved. Others are still path-coupled and should not be forced.

### Substrate Layers

`foundations/`, `lodestones/`, and `mode_pack/` still need sharper classification.

Current progress:

- `lodestones/` now has an explicit local index at `lodestones/README.md`
- substrate handling policy now lives at `docs/plans/2026-04-02-substrate-layer-policy.md`
- the remaining work is to settle the boundary between conceptual canon (`foundations/`), orienting substrate (`lodestones/`), and operational workflow contract (`mode_pack/`)

## Run Plan

### Near-Term Bounded Runs

1. complete the current `specs/` prompt-and-closeout tranche
2. audit root-level residue into canon, archive, or historical buckets
3. finish substrate classification for `foundations/`, `lodestones/`, and `mode_pack/`

### What Not To Do

- do not try to clean the entire repo in one pass
- do not force generated families to move while they are still path-coupled
- do not demand a clean worktree from the hot TUI lane while it is actively converging

## Plain-English Read

The repo is dirty because several different kinds of work are mixed together in one Git view.

That does not mean the repo is incoherent.
It means the repo is in the middle of being sorted into:

- living code
- current doctrine
- plans and prompts
- historical memory
- generated artifacts

The cleanup goal is not “few changed files.”
The cleanup goal is “changed files that belong to understandable classes.”
