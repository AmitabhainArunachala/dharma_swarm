---
title: Retained Generated Packet Families Preaudit
path: docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md
slug: retained-generated-packet-families-preaudit
doc_type: plan
status: active
summary: Concrete path-coupling preaudit for the retained generated packet families under reports/, naming exact blockers and the conditions required before relocation into reports/generated/.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/plans/2026-04-02-generated-artifact-control-center.md
  - docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
  - dharma_swarm/long_context_sidecar_eval.py
  - dharma_swarm/mission_garden.py
  - tests/test_long_context_sidecar_eval.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- operations
- documentation
- software_architecture
- verification
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-02-generated-artifact-control-center.md
- docs/plans/2026-04-02-generated-packet-path-resolution-design.md
- docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
- docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md
- dharma_swarm/long_context_sidecar_eval.py
- dharma_swarm/mission_garden.py
- tests/test_long_context_sidecar_eval.py
- docs/missions/PSMV_HYPERFILE_BRANCH_2026-03-13.md
- reports/dgc_self_proving_packet_20260313/working_system_spec.md
- reports/dgc_self_proving_packet_20260313/proof_packet.md
improvement:
  room_for_improvement:
  - Convert these blocker classes into a relocation checklist if a future move tranche is approved.
  - Separate direct code coupling from historical/report-evidence coupling more sharply if the families are partially split later.
  - Recheck references after any sidecar-eval or mission-state refactor.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md
  retrieval_terms:
  - generated packets
  - preaudit
  - path coupling
  - reports
  - dual engine swarm
  - psmv hyperfiles
  evergreen_potential: high
stigmergy:
  meaning: This file turns vague relocation deferral into a concrete blocker map for the two retained generated packet families.
  state: active
  semantic_weight: 0.88
  coordination_comment: Use this file before proposing any move of dual_engine_swarm_20260313_run or psmv_hyperfiles_20260313.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T00:20:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Retained Generated Packet Families Preaudit

## Purpose

This preaudit covers the two generated-heavy report families that are not yet safe to move:

- `reports/dual_engine_swarm_20260313_run/`
- `reports/psmv_hyperfiles_20260313/`

These directories are generated in character, but current repo usage still treats their present paths as live anchors.

## Current Decision

Do not relocate either family yet.

The correct current posture is:

- classify them as retained generated packet families
- keep them out of canon and product truth
- defer relocation until path coupling is explicitly removed

## Family A: `reports/dual_engine_swarm_20260313_run/`

### What It Contains

- `semantic_graph.json`
- `semantic_brief_packet.{json,md}`
- `provider_smoke.json`
- `state/mission.json`
- `state/campaign.json`
- `state/shared/*.md`
- `state/logs/**`

### Live Coupling Found

#### Code coupling

- [long_context_sidecar_eval.py](/Users/dhyana/dharma_swarm/dharma_swarm/long_context_sidecar_eval.py) reads `reports/dual_engine_swarm_20260313_run/state/mission.json` as an evaluation source.
- [mission_garden.py](/Users/dhyana/dharma_swarm/dharma_swarm/mission_garden.py) hardcodes `reports/dual_engine_swarm_20260313_run/state/` as `DEFAULT_SNAPSHOT_ROOT`.

#### Test coupling

- [test_long_context_sidecar_eval.py](/Users/dhyana/dharma_swarm/tests/test_long_context_sidecar_eval.py) constructs the `reports/dual_engine_swarm_20260313_run/state/` path directly and writes `mission.json` there.

#### Adjacent report-packet coupling

- [working_system_spec.md](/Users/dhyana/dharma_swarm/reports/dgc_self_proving_packet_20260313/working_system_spec.md) names:
  - `reports/dual_engine_swarm_20260313_run/state/mission.json`
  - `reports/dual_engine_swarm_20260313_run/state/campaign.json`
  - `reports/dual_engine_swarm_20260313_run/state/shared/thinkodynamic_director_latest.md`
- [proof_packet.md](/Users/dhyana/dharma_swarm/reports/dgc_self_proving_packet_20260313/proof_packet.md) cites `reports/dual_engine_swarm_20260313_run/provider_smoke.json` as evidence.

### Relocation Blockers

- hardcoded runtime path use in Python
- hardcoded test-path expectations
- report-packet evidence trails that still cite the current location
- mixed content inside the family: logs, state, brief packets, and evidence artifacts are bundled together

## Family B: `reports/psmv_hyperfiles_20260313/`

### What It Contains

- `repo_semantic_summary.md`
- `vault_semantic_summary.md`
- `cross_corpus_bridge.md`
- `manifest.json`
- `hyperfiles/**`

### Live Coupling Found

#### Code coupling

- [long_context_sidecar_eval.py](/Users/dhyana/dharma_swarm/dharma_swarm/long_context_sidecar_eval.py) reads `reports/psmv_hyperfiles_20260313/repo_semantic_summary.md` as an evaluation source.

#### Test coupling

- [test_long_context_sidecar_eval.py](/Users/dhyana/dharma_swarm/tests/test_long_context_sidecar_eval.py) constructs the `reports/psmv_hyperfiles_20260313/` path directly and writes `repo_semantic_summary.md` there.

#### Mission-doc coupling

- [PSMV_HYPERFILE_BRANCH_2026-03-13.md](/Users/dhyana/dharma_swarm/docs/missions/PSMV_HYPERFILE_BRANCH_2026-03-13.md) instructs operators to emit outputs into `reports/psmv_hyperfiles_20260313/` and its `hyperfiles/` subtree.

#### Adjacent report-manifest coupling

- `reports/architectural/kimi_linear_sidecar_manifest_20260315.{md,json}` records `reports/psmv_hyperfiles_20260313/repo_semantic_summary.md` as a present path.

### Relocation Blockers

- hardcoded evaluation-source path in Python
- hardcoded test-path expectations
- mission instructions that still name the current destination
- packet-manifest/report references that would go stale after a move

## Coupling Classes

The two families are blocked by four different coupling types:

1. code-path coupling
2. test fixture coupling
3. mission or operator-instruction coupling
4. packet/report evidence coupling

That means they are not just "generated folders." They are still part of the repo's current reference graph.

## What Must Be True Before Relocation

Before either family can move under `reports/generated/`, all of the following must happen:

1. Replace hardcoded Python path usage with a configurable or canonical path resolver.
2. Update tests so they depend on the resolver or the new canonical location instead of the old literal paths.
3. Rewrite live mission/operator docs that still instruct output into the old locations.
4. Decide whether adjacent packet/report references should be:
   - updated as live references, or
   - preserved as historical evidence with explicit old-path wording.
5. Decide whether each family moves whole or is split into:
   - retained generated evidence
   - generated logs/state
   - authored packet documentation

## Recommended Next Move

Do not move these directories yet.

The next safe tranche is:

1. introduce a path-resolution layer for code and tests
2. update live mission instructions to point at that canonical destination
3. only then attempt a bounded relocation under `reports/generated/`

Design entrypoint:

- [2026-04-02-generated-packet-path-resolution-design.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-packet-path-resolution-design.md)

## Current Control Entry Points

- [generated-artifact-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-artifact-control-center.md)
- [reports-cartography-and-cleanup-plan.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md)
- [GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md](/Users/dhyana/dharma_swarm/docs/GENERATED_ARTIFACT_BOUNDARY_MATRIX_2026-04-02.md)
