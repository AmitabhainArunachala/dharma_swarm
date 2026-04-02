---
title: Root Helper Artifact Policy
path: docs/plans/2026-04-02-root-helper-artifact-policy.md
slug: root-helper-artifact-policy
doc_type: plan
status: active
summary: Separates root-level helper artifacts, generated analysis files, and operational state files from prose cleanup so root hygiene does not treat every odd file as the same class of problem.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
    - CODEBASE_STRUCTURE_ANALYSIS.txt
    - uv.lock
    - synthesizer_memory.json
    - git status --short
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
  - repository_hygiene
  - operations
  - knowledge_management
inspiration:
  - repo_hygiene
  - canonical_truth
connected_relevant_files:
  - docs/plans/2026-04-02-cleanup-control-center.md
  - CODEBASE_STRUCTURE_ANALYSIS.txt
  - uv.lock
  - synthesizer_memory.json
  - docs/plans/2026-04-02-root-residue-classification.md
  - docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md
improvement:
  room_for_improvement:
    - Decide whether uv should become a first-class package-management path in this repo.
    - Rehome generated analysis artifacts into reports or archive once ownership is clear.
    - Separate runtime state files from helper-analysis outputs in future audits.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-root-helper-artifact-policy.md
  retrieval_terms:
    - root
    - helper
    - artifact
    - uv.lock
    - analysis
  evergreen_potential: medium
stigmergy:
  meaning: This file prevents root cleanup from confusing package-management state, runtime state, and generated analysis artifacts.
  state: active
  semantic_weight: 0.79
  coordination_comment: Use this file when triaging odd root-level files that are not prose canon and not obvious product entrypoints.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-02T23:59:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# Root Helper Artifact Policy

## Purpose

Some root-level files are neither prose canon nor product/runtime entrypoints.

If they are not classified explicitly, they inflate the feeling that the root is “randomly dirty” even when the underlying issue is smaller and more specific.

## Current Cases

### `CODEBASE_STRUCTURE_ANALYSIS.txt`

Character:

- generated or semi-generated analysis artifact
- dated and descriptive
- not suitable as root canon

Recommended class:

- helper analysis artifact
- eventual destination should be `reports/` or `docs/archive/` once ownership is clear

### `uv.lock`

Character:

- operational dependency lockfile
- package-management state, not prose
- its presence is only a problem if the repo is not actually standardizing on uv

Recommended class:

- operational build/dependency artifact
- evaluate as packaging policy, not as docs clutter

### `synthesizer_memory.json`

Character:

- runtime/helper state
- not repo canon
- not product-facing prose

Recommended class:

- local or helper state artifact
- should eventually be judged against runtime-state storage rules, not prose rules

## Rule

Do not fold these into generic prose cleanup.

When a root-level file is odd but not prose, first decide whether it is:

1. generated analysis
2. dependency/build state
3. runtime/helper state
4. actual accidental residue

Only then decide whether it should move, remain, or be ignored.

## Why This Matters

This prevents one of the main cleanup mistakes:

treating every strange root file like evidence of the same problem.

The root can be noisy for different reasons, and each reason needs a different fix.
