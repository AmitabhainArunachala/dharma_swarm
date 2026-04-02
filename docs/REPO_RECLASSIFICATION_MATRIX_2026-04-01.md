---
title: Repo Reclassification Matrix
path: docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md
slug: repo-reclassification-matrix
doc_type: plan
status: active
summary: "Date: 2026-04-01 Scope: non-hot-path cleanup matrix translating the repo ontology doctrine into path-level reclassification decisions."
source:
  provenance: repo_local
  kind: plan
  origin_signals:
  - docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
  - docs/README.md
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
- docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
- docs/README.md
- docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
- docs/plans/2026-04-02-non-tui-repo-hygiene-map.md
improvement:
  room_for_improvement:
  - Reconcile this matrix with completed cleanup tranches so moved paths point only at current locations.
  - Split already-completed decisions from deferred decisions more clearly.
  next_review_at: '2026-04-03T00:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md
  retrieval_terms:
  - repo
  - reclassification
  - matrix
  - cleanup
  - ontology
  evergreen_potential: high
stigmergy:
  meaning: This file operationalizes the repo ontology doctrine into concrete file-class decisions.
  state: working
  semantic_weight: 0.8
  coordination_comment: Use this matrix to convert doctrine into path-level cleanup choices.
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
# Repo Reclassification Matrix

Date: 2026-04-01
Repo: `dharma_swarm`
Scope: non-hot-path cleanup matrix

This matrix translates the ontology spec into specific reclassification decisions.

Reference doctrine:

- `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`

## Keep As Canon

These are strong candidates to remain first-class orientation surfaces:

| Path | Role | Why |
|------|------|-----|
| `README.md` | operator truth | Primary repo entrypoint |
| `CLAUDE.md` | agent operating contract | Behavioral and architectural operating rules |
| `PRODUCT_SURFACE.md` | product truth | Clear statement of canonical user-facing surface |
| `docs/REPO_LIVING_MAP_2026-03-31.md` | architecture truth | Current repo orientation layer |
| `docs/SWARM_FRONTEND_MASTER_SPEC_2026-04-01.md` | active product canon | Defines current frontend shell doctrine |
| `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md` | repo hygiene canon | Defines prose and artifact precedence |

## Move To `docs/canon/` Or `docs/architecture/`

These may be worth preserving as durable architecture notes, but not at root:

| Path | Recommended class | Reason |
|------|-------------------|--------|
| `docs/architecture/NAVIGATION.md` | architecture truth | Useful orientation doc, wrong placement |
| `docs/architecture/INTEGRATION_MAP.md` | architecture truth | Design synthesis, not bootstrap material |
| `LIVING_LAYERS.md` | architecture truth | Layering note, root placement inflates authority |
| `docs/architecture/MODEL_ROUTING_CANON.md` | architecture truth | Narrow canon, should live with architecture docs |
| `docs/archive/UNASSAILABLE_SYSTEM_BLUEPRINT.md` | advisory architecture | Ambitious design note, not root canon |
| `GENOME_WIRING.md` | architecture truth or active spec | Narrow subsystem note |
| `SWARMLENS_MASTER_SPEC.md` | advisory spec | Product/spec content, not root bootstrap |

## Move To `reports/` Or `docs/archive/`

These are historical or evaluative artifacts:

| Path | Recommended class | Reason |
|------|-------------------|--------|
| `FULL_REPO_AUDIT_2026-03-28.md` | report | Time-stamped audit |
| `CONSTITUTIONAL_XRAY_REPORT.md` | report | Report by name and role |
| `CONSTITUTIONAL_HARDENING_SPRINT_REPORT.md` | report | Sprint report |
| `DUAL_SPRINT_COMPLETION_REPORT.md` | report | Completion artifact |
| `PHASE2_COMPLETION_REPORT.md` | report | Completion artifact |
| `PHASE3_COMPLETION_REPORT.md` | report | Completion artifact |
| `GODEL_CLAW_V1_REPORT.md` | report | Report by role |
| `xray_report.md` | report | Inventory output |
| `WAVE2_ACCEPTANCE_CHECKLIST.md` | historical checklist | Delivery-time support artifact |
| `docs/architecture/VERIFICATION_LANE.md` | historical plan or report | Not canonical by default |

## Move To `docs/prompts/` Or `docs/archive/prompts/`

These are useful, but they should not compete with architecture truth:

| Path | Recommended class | Reason |
|------|-------------------|--------|
| `docs/prompts/MEGA_PROMPT_STRANGE_LOOP.md` | prompt | Prompt artifact |
| `docs/prompts/MEGA_PROMPT_v2.md` | prompt | Prompt artifact |
| `docs/prompts/MEGA_PROMPT_v3.md` | prompt | Prompt artifact |
| `docs/prompts/MEGA_PROMPT_v4.md` | prompt | Prompt artifact |
| `docs/prompts/STRANGE_LOOP_COMPLETE_PROMPT.md` | prompt | Prompt artifact |
| `docs/prompts/STRANGE_LOOP_COMPLETE_PROMPT_v2.md` | prompt | Prompt artifact |
| `docs/prompts/ORTHOGONAL_UPGRADE_PROMPT.md` | prompt | Prompt artifact |
| `docs/prompts/PALANTIR_UPGRADE_PROMPT.md` | prompt | Prompt artifact |
| `docs/prompts/STRATEGIC_PROMPT.md` | prompt | Prompt artifact |

## Move To `docs/plans/` Or `docs/archive/`

These are design or execution plans, not bootstrap truth:

| Path | Recommended class | Reason |
|------|-------------------|--------|
| `docs/archive/MOONSHOT_COMPLETE.md` | historical plan | Project-phase artifact |
| `docs/archive/PALANTIR_ONTOLOGY_GAP_ANALYSIS.md` | active spec or report | Analytical planning note |
| `docs/archive/AGENT_SWARM_SYNTHESIS.md` | synthesis note | Useful, but not root canon |
| `program.md` | plan | Planning note by name and role |
| `program_ecosystem.md` | plan | Planning note by name and role |
| `docs/dse/GAIA_UI.md` | active spec | Product/UX note, not root bootstrap |

## Keep In `specs/`, But Tighten Status

These belong in a spec domain, but need clearer authority labels:

| Path | Recommended class | Reason |
|------|-------------------|--------|
| `specs/DGC_TERMINAL_ARCHITECTURE.md` | active spec | Narrow architecture spec |
| `specs/DGC_TERMINAL_ARCHITECTURE_v1.1.md` | superseded or versioned spec | Needs precedence against v1 |
| `specs/KERNEL_CORE_SPEC.md` | formal or canonical spec | Strong bounded scope |
| `specs/ONTOLOGY_PHASE2_SQLITE_UNIFICATION_SPEC_2026-03-19.md` | active spec | Concrete current build packet |
| `specs/STIGMERGY_11_LAYER_SPEC_2026-03-23.md` | active spec | Formalish subsystem spec |
| `specs/TaskBoardCoordination.tla` | formal spec | Clearly belongs here |
| `specs/TaskBoardCoordination.cfg` | formal spec support | Clearly belongs here |

## Keep In `reports/`

These already have the right home:

| Path | Recommended class | Reason |
|------|-------------------|--------|
| `reports/repo_xray_2026-03-31.md` | report | Correctly scoped inventory output |
| `reports/repo_xray_2026-03-31.json` | generated report | Machine-oriented report output |
| `reports/CRYPTOGRAPHIC_AUDIT_TRAILS_RESEARCH.md` | report or research | Better than root, still non-canonical |

## Treat As Generated State

These should never be treated as architecture truth:

| Path family | Recommended class | Reason |
|-------------|-------------------|--------|
| `.dharma_psmv_hyperfile_branch/**` | generated state | Shared run/branch trace |
| `.dharma_psmv_hyperfile_branch_v2/**` | generated state | Shared run/branch trace |

## Treat As Foundation

These should remain intellectually important but operationally secondary:

| Path family | Recommended class | Reason |
|-------------|-------------------|--------|
| `foundations/**` | foundation | Conceptual substrate |
| `lodestones/**` | foundation | Conceptual orientation |
| `mode_pack/**` | foundation or operational doctrine | Distinct from runtime/product truth |

## First Safe Cleanup Sequence

1. Freeze hot-path dashboard files and leave them alone.
2. Ratify the canon set from this matrix.
3. Drain root-level reports into `reports/` or `docs/archive/`.
4. Drain root-level prompts into `docs/prompts/` or `docs/archive/prompts/`.
5. Move durable architecture notes into `docs/canon/` or `docs/architecture/`.
6. Rewrite `docs/README.md` and `specs/README.md` around the new ontology.
7. Only then consider bulk moves in `foundations/`, `lodestones/`, and `mode_pack/`.

## Hard Rule

Until this cleanup lands, no new root-level markdown should be added unless it is explicitly intended to become canon.
