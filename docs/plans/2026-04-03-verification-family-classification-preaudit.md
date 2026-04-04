---
title: Verification Family Classification Preaudit
path: docs/plans/2026-04-03-verification-family-classification-preaudit.md
slug: verification-family-classification-preaudit
doc_type: plan
status: active
summary: Classifies reports/verification into authored manifests, authored acceptance reports, generated probe outputs, and durable evidence traces so later cleanup can separate them without flattening evidence.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - reports/verification/GODEL_FINAL_KEEP_PRUNE_MANIFEST_2026-03-05.md
  - reports/verification/WAVE2_KEEP_PRUNE_MANIFEST_2026-03-05.md
  - reports/verification/dgc_full_power_probe_20260313T015447Z.md
  - reports/verification/eval_probe_task_20260325T141025Z.md
  - reports/verification/wave2_acceptance_20260305_182933.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- knowledge_management
- verification
- operations
- documentation
- software_architecture
inspiration:
- verification
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-03-verification-family-retention-policy.md
- docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md
- docs/plans/2026-04-02-generated-artifact-control-center.md
- reports/verification/GODEL_FINAL_KEEP_PRUNE_MANIFEST_2026-03-05.md
- reports/verification/WAVE2_KEEP_PRUNE_MANIFEST_2026-03-05.md
- reports/verification/WAVE3_INFLIGHT_KEEP_PRUNE_MANIFEST_2026-03-05.md
- reports/verification/dgc_full_power_probe_20260313T015447Z.md
- reports/verification/eval_probe_task_20260325T141025Z.md
- reports/verification/wave2_acceptance_20260305_182933.md
- dharma_swarm/full_power_probe.py
- scripts/wave2_acceptance_gate.sh
improvement:
  room_for_improvement:
  - Separate authored verification manifests from generated probe traces more explicitly if a relocation tranche is approved.
  - Add a retention policy for paired md/json probe outputs.
  - Recheck live evidence citations before any move of the full-power probe family.
  next_review_at: '2026-04-04T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-03-verification-family-classification-preaudit.md
  retrieval_terms:
  - verification
  - preaudit
  - manifests
  - probes
  - acceptance
  - evidence
  evergreen_potential: high
stigmergy:
  meaning: This file prevents reports/verification from being treated as one undifferentiated dump by classifying the family into evidence subtypes before any relocation.
  state: active
  semantic_weight: 0.85
  coordination_comment: Read this before proposing cleanup moves inside reports/verification.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T01:02:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Verification Family Classification Preaudit

## Purpose

`reports/verification/` is not one thing.

It already contains at least four distinct evidence classes:

- authored keep/prune manifests
- authored acceptance reports
- generated probe outputs
- durable operator evidence traces cited by adjacent packets

The right next move is classification first, not relocation.

## Current Family Shape

Representative files show the split clearly:

### 1. Authored verification manifests

Examples:

- `GODEL_FINAL_KEEP_PRUNE_MANIFEST_2026-03-05.md`
- `WAVE2_KEEP_PRUNE_MANIFEST_2026-03-05.md`
- `WAVE3_INFLIGHT_KEEP_PRUNE_MANIFEST_2026-03-05.md`

Characteristics:

- human decision-oriented prose
- merge and keep/prune guidance
- linked to code and verification outcomes
- semantically closer to authored verification reports than to generated traces

### 2. Authored acceptance reports

Examples:

- `wave2_acceptance_20260305_182933.md`
- `wave2_acceptance_20260305_183023.md`
- `wave2_acceptance_20260305_183320.md`
- `wave2_acceptance_20260305_184403.md`

Characteristics:

- generated from a gate script, but rendered as readable authored-style evidence packets
- preserve test-run outcomes and operator interpretation
- closer to durable evidence than to disposable logs

### 3. Generated probe outputs

Examples:

- `dgc_full_power_probe_20260312T131318Z.{md,json}`
- `dgc_full_power_probe_20260313T015447Z.{md,json}`
- `dgc_full_power_probe_20260324T153444Z.{md,json}`
- `provider_smoke_20260313T071659Z.json`
- `eval_probe_task_20260325T141025Z.md`

Characteristics:

- timestamped diagnostic emissions
- often paired markdown/json output
- closer to generated diagnostics than to authored doctrine
- some have real evidence value and are cited by adjacent report packets

## Live Coupling Found

### Adjacent packet/report evidence coupling

The strongest live references are to the full-power probe family:

- [working_system_spec.md](/Users/dhyana/dharma_swarm/reports/dgc_self_proving_packet_20260313/working_system_spec.md)
- [proof_packet.md](/Users/dhyana/dharma_swarm/reports/dgc_self_proving_packet_20260313/proof_packet.md)
- [director_summary.md](/Users/dhyana/dharma_swarm/reports/dgc_self_proving_packet_20260313/director_summary.md)

These cite `reports/verification/dgc_full_power_probe_20260313T015447Z.md` as current evidence.

### Script coupling

- [wave2_acceptance_gate.sh](/Users/dhyana/dharma_swarm/scripts/wave2_acceptance_gate.sh) writes acceptance reports directly into `reports/verification/`
- [full_power_probe.py](/Users/dhyana/dharma_swarm/dharma_swarm/full_power_probe.py) writes paired markdown/json probe outputs there as well

### Test / prompt coupling nearby

- [test_agent_runner_semantic_acceptance.py](/Users/dhyana/dharma_swarm/tests/test_agent_runner_semantic_acceptance.py) names `reports/verification/ctvsm_probe.json` as required evidence
- several adjacent report packets and mission docs cite verification outputs by current path

## Current Classification

Recommended current split:

1. authored verification manifests
   - keep in `reports/verification/` for now
   - treat as durable authored evidence

2. authored acceptance reports
   - keep in `reports/verification/` for now
   - treat as durable gate evidence, not canon

3. generated probe outputs
   - classify as generated verification evidence
   - do not move blindly while adjacent packets still cite specific paths

4. provider smoke / narrow probe JSON artifacts
   - classify as generated diagnostic evidence
   - candidates for a later `reports/generated/verification/` subtree only after citation cleanup

## What Not To Do Yet

Do not:

- flatten all verification files into one generated bucket
- move the full-power probe family while report packets still cite it as evidence
- treat authored manifests the same way as timestamped probe traces
- purge json outputs just because they look machine-produced

## Recommended Next Move

The strongest next seam is a verification-family policy note that separates:

1. authored manifests
2. authored acceptance reports
3. generated probe traces
4. durable cited evidence that must stay path-stable for now

After that, a later relocation tranche could move only the uncited generated probe outputs first.

Policy entrypoint:

- [2026-04-03-verification-family-retention-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-verification-family-retention-policy.md)

## Current Control Entry Points

- [reports-cartography-and-cleanup-plan.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-reports-cartography-and-cleanup-plan.md)
- [generated-artifact-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-artifact-control-center.md)
