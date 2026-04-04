---
title: Repo Hygiene Triage Memo
path: docs/plans/REPO_HYGIENE_TRIAGE_2026-04-01.md
slug: repo-hygiene-triage-2026-04-01
doc_type: plan
status: active
summary: "Date: 2026-04-01 Purpose: classify the dirty tree into hot-path, docs/spec, generated-state, and risky groups without editing the hot path."
source:
  provenance: repo_local
  kind: plan
  origin_signals:
  - dashboard/src/app/dashboard/layout.tsx
  - dashboard/src/lib/dashboardNav.ts
  - terminal/
  - reports/repo_xray_2026-03-31.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- operations
- verification
- software_architecture
- knowledge_management
inspiration:
- verification
- operator_runtime
connected_relevant_files:
- docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
- docs/plans/2026-04-02-non-tui-repo-hygiene-map.md
- docs/plans/2026-04-02-repo-dirt-taxonomy-and-run-plan.md
- reports/repo_xray_2026-03-31.md
pkm:
  note_class: plan
  vault_path: docs/plans/REPO_HYGIENE_TRIAGE_2026-04-01.md
  retrieval_terms:
  - repo
  - hygiene
  - triage
  - dirty tree
  - cleanup
  evergreen_potential: medium
stigmergy:
  meaning: This file is a bounded dirty-tree triage packet rather than top-level canon.
  state: active
  semantic_weight: 0.72
  coordination_comment: Use this when you need the early dirty-tree split, not as canonical repo doctrine.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T12:00:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# Repo Hygiene Triage Memo

Date: 2026-04-01
Repo: `dharma_swarm`
Scope: dirty-tree classification only; no hot-path edits

## Clean vs Dirty Summary

- Repo state is decisively dirty.
- `git status --short` shows 508 changed paths total.
- 499 tracked files are modified.
- 9 top-level paths are untracked.
- `git diff --stat` reports 499 changed files with about 44,369 insertions and 523 deletions.
- There are no staged changes.
- Hot-path dashboard files are already dirty and should be treated as actively in-flight:
  - `dashboard/src/app/dashboard/layout.tsx`
  - `dashboard/src/app/dashboard/page.tsx`
  - `dashboard/src/lib/dashboardNav.ts`
  - `dashboard/src/lib/dashboardNav.test.ts`

## Classification

### Product

- Active product code:
  - `dashboard/src/...`
  - `dharma_swarm/__init__.py`
  - `dharma_swarm/dgc_cli.py`
  - `dharma_swarm/tui/...`
- Product-adjacent implementation experiments:
  - `dharma_swarm/terminal_bridge.py` (untracked)
  - `terminal/` app tree (untracked)

### Docs/Spec

- Very large docs/spec drift dominates the tree:
  - `docs/` (206 paths)
  - `specs/` (22 paths)
  - `spec-forge/` (17 paths)
  - `architecture/`, `benchmarks/`, `desktop-shell/`, `research/`
  - many root-level `*.md` strategy/spec/report files
- These appear to be planning, architecture, prompts, reports, and narrative repo-shaping material rather than the active dashboard hot path.

### Generated/Report/State

- Machine- or run-generated state appears heavily represented in:
  - `.dharma_psmv_hyperfile_branch/`
  - `.dharma_psmv_hyperfile_branch_v2/`
  - `reports/`
  - `reports/repo_xray_2026-03-31.{json,md}` (untracked)
- These are the safest candidates to treat as non-hot-path noise during current product work.

### Experimental

- Experimental or parallel-surface work likely exists in:
  - `terminal/` (untracked TypeScript app tree)
  - `dharma_swarm/terminal_bridge.py` (untracked)
  - `scripts/normalize_markdown_frontmatter.rb` (untracked utility)
  - `docs/TERMINAL_REBUILD_2026-04-01.md`
  - `docs/SWARM_FRONTEND_MASTER_SPEC_2026-04-01.md`

### Unknown

- Nothing looks truly mysterious, but a few buckets need owner clarification before review:
  - `foundations/`
  - `lodestones/`
  - `mode_pack/`
  - root files such as `program.md`, `program_ecosystem.md`, `docs/dse/GAIA_UI.md`, `xray_report.md`
- These read as real repo content, but their intended lifecycle is unclear from filename alone.

## Safe-to-Ignore Groups For Current Hot Path

- Generated run/state material under `.dharma_psmv_hyperfile_branch*`
- Most of `reports/`, especially dated run artifacts and audit outputs
- Bulk docs/spec churn under `docs/`, `specs/`, `spec-forge/`, `architecture/`, `research/`
- Experimental terminal work under `terminal/` and `dharma_swarm/terminal_bridge.py`, as long as nobody expects it in the current dashboard/control-plane path
- Untracked xray/report outputs under `reports/repo_xray_2026-03-31.*`

## Risky Groups

- Hot-path dashboard edits already present in tracked files:
  - `dashboard/src/app/dashboard/layout.tsx`
  - `dashboard/src/app/dashboard/page.tsx`
  - `dashboard/src/lib/dashboardNav.ts`
  - `dashboard/src/lib/dashboardNav.test.ts`
- Shared runtime/package changes that could complicate later merge review:
  - `dharma_swarm/__init__.py`
  - `dharma_swarm/dgc_cli.py`
  - `dharma_swarm/tui/...`
- The untracked `terminal/` surface is risky for later review because it is a substantial parallel product area, not a tiny scratch file.
- Large-scale docs/spec drift is individually low-risk to runtime, but collectively high-risk to review clarity because it buries the few product deltas inside hundreds of unrelated changes.

## Recommended Cleanup Order After Current Hot Path

1. Freeze and isolate the active dashboard/control-plane work first; do not mix it with repo-wide hygiene.
2. Separate generated/state artifacts into their own cleanup decision, especially `.dharma_psmv_hyperfile_branch*` and dated `reports/`.
3. Decide whether `terminal/` plus `dharma_swarm/terminal_bridge.py` is a real branch of work; if yes, isolate it into a dedicated commit or branch.
4. Split runnable product/runtime changes (`dharma_swarm/*.py`, `dharma_swarm/tui/...`, non-hot-path dashboard files) away from docs/spec churn.
5. Triage docs/spec material into smaller thematic batches instead of one giant mixed review.
6. Resolve the ambiguous content buckets (`foundations/`, `lodestones/`, `mode_pack/`, root narrative files) last, after ownership is clear.

## Bottom Line

- Current repo state is not review-friendly.
- The hot path is already dirty.
- Most noise is docs/spec and generated state, which is safe to ignore temporarily.
- The main future-merge hazards are the active dashboard edits and the untracked `terminal/` product surface hidden inside a repo-wide documentation storm.
