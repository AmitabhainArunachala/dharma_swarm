---
title: DHARMA Documentation Index
path: docs/README.md
slug: dharma-documentation-index
doc_type: readme
status: canonical
summary: Documentation entrypoint for canon, plans, prompts, reports, and archive material in the DHARMA SWARM repo.
source:
  provenance: repo_local
  kind: readme
  origin_signals:
  - README.md
  - docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
  - docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md
  - docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
  - docs/plans/ROOT_DRAIN_VALIDATION_2026-04-02.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- knowledge_management
- operations
- verification
- frontend_engineering
inspiration:
- verification
- operator_runtime
- product_surface
connected_relevant_files:
- README.md
- docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
- docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md
- docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
- docs/plans/2026-04-02-cleanup-control-center.md
- docs/plans/2026-04-02-generated-artifact-control-center.md
- docs/plans/2026-04-03-tui-baseline-protection-note.md
- docs/plans/ROOT_DRAIN_VALIDATION_2026-04-02.md
- docs/REPO_LIVING_MAP_2026-03-31.md
- docs/SWARM_FRONTEND_MASTER_SPEC_2026-04-01.md
improvement:
  room_for_improvement:
  - Keep the canon set small and explicit.
  - Continue draining root-level markdown into clearer homes.
  - Add dedicated subdirectory indexes as cleanup progresses.
  - Keep active cleanup entrypoints compact so historical wave notes do not masquerade as current doctrine.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: readme
  vault_path: docs/README.md
  retrieval_terms:
  - docs
  - documentation
  - canon
  - plans
  - prompts
  - reports
  evergreen_potential: high
stigmergy:
  meaning: This file is the entrypoint for the prose layer of the repo.
  state: canonical
  semantic_weight: 0.95
  coordination_comment: Use this file to decide where a document belongs before creating or moving it.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T00:00:00+09:00'
  curated_by_model: Codex (GPT-5)
  schema_version: pkm-phd-stigmergy-v1
---
# DHARMA Documentation Index

This directory is the prose layer for `dharma_swarm`. It is not one thing.

Use the repo ontology from [REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md) as the governing contract for what belongs here and what does not.

## Start Here

If you need the current repo and product truth:

- [README.md](/Users/dhyana/dharma_swarm/README.md): top-level operator entrypoint
- [CLAUDE.md](/Users/dhyana/dharma_swarm/CLAUDE.md): agent operating contract
- [PRODUCT_SURFACE.md](/Users/dhyana/dharma_swarm/PRODUCT_SURFACE.md): canonical product-surface statement
- [REPO_LIVING_MAP_2026-03-31.md](/Users/dhyana/dharma_swarm/docs/REPO_LIVING_MAP_2026-03-31.md): human repo orientation layer
- [SWARM_FRONTEND_MASTER_SPEC_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/SWARM_FRONTEND_MASTER_SPEC_2026-04-01.md): current frontend doctrine

## Document Classes

Treat prose files in this repo as one of these classes:

- `canon`: durable operator, product, or architecture truth
- `active spec`: implementation-driving design docs for current work
- `working plan`: bounded execution plans, missions, or handoff packets
- `foundation`: conceptual substrate and research synthesis
- `report`: dated descriptive outputs and audits
- `generated state`: machine-produced traces and branch artifacts

If a file does not fit one of those classes, it probably should not be created yet.

## What Lives Where

- `docs/` top level:
  canonical or near-canonical repo and product docs only
- `docs/plans/`:
  dated implementation plans and bounded build packets
- [plans/README.md](/Users/dhyana/dharma_swarm/docs/plans/README.md): index for bounded execution plans, cleanup packets, and operating-mode docs
- `docs/architecture/`:
  subsystem architecture docs and technical structure notes that should not compete with repo-level canon
- [architecture/README.md](/Users/dhyana/dharma_swarm/docs/architecture/README.md): index for subsystem architecture and architecture-local operator docs
- `docs/reports/`:
  authored active-reference reports and synthesis packets that still matter operationally
- [reports/README.md](/Users/dhyana/dharma_swarm/docs/reports/README.md): index for active-reference report material that is neither canon nor archive
- `docs/missions/`:
  mission-specific execution docs
- `docs/prompts/`:
  reusable prompt artifacts and operator prompt packs
- `docs/research/`:
  research and synthesis materials that should stay readable without competing with canon
- `specs/`:
  normative specification layer for formal, protocol, and current contract truth
- `spec-forge/`:
  incubating draft-spec layer for exploratory or pre-canonical spec work
- `foundations/`:
  conceptual substrate and pillar-level canon that should remain distinct from active product doctrine
- `lodestones/`:
  orienting seeds, reframes, bridges, and grounding material that influence direction without acting as normative canon
- `mode_pack/`:
  operational workflow contract layer for explicit modes and machine-readable operator support
- `docs/archive/`:
  superseded or historical prose that should remain readable but not authoritative
- [archive/README.md](/Users/dhyana/dharma_swarm/docs/archive/README.md): index for superseded and historical prose retained for reference
- `reports/historical/`:
  durable historical reports that should stay readable but should not compete with current canon
- generated state under `.dharma_psmv_hyperfile_branch*/` and `reports/**/state/`:
  run output, handoff traces, logs, and machine artifacts rather than authored source of truth
- topic subtrees such as `docs/dse/`, `docs/merge/`, `docs/reports/`:
  domain-local material that should not compete with canon

## Current Canon Set

The current compact canon for repo understanding is:

- [README.md](/Users/dhyana/dharma_swarm/README.md)
- [CLAUDE.md](/Users/dhyana/dharma_swarm/CLAUDE.md)
- [PRODUCT_SURFACE.md](/Users/dhyana/dharma_swarm/PRODUCT_SURFACE.md)
- [REPO_LIVING_MAP_2026-03-31.md](/Users/dhyana/dharma_swarm/docs/REPO_LIVING_MAP_2026-03-31.md)
- [SWARM_FRONTEND_MASTER_SPEC_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/SWARM_FRONTEND_MASTER_SPEC_2026-04-01.md)
- [REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md)

## Architecture-Local Docs

These are important, but they should not compete with repo-level canon:

- [DGC_STRESS_HARNESS.md](/Users/dhyana/dharma_swarm/docs/architecture/DGC_STRESS_HARNESS.md)
- [ORCHESTRATOR_LEDGERS.md](/Users/dhyana/dharma_swarm/docs/architecture/ORCHESTRATOR_LEDGERS.md)
- [PROVIDER_MATRIX_HARNESS.md](/Users/dhyana/dharma_swarm/docs/architecture/PROVIDER_MATRIX_HARNESS.md)
- [SWARMLENS_MASTER_SPEC.md](/Users/dhyana/dharma_swarm/docs/architecture/SWARMLENS_MASTER_SPEC.md)

## Research-Local Docs

These are useful, but they should not compete with repo-level canon:

- [research/README.md](/Users/dhyana/dharma_swarm/docs/research/README.md)
- [COMPLIANCE_CERTIFICATION_RESEARCH.md](/Users/dhyana/dharma_swarm/docs/research/COMPLIANCE_CERTIFICATION_RESEARCH.md)
- [CONSCIOUSNESS_ARCHAEOLOGY_SCAN.md](/Users/dhyana/dharma_swarm/docs/research/CONSCIOUSNESS_ARCHAEOLOGY_SCAN.md)
- [DARWIN_ENGINE_RESEARCH_EXECUTIVE_SUMMARY.md](/Users/dhyana/dharma_swarm/docs/research/DARWIN_ENGINE_RESEARCH_EXECUTIVE_SUMMARY.md)
- [FORMAL_VERIFICATION_PRODUCTION_RESEARCH.md](/Users/dhyana/dharma_swarm/docs/research/FORMAL_VERIFICATION_PRODUCTION_RESEARCH.md)

## Active Cleanup Guides

- [cleanup-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-cleanup-control-center.md): compact entrypoint into the current non-TUI cleanup doctrine and control surface
- [generated-artifact-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-artifact-control-center.md): compact entrypoint for generated-report quarantine, retained packet families, and artifact-boundary decisions
- [REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md): governing cleanup doctrine
- [REPO_RECLASSIFICATION_MATRIX_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md): concrete file reclassification table
- [research/README.md](/Users/dhyana/dharma_swarm/docs/research/README.md): index for research and synthesis materials
- [ROOT_DRAIN_PASS_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/plans/ROOT_DRAIN_PASS_2026-04-01.md): first completed root-drain wave
- [GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md](/Users/dhyana/dharma_swarm/docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md): classification of generated traces versus durable reports
- [ROOT_DRAIN_VALIDATION_2026-04-02.md](/Users/dhyana/dharma_swarm/docs/plans/ROOT_DRAIN_VALIDATION_2026-04-02.md): replacement and backlink validation for drained root docs
- [root-helper-artifact-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-helper-artifact-policy.md): classification rules for non-prose root artifacts and state files
- [root-operational-notes-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-operational-notes-policy.md): retention and future-move policy for `PRODUCT_SURFACE.md` and the `program*` runbooks
- [program-pair-relocation-preaudit.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-program-pair-relocation-preaudit.md): exact blocker and landing-path precheck for moving the `program*` runbooks out of root
- [root-next-tranche-plan.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-next-tranche-plan.md): bounded next-step plan for the remaining root cleanup seam
- [root-state-reconciliation.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-root-state-reconciliation.md): current-state bridge between older root-drain wave notes and the present root layout
- [substrate-layer-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-substrate-layer-policy.md): boundary rules for `foundations/`, `lodestones/`, and `mode_pack/`
- [substrate-directory-cartography.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-substrate-directory-cartography.md): directory-reality map for the substrate layer
- [substrate-graduation-candidates.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-substrate-graduation-candidates.md): keep-versus-watch map for `foundations/`, `lodestones/`, and `mode_pack/`
- [substrate-local-indexing-guidelines.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-substrate-local-indexing-guidelines.md): local labeling rules that keep canon, orientation, and operational contract surfaces distinct
- [autonomous-cleanup-overnight-control.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-autonomous-cleanup-overnight-control.md): control file for bounded overnight non-TUI cleanup runs
- [autonomous-build-skill-issues-and-fixes.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-autonomous-build-skill-issues-and-fixes.md): live issue log for the repo-local autonomous-build mode
- [tui-baseline-protection-note.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-tui-baseline-protection-note.md): boundary note that keeps repo hygiene from misreading overall dirt as evidence against the Bun TUI freeze baseline

Operational helper:

- `bash scripts/start_autonomous_cleanup_tmux.sh`: start the bounded non-TUI overnight cleanup launcher
- [HOT_PATH_INTEGRATION_PROTOCOL_2026-04-01.md](/Users/dhyana/dharma_swarm/docs/HOT_PATH_INTEGRATION_PROTOCOL_2026-04-01.md): dashboard hot-path freeze and integration rules

## Rules

- Do not add new root-level markdown unless it is intended to become canon.
- Do not treat prompts, reports, and plans as product truth.
- Do not put generated state in `docs/`.
- Do not treat `reports/historical/` or `.dharma_psmv_hyperfile_branch*/` as canonical inputs to runtime work.
- When in doubt, place a new prose file under a subdirectory, not `docs/` top level.

## Next Cleanup Targets

- move root-level architecture notes into clearer homes
- continue draining subsystem architecture docs out of top-level `docs/`
- continue reclassifying active vs historical docs
- add subdirectory indexes where the volume justifies them

Recent tranche moves:

- `docs/ORCHESTRATOR_LEDGERS.md` -> `docs/architecture/ORCHESTRATOR_LEDGERS.md`
- `docs/PROVIDER_MATRIX_HARNESS.md` -> `docs/architecture/PROVIDER_MATRIX_HARNESS.md`
