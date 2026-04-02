---
title: Top-Level Docs Canon Map
path: docs/plans/2026-04-02-top-level-docs-canon-map.md
slug: top-level-docs-canon-map
doc_type: plan
status: active
summary: "Date: 2026-04-02 Purpose: classify top-level docs/*.md into canon, move, archive, and coupled surfaces for the next cleanup tranche."
source:
  provenance: repo_local
  kind: plan
  origin_signals:
  - docs/README.md
  - docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
  - docs/plans/2026-04-02-non-tui-repo-hygiene-map.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- knowledge_management
- documentation
- verification
inspiration:
- repo_topology
- architecture
connected_relevant_files:
- docs/README.md
- docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md
- docs/plans/2026-04-02-non-tui-repo-hygiene-map.md
- docs/plans/2026-04-02-architecture-docs-tranche-plan.md
- docs/architecture/README.md
improvement:
  room_for_improvement:
  - Keep the top-level canon list small enough to stay legible.
  - Revisit support-doctrine items after the next research and substrate tranches.
  next_review_at: '2026-04-03T00:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-top-level-docs-canon-map.md
  retrieval_terms:
  - docs
  - canon
  - map
  - top-level
  - authority
  - cleanup
  evergreen_potential: medium
stigmergy:
  meaning: This map classifies which top-level docs should remain visible and which should drain into subtrees.
  state: working
  semantic_weight: 0.78
  coordination_comment: Use this map before moving top-level docs so authority reduction stays coherent.
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
# Top-Level Docs Canon Map

Date: 2026-04-02
Scope: `docs/*.md` only
Purpose: decide what should remain top-level in `docs/` and what should move elsewhere.

## Plain Rule

Top-level `docs/` should contain only:

- canon
- near-canon doctrine
- a very small number of repo-level indexes

Everything else should move into a more specific subtree or archive.

## Keep Top-Level Canon Or Near-Canon

These are the best candidates to remain visible at `docs/` top level.

- `docs/README.md`
- `docs/REPO_ONTOLOGY_AND_HYGIENE_MASTER_SPEC_2026-04-01.md`
- `docs/REPO_LIVING_MAP_2026-03-31.md`
- `docs/SWARM_FRONTEND_MASTER_SPEC_2026-04-01.md`
- `docs/DHARMA_COMMAND_NORTH_STAR_SPEC_2026-04-01.md`

Keep top-level for now, but mark as support doctrine rather than core canon:

- `docs/REPO_RECLASSIFICATION_MATRIX_2026-04-01.md`
- `docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md`
- `docs/CURRENT_META_TOPOLOGY_2026-04-02.md`

Reason:

- these define repo understanding, cleanup doctrine, or a current major product north star

## Move To `docs/plans/`

These are clearly bounded execution packets, cleanup waves, or build-mode docs.

- `docs/plans/ALLOUT_6H_MODE.md`
- `docs/plans/ALL_NIGHT_BUILD_CONCLAVE_2026-03-20.md`
- `docs/plans/CODEX_ALLNIGHT_YOLO.md`
- `docs/HOT_PATH_INTEGRATION_PROTOCOL_2026-04-01.md`
- `docs/OVERNIGHT_AGENT_SUPERVISOR_ARCHITECTURE_2026-04-01.md`
- `docs/plans/ROOT_DRAIN_PASS_2026-04-01.md`
- `docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE2.md`
- `docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE3.md`
- `docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE4.md`
- `docs/plans/ROOT_DRAIN_VALIDATION_2026-04-02.md`
- `docs/SPRINT_GOTCHAS.md`
- `docs/TERMINAL_ALPHA_FREEZE_2026-04-01.md`
- `docs/TERMINAL_FEASIBILITY_DECISION_2026-04-01.md`
- `docs/TERMINAL_OVERNIGHT_SUPERVISOR_2026-04-01.md`
- `docs/TERMINAL_REBUILD_2026-04-01.md`
- `docs/YOLO_4AM_TASKS.md`

Reason:

- these are active wave packets, bounded passes, or temporary operating notes

## Move To `docs/architecture/`

These are architectural or system-structure docs rather than general top-level canon.

- `docs/DHARMA_SWARM_THREE_PLANE_ARCHITECTURE_2026-03-16.md`
- `docs/architecture/JIKOKU_SAMAYA_ARCHITECTURE.md`
- `docs/architecture/JIKOKU_SAMAYA_SYSTEM_DIAGRAM.md`
- `docs/architecture/ORCHESTRATOR_LEDGERS.md`
- `docs/architecture/PROVIDER_MATRIX_HARNESS.md`
- `docs/TERMINAL_V2_OPERATOR_SHELL_SPEC_2026-04-01.md`
- `docs/TERMINAL_V3_OPERATOR_INTELLIGENCE_SPEC_2026-04-01.md`

Reason:

- these are architecture-local and should stop competing with repo-level canon

## Move To `docs/research/`

These are research, synthesis, or exploratory studies rather than current doctrine.

- `docs/research/COMPLIANCE_CERTIFICATION_RESEARCH.md`
- `docs/research/CONSCIOUSNESS_ARCHAEOLOGY_SCAN.md`
- `docs/research/DARWIN_ENGINE_META_LEARNING_PROTOTYPE.md`
- `docs/research/DARWIN_ENGINE_PERPETUAL_EVOLUTION_RESEARCH.md`
- `docs/research/DARWIN_ENGINE_RESEARCH_EXECUTIVE_SUMMARY.md`
- `docs/research/FORMAL_VERIFICATION_PRODUCTION_RESEARCH.md`
- `docs/research/KAIZEN_EFFICIENCY_ANALYSIS.md`
- `docs/MASTER_RESEARCH_PROMPT_DHARMIC_SINGULARITY.md`

Reason:

- these are research or synthesis materials, not current repo entrypoint docs

Completed in current cleanup:

- `docs/research/COMPLIANCE_CERTIFICATION_RESEARCH.md`
- `docs/research/CONSCIOUSNESS_ARCHAEOLOGY_SCAN.md`
- `docs/research/DARWIN_ENGINE_META_LEARNING_PROTOTYPE.md`
- `docs/research/DARWIN_ENGINE_PERPETUAL_EVOLUTION_RESEARCH.md`
- `docs/research/DARWIN_ENGINE_RESEARCH_EXECUTIVE_SUMMARY.md`
- `docs/research/FORMAL_VERIFICATION_PRODUCTION_RESEARCH.md`
- `docs/research/KAIZEN_EFFICIENCY_ANALYSIS.md`

## Move To `docs/prompts/`

These are prompt artifacts and should not live at `docs/` top level.

- `docs/prompts/DEEP_REPO_CARTOGRAPHER_PROMPT_2026-03-31.md`
- `docs/prompts/DGC_SUBAGENT_GAUNTLET_PROMPT.md`
- `docs/prompts/DHARMIC_SINGULARITY_PROMPT_v2.md`
- `docs/prompts/ROUTER_EVOLUTION_SUBSTRATE_PROMPT.md`

Reason:

- prompt packs should be grouped with other prompts

## Move To `docs/archive/`

These are likely valuable but should not remain top-level authority signals.

- `docs/archive/DGC_100X_LEAN_ESSENCE_2026-03-08.md`
- `docs/archive/DGC_KEEP_CUT_ADD_MATRIX_2026-03-08.md`
- `docs/archive/DHARMA_SWARM_1000X_MASTERPLAN_2026-03-16.md`
- `docs/GINKO_ENHANCEMENT_WAVE.md`
- `docs/archive/KAIZEN_IMPLEMENTATION_SUMMARY.md`
- `docs/archive/VISION_COMPLETE_CIRCUIT.md`

Reason:

- these read as historical vision waves, summaries, or earlier strategic packets

## Move To More Specific Domain Trees

These should likely move, but their destination depends on local subtree intent.

- `docs/CODEX_TERMINAL_SUPERVISOR_LAUNCHD.md`
  Suggested home: `docs/architecture/` or `docs/plans/`

- `docs/COMPLIANCE_MAPPING.md`
  Suggested home: `docs/research/` or `docs/architecture/`

- `docs/DARWIN_ENGINE_P0_IMPLEMENTATION_SPEC.md`
  Suggested home: `docs/telos-engine/` or `docs/plans/`

- `docs/DARWIN_ENGINE_QUICK_START_GUIDE.md`
  Suggested home: `docs/telos-engine/`

- `docs/architecture/DGC_STRESS_HARNESS.md`
  Suggested home: `docs/architecture/` or `docs/reports/`

- `docs/GOTCHA_PROTOCOL.md`
  Suggested home: `docs/plans/` or `docs/architecture/`

- `docs/architecture/JIKOKU_SAMAYA_EXECUTIVE_SUMMARY.md`
  Suggested home: `docs/research/` or `docs/telos-engine/`

- `docs/architecture/JIKOKU_SAMAYA_IMPLEMENTATION_ROADMAP.md`
  Suggested home: `docs/plans/` or `docs/telos-engine/`

- `docs/LOOP_PROTOCOL.md`
  Suggested home: `docs/architecture/` or `docs/prompts/`

- `docs/NVIDIA_INFRA_SELF_HEAL.md`
  Suggested home: `docs/architecture/` or `docs/reports/`

- `docs/PRODUCTION_DEPLOYMENT_GUIDE.md`
  Suggested home: `docs/architecture/`

- `docs/RECURSIVE_READING_PROTOCOL.md`
  Suggested home: `docs/prompts/` or `docs/architecture/`

- `docs/RECURSIVE_READING_SWARM_PROTOCOL.md`
  Suggested home: `docs/prompts/` or `docs/architecture/`

## Leave For Now Because They Are Coupled Or Public-Facing

These do not need to stay top-level forever, but they are plausible to leave until ownership is clearer.

- `docs/ASCII_STUDIO_SETUP.md`
- `docs/hn_launch_post.md`
- `docs/substack_first_issue.md`
- `docs/yc_w27_application.md`
- `docs/SKILL_LIBRARY.md`
- `docs/DHARMA_COMMAND_POWER_BUILD_LOOP_SPEC_2026-04-01.md`
- `docs/DHARMA_COMMAND_WORLD_CLASS_PRODUCT_SPEC_2026-04-01.md`

Reason:

- these are either externally oriented, coupled to operator workflows, or still need an explicit destination choice

## Smallest Safe Next Batch

The lowest-blast-radius cleanup batch after the stabilized root-drain slice is:

1. move the root-drain and build-wave packets into `docs/plans/`
2. move obvious prompt artifacts into `docs/prompts/`
3. leave canon and near-canon top-level files untouched

Recommended first batch:

- `docs/plans/ROOT_DRAIN_PASS_2026-04-01.md`
- `docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE2.md`
- `docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE3.md`
- `docs/plans/ROOT_DRAIN_PASS_2026-04-01_WAVE4.md`
- `docs/plans/ROOT_DRAIN_VALIDATION_2026-04-02.md`
- `docs/prompts/DEEP_REPO_CARTOGRAPHER_PROMPT_2026-03-31.md`
- `docs/prompts/DGC_SUBAGENT_GAUNTLET_PROMPT.md`
- `docs/prompts/DHARMIC_SINGULARITY_PROMPT_v2.md`
- `docs/prompts/ROUTER_EVOLUTION_SUBSTRATE_PROMPT.md`

Why this batch:

- it is classification-clean
- it is low-risk
- it reduces false-canon density immediately
- it does not disturb major product doctrine

## Conflict Risks

1. Terminal-related docs may still be referenced by active operator workflows, so do not bulk-move terminal docs without checking link surfaces.
2. Some top-level docs are active because of habit, not because of ontology. Moving them too aggressively may surprise users before indexes are updated.
3. Public-facing or external-application docs should not be moved unless their discoverability is preserved.
4. `docs/README.md` should be updated in the same tranche as any top-level moves.

## Stop Point

Do not attempt to clean every top-level doc at once.

The correct near-term objective is:

- make top-level `docs/` visibly more canonical
- keep the canon set small
- peel off the obviously non-canonical files in low-risk batches
- leave coupled or ambiguous docs for a later pass
