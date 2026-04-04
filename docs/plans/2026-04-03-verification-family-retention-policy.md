---
title: Verification Family Retention Policy
path: docs/plans/2026-04-03-verification-family-retention-policy.md
slug: verification-family-retention-policy
doc_type: plan
status: active
summary: Defines retention and handling rules for reports/verification so authored manifests, acceptance packets, and generated probe traces stop behaving like one undifferentiated family.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/plans/2026-04-03-verification-family-classification-preaudit.md
  - dharma_swarm/full_power_probe.py
  - scripts/wave2_acceptance_gate.sh
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- verification
- operations
- documentation
- knowledge_management
- software_architecture
inspiration:
- verification
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-03-uncited-verification-probe-relocation-preplan.md
- docs/plans/2026-04-03-verification-probe-citation-census.md
- docs/plans/2026-04-03-verification-family-classification-preaudit.md
- docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
- docs/plans/2026-04-02-generated-artifact-control-center.md
- reports/generated/verification/README.md
- reports/verification/GODEL_FINAL_KEEP_PRUNE_MANIFEST_2026-03-05.md
- reports/verification/dgc_full_power_probe_20260313T015447Z.md
- reports/verification/wave2_acceptance_20260305_182933.md
- dharma_swarm/full_power_probe.py
- scripts/wave2_acceptance_gate.sh
improvement:
  room_for_improvement:
  - Add a finer rule for paired md/json probe outputs if a relocation tranche is approved.
  - Distinguish cited probe traces from uncited probe traces more mechanically later.
  - Revisit this policy before any move into reports/generated/verification/.
  next_review_at: '2026-04-04T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-03-verification-family-retention-policy.md
  retrieval_terms:
  - verification
  - retention
  - policy
  - manifests
  - probes
  - acceptance
  evergreen_potential: high
stigmergy:
  meaning: This file gives later cleanup runs explicit handling rules for reports/verification so evidence can be separated intentionally without destroying audit value.
  state: active
  semantic_weight: 0.86
  coordination_comment: Use this note before moving, pruning, or reclassifying anything inside reports/verification.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T01:14:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Verification Family Retention Policy

## Purpose

This policy defines how `reports/verification/` should be handled until a later relocation tranche is actually ready.

The immediate goal is not movement.
The immediate goal is to stop treating all verification files as if they are the same kind of thing.

## Policy Classes

### 1. Authored Verification Manifests

Examples:

- `GODEL_FINAL_KEEP_PRUNE_MANIFEST_2026-03-05.md`
- `WAVE2_KEEP_PRUNE_MANIFEST_2026-03-05.md`
- `WAVE3_INFLIGHT_KEEP_PRUNE_MANIFEST_2026-03-05.md`

Policy:

- keep in `reports/verification/`
- treat as durable authored evidence
- do not classify as generic generated noise
- do not relocate with generated probe traces

### 2. Authored Acceptance Reports

Examples:

- `wave2_acceptance_20260305_182933.md`
- `wave2_acceptance_20260305_183023.md`
- `wave2_acceptance_20260305_183320.md`
- `wave2_acceptance_20260305_184403.md`

Policy:

- keep in `reports/verification/`
- treat as durable gate evidence
- allow continued script emission here for now
- do not flatten into a generic generated bucket

### 3. Generated Probe Traces

Examples:

- `dgc_full_power_probe_*.{md,json}`
- `provider_smoke_20260313T071659Z.json`
- `eval_probe_task_20260325T141025Z.md`

Policy:

- classify as generated verification evidence
- keep cited traces path-stable while adjacent packets and tests still cite current paths
- allow uncited traces to live under `reports/generated/verification/`
- distinguish cited traces from uncited traces before any move
- consider future relocation only under a dedicated `reports/generated/verification/` policy

### 4. Cited Durable Evidence

Examples:

- `dgc_full_power_probe_20260313T015447Z.md`

Policy:

- treat as path-stable evidence while active packet docs still cite it
- do not relocate or rename casually
- if moved later, update every live evidence citation in the same tranche

## Current Write Rules

Until a later cleanup tranche lands:

- [full_power_probe.py](/Users/dhyana/dharma_swarm/dharma_swarm/full_power_probe.py) may continue writing probe outputs into `reports/verification/`
- [wave2_acceptance_gate.sh](/Users/dhyana/dharma_swarm/scripts/wave2_acceptance_gate.sh) may continue writing acceptance reports into `reports/verification/`

That is acceptable for now because current repo references still assume this location.

## What Not To Do

Do not:

- move the full-power probe family as one blind sweep
- treat keep/prune manifests as generated clutter
- purge probe json outputs without checking whether tests or packet docs cite them
- split verification files across multiple homes without one bounded migration plan

## Safe Next Move

The next safe move is not relocation.

It is:

1. identify which probe traces are actually cited
2. identify which probe traces are effectively cold/generated-only
3. then propose a narrow first move for uncited generated traces only

Citation census:

- [2026-04-03-verification-probe-citation-census.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-verification-probe-citation-census.md)

Current generated subtree:

- [reports/generated/verification/README.md](/Users/dhyana/dharma_swarm/reports/generated/verification/README.md)

## Control Entry Points

- [uncited-verification-probe-relocation-preplan.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-uncited-verification-probe-relocation-preplan.md)
- [verification-probe-citation-census.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-verification-probe-citation-census.md)
- [verification-family-classification-preaudit.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-verification-family-classification-preaudit.md)
- [reports-cartography-and-cleanup-plan.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md)
- [generated-artifact-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-artifact-control-center.md)
