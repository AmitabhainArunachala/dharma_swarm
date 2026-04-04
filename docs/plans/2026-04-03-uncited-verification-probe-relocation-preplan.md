---
title: Uncited Verification Probe Relocation Preplan
path: docs/plans/2026-04-03-uncited-verification-probe-relocation-preplan.md
slug: uncited-verification-probe-relocation-preplan
doc_type: plan
status: active
summary: Records the executed first-move candidate set for uncited verification probe artifacts now relocated under reports/generated/verification/, plus the exclusions and safeguards that kept the tranche bounded.
source:
  provenance: repo_local
  kind: cleanup_plan
  origin_signals:
  - docs/plans/2026-04-03-verification-probe-citation-census.md
  - docs/plans/2026-04-03-verification-family-retention-policy.md
  - reports/generated/README.md
  cited_urls: []
  generated_hint: human_or_agent_authored_repo_doc
disciplines:
- verification
- operations
- documentation
- knowledge_management
inspiration:
- verification
- canonical_truth
connected_relevant_files:
- docs/plans/2026-04-03-verification-probe-citation-census.md
- docs/plans/2026-04-03-verification-family-retention-policy.md
- docs/plans/2026-04-03-verification-family-classification-preaudit.md
- docs/plans/2026-04-02-generated-artifact-control-center.md
- reports/generated/README.md
- reports/verification/dgc_full_power_probe_20260312T131318Z.md
- reports/verification/dgc_full_power_probe_20260312T131318Z.json
- reports/verification/dgc_full_power_probe_20260312T135427Z.md
- reports/verification/dgc_full_power_probe_20260312T135427Z.json
- reports/verification/dgc_full_power_probe_20260313T015447Z.json
- reports/verification/dgc_full_power_probe_20260324T153444Z.md
- reports/verification/dgc_full_power_probe_20260324T153444Z.json
- reports/verification/eval_probe_task_20260325T141025Z.md
improvement:
  room_for_improvement:
  - Re-run the citation census immediately before any actual move tranche.
  - Add the destination subtree README update once a move tranche is approved.
  - Define md/json pairing rules more explicitly if partial probe families are relocated.
  next_review_at: '2026-04-04T12:00:00+09:00'
pkm:
  note_class: plan
  vault_path: docs/plans/2026-04-03-uncited-verification-probe-relocation-preplan.md
  retrieval_terms:
  - verification
  - uncited
  - relocation
  - preplan
  - generated
  - probes
  evergreen_potential: medium
stigmergy:
  meaning: This file turns the citation census into a bounded first relocation candidate set while protecting live cited evidence from accidental churn.
  state: active
  semantic_weight: 0.85
  coordination_comment: Use this note before any move of verification probe traces into reports/generated/verification/.
  trace_role: coordination_trace
curation:
  last_frontmatter_refresh: '2026-04-03T01:32:00+09:00'
  curated_by_model: Codex (GPT-5)
  future_model_handoffs:
  - GPT-5 Codex
  - Claude
  - Gemini
  - Local evaluator
  schema_version: pkm-phd-stigmergy-v1
---
# Uncited Verification Probe Relocation Preplan

## Purpose

This preplan defined the first safe relocation candidate set inside `reports/verification/`.

It is intentionally narrow:

- only probe-like artifacts
- only currently uncited ones
- no authored manifests
- no acceptance reports
- no live-cited evidence files

## Proposed Destination

If a later move tranche is approved, the intended destination should be:

- `reports/generated/verification/`

That keeps generated verification evidence inside the generated reports subtree without collapsing authored verification material into the same bucket.

## Executed First-Move Set

Based on the citation census, this tranche moved:

- `reports/generated/verification/dgc_full_power_probe_20260312T131318Z.md`
- `reports/generated/verification/dgc_full_power_probe_20260312T131318Z.json`
- `reports/generated/verification/dgc_full_power_probe_20260312T135427Z.md`
- `reports/generated/verification/dgc_full_power_probe_20260312T135427Z.json`
- `reports/generated/verification/dgc_full_power_probe_20260313T015447Z.json`
- `reports/generated/verification/dgc_full_power_probe_20260324T153444Z.md`
- `reports/generated/verification/dgc_full_power_probe_20260324T153444Z.json`
- `reports/generated/verification/eval_probe_task_20260325T141025Z.md`

These were selected because no live non-cleanup references were found for them outside `reports/verification/` at move time.

## Explicit Exclusions

Do not include these in the first move:

- `reports/verification/dgc_full_power_probe_20260313T015447Z.md`
- `reports/verification/provider_smoke_20260313T071659Z.json`
- `reports/verification/GODEL_FINAL_KEEP_PRUNE_MANIFEST_2026-03-05.md`
- `reports/verification/WAVE2_KEEP_PRUNE_MANIFEST_2026-03-05.md`
- `reports/verification/WAVE3_INFLIGHT_KEEP_PRUNE_MANIFEST_2026-03-05.md`
- `reports/verification/wave2_acceptance_20260305_182933.md`
- `reports/verification/wave2_acceptance_20260305_183023.md`
- `reports/verification/wave2_acceptance_20260305_183320.md`
- `reports/verification/wave2_acceptance_20260305_184403.md`

Reasons:

- live evidence citations still exist
- or the files are authored verification material rather than generated probe artifacts

## Same-Tranche Safeguards

This tranche required the following safeguards in the same change set:

1. update [reports/generated/README.md](/Users/dhyana/dharma_swarm/reports/generated/README.md) to name the `verification/` subtree
2. re-run the citation census immediately before the move
3. confirm that no tests or docs have started citing any candidate since this preplan was written
4. move paired `.md` and `.json` probe outputs together where pairing exists
5. leave the live-cited evidence files untouched

## What This Preplan Does Not Authorize

This note does not authorize:

- moving the cited `20260313T015447Z.md` full-power probe report
- moving `provider_smoke_20260313T071659Z.json`
- moving authored manifests or acceptance reports
- rewriting verification scripts in the same tranche

## Clean Execution Shape

The ideal first relocation tranche would be:

1. one bounded move set for uncited generated probe artifacts only
2. one README/index update in `reports/generated/`
3. one verification of no live backlink leakage

Anything broader than that should be treated as a separate tranche.

## Control Entry Points

- [verification-probe-citation-census.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-verification-probe-citation-census.md)
- [verification-family-retention-policy.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-03-verification-family-retention-policy.md)
- [generated-artifact-control-center.md](/Users/dhyana/dharma_swarm/docs/plans/2026-04-02-generated-artifact-control-center.md)
