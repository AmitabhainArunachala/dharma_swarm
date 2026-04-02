---
title: Generated Artifact Boundary Matrix
path: docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
slug: generated-artifact-boundary-matrix
doc_type: plan
status: active
summary: "Date: 2026-04-02 Scope: classify generated operational traces versus durable authored material and define the generated-report quarantine boundary."
source:
  provenance: repo_local
  kind: plan
  origin_signals:
  - reports/nightwatch/terminal_nightwatch_20260401.log
  - reports/repo_xray_2026-03-31.md
  - scripts/terminal_nightwatch.sh
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- knowledge_management
- operations
- verification
inspiration:
- operator_runtime
- verification
connected_relevant_files:
- docs/plans/2026-04-02-generated-artifact-control-center.md
- docs/plans/2026-04-02-cleanup-control-center.md
- docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md
- reports/repo_xray_2026-03-31.md
- reports/generated/README.md
- scripts/terminal_nightwatch.sh
- docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
improvement:
  room_for_improvement:
  - Distinguish retained generated packet families from low-coupling generated logs more sharply.
  - Add follow-up rules for path-coupling cleanup before larger report-family relocations.
  next_review_at: '2026-04-03T00:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
  retrieval_terms:
  - generated
  - artifacts
  - reports
  - boundary
  - quarantine
  - control center
  evergreen_potential: high
stigmergy:
  meaning: This file defines the generated-vs-authored boundary for report and run-output cleanup.
  state: working
  semantic_weight: 0.85
  coordination_comment: Use this file before moving or reviewing generated report families.
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
# Generated Artifact Boundary Matrix

Date: 2026-04-02
Repo: `dharma_swarm`
Scope: classify generated operational traces versus durable authored material

This pass does not delete anything. It defines handling boundaries so future cleanup can separate authored truth from run output.

## Classification Matrix

| Path family | Current contents | Classification | Git posture | Canonical home |
|-------------|------------------|----------------|-------------|----------------|
| `.dharma_psmv_hyperfile_branch/**` | mission metadata, PID/log files, shared handoffs, timestamped artifact notes | generated branch state | should not be treated as source of truth | dedicated generated-state bucket if retained at all |
| `.dharma_psmv_hyperfile_branch_v2/**` | second generated branch state set with the same shape | generated branch state | should not be treated as source of truth | dedicated generated-state bucket if retained at all |
| `reports/psmv_hyperfiles_20260313/**` | generated hyperfile staging set, semantic summaries, manifest, and corpus bridge outputs | retained generated packet family | keep in place for now because code, tests, and mission docs still point at it | future `reports/generated/psmv_hyperfiles_20260313/` after path-coupling cleanup |
| `reports/dual_engine_swarm_20260313_run/**` | run packet plus state, semantic graph, and generated mission traces | retained generated packet family | keep in place for now because code, tests, and report packets still point at it | future `reports/generated/dual_engine_swarm_20260313_run/` after path-coupling cleanup |
| `reports/dual_engine_swarm_20260313_run/state/shared/artifacts/**` | timestamped execution chamber outputs and prompts | generated run artifacts | keep only if needed for replay/audit | `reports/generated/dual_engine_swarm_20260313_run/...` |
| `reports/dual_engine_swarm_20260313_run/state/shared/*.md` | morning brief, handoff, latest director state, timestamped visions | generated run state with some audit value | durable for audit, not for canon | `reports/generated/dual_engine_swarm_20260313_run/...` |
| `reports/dual_engine_swarm_20260313_run/state/logs/**` | jsonl and log files | generated logs | generated-only | `reports/generated/...` or external run storage |
| `reports/nightwatch/*.log` | terminal watchdog log output | generated log | generated-only; migrated into generated subtree in this cleanup wave | `reports/generated/nightwatch/` or external run storage |
| `reports/repo_xray_2026-03-31.{md,json}` | inventory snapshot and machine-readable xray output | generated report with review value | acceptable in git if intentionally versioned | `reports/` |
| `reports/historical/**` | historical audits and completion reports | durable historical authored material | keep in git | `reports/historical/` |
| `docs/**` | authored canon, plans, prompts, research, and archive prose | authored documentation | keep in git | `docs/` |

## Decision Rules

- `generated branch state`: machine-written working state from a live branch or run; never canonical.
- `generated run artifacts`: useful for replay, forensics, or audit, but not implementation truth.
- `durable historical authored material`: keep readable in git because humans may cite it later.
- `authored documentation`: intentional docs and specs with explicit ownership and navigation.

## Immediate Observations

- `.dharma_psmv_hyperfile_branch/**` and `.dharma_psmv_hyperfile_branch_v2/**` contain `.pid`, `.log`, heartbeat, handoff, and timestamped trace files. That is operational state, not authored source.
- `reports/psmv_hyperfiles_20260313/**` is also generated/report-like in character, but it is still referenced by code, tests, and mission docs, so it is not yet a safe relocation seam.
- `reports/dual_engine_swarm_20260313_run/state/shared/**` follows the same pattern under a report tree. It has more historical audit value than the hyperfile branches, but it is still run state first.
- `reports/dual_engine_swarm_20260313_run/**` is similarly generated-heavy, but its `state/` subtree is still referenced by code, tests, and adjacent packet docs, so relocation should wait for a path-coupling pass.
- `reports/nightwatch/terminal_nightwatch_20260401.log` was rehomed under `reports/generated/nightwatch/` as the first concrete generated-report quarantine move.

## Recommended Next Move

1. Keep building out the canonical `reports/generated/` subtree for retained run output.
2. Move only low-coupling generated families there first.
3. Treat `reports/psmv_hyperfiles_20260313/**` and `reports/dual_engine_swarm_20260313_run/**` as retained generated packet families until path-coupling cleanup lands.
4. Keep `reports/historical/` separate from generated state.
5. Add ignore or export rules later, after deciding which generated families should leave git entirely.

Current control entrypoint:

- `docs/plans/2026-04-02-generated-artifact-control-center.md`
- `docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md`

Main cleanup doctrine entrypoint:

- `docs/plans/2026-04-02-cleanup-control-center.md`

## Hard Boundary

Until a follow-up cleanup lands, do not use `.dharma_psmv_hyperfile_branch*/`, `reports/**/state/`, or `reports/generated/**` as architectural truth in reviews, docs, or tests.
