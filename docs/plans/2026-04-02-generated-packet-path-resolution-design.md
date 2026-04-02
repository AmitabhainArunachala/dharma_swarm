---
title: Generated Packet Path Resolution Design
path: docs/plans/2026-04-02-generated-packet-path-resolution-design.md
slug: generated-packet-path-resolution-design
doc_type: plan
status: active
summary: Minimal design note for removing hardcoded code and test dependencies on retained generated packet-family paths so those families can eventually move under reports/generated/.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md
  - dharma_swarm/mission_garden.py
  - dharma_swarm/long_context_sidecar_eval.py
  - tests/test_long_context_sidecar_eval.py
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- software_architecture
- operations
- verification
- documentation
- knowledge_management
inspiration:
- repo_topology
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md
- docs/plans/2026-04-02-generated-artifact-control-center.md
- dharma_swarm/mission_garden.py
- dharma_swarm/long_context_sidecar_eval.py
- tests/test_long_context_sidecar_eval.py
- docs/missions/PSMV_HYPERFILE_BRANCH_2026-03-13.md
improvement:
  room_for_improvement:
  - Keep this as a tiny adapter-layer design, not a broad report-ontology rewrite.
  - Add implementation notes only after a bounded engineering tranche is approved.
  - Revisit once mission docs are ready to stop naming literal generated packet paths.
  next_review_at: '2026-04-03T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-02-generated-packet-path-resolution-design.md
  retrieval_terms:
  - path resolution
  - generated packets
  - reports generated
  - mission garden
  - sidecar eval
  - relocation blocker
  evergreen_potential: high
stigmergy:
  meaning: This file turns packet-family relocation blockers into one small engineering seam: resolve generated packet paths indirectly instead of hardcoding them.
  state: active
  semantic_weight: 0.86
  coordination_comment: Use this note before changing mission_garden, long_context_sidecar_eval, or their tests to support later relocation of generated packet families.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T00:28:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Generated Packet Path Resolution Design

## Purpose

The next enabling seam is not moving report directories.

It is removing the small number of hardcoded code and test references that still pin these generated packet families to their current locations:

- `reports/dual_engine_swarm_20260313_run/`
- `reports/psmv_hyperfiles_20260313/`

## Current Hardcoded Callers

### Runtime / utility code

- [mission_garden.py](/Users/dhyana/dharma_swarm/dharma_swarm/mission_garden.py)
  - `DEFAULT_SNAPSHOT_ROOT = DEFAULT_REPO_ROOT / "reports" / "dual_engine_swarm_20260313_run" / "state"`
- [long_context_sidecar_eval.py](/Users/dhyana/dharma_swarm/dharma_swarm/long_context_sidecar_eval.py)
  - reads `reports/dual_engine_swarm_20260313_run/state/mission.json`
  - reads `reports/psmv_hyperfiles_20260313/repo_semantic_summary.md`

### Tests

- [test_long_context_sidecar_eval.py](/Users/dhyana/dharma_swarm/tests/test_long_context_sidecar_eval.py)
  - creates both literal report-family paths in fixtures
  - writes `mission.json` and `repo_semantic_summary.md` directly into them

## Design Goal

Replace literal packet-family paths with one small resolution layer so:

1. code can still find the intended artifacts
2. tests can still build fixtures cleanly
3. the canonical location can later change without repo-wide string surgery

## Minimal Design

Introduce a tiny resolver surface, not a framework.

Suggested shape:

- one helper module or one narrow utility function family
- responsibility:
  - return the current canonical path for:
    - generated mission snapshot root
    - generated repo semantic summary
  - allow later relocation under `reports/generated/` without changing every caller

Possible interface:

- `resolve_generated_snapshot_root(repo_root: Path) -> Path`
- `resolve_generated_repo_semantic_summary(repo_root: Path) -> Path`

For `mission_garden.py`, allow:

- default resolver-backed path
- explicit override argument still wins when supplied

For `long_context_sidecar_eval.py`, replace inline literal paths in the default source list with resolver-backed paths.

For tests, build fixtures against the resolver output instead of duplicating literal family names.

## Non-Goals

This design should not:

- move the packet families yet
- rewrite mission docs yet
- split generated reports into subfamilies yet
- turn into a general repo path-abstraction layer

This is only about removing the literal path dependency that currently blocks relocation.

## Why This Is Enough

The blocker map is small:

- one mission utility module
- one evaluation-plan module
- one direct test file

That means the enabling seam is narrow enough to do later as one bounded engineering tranche.

## Follow-On Sequence

Once the resolver exists:

1. update [mission_garden.py](/Users/dhyana/dharma_swarm/dharma_swarm/mission_garden.py)
2. update [long_context_sidecar_eval.py](/Users/dhyana/dharma_swarm/dharma_swarm/long_context_sidecar_eval.py)
3. update [test_long_context_sidecar_eval.py](/Users/dhyana/dharma_swarm/tests/test_long_context_sidecar_eval.py)
4. then revisit live mission-doc and packet-report references
5. only after that consider moving either family under `reports/generated/`

## Recommended Next Engineering Tranche

One small code tranche:

1. add the resolver
2. migrate the three direct callers
3. keep behavior unchanged
4. do not move files in the same tranche

That would convert the current relocation blocker from “hardcoded paths everywhere” into “doctrine and historical references still need policy.”

## Related Control Docs

- [generated-artifact-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-artifact-control-center.md)
- [retained-generated-packet-families-preaudit.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-retained-generated-packet-families-preaudit.md)
- [reports-cartography-and-cleanup-plan.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md)
